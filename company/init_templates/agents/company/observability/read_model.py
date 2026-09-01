from __future__ import annotations

import json

from ..state import Database


class Observer:
    def __init__(self, database: Database):
        self.database = database

    def health(self) -> dict:
        with self.database.connect() as connection:
            def count(table: str, where: str = "") -> int:
                return connection.execute(
                    f"SELECT COUNT(*) FROM {table} {where}").fetchone()[0]
            return {
                "goals": count("core_goals"),
                "active_goals": count("core_goals", "WHERE status='active'"),
                "runs": count("core_runs"),
                "active_interventions": count(
                    "core_interventions", "WHERE status IN ('running','waiting')"),
                "open_work_orders": count(
                    "core_work_orders", "WHERE status IN ('open','claimed')"),
                "evidence": count("core_evidence"),
                "memory": count("core_memory"),
            }

    def trace(self, goal_id: str) -> dict:
        """Explain why execution happened by walking Goal → Run → Intervention."""
        with self.database.connect() as connection:
            goal = connection.execute(
                "SELECT * FROM core_goals WHERE id=?", (goal_id,)).fetchone()
            if goal is None:
                raise KeyError(f"unknown goal: {goal_id}")
            runs = connection.execute(
                "SELECT * FROM core_runs WHERE goal_id=? ORDER BY sequence", (goal_id,)
            ).fetchall()
            values = []
            for run in runs:
                interventions = connection.execute(
                    "SELECT * FROM core_interventions WHERE run_id=? ORDER BY created_at",
                    (run["id"],),
                ).fetchall()
                values.append({
                    "id": run["id"], "sequence": run["sequence"],
                    "stage": run["stage"], "status": run["status"],
                    "interventions": [{
                        "id": item["id"], "kind": item["kind"],
                        "description": item["description"], "status": item["status"],
                        "outcome": item["resolution_outcome"],
                        "context": json.loads(item["context_json"]),
                    } for item in interventions],
                })
        return {"goal": {"id": goal["id"], "name": goal["name"],
                         "status": goal["status"]}, "runs": values}
