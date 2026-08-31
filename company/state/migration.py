"""Explicit, bounded import from the pre-clean-core Goal tables."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from .database import Database


def plan_legacy_goal_migration(database: Database, goal_ids: list[str]) -> dict:
    """Describe an owner-selected import without changing either state model."""

    selected = tuple(dict.fromkeys(goal_ids))
    plan = {"selected": [], "missing": [], "parents_omitted": [],
            "supports_omitted": [], "core_conflicts": []}
    if not selected:
        return plan
    with database.connect() as connection:
        tables = {row[0] for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        if "goals" not in tables:
            plan["missing"] = list(selected)
            return plan
        existing_core = ({row[0] for row in connection.execute(
            "SELECT id FROM core_goals")} if "core_goals" in tables else set())
        rows = {}
        for goal_id in selected:
            row = connection.execute(
                "SELECT * FROM goals WHERE id=?", (goal_id,)).fetchone()
            if row is None:
                plan["missing"].append(goal_id)
                continue
            rows[goal_id] = row
            plan["selected"].append(goal_id)
            if goal_id in existing_core:
                plan["core_conflicts"].append(goal_id)
        for goal_id, row in rows.items():
            if row["parent_id"] and row["parent_id"] not in rows:
                plan["parents_omitted"].append({
                    "goal_id": goal_id, "parent_id": row["parent_id"]})
            config = json.loads(row["config_json"] or "{}")
            for target in config.get("supports_goal_ids") or ():
                if target not in rows:
                    plan["supports_omitted"].append({
                        "goal_id": goal_id, "target_goal_id": target})
    return plan


def backup_database(database: Database, destination: str | Path) -> Path:
    """Create a consistent SQLite backup before any owner-approved cutover."""

    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    source = sqlite3.connect(database.path)
    target = sqlite3.connect(destination)
    try:
        source.backup(target)
    finally:
        target.close()
        source.close()
    return destination


def migrate_legacy_goals(database: Database, goal_ids: list[str]) -> dict:
    """Import only owner-selected Goals; never silently activate historical work."""

    selected = tuple(dict.fromkeys(goal_ids))
    if not selected:
        return {"migrated": [], "skipped": []}
    migrated, skipped = [], []
    stamp = datetime.now(timezone.utc).isoformat()
    with database.connect() as connection:
        tables = {row[0] for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        if "goals" not in tables:
            return {"migrated": [], "skipped": list(selected)}
        rows = {}
        for goal_id in selected:
            row = connection.execute("SELECT * FROM goals WHERE id=?", (goal_id,)).fetchone()
            if row is None:
                skipped.append(goal_id)
                continue
            rows[goal_id] = row
            status = "active" if row["goal_status"] == "active" else "paused"
            connection.execute("""INSERT OR IGNORE INTO core_goals
                (id,name,metric,operator,target_json,parent_id,status,created_at,updated_at)
                VALUES (?,?,?,?,?,?,?,?,?)""",
                (row["id"], row["name"], row["metric"], row["operator"],
                 row["target_json"], None, status, row["created_at"], stamp))
            migrated.append(goal_id)
        for goal_id, row in rows.items():
            parent_id = row["parent_id"] if row["parent_id"] in rows else None
            if parent_id:
                connection.execute(
                    "UPDATE core_goals SET parent_id=? WHERE id=?", (parent_id, goal_id))
            config = json.loads(row["config_json"] or "{}")
            for target in config.get("supports_goal_ids") or ():
                if target not in rows or target == goal_id:
                    continue
                connection.execute("""INSERT OR IGNORE INTO core_goal_edges
                    VALUES (?,?,'supports',?)""", (goal_id, target, stamp))
    return {"migrated": migrated, "skipped": skipped}
