"""SQLite is the runtime authority; chat sessions are only clients."""

from __future__ import annotations

import json
import os
import sqlite3
import sys
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterator

from . import config as _config

channel_for_owner = _config.channel_for_owner


def canonical_live_db() -> Path:
    """Resolved path of the repository-local company database."""
    from .paths import find_project_root
    return (find_project_root() / ".spielos" / "state" / "company.sqlite").resolve()

TERMINAL_GOAL_STATUSES = ("achieved", "abandoned", "expired")
ACTIONABLE_NOTIFICATION_KINDS = (
    "approval_required", "action_required", "blocked", "failed",
)

# Repair-once-per-process guard (bug 15): database files already scanned by
# _repair_terminal_states/_repair_attention_states in this process.
_REPAIR_SCANNED_DBS: set[str] = set()


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def format_utc(value) -> str:
    """Render an ISO-8601 timestamp as a plain UTC wall-clock string."""
    if not value:
        return ""
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return str(value)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def _why_next_for_run(run_status: str, goal_status: str, resume_at,
                      data: dict | None, *, experiment=None,
                      resource_conflict: str | None = None) -> str | None:
    """Plain-language why/next line for a run in the compact projection.

    Machine tokens remain available unchanged; this adds one human-readable
    line that makes suspended states self-explanatory.
    """
    data = data or {}
    action = data.get("action_result") or {}
    if goal_status == "proposed":
        return "proposed — Director recommends deferral; override to start"
    if run_status == "waiting":
        parts = ["waiting"]
        deadline = action.get("evidence_deadline")
        if deadline:
            parts.append(f"evidence window open until {format_utc(deadline)}")
        if resume_at:
            parts.append(f"next automatic check {format_utc(resume_at)}")
        if len(parts) == 1:
            parts.append("awaiting evidence or a state change")
        return parts[0] + (" — " + "; ".join(parts[1:]) if len(parts) > 1 else "")
    if run_status == "blocked":
        evaluation = data.get("evaluation") or {}
        experiment = evaluation.get("next_experiment") or {}
        if experiment.get("action") == "retry_same_scope":
            return "blocked — next same-scope attempt starts automatically"
        task = action.get("task") or {}
        if task.get("status") == "approved":
            return "blocked — needs coding executor"
        capability = ((data.get("observation") or {}).get("attention") or {}).get("capability")
        if capability:
            return f"blocked — needs {capability}"
        return "blocked — needs action or remediation"
    if run_status == "awaiting_approval":
        return "awaiting_approval — prepared action needs your approval"
    if run_status == "completed":
        if goal_status in {"achieved", "abandoned", "expired"}:
            return {"achieved": "completed — goal achieved",
                    "abandoned": "completed — goal abandoned",
                    "expired": "completed — goal expired"}[goal_status]
        # change-a8869554dd (runner-resilience-1): read the proposed
        # experiment from the persisted evaluation record (the caller passes
        # it), not from the evaluate-step payload stored in cycle data — the
        # payload never carried next_experiment, so valid continuations were
        # misreported as "no valid next experiment".
        evaluation = data.get("evaluation") or {}
        experiment = experiment if experiment is not None else (
            evaluation.get("next_experiment") or {})
        validity = evaluation.get("validity") or "business"
        if validity in {"invalid", "contaminated"}:
            return f"completed — evaluation is {validity}; continuation stopped"
        if isinstance(experiment, dict) and experiment.get("system_improvement"):
            return "completed — continuation blocked; a system improvement is required"
        if isinstance(experiment, dict) and any(
                experiment.get(key) not in (None, "", {}, [])
                for key in ("action", "change_one_variable", "hypothesis", "variable")):
            if resource_conflict:
                return ("completed — next experiment ready; "
                        f"{resource_conflict}")
            return "completed — next run starts automatically"
        return "completed — run finished; no valid next experiment"
    if run_status == "failed":
        return "failed — needs investigation; retry with `company retry <goal>`"
    if run_status == "idle":
        return "active — run ready to advance"
    return None


def _why_next_for_kind(kind: str, payload: dict | None = None) -> str | None:
    """Plain-language why/next wording for a notification kind."""
    payload = payload or {}
    attention = payload.get("attention") or {}
    if kind == "approval_required":
        alignment = payload.get("alignment") or {}
        if alignment.get("judgment") == "defer_recommended":
            return "approval needed — Director recommends deferral; override to start"
        return "approval needed — prepared action needs your approval"
    if kind == "blocked":
        result = payload.get("result") or {}
        task = (attention.get("task") or (result.get("metrics") or {}).get("task")
                or (payload.get("action_result") or {}).get("task") or {})
        if task.get("status") == "approved":
            return "blocked — needs coding executor"
        capability = attention.get("capability")
        if capability:
            return f"blocked — needs {capability}"
        return "blocked — needs action or remediation"
    if kind == "action_required":
        capability = attention.get("capability")
        if capability:
            return f"action needed — {capability} required"
        required = payload.get("required_user_action")
        if required:
            return f"action needed — {required}"
        return "action needed — a capability or input is missing"
    if kind == "failed":
        return "failed — needs investigation; retry with `company retry <goal>`"
    if kind == "run_completed":
        experiment = (payload.get("next_experiment") or {})
        if experiment.get("system_improvement"):
            return "run completed — continuation blocked; a system improvement is required"
        if experiment:
            return "run completed — review the result; the next run starts automatically"
        return "run completed — review the result; no valid next experiment"
    if kind == "goal_achieved":
        return "goal completed — outcome achieved"
    if kind == "goal_abandoned":
        return "goal abandoned — closed without reaching the outcome"
    if kind == "goal_expired":
        return "goal expired — deadline passed before reaching the target"
    return None


def canonical_live_db() -> Path:
    """Resolved path of the repository-local company database."""
    from .paths import find_project_root

    return (find_project_root() / ".spielos" / "state" / "company.sqlite").resolve()


def is_canonical_live_db(path: str | Path) -> bool:
    try:
        return Path(path).resolve() == canonical_live_db()
    except OSError:
        return False


def _in_test_process() -> bool:
    """True when company tests are running and live writes are not explicitly allowed."""

    if os.environ.get("SPIELOS_ALLOW_LIVE_DB_WRITE") == "1":
        return False
    if os.environ.get("SPIELOS_TEST_ISOLATION") == "1":
        return True
    argv = " ".join(sys.argv)
    return "unittest" in sys.modules and ("unittest" in argv or "test_" in argv)


def _guard_live_write(path: Path) -> None:
    if _in_test_process() and is_canonical_live_db(path):
        raise RuntimeError(
            "tests cannot open the canonical live company database for writing")


class Store:
    def __init__(self, path: str | Path, *, readonly: bool = False):
        self.path = Path(path)
        self.readonly = readonly
        if readonly:
            # A read-only open cannot create the database file, so a fresh
            # home would make even `company status` fail. Bootstrap the
            # schema once through a normal open, then proceed read-only.
            if not self.path.exists():
                Store(self.path, readonly=False)
            return
        _guard_live_write(self.path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init()

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        if self.readonly:
            con = sqlite3.connect(f"file:{self.path.resolve()}?mode=ro", uri=True, timeout=10)
            con.row_factory = sqlite3.Row
            con.execute("PRAGMA query_only=ON")
            try:
                con.execute("PRAGMA foreign_keys=ON")
                yield con
            finally:
                con.close()
            return
        _guard_live_write(self.path)
        con = sqlite3.connect(self.path, timeout=10)
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA foreign_keys=ON")
        try:
            yield con
            con.commit()
        finally:
            con.close()

    def _init(self) -> None:
        with self.connect() as con:
            self._migrate_v5(con)
            con.executescript("""
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS goals (
                    id TEXT PRIMARY KEY, name TEXT NOT NULL, owner_id TEXT NOT NULL,
                    metric TEXT NOT NULL, operator TEXT NOT NULL, target_json TEXT NOT NULL,
                    deadline TEXT, parent_id TEXT REFERENCES goals(id),
                    goal_status TEXT NOT NULL, config_json TEXT NOT NULL,
                    created_at TEXT NOT NULL, updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS cycles (
                    id TEXT PRIMARY KEY, goal_id TEXT NOT NULL REFERENCES goals(id),
                    sequence INTEGER NOT NULL, stage TEXT NOT NULL, step TEXT NOT NULL,
                    run_status TEXT NOT NULL, resume_at TEXT, data_json TEXT NOT NULL,
                    created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
                    UNIQUE(goal_id, sequence)
                );
                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, goal_id TEXT NOT NULL,
                    cycle_id TEXT, kind TEXT NOT NULL, payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS approvals (
                    goal_id TEXT NOT NULL, cycle_id TEXT NOT NULL, approval_key TEXT NOT NULL,
                    status TEXT NOT NULL, note TEXT NOT NULL, updated_at TEXT NOT NULL,
                    PRIMARY KEY(goal_id, cycle_id, approval_key)
                );
                CREATE TABLE IF NOT EXISTS memory (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, owner_id TEXT NOT NULL,
                    goal_id TEXT, claim TEXT NOT NULL, evidence_json TEXT NOT NULL,
                    confidence REAL NOT NULL, created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS profile_claims (
                    id TEXT PRIMARY KEY,
                    namespace TEXT NOT NULL,
                    claim_key TEXT NOT NULL,
                    value_json TEXT NOT NULL,
                    scope TEXT NOT NULL,
                    goal_id TEXT,
                    workflow_id TEXT,
                    authority TEXT NOT NULL,
                    source_type TEXT NOT NULL,
                    source_ref TEXT,
                    source_excerpt TEXT NOT NULL,
                    supersedes_id TEXT,
                    status TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_profile_claims_active
                    ON profile_claims(status, namespace, claim_key, updated_at DESC);
                CREATE TABLE IF NOT EXISTS experiment_memories (
                    id TEXT PRIMARY KEY,
                    owner_id TEXT NOT NULL,
                    goal_id TEXT NOT NULL,
                    run_id TEXT NOT NULL,
                    claim TEXT NOT NULL,
                    verdict TEXT NOT NULL,
                    context_json TEXT NOT NULL,
                    evidence_ids_json TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    confirmations INTEGER NOT NULL,
                    contradictions INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    last_confirmed_at TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_experiment_memory_active
                    ON experiment_memories(status, owner_id, updated_at DESC);
                CREATE TABLE IF NOT EXISTS workflow_memories (
                    id TEXT PRIMARY KEY,
                    workgroup_id TEXT,
                    workflow_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    trigger_json TEXT NOT NULL,
                    instructions_json TEXT NOT NULL,
                    dependencies_json TEXT NOT NULL,
                    evidence_ids_json TEXT NOT NULL,
                    source_refs_json TEXT NOT NULL,
                    status TEXT NOT NULL,
                    occurrence_count INTEGER NOT NULL,
                    first_seen_at TEXT NOT NULL,
                    last_seen_at TEXT NOT NULL,
                    expires_at TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_workflow_memory_active
                    ON workflow_memories(status, workflow_id, updated_at DESC);
                CREATE TABLE IF NOT EXISTS memory_candidates (
                    id TEXT PRIMARY KEY,
                    intent TEXT NOT NULL,
                    scope TEXT NOT NULL,
                    authority TEXT NOT NULL,
                    status TEXT NOT NULL,
                    candidate_json TEXT NOT NULL,
                    result_json TEXT NOT NULL,
                    source_ref TEXT,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS directives (
                    id TEXT PRIMARY KEY, text TEXT NOT NULL,
                    scope TEXT NOT NULL, goal_id TEXT REFERENCES goals(id),
                    status TEXT NOT NULL, created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS leases (
                    goal_id TEXT PRIMARY KEY, holder TEXT NOT NULL, expires_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS hypotheses (
                    id TEXT PRIMARY KEY, goal_id TEXT NOT NULL REFERENCES goals(id),
                    statement TEXT NOT NULL, variable TEXT, prediction TEXT,
                    status TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS runs (
                    id TEXT PRIMARY KEY, goal_id TEXT NOT NULL REFERENCES goals(id),
                    run_type TEXT NOT NULL, parent_run_id TEXT, triggered_by_run_id TEXT,
                    owner_id TEXT NOT NULL, owner_version TEXT NOT NULL,
                    hypothesis_id TEXT, config_snapshot_json TEXT NOT NULL,
                    controlled_variables_json TEXT NOT NULL, changed_variables_json TEXT NOT NULL,
                    evidence_validity TEXT NOT NULL, contamination_reason TEXT,
                    resume_run_id TEXT, status TEXT NOT NULL,
                    created_at TEXT NOT NULL, updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS evidence (
                    id TEXT PRIMARY KEY, goal_id TEXT NOT NULL REFERENCES goals(id),
                    run_id TEXT NOT NULL REFERENCES runs(id), kind TEXT NOT NULL,
                    source TEXT NOT NULL, payload_json TEXT NOT NULL,
                    validity TEXT NOT NULL, observed_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS decisions (
                    id TEXT PRIMARY KEY, goal_id TEXT NOT NULL REFERENCES goals(id),
                    run_id TEXT NOT NULL REFERENCES runs(id), decision_type TEXT NOT NULL,
                    rationale TEXT NOT NULL, evidence_ids_json TEXT NOT NULL,
                    next_run_type TEXT, payload_json TEXT NOT NULL, created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS evaluations (
                    id TEXT PRIMARY KEY, goal_id TEXT NOT NULL REFERENCES goals(id),
                    run_id TEXT NOT NULL REFERENCES runs(id), verdict TEXT NOT NULL,
                    goal_met INTEGER NOT NULL, metrics_json TEXT NOT NULL,
                    validity TEXT NOT NULL, contamination_reason TEXT,
                    next_experiment_json TEXT NOT NULL, created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS owner_versions (
                    owner_id TEXT NOT NULL, version TEXT NOT NULL, code_ref TEXT,
                    status TEXT NOT NULL, test_summary_json TEXT NOT NULL,
                    created_at TEXT NOT NULL, deployed_at TEXT,
                    PRIMARY KEY(owner_id, version)
                );
                CREATE TABLE IF NOT EXISTS change_tasks (
                    id TEXT PRIMARY KEY, goal_id TEXT NOT NULL REFERENCES goals(id),
                    run_id TEXT NOT NULL REFERENCES runs(id), owner_id TEXT NOT NULL,
                    from_version TEXT NOT NULL, target_version TEXT NOT NULL,
                    problem TEXT NOT NULL, allowed_files_json TEXT NOT NULL,
                    acceptance_tests_json TEXT NOT NULL, status TEXT NOT NULL,
                    result_json TEXT NOT NULL, originating_run_id TEXT,
                    created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
                    change_kind TEXT NOT NULL DEFAULT 'repair',
                    specification_json TEXT NOT NULL DEFAULT '{}'
                );
                CREATE TABLE IF NOT EXISTS notifications (
                    id TEXT PRIMARY KEY, goal_id TEXT NOT NULL REFERENCES goals(id),
                    run_id TEXT NOT NULL REFERENCES runs(id), kind TEXT NOT NULL,
                    payload_json TEXT NOT NULL, status TEXT NOT NULL,
                    created_at TEXT NOT NULL, delivered_at TEXT,
                    UNIQUE(goal_id,run_id,kind)
                );
                CREATE TABLE IF NOT EXISTS work_orders (
                    id TEXT PRIMARY KEY,
                    goal_id TEXT NOT NULL REFERENCES goals(id),
                    run_id TEXT NOT NULL REFERENCES runs(id),
                    employee_id TEXT NOT NULL,
                    workflow_id TEXT,
                    step_id TEXT,
                    needed INTEGER NOT NULL DEFAULT 1,
                    accepts_evidence_json TEXT NOT NULL,
                    brief_json TEXT NOT NULL,
                    status TEXT NOT NULL,
                    claimed_by TEXT,
                    claimed_at TEXT,
                    result_evidence_ids_json TEXT NOT NULL DEFAULT '[]',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_work_orders_status
                    ON work_orders(status, created_at);
                CREATE INDEX IF NOT EXISTS idx_work_orders_goal_run
                    ON work_orders(goal_id, run_id, status);
                CREATE INDEX IF NOT EXISTS idx_directives_status
                    ON directives(status, created_at);
                CREATE TABLE IF NOT EXISTS dispatch_retries (
                    goal_id TEXT NOT NULL,
                    run_id TEXT NOT NULL,
                    attempt INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    first_error TEXT,
                    next_retry_at TEXT,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY(goal_id, run_id, attempt)
                );
                CREATE INDEX IF NOT EXISTS idx_dispatch_retries_updated
                    ON dispatch_retries(updated_at DESC);
            """)
            change_columns = {row[1] for row in con.execute("PRAGMA table_info(change_tasks)")}
            if "change_kind" not in change_columns:
                con.execute("ALTER TABLE change_tasks ADD COLUMN change_kind TEXT NOT NULL DEFAULT 'repair'")
            if "specification_json" not in change_columns:
                con.execute("ALTER TABLE change_tasks ADD COLUMN specification_json TEXT NOT NULL DEFAULT '{}'")
            workflow_memory_columns = {
                row[1] for row in con.execute("PRAGMA table_info(workflow_memories)")
            }
            for column, declaration in (
                ("behavior_key", "TEXT NOT NULL DEFAULT ''"),
                ("scope", "TEXT NOT NULL DEFAULT 'workflow'"),
                ("authority", "TEXT NOT NULL DEFAULT 'observed'"),
                ("supersedes_id", "TEXT"),
            ):
                if column not in workflow_memory_columns:
                    con.execute(
                        f"ALTER TABLE workflow_memories ADD COLUMN {column} {declaration}")
            con.execute("""UPDATE workflow_memories
                SET behavior_key=LOWER(REPLACE(REPLACE(TRIM(title),' ','-'),'_','-'))
                WHERE behavior_key=''""")
            work_order_columns = {
                row[1] for row in con.execute("PRAGMA table_info(work_orders)")
            }
            if "claimed_by" not in work_order_columns:
                con.execute("ALTER TABLE work_orders ADD COLUMN claimed_by TEXT")
            if "claimed_at" not in work_order_columns:
                con.execute("ALTER TABLE work_orders ADD COLUMN claimed_at TEXT")
            self._backfill_missing_runs(con)
            if str(self.path.resolve()) not in _REPAIR_SCANNED_DBS:
                # Repair scans run once per process per database file: they
                # are pure maintenance reads/writes whose result cannot change
                # between two Store constructions of the same file, and they
                # cost a full-table scan on every open otherwise.
                _REPAIR_SCANNED_DBS.add(str(self.path.resolve()))
                self._repair_terminal_states(con)
                self._repair_attention_states(con)

    @staticmethod
    def _backfill_missing_runs(con: sqlite3.Connection) -> None:
        """Fabricate run rows for legacy cycles that predate the runs table.

        The historical run config was never recorded, so the fabricated
        snapshot copies the CURRENT goal config but carries an explicit
        provenance marker — it must never read as genuine run history.
        """
        missing = con.execute("""SELECT c.id,c.goal_id,c.run_status,c.created_at,c.updated_at,
                g.owner_id,g.config_json
            FROM cycles c JOIN goals g ON g.id=c.goal_id
            WHERE NOT EXISTS (SELECT 1 FROM runs r WHERE r.id=c.id)""").fetchall()
        for row in missing:
            try:
                goal_config = json.loads(row["config_json"] or "{}")
            except ValueError:
                goal_config = {}
            snapshot = {
                "config": goal_config,
                "provenance": "migration_backfill",
                "provenance_note": (
                    "Fabricated run row synthesized during migration from the "
                    "CURRENT goal config; the historical run configuration "
                    "was never recorded."),
                "backfilled_at": now(),
            }
            con.execute("""INSERT OR IGNORE INTO runs VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                        (row["id"], row["goal_id"], "execution", None, None,
                         row["owner_id"], "unversioned", None, json.dumps(snapshot),
                         "{}", "{}", "business", None, None,
                         row["run_status"], row["created_at"], row["updated_at"]))

    @staticmethod
    def _migrate_v5(con: sqlite3.Connection) -> None:
        """Rename internal v4 storage without rewriting historical evidence."""

        tables = {row[0] for row in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        if "engine_versions" in tables and "owner_versions" not in tables:
            con.execute("ALTER TABLE engine_versions RENAME TO owner_versions")
            tables.remove("engine_versions")
            tables.add("owner_versions")
        for table, old, new in (
            ("goals", "engine_id", "owner_id"),
            ("memory", "engine_id", "owner_id"),
            ("runs", "engine_id", "owner_id"),
            ("runs", "engine_version", "owner_version"),
            ("owner_versions", "engine_id", "owner_id"),
            ("change_tasks", "engine_id", "owner_id"),
        ):
            if table not in tables:
                continue
            columns = {row[1] for row in con.execute(f"PRAGMA table_info({table})")}
            if old in columns and new not in columns:
                con.execute(f"ALTER TABLE {table} RENAME COLUMN {old} TO {new}")

    @staticmethod
    def _repair_terminal_states(con: sqlite3.Connection) -> None:
        """Make terminal goals non-actionable while preserving their audit data."""

        placeholders = ",".join("?" for _ in TERMINAL_GOAL_STATUSES)
        con.execute(f"""UPDATE cycles SET run_status='completed',resume_at=NULL
            WHERE id IN (
                SELECT c.id FROM cycles c JOIN goals g ON g.id=c.goal_id
                WHERE g.goal_status IN ({placeholders})
                  AND c.sequence=(SELECT MAX(c2.sequence) FROM cycles c2 WHERE c2.goal_id=g.id)
            ) AND run_status!='completed'""", TERMINAL_GOAL_STATUSES)
        con.execute(f"""UPDATE runs SET status='completed'
            WHERE id IN (
                SELECT c.id FROM cycles c JOIN goals g ON g.id=c.goal_id
                WHERE g.goal_status IN ({placeholders})
                  AND c.sequence=(SELECT MAX(c2.sequence) FROM cycles c2 WHERE c2.goal_id=g.id)
            ) AND status!='completed'""", TERMINAL_GOAL_STATUSES)
        terminal_marks = ",".join("?" for _ in TERMINAL_GOAL_STATUSES)
        action_marks = ",".join("?" for _ in ACTIONABLE_NOTIFICATION_KINDS)
        con.execute(f"""UPDATE notifications SET status='delivered',delivered_at=COALESCE(delivered_at,?)
            WHERE status='pending' AND kind IN ({action_marks})
              AND goal_id IN (SELECT id FROM goals WHERE goal_status IN ({terminal_marks}))""",
                    (now(), *ACTIONABLE_NOTIFICATION_KINDS, *TERMINAL_GOAL_STATUSES))

    @staticmethod
    def _repair_attention_states(con: sqlite3.Connection) -> None:
        """Keep only attention that matches the run's current suspension."""

        marks = ",".join("?" for _ in ACTIONABLE_NOTIFICATION_KINDS)
        con.execute(f"""UPDATE notifications AS n
            SET status='delivered',delivered_at=COALESCE(delivered_at,?)
            WHERE n.status='pending' AND n.kind IN ({marks}) AND NOT EXISTS (
                SELECT 1 FROM goals g JOIN cycles c ON c.id=n.run_id
                WHERE g.id=n.goal_id AND g.goal_status='active' AND (
                    (c.run_status='awaiting_approval' AND n.kind='approval_required') OR
                    (c.run_status='blocked' AND n.kind IN ('blocked','action_required')) OR
                    (c.run_status='failed' AND n.kind='failed')
                )
            )""", (now(), *ACTIONABLE_NOTIFICATION_KINDS))

    @staticmethod
    def _decode(row: sqlite3.Row | None) -> dict[str, Any] | None:
        if row is None:
            return None
        out = dict(row)
        for key in tuple(out):
            if key.endswith("_json"):
                out[key[:-5]] = Store._normalize(json.loads(out.pop(key)))
        return out

    @staticmethod
    def _normalize(value: Any) -> Any:
        """Read v4 JSON snapshots through the v5 vocabulary."""

        if isinstance(value, list):
            return [Store._normalize(item) for item in value]
        if not isinstance(value, dict):
            return "create_department" if value == "create_engine" else value
        aliases = {"engine_id": "owner_id", "engine_version": "owner_version",
                   "engine_spec": "workgroup_spec", "department_spec": "workgroup_spec"}
        return {aliases.get(key, key): Store._normalize(item) for key, item in value.items()}

    def create_goal(self, *, name: str, owner_id: str, metric: str,
                    operator: str, target: Any, deadline: str | None = None,
                    parent_id: str | None = None, config: dict | None = None,
                    goal_id: str | None = None, run_type: str = "execution",
                    owner_version: str = "unversioned", hypothesis: dict | None = None,
                    parent_run_id: str | None = None, triggered_by_run_id: str | None = None,
                    controlled_variables: dict | None = None, changed_variables: dict | None = None,
                    evidence_validity: str = "business", resume_run_id: str | None = None) -> dict:
        goal_id = goal_id or f"goal-{uuid.uuid4().hex[:10]}"
        stamp = now()
        with self.connect() as con:
            con.execute("""INSERT INTO goals VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""", (
                goal_id, name, owner_id, metric, operator, json.dumps(target), deadline,
                parent_id, "active", json.dumps(config or {}), stamp, stamp))
            cycle_id = f"run-{uuid.uuid4().hex[:10]}"
            hypothesis_id = None
            if hypothesis:
                hypothesis_id = f"hyp-{uuid.uuid4().hex[:10]}"
                con.execute("INSERT INTO hypotheses VALUES (?,?,?,?,?,?,?,?)", (
                    hypothesis_id, goal_id, hypothesis["statement"], hypothesis.get("variable"),
                    hypothesis.get("prediction"), "active", stamp, stamp))
            con.execute("""INSERT INTO cycles VALUES (?,?,?,?,?,?,?,?,?,?)""", (
                cycle_id, goal_id, 1, "OBSERVE", "collect", "idle", None,
                json.dumps({}), stamp, stamp))
            con.execute("""INSERT INTO runs VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", (
                cycle_id, goal_id, run_type, parent_run_id, triggered_by_run_id,
                owner_id, owner_version, hypothesis_id, json.dumps(config or {}),
                json.dumps(controlled_variables or {}), json.dumps(changed_variables or {}),
                evidence_validity, None, resume_run_id, "idle", stamp, stamp))
            con.execute("INSERT INTO events(goal_id,cycle_id,kind,payload_json,created_at) VALUES (?,?,?,?,?)",
                        (goal_id, cycle_id, "goal.created", json.dumps({"owner_id": owner_id}), stamp))
        return self.goal(goal_id)

    def goal(self, goal_id: str) -> dict:
        with self.connect() as con:
            row = con.execute("SELECT * FROM goals WHERE id=?", (goal_id,)).fetchone()
        value = self._decode(row)
        if not value:
            raise KeyError(f"unknown goal: {goal_id}")
        return value

    def goals(self, parent_id: str | None = None) -> list[dict]:
        with self.connect() as con:
            if parent_id is None:
                rows = con.execute("SELECT * FROM goals ORDER BY created_at").fetchall()
            else:
                rows = con.execute("SELECT * FROM goals WHERE parent_id=? ORDER BY created_at", (parent_id,)).fetchall()
        return [self._decode(r) for r in rows]

    def goals_supporting(self, goal_id: str) -> list[dict]:
        """Goals whose semantic support edges point at ``goal_id``."""

        from .alignment import support_goal_ids
        return [goal for goal in self.goals() if goal_id in support_goal_ids(goal)]

    def goal_summaries(self, *, statuses: tuple[str, ...] | None = None,
                       limit: int = 20, goal_id: str | None = None) -> list[dict]:
        """Return bounded operational projections, never stored payload bodies."""

        clauses, parameters = [], []
        if statuses:
            clauses.append(f"g.goal_status IN ({','.join('?' for _ in statuses)})")
            parameters.extend(statuses)
        if goal_id:
            clauses.append("g.id=?")
            parameters.append(goal_id)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        parameters.append(max(1, min(int(limit), 100)))
        with self.connect() as con:
            rows = con.execute(f"""SELECT
                    g.id,g.name,g.owner_id,g.metric,g.operator,g.target_json,g.deadline,
                    g.parent_id,g.goal_status,
                    g.config_json,json_extract(g.config_json,'$.priority') AS priority,
                    g.created_at,g.updated_at,
                    c.id AS run_id,c.sequence,c.stage,c.step,c.run_status,c.resume_at,
                    c.data_json,c.updated_at AS runtime_updated_at,r.run_type,r.evidence_validity,
                    (SELECT COUNT(*) FROM evidence ev WHERE ev.run_id=c.id) AS evidence_count,
                    (SELECT verdict FROM evaluations e WHERE e.goal_id=g.id
                        ORDER BY e.created_at DESC LIMIT 1) AS verdict,
                    (SELECT goal_met FROM evaluations e WHERE e.goal_id=g.id
                        ORDER BY e.created_at DESC LIMIT 1) AS goal_met,
                    (SELECT e.next_experiment_json FROM evaluations e WHERE e.goal_id=g.id
                        AND e.run_id=c.id ORDER BY e.created_at DESC LIMIT 1)
                        AS next_experiment_json
                FROM goals g
                JOIN cycles c ON c.goal_id=g.id AND c.sequence=(
                    SELECT MAX(c2.sequence) FROM cycles c2 WHERE c2.goal_id=g.id)
                JOIN runs r ON r.id=c.id
                {where}
                ORDER BY g.updated_at DESC,g.id DESC LIMIT ?""", parameters).fetchall()
        # change-a8869554dd (runner-resilience-1): one read of busy goals so a
        # completed run with a valid next experiment can name the real blocker
        # (a same-channel goal holding the shared resource) instead of the
        # misleading "no valid next experiment".
        busy: dict[str, dict[str, str]] = {}
        with self.connect() as con2:
            busy_rows = con2.execute("""SELECT g.id,g.owner_id,c.run_status
                    FROM goals g
                    JOIN cycles c ON c.goal_id=g.id AND c.sequence=(
                        SELECT MAX(c2.sequence) FROM cycles c2 WHERE c2.goal_id=g.id)
                    WHERE g.goal_status='active'
                      AND c.run_status IN ('idle','running','awaiting_approval','waiting')"""
            ).fetchall()
        for row in busy_rows:
            channel = channel_for_owner(row["owner_id"])
            key = ("channel", channel) if channel else ("owner", row["owner_id"])
            busy.setdefault(key, {})[row["id"]] = row["run_status"]

        values = []
        for row in rows:
            item = dict(row)
            item["target"] = self._normalize(json.loads(item.pop("target_json")))
            config = self._normalize(json.loads(item.pop("config_json")))
            from .alignment import pursuit_kind, support_goal_ids
            item["pursuit_kind"] = pursuit_kind({**item, "config": config})
            item["supports_goal_ids"] = list(support_goal_ids({"config": config}))
            item["causal_lineage"] = config.get("causal_lineage") or {}
            data = self._normalize(json.loads(item.pop("data_json")))
            raw_experiment = item.pop("next_experiment_json", None)
            try:
                experiment = json.loads(raw_experiment) if raw_experiment else None
            except (TypeError, ValueError):
                experiment = None
            conflict = None
            if item["run_status"] == "completed" and item["goal_status"] == "active":
                owner = item["owner_id"]
                if owner != "system-improvement":
                    channel = channel_for_owner(owner)
                    key = ("channel", channel) if channel else ("owner", owner)
                    holders = {gid: status for gid, status in busy.get(key, {}).items()
                               if gid != item["id"]}
                    if holders:
                        gid, status = next(iter(holders.items()))
                        conflict = f"resource held by {gid} ({status})"
            item["why_next"] = _why_next_for_run(item["run_status"], item["goal_status"],
                                                 item.get("resume_at"), data,
                                                 experiment=experiment,
                                                 resource_conflict=conflict)
            if item.get("goal_met") is not None:
                item["goal_met"] = bool(item["goal_met"])
            values.append(item)
        return values

    def goal_counts(self) -> dict[str, int]:
        with self.connect() as con:
            rows = con.execute(
                "SELECT goal_status,COUNT(*) AS count FROM goals GROUP BY goal_status"
            ).fetchall()
        values = {status: 0 for status in (
            "proposed", "active", "paused", "achieved", "abandoned", "expired")}
        values.update({row["goal_status"]: row["count"] for row in rows})
        values["total"] = sum(row["count"] for row in rows)
        return values

    def attention(self, limit: int = 10) -> list[dict]:
        """Return unresolved notifications on active or proposed goals."""

        marks = ",".join("?" for _ in ACTIONABLE_NOTIFICATION_KINDS)
        with self.connect() as con:
            rows = con.execute(f"""SELECT n.id,n.goal_id,n.run_id,n.kind,n.created_at,
                    n.payload_json,g.name,g.owner_id,c.stage,c.step,c.run_status
                FROM notifications n JOIN goals g ON g.id=n.goal_id
                JOIN cycles c ON c.id=n.run_id
                WHERE n.status='pending' AND g.goal_status IN ('active','proposed')
                    AND n.kind IN ({marks})
                ORDER BY n.created_at,n.id LIMIT ?""",
                (*ACTIONABLE_NOTIFICATION_KINDS, max(1, min(int(limit), 100)))).fetchall()
        values = []
        for row in rows:
            item = dict(row)
            payload = self._normalize(json.loads(item.pop("payload_json")))
            item["message"] = (payload.get("result") or {}).get("message")
            item["required_user_action"] = payload.get("required_user_action")
            item["approval_interaction"] = payload.get("approval_interaction")
            why_next = _why_next_for_kind(item["kind"], payload)
            if why_next:
                item["why_next"] = why_next
            values.append(item)
        return values

    def unread_results(self, limit: int = 5) -> list[dict]:
        with self.connect() as con:
            rows = con.execute("""SELECT n.id,n.goal_id,n.run_id,n.kind,n.created_at,
                    g.name,g.owner_id,g.goal_status
                FROM notifications n JOIN goals g ON g.id=n.goal_id
                WHERE n.status='pending' AND n.kind IN (
                    'run_completed','goal_achieved','goal_abandoned','goal_expired')
                ORDER BY n.created_at DESC,n.id DESC LIMIT ?""",
                (max(1, min(int(limit), 100)),)).fetchall()
        values = [dict(row) for row in rows]
        for item in values:
            why_next = _why_next_for_kind(item["kind"])
            if why_next:
                item["why_next"] = why_next
        return values

    def cycle(self, goal_id: str) -> dict:
        with self.connect() as con:
            row = con.execute("SELECT * FROM cycles WHERE goal_id=? ORDER BY sequence DESC LIMIT 1", (goal_id,)).fetchone()
        value = self._decode(row)
        if not value:
            raise KeyError(f"goal has no cycle: {goal_id}")
        return value

    def update_cycle(self, cycle_id: str, *, stage: str, step: str, run_status: str,
                     data: dict, resume_at: str | None = None) -> None:
        with self.connect() as con:
            con.execute("""UPDATE cycles SET stage=?,step=?,run_status=?,resume_at=?,data_json=?,updated_at=? WHERE id=?""",
                        (stage, step, run_status, resume_at, json.dumps(data), now(), cycle_id))

    def new_cycle(self, goal_id: str, metadata: dict | None = None) -> dict:
        previous = self.cycle(goal_id)
        previous_run = self.run(previous["id"])
        goal = self.goal(goal_id)
        metadata = metadata or {}
        stamp = now()
        cycle_id = f"run-{uuid.uuid4().hex[:10]}"
        with self.connect() as con:
            try:
                con.execute("INSERT INTO cycles VALUES (?,?,?,?,?,?,?,?,?,?)", (
                    cycle_id, goal_id, previous["sequence"] + 1, "OBSERVE", "collect", "idle", None,
                    json.dumps({}), stamp, stamp))
            except sqlite3.IntegrityError:
                # Atomic continuation (plan §7.2): UNIQUE(goal_id, sequence) is
                # the write fence. A concurrent client that decided first
                # already created the next run; this loser returns the winner's
                # cycle as a clean idempotent no-op instead of leaking a raw
                # IntegrityError.
                return self.cycle(goal_id)
            hypothesis_id = None
            hypothesis = metadata.get("hypothesis")
            if hypothesis:
                hypothesis_id = f"hyp-{uuid.uuid4().hex[:10]}"
                con.execute("INSERT INTO hypotheses VALUES (?,?,?,?,?,?,?,?)", (
                    hypothesis_id, goal_id, hypothesis["statement"], hypothesis.get("variable"),
                    hypothesis.get("prediction"), "active", stamp, stamp))
            con.execute("""INSERT INTO runs VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", (
                cycle_id, goal_id, metadata.get("run_type", previous_run["run_type"]),
                metadata.get("parent_run_id", previous["id"]),
                metadata.get("triggered_by_run_id", previous["id"]), goal["owner_id"],
                metadata.get("owner_version", previous_run["owner_version"]), hypothesis_id,
                json.dumps(metadata.get("config_snapshot", goal["config"])),
                json.dumps(metadata.get("controlled_variables", previous_run["controlled_variables"])),
                json.dumps(metadata.get("changed_variables", {})),
                metadata.get("evidence_validity", previous_run["evidence_validity"]),
                None, metadata.get("resume_run_id"), "idle", stamp, stamp))
        return self.cycle(goal_id)

    def run(self, run_id: str) -> dict:
        with self.connect() as con:
            row = con.execute("SELECT * FROM runs WHERE id=?", (run_id,)).fetchone()
        value = self._decode(row)
        if not value:
            raise KeyError(f"unknown run: {run_id}")
        return value

    def hypothesis(self, hypothesis_id: str) -> dict:
        with self.connect() as con:
            row = con.execute("SELECT * FROM hypotheses WHERE id=?", (hypothesis_id,)).fetchone()
        value = self._decode(row)
        if not value:
            raise KeyError(f"unknown hypothesis: {hypothesis_id}")
        return value

    def resolve_hypothesis(self, hypothesis_id: str, status: str) -> dict:
        if status not in {"supported", "rejected", "inconclusive"}:
            raise ValueError(f"invalid hypothesis status: {status}")
        with self.connect() as con:
            con.execute(
                "UPDATE hypotheses SET status=?,updated_at=? WHERE id=? AND status='active'",
                (status, now(), hypothesis_id))
        return self.hypothesis(hypothesis_id)

    def update_run(self, run_id: str, *, status: str | None = None,
                   validity: str | None = None, contamination_reason: str | None = None,
                   resume_run_id: str | None = None) -> None:
        current = self.run(run_id)
        with self.connect() as con:
            con.execute("""UPDATE runs SET status=?,evidence_validity=?,contamination_reason=?,
                resume_run_id=?,updated_at=? WHERE id=?""", (
                status or current["status"], validity or current["evidence_validity"],
                contamination_reason if contamination_reason is not None else current["contamination_reason"],
                resume_run_id if resume_run_id is not None else current["resume_run_id"], now(), run_id))

    def add_evidence(self, goal_id: str, run_id: str, kind: str, source: str,
                     payload: dict, validity: str = "business") -> dict:
        evidence_id = f"ev-{uuid.uuid4().hex[:12]}"
        with self.connect() as con:
            con.execute("INSERT INTO evidence VALUES (?,?,?,?,?,?,?,?)", (
                evidence_id, goal_id, run_id, kind, source, json.dumps(payload), validity, now()))
        return self.evidence(run_id)[-1]

    def evidence(self, run_id: str) -> list[dict]:
        with self.connect() as con:
            rows = con.execute("SELECT * FROM evidence WHERE run_id=? ORDER BY observed_at,id", (run_id,)).fetchall()
        return [self._decode(row) for row in rows]

    def add_decision(self, goal_id: str, run_id: str, decision: dict) -> dict:
        decision_id = f"dec-{uuid.uuid4().hex[:12]}"
        with self.connect() as con:
            con.execute("INSERT INTO decisions VALUES (?,?,?,?,?,?,?,?,?)", (
                decision_id, goal_id, run_id, decision.get("type", "intervention"),
                decision.get("rationale", ""), json.dumps(decision.get("evidence_ids", [])),
                decision.get("next_run_type"), json.dumps(decision.get("payload", {})), now()))
        return self.decisions(run_id)[-1]

    def decisions(self, run_id: str) -> list[dict]:
        with self.connect() as con:
            rows = con.execute("SELECT * FROM decisions WHERE run_id=? ORDER BY created_at,id", (run_id,)).fetchall()
        return [self._decode(row) for row in rows]

    def add_evaluation(self, goal_id: str, run_id: str, evaluation: dict) -> dict:
        evaluation_id = f"eval-{uuid.uuid4().hex[:12]}"
        metrics = dict(evaluation.get("metrics", {}))
        if evaluation.get("hypothesis_result"):
            metrics["hypothesis_result"] = dict(evaluation["hypothesis_result"])
        with self.connect() as con:
            con.execute("INSERT INTO evaluations VALUES (?,?,?,?,?,?,?,?,?,?)", (
                evaluation_id, goal_id, run_id, evaluation.get("verdict", "inconclusive"),
                int(bool(evaluation.get("goal_met"))), json.dumps(metrics),
                evaluation.get("validity", "business"), evaluation.get("contamination_reason"),
                json.dumps(evaluation.get("next_experiment", {})), now()))
        return self.evaluation(run_id)

    def evaluation(self, run_id: str) -> dict | None:
        with self.connect() as con:
            row = con.execute("SELECT * FROM evaluations WHERE run_id=? ORDER BY created_at DESC LIMIT 1", (run_id,)).fetchone()
        return self._decode(row)

    def latest_evaluation_for_goal(self, goal_id: str) -> dict | None:
        with self.connect() as con:
            row = con.execute("SELECT * FROM evaluations WHERE goal_id=? ORDER BY created_at DESC LIMIT 1",
                              (goal_id,)).fetchone()
        return self._decode(row)

    def goal_run_history(self, goal_id: str, limit: int = 5) -> tuple[dict, ...]:
        with self.connect() as con:
            rows = con.execute(
                "SELECT * FROM runs WHERE goal_id=? ORDER BY created_at DESC LIMIT ?",
                (goal_id, max(1, min(limit, 20)))).fetchall()
        history = []
        for row in rows:
            run = self._decode(row)
            evaluation = self.evaluation(run["id"])
            if not evaluation:
                continue
            hypothesis = (self.hypothesis(run["hypothesis_id"])
                          if run.get("hypothesis_id") else None)
            history.append({
                "run": run,
                "evaluation": evaluation,
                "hypothesis": hypothesis,
                "evidence": tuple(self.evidence(run["id"])),
            })
        return tuple(history)

    def register_owner_version(self, owner_id: str, version: str, status: str = "deployed",
                               code_ref: str | None = None, test_summary: dict | None = None) -> None:
        stamp = now()
        with self.connect() as con:
            con.execute("""INSERT INTO owner_versions VALUES (?,?,?,?,?,?,?)
                ON CONFLICT(owner_id,version) DO UPDATE SET status=excluded.status,
                code_ref=COALESCE(excluded.code_ref,owner_versions.code_ref),
                test_summary_json=excluded.test_summary_json,deployed_at=excluded.deployed_at""", (
                owner_id, version, code_ref, status, json.dumps(test_summary or {}), stamp,
                stamp if status == "deployed" else None))

    def owner_versions(self, owner_id: str | None = None) -> list[dict]:
        with self.connect() as con:
            if owner_id:
                rows = con.execute("SELECT * FROM owner_versions WHERE owner_id=? ORDER BY created_at", (owner_id,)).fetchall()
            else:
                rows = con.execute("SELECT * FROM owner_versions ORDER BY owner_id,created_at").fetchall()
        return [self._decode(row) for row in rows]

    def create_change_task(self, *, goal_id: str, run_id: str, owner_id: str,
                           from_version: str, target_version: str, problem: str,
                           allowed_files: list, acceptance_tests: list,
                           originating_run_id: str | None = None,
                           change_kind: str = "repair",
                           specification: dict | None = None) -> dict:
        task_id, stamp = f"change-{uuid.uuid4().hex[:10]}", now()
        with self.connect() as con:
            con.execute("""INSERT INTO change_tasks(
                id,goal_id,run_id,owner_id,from_version,target_version,problem,
                allowed_files_json,acceptance_tests_json,status,result_json,
                originating_run_id,created_at,updated_at,change_kind,specification_json)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", (
                task_id, goal_id, run_id, owner_id, from_version, target_version, problem,
                json.dumps(allowed_files), json.dumps(acceptance_tests), "proposed", json.dumps({}),
                originating_run_id, stamp, stamp, change_kind, json.dumps(specification or {})))
        return self.change_task(task_id)

    def change_task(self, task_id: str) -> dict:
        with self.connect() as con:
            row = con.execute("SELECT * FROM change_tasks WHERE id=?", (task_id,)).fetchone()
        value = self._decode(row)
        if not value:
            raise KeyError(f"unknown change task: {task_id}")
        return value

    def change_tasks_for_run(self, run_id: str) -> list[dict]:
        with self.connect() as con:
            rows = con.execute("SELECT * FROM change_tasks WHERE run_id=? ORDER BY created_at", (run_id,)).fetchall()
        return [self._decode(row) for row in rows]

    def change_tasks_for_goal(self, goal_id: str) -> list[dict]:
        with self.connect() as con:
            rows = con.execute(
                "SELECT * FROM change_tasks WHERE goal_id=? ORDER BY created_at,id",
                (goal_id,)).fetchall()
        return [self._decode(row) for row in rows]

    def complete_change_task(self, task_id: str, status: str, result: dict) -> dict:
        current = self.change_task(task_id)
        allowed = {
            "proposed": {"approved"},
            "approved": {"completed", "failed"},
        }
        if status not in allowed.get(current["status"], ()):
            raise RuntimeError(
                f"change task {task_id} cannot move from {current['status']} to {status}")
        with self.connect() as con:
            con.execute("UPDATE change_tasks SET status=?,result_json=?,updated_at=? WHERE id=?",
                        (status, json.dumps(result), now(), task_id))
        return self.change_task(task_id)

    def update_goal_config(self, goal_id: str, config: dict) -> dict:
        with self.connect() as con:
            con.execute("UPDATE goals SET config_json=?,updated_at=? WHERE id=?",
                        (json.dumps(config), now(), goal_id))
        return self.goal(goal_id)

    def set_goal_status(self, goal_id: str, status: str) -> None:
        with self.connect() as con:
            stamp = now()
            con.execute("UPDATE goals SET goal_status=?,updated_at=? WHERE id=?", (status, stamp, goal_id))
            if status in TERMINAL_GOAL_STATUSES:
                con.execute("""UPDATE cycles SET run_status='completed',resume_at=NULL,updated_at=?
                    WHERE goal_id=? AND sequence=(SELECT MAX(sequence) FROM cycles WHERE goal_id=?)""",
                    (stamp, goal_id, goal_id))
                con.execute("""UPDATE runs SET status='completed',updated_at=? WHERE id=(
                    SELECT id FROM cycles WHERE goal_id=? ORDER BY sequence DESC LIMIT 1)""",
                    (stamp, goal_id))
                marks = ",".join("?" for _ in ACTIONABLE_NOTIFICATION_KINDS)
                con.execute(f"""UPDATE notifications SET status='delivered',delivered_at=?
                    WHERE goal_id=? AND status='pending' AND kind IN ({marks})""",
                    (stamp, goal_id, *ACTIONABLE_NOTIFICATION_KINDS))
                con.execute("""UPDATE work_orders SET status='cancelled',updated_at=?
                    WHERE goal_id=? AND status IN ('open','claimed')""", (stamp, goal_id))

    def event(self, goal_id: str, cycle_id: str | None, kind: str, payload: dict) -> None:
        with self.connect() as con:
            con.execute("INSERT INTO events(goal_id,cycle_id,kind,payload_json,created_at) VALUES (?,?,?,?,?)",
                        (goal_id, cycle_id, kind, json.dumps(payload), now()))

    def notify(self, goal_id: str, run_id: str, kind: str, payload: dict,
               *, reopen: bool = False) -> dict:
        """Upsert one notification row per (goal, run, kind).

        The upsert refreshes ``payload_json`` and ``created_at`` so callers
        can rate-limit re-emission by re-stamping the row (the runner's
        send-stall limiter relies on this). Delivery state is PRESERVED by
        default: an accidental upsert must not resurrect an already-delivered
        notification as pending. Pass ``reopen=True`` for a deliberate
        re-alert that should become visible again.
        """
        notification_id = f"note-{uuid.uuid4().hex[:12]}"
        stamp = now()
        with self.connect() as con:
            if reopen:
                conflict_update = """payload_json=excluded.payload_json,status='pending',
                    created_at=excluded.created_at,delivered_at=NULL"""
            else:
                conflict_update = """payload_json=excluded.payload_json,
                    created_at=excluded.created_at"""
            con.execute(f"""INSERT INTO notifications
                (id,goal_id,run_id,kind,payload_json,status,created_at,delivered_at)
                VALUES (?,?,?,?,?,'pending',?,NULL)
                ON CONFLICT(goal_id,run_id,kind) DO UPDATE SET {conflict_update}""",
                (notification_id, goal_id, run_id, kind, json.dumps(payload), stamp))
            row = con.execute("""SELECT * FROM notifications
                WHERE goal_id=? AND run_id=? AND kind=?""", (goal_id, run_id, kind)).fetchone()
        return self._decode(row)

    def resolve_actionable_notifications(self, goal_id: str, run_id: str) -> None:
        """Close attention items when the run has moved to a new state."""

        marks = ",".join("?" for _ in ACTIONABLE_NOTIFICATION_KINDS)
        stamp = now()
        with self.connect() as con:
            con.execute(f"""UPDATE notifications SET status='delivered',delivered_at=?
                WHERE goal_id=? AND run_id=? AND status='pending' AND kind IN ({marks})""",
                (stamp, goal_id, run_id, *ACTIONABLE_NOTIFICATION_KINDS))

    def notifications(self, status: str | None = None, limit: int = 100) -> list[dict]:
        with self.connect() as con:
            if status:
                rows = con.execute("""SELECT * FROM notifications WHERE status=?
                    ORDER BY created_at,id LIMIT ?""", (status, limit)).fetchall()
            else:
                rows = con.execute("SELECT * FROM notifications ORDER BY created_at,id LIMIT ?", (limit,)).fetchall()
        values = []
        for row in rows:
            item = self._decode(row)
            why_next = _why_next_for_kind(item["kind"], item.get("payload") or {})
            if why_next:
                item["why_next"] = why_next
            values.append(item)
        return values

    def acknowledge_notification(self, notification_id: str) -> dict:
        stamp = now()
        with self.connect() as con:
            con.execute("UPDATE notifications SET status='delivered',delivered_at=? WHERE id=?",
                        (stamp, notification_id))
            row = con.execute("SELECT * FROM notifications WHERE id=?", (notification_id,)).fetchone()
        value = self._decode(row)
        if not value:
            raise KeyError(f"unknown notification: {notification_id}")
        return value

    def record_dispatch_retry(self, goal_id: str, run_id: str, attempt: int, status: str,
                              *, first_error: str | None = None,
                              next_retry_at: str | None = None) -> dict:
        """Upsert one dispatch retry attempt.

        ``attempt`` is the retry sequence number; ``status`` is free-form
        (retrying/failed/succeeded/...); ``next_retry_at`` is an ISO timestamp
        of the next scheduled attempt when one exists. ``first_error`` is
        preserved from the FIRST attempt of the (goal, run) pair so the ledger
        keeps the original failure even after later attempts upsert fresh rows
        (readers see the newest row's first_error).
        """
        stamp = now()
        with self.connect() as con:
            # Pair-level original error: the earliest attempt's first_error
            # wins for every row of the (goal, run) pair. NULL on the earliest
            # row falls back to the error passed for this attempt.
            earliest = con.execute(
                """SELECT first_error FROM dispatch_retries
                   WHERE goal_id=? AND run_id=?
                   ORDER BY attempt ASC LIMIT 1""",
                (goal_id, run_id)).fetchone()
            pair_first_error = (earliest[0] if earliest and earliest[0]
                                 else first_error)
            con.execute("""INSERT INTO dispatch_retries
                (goal_id,run_id,attempt,status,first_error,next_retry_at,updated_at)
                VALUES (?,?,?,?,?,?,?)
                ON CONFLICT(goal_id,run_id,attempt) DO UPDATE SET
                    status=excluded.status,
                    first_error=COALESCE(dispatch_retries.first_error,excluded.first_error),
                    next_retry_at=excluded.next_retry_at,
                    updated_at=excluded.updated_at""",
                (goal_id, run_id, attempt, status, pair_first_error,
                 next_retry_at, stamp))
            row = con.execute("""SELECT * FROM dispatch_retries
                WHERE goal_id=? AND run_id=? AND attempt=?""",
                (goal_id, run_id, attempt)).fetchone()
        return self._decode(row)

    def dispatch_retries(self, goal_id: str | None = None, limit: int = 20) -> list[dict]:
        """Read the retry ledger newest-first, optionally scoped to a goal."""
        clauses, parameters = [], []
        if goal_id:
            clauses.append("goal_id=?")
            parameters.append(goal_id)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        parameters.append(max(1, min(int(limit), 100)))
        with self.connect() as con:
            rows = con.execute(f"""SELECT * FROM dispatch_retries
                {where} ORDER BY updated_at DESC,attempt DESC LIMIT ?""",
                parameters).fetchall()
        return [self._decode(row) for row in rows]

    def wake_goal(self, goal_id: str, reason: str) -> bool:
        """Return a waiting parent to OBSERVE, or make an evidence wait due now.

        Does not touch awaiting_approval or an in-progress coding block.
        """

        cycle = self.cycle(goal_id)
        status = cycle["run_status"]
        stage = cycle["stage"]
        if status not in {"waiting", "blocked"}:
            return False
        stamp = now()
        if status == "waiting" and stage == "OBSERVE":
            self.update_cycle(cycle["id"], stage="OBSERVE", step="collect",
                              run_status="idle", resume_at=None, data=cycle.get("data") or {})
        elif status == "waiting":
            with self.connect() as con:
                con.execute("UPDATE cycles SET resume_at=?,updated_at=? WHERE id=?",
                            (stamp, stamp, cycle["id"]))
        elif status == "blocked" and stage == "EVALUATE":
            self.update_cycle(cycle["id"], stage="OBSERVE", step="collect",
                              run_status="idle", resume_at=None, data=cycle.get("data") or {})
        else:
            return False
        self.event(goal_id, cycle["id"], "run.woken", {"reason": reason})
        return True

    def cancel_work_orders(self, goal_id: str, *, include_claimed: bool = False) -> int:
        statuses = ("open", "claimed") if include_claimed else ("open",)
        marks = ",".join("?" for _ in statuses)
        with self.connect() as con:
            cur = con.execute(
                f"""UPDATE work_orders SET status='cancelled',updated_at=?
                    WHERE goal_id=? AND status IN ({marks})""",
                (now(), goal_id, *statuses))
            return cur.rowcount

    def events(self, goal_id: str, limit: int = 20) -> list[dict]:
        with self.connect() as con:
            rows = con.execute("SELECT * FROM events WHERE goal_id=? ORDER BY id DESC LIMIT ?", (goal_id, limit)).fetchall()
        return [self._decode(r) for r in rows]

    def approve(self, goal_id: str, cycle_id: str, key: str, note: str = "") -> None:
        with self.connect() as con:
            con.execute("""INSERT INTO approvals VALUES (?,?,?,?,?,?)
                ON CONFLICT(goal_id,cycle_id,approval_key) DO UPDATE SET status=excluded.status,note=excluded.note,updated_at=excluded.updated_at""",
                (goal_id, cycle_id, key, "approved", note, now()))
        self.event(goal_id, cycle_id, "approval.granted", {"key": key, "note": note})
        self.resolve_actionable_notifications(goal_id, cycle_id)

    def approval(self, goal_id: str, cycle_id: str, key: str) -> str | None:
        with self.connect() as con:
            row = con.execute("SELECT status FROM approvals WHERE goal_id=? AND cycle_id=? AND approval_key=?",
                              (goal_id, cycle_id, key)).fetchone()
        return row[0] if row else None

    def memories(self, owner_id: str, goal_id: str,
                 ancestor_goal_ids: tuple[str, ...] = ()) -> tuple[dict, ...]:
        """Relevant owner Memory, including prior sibling Goals.

        Current/ancestor claims sort first. ``relevant_memory`` still applies
        the metric/workflow filter before a claim may affect a decision, so a
        A Workgroup gains cross-campaign recall without receiving arbitrary old
        context.
        """

        goal_ids = tuple(dict.fromkeys((goal_id, *ancestor_goal_ids)))
        marks = ",".join("?" for _ in goal_ids)
        with self.connect() as con:
            rows = con.execute(
                f"SELECT * FROM memory WHERE owner_id=? "
                f"ORDER BY CASE WHEN goal_id IN ({marks}) THEN 0 ELSE 1 END,id DESC LIMIT 50",
                (owner_id, *goal_ids)).fetchall()
        return tuple(self._decode(r) for r in rows)

    def shared_memories(self, audience_owner_id: str, topics: tuple[str, ...],
                        limit: int = 10) -> tuple[dict, ...]:
        requested = {item for item in topics if item}
        if not requested or limit <= 0:
            return ()
        with self.connect() as con:
            rows = con.execute(
                "SELECT * FROM memory WHERE owner_id!=? ORDER BY id DESC LIMIT 200",
                (audience_owner_id,)).fetchall()
        selected = []
        for row in rows:
            item = self._decode(row)
            evidence = item.get("evidence") or {}
            if evidence.get("share_scope") != "company":
                continue
            audiences = (evidence.get("audience_workgroups")
                         or evidence.get("audience_departments") or ())
            if audience_owner_id not in set(audiences):
                continue
            if not requested.intersection(evidence.get("topics") or ()):
                continue
            selected.append(item)
            if len(selected) >= min(limit, 10):
                break
        return tuple(selected)

    def learn(self, owner_id: str, goal_id: str, claim: str, evidence: dict, confidence: float) -> None:
        with self.connect() as con:
            duplicate = con.execute(
                "SELECT 1 FROM memory WHERE owner_id=? AND claim=? AND evidence_json=? LIMIT 1",
                (owner_id, claim, json.dumps(evidence))).fetchone()
            if duplicate:
                return
            con.execute("INSERT INTO memory(owner_id,goal_id,claim,evidence_json,confidence,created_at) VALUES (?,?,?,?,?,?)",
                        (owner_id, goal_id, claim, json.dumps(evidence), confidence, now()))

    def recent_memories(self, limit: int = 5) -> tuple[dict, ...]:
        with self.connect() as con:
            rows = con.execute(
                "SELECT * FROM memory ORDER BY id DESC LIMIT ?",
                (max(1, min(int(limit), 50)),)).fetchall()
        return tuple(self._decode(row) for row in rows)

    # ---- Typed company profile and operating memory -----------------

    def set_profile_claim(self, *, namespace: str, claim_key: str, value: Any,
                          scope: str = "company", goal_id: str | None = None,
                          workflow_id: str | None = None,
                          authority: str = "owner_explicit",
                          source_type: str = "conversation",
                          source_ref: str | None = None,
                          source_excerpt: str = "", confidence: float = 1.0) -> dict:
        """Activate one owner-scoped profile claim and supersede its predecessor.

        Raw strategy documents remain the base layer.  This table stores typed,
        auditable overlays; empirical memories never call this method.
        """

        namespace = str(namespace or "").strip()
        claim_key = str(claim_key or "").strip()
        if not namespace or not claim_key:
            raise ValueError("profile namespace and key are required")
        if scope not in {"company", "goal", "workflow"}:
            raise ValueError("profile scope must be company, goal, or workflow")
        if scope == "goal" and not goal_id:
            raise ValueError("goal-scoped profile claim requires goal_id")
        if scope == "workflow" and not workflow_id:
            raise ValueError("workflow-scoped profile claim requires workflow_id")
        stamp = now()
        claim_id = f"profile-{uuid.uuid4().hex[:12]}"
        with self.connect() as con:
            prior = con.execute("""SELECT id FROM profile_claims
                WHERE namespace=? AND claim_key=? AND scope=?
                  AND COALESCE(goal_id,'')=COALESCE(?,'')
                  AND COALESCE(workflow_id,'')=COALESCE(?,'')
                  AND status='active'
                ORDER BY updated_at DESC LIMIT 1""",
                (namespace, claim_key, scope, goal_id, workflow_id)).fetchone()
            prior_id = prior["id"] if prior else None
            if prior_id:
                con.execute("UPDATE profile_claims SET status='superseded',updated_at=? WHERE id=?",
                            (stamp, prior_id))
            con.execute("""INSERT INTO profile_claims VALUES
                (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", (
                claim_id, namespace, claim_key, json.dumps(value), scope,
                goal_id, workflow_id, authority, source_type, source_ref,
                str(source_excerpt or "").strip(), prior_id, "active",
                max(0.0, min(float(confidence), 1.0)), stamp, stamp))
        return self.profile_claim(claim_id)

    def profile_claim(self, claim_id: str) -> dict:
        with self.connect() as con:
            row = con.execute("SELECT * FROM profile_claims WHERE id=?", (claim_id,)).fetchone()
        value = self._decode(row)
        if not value:
            raise KeyError(f"unknown profile claim: {claim_id}")
        return value

    def profile_claims(self, *, status: str = "active", goal_id: str | None = None,
                       workflow_id: str | None = None, limit: int = 50) -> tuple[dict, ...]:
        clauses = ["status=?"]
        params: list[Any] = [status]
        scope_parts = ["scope='company'"]
        if goal_id:
            scope_parts.append("goal_id=?")
            params.append(goal_id)
        if workflow_id:
            scope_parts.append("workflow_id=?")
            params.append(workflow_id)
        clauses.append("(" + " OR ".join(scope_parts) + ")")
        params.append(max(1, min(int(limit), 200)))
        with self.connect() as con:
            rows = con.execute(
                f"SELECT * FROM profile_claims WHERE {' AND '.join(clauses)} "
                "ORDER BY updated_at DESC LIMIT ?", params).fetchall()
        return tuple(self._decode(row) for row in rows)

    def record_experiment_memory(self, *, owner_id: str, goal_id: str, run_id: str,
                                 claim: str, verdict: str, context: dict,
                                 evidence_ids: list[str], confidence: float = 0.5) -> dict:
        """Persist or reinforce one evidence-backed experiment learning."""

        claim = str(claim or "").strip()
        if not claim or not evidence_ids:
            raise ValueError("experiment memory requires a claim and evidence_ids")
        stamp = now()
        canonical_context = json.dumps(context or {}, sort_keys=True)
        with self.connect() as con:
            prior = con.execute("""SELECT * FROM experiment_memories
                WHERE owner_id=? AND claim=? AND context_json=? AND status='active'
                ORDER BY updated_at DESC LIMIT 1""",
                (owner_id, claim, canonical_context)).fetchone()
            if prior:
                confirmations = int(prior["confirmations"]) + (0 if verdict == "contradicted" else 1)
                contradictions = int(prior["contradictions"]) + (1 if verdict == "contradicted" else 0)
                adjusted = max(0.0, min(1.0, float(confidence)
                                       + confirmations * 0.03 - contradictions * 0.12))
                ids = list(dict.fromkeys([
                    *json.loads(prior["evidence_ids_json"]), *evidence_ids]))
                con.execute("""UPDATE experiment_memories
                    SET verdict=?,evidence_ids_json=?,confidence=?,confirmations=?,
                        contradictions=?,last_confirmed_at=?,updated_at=? WHERE id=?""",
                    (verdict, json.dumps(ids), adjusted, confirmations, contradictions,
                     stamp, stamp, prior["id"]))
                memory_id = prior["id"]
            else:
                memory_id = f"learning-{uuid.uuid4().hex[:12]}"
                con.execute("""INSERT INTO experiment_memories VALUES
                    (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", (
                    memory_id, owner_id, goal_id, run_id, claim, verdict,
                    canonical_context, json.dumps(list(dict.fromkeys(evidence_ids))),
                    max(0.0, min(float(confidence), 1.0)),
                    1 if verdict != "contradicted" else 0,
                    1 if verdict == "contradicted" else 0,
                    "active", stamp, stamp, stamp))
        return self.experiment_memory(memory_id)

    def experiment_memory(self, memory_id: str) -> dict:
        with self.connect() as con:
            row = con.execute("SELECT * FROM experiment_memories WHERE id=?", (memory_id,)).fetchone()
        value = self._decode(row)
        if not value:
            raise KeyError(f"unknown experiment memory: {memory_id}")
        return value

    def experiment_memories(self, *, owner_id: str | None = None,
                            status: str = "active", limit: int = 100) -> tuple[dict, ...]:
        clauses, params = ["status=?"], [status]
        if owner_id:
            clauses.append("owner_id=?")
            params.append(owner_id)
        params.append(max(1, min(int(limit), 500)))
        with self.connect() as con:
            rows = con.execute(
                f"SELECT * FROM experiment_memories WHERE {' AND '.join(clauses)} "
                "ORDER BY updated_at DESC LIMIT ?", params).fetchall()
        return tuple(self._decode(row) for row in rows)

    def observe_workflow_memory(self, *, workflow_id: str, title: str,
                                instructions: list, trigger: dict | None = None,
                                dependencies: list | None = None,
                                evidence_ids: list[str] | None = None,
                                source_ref: str | None = None,
                                workgroup_id: str | None = None,
                                behavior_key: str | None = None,
                                scope: str = "workflow",
                                authority: str = "observed",
                                explicit_update: bool = False,
                                observed_at: str | None = None) -> dict:
        """Create/reinforce procedural memory by stable behavior identity.

        The model supplies the semantic ``behavior_key``. Deterministic storage
        owns identity, reinforcement, authority, supersession, and provenance.
        """

        if not workflow_id or not instructions:
            raise ValueError("workflow memory requires workflow_id and instructions")
        if scope not in {"workflow", "company"}:
            raise ValueError("workflow memory scope must be workflow or company")
        key = str(behavior_key or title or "").strip().lower().replace("_", "-").replace(" ", "-")
        key = "-".join(part for part in key.split("-") if part)
        if not key:
            raise ValueError("workflow memory requires behavior_key or title")
        stamp = observed_at or now()
        observed = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
        expiry = (observed + timedelta(days=14)).isoformat()
        trigger_json = json.dumps(trigger or {}, sort_keys=True)
        instruction_json = json.dumps(instructions)
        with self.connect() as con:
            prior = con.execute("""SELECT * FROM workflow_memories
                WHERE workflow_id=? AND behavior_key=? AND scope=?
                  AND trigger_json=? AND status IN ('candidate','hardening','promoted')
                ORDER BY updated_at DESC LIMIT 1""",
                (workflow_id, key, scope, trigger_json)).fetchone()
            if prior:
                first = datetime.fromisoformat(prior["first_seen_at"].replace("Z", "+00:00"))
                changed = json.loads(prior["instructions_json"]) != instructions
                if explicit_update and changed:
                    con.execute("UPDATE workflow_memories SET status='superseded',updated_at=? WHERE id=?",
                                (stamp, prior["id"]))
                    memory_id = f"workflow-memory-{uuid.uuid4().hex[:12]}"
                    con.execute("""INSERT INTO workflow_memories (
                        id,workgroup_id,workflow_id,title,trigger_json,instructions_json,
                        dependencies_json,evidence_ids_json,source_refs_json,status,
                        occurrence_count,first_seen_at,last_seen_at,expires_at,created_at,
                        updated_at,behavior_key,scope,authority,supersedes_id)
                        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", (
                        memory_id, workgroup_id, workflow_id, title, trigger_json,
                        instruction_json, json.dumps(dependencies or []),
                        json.dumps(evidence_ids or []),
                        json.dumps([source_ref] if source_ref else []), "hardening", 1,
                        stamp, stamp, expiry, stamp, stamp, key, scope,
                        "owner_explicit", prior["id"]))
                else:
                    count = int(prior["occurrence_count"]) + 1
                    status = ("hardening" if explicit_update or
                              (count >= 2 and observed - first <= timedelta(days=14))
                              else prior["status"])
                    sources = list(dict.fromkeys([
                        *json.loads(prior["source_refs_json"]),
                        *([source_ref] if source_ref else [])]))
                    evidence = list(dict.fromkeys([
                        *json.loads(prior["evidence_ids_json"]), *(evidence_ids or [])]))
                    resolved_authority = ("owner_explicit" if explicit_update
                                          else prior["authority"] or authority)
                    con.execute("""UPDATE workflow_memories SET title=?,instructions_json=?,
                        dependencies_json=?,status=?,occurrence_count=?,evidence_ids_json=?,
                        source_refs_json=?,authority=?,last_seen_at=?,expires_at=?,updated_at=?
                        WHERE id=?""", (
                        title, instruction_json, json.dumps(dependencies or []), status,
                        count, json.dumps(evidence), json.dumps(sources), resolved_authority,
                        stamp, expiry, stamp, prior["id"]))
                    memory_id = prior["id"]
            else:
                memory_id = f"workflow-memory-{uuid.uuid4().hex[:12]}"
                con.execute("""INSERT INTO workflow_memories (
                    id,workgroup_id,workflow_id,title,trigger_json,instructions_json,
                    dependencies_json,evidence_ids_json,source_refs_json,status,
                    occurrence_count,first_seen_at,last_seen_at,expires_at,created_at,
                    updated_at,behavior_key,scope,authority,supersedes_id)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", (
                    memory_id, workgroup_id, workflow_id, title,
                    trigger_json, instruction_json,
                    json.dumps(dependencies or []), json.dumps(evidence_ids or []),
                    json.dumps([source_ref] if source_ref else []),
                    "hardening" if explicit_update else "candidate", 1,
                    stamp, stamp, expiry, stamp, stamp, key, scope,
                    "owner_explicit" if explicit_update else authority, None))
        return self.workflow_memory(memory_id)

    def record_memory_candidate(self, *, candidate: dict, status: str,
                                result: dict, source_ref: str | None = None) -> dict:
        """Keep provenance for every applied, temporary, routed, or rejected candidate."""

        candidate_id = f"memory-candidate-{uuid.uuid4().hex[:12]}"
        stamp = now()
        authority = "owner_explicit" if candidate.get("explicit") is True else "interpreted"
        with self.connect() as con:
            con.execute("""INSERT INTO memory_candidates
                (id,intent,scope,authority,status,candidate_json,result_json,source_ref,created_at)
                VALUES (?,?,?,?,?,?,?,?,?)""", (
                candidate_id, str(candidate.get("intent") or ""),
                str(candidate.get("scope") or ""), authority, status,
                json.dumps(candidate), json.dumps(result, default=str), source_ref, stamp))
        with self.connect() as con:
            row = con.execute("SELECT * FROM memory_candidates WHERE id=?",
                              (candidate_id,)).fetchone()
        return self._decode(row)

    def memory_candidates(self, *, limit: int = 100) -> tuple[dict, ...]:
        with self.connect() as con:
            rows = con.execute(
                "SELECT * FROM memory_candidates ORDER BY created_at DESC LIMIT ?",
                (max(1, min(int(limit), 500)),)).fetchall()
        return tuple(self._decode(row) for row in rows)

    def workflow_memory(self, memory_id: str) -> dict:
        with self.connect() as con:
            row = con.execute("SELECT * FROM workflow_memories WHERE id=?", (memory_id,)).fetchone()
        value = self._decode(row)
        if not value:
            raise KeyError(f"unknown workflow memory: {memory_id}")
        return value

    def workflow_memories(self, *, statuses: tuple[str, ...] = ("candidate", "hardening"),
                          limit: int = 100) -> tuple[dict, ...]:
        marks = ",".join("?" for _ in statuses)
        with self.connect() as con:
            rows = con.execute(
                f"SELECT * FROM workflow_memories WHERE status IN ({marks}) "
                "ORDER BY updated_at DESC LIMIT ?",
                (*statuses, max(1, min(int(limit), 500)))).fetchall()
        return tuple(self._decode(row) for row in rows)

    def consolidate_operating_memory(self, *, at: str | None = None) -> dict:
        """Deterministically expire stale one-off procedural candidates."""

        stamp = at or now()
        with self.connect() as con:
            expired = con.execute("""UPDATE workflow_memories
                SET status='expired',updated_at=?
                WHERE status='candidate' AND occurrence_count<2
                  AND expires_at IS NOT NULL AND expires_at<?""", (stamp, stamp)).rowcount
        return {"expired_workflow_candidates": expired, "consolidated_at": stamp}

    def record_directive(self, text: str, *, scope: str = "company",
                         goal_id: str | None = None) -> dict:
        value = str(text or "").strip()
        if not value:
            raise ValueError("directive text is required")
        if scope not in {"company", "goal"}:
            raise ValueError("directive scope must be company or goal")
        if scope == "goal" and not goal_id:
            raise ValueError("goal-scoped directive requires goal_id")
        if goal_id:
            self.goal(goal_id)
        directive_id = f"directive-{uuid.uuid4().hex[:12]}"
        stamp = now()
        with self.connect() as con:
            con.execute("INSERT INTO directives VALUES (?,?,?,?,?,?,?)", (
                directive_id, value, scope, goal_id, "active", stamp, stamp))
        return self.directive(directive_id)

    def directive(self, directive_id: str) -> dict:
        with self.connect() as con:
            row = con.execute(
                "SELECT * FROM directives WHERE id=?", (directive_id,)).fetchone()
        value = self._decode(row)
        if not value:
            raise KeyError(f"unknown directive: {directive_id}")
        return value

    def directives(self, *, goal_ids: tuple[str, ...] = (),
                   status: str = "active", limit: int = 20) -> tuple[dict, ...]:
        lineage = tuple(dict.fromkeys(item for item in goal_ids if item))
        parameters: list[Any] = [status]
        clause = "scope='company'"
        if lineage:
            marks = ",".join("?" for _ in lineage)
            clause += f" OR (scope='goal' AND goal_id IN ({marks}))"
            parameters.extend(lineage)
        parameters.append(max(1, min(int(limit), 100)))
        with self.connect() as con:
            rows = con.execute(
                f"SELECT * FROM directives WHERE status=? AND ({clause}) "
                "ORDER BY created_at DESC,id DESC LIMIT ?", parameters).fetchall()
        return tuple(self._decode(row) for row in rows)

    def retire_directive(self, directive_id: str) -> dict:
        stamp = now()
        with self.connect() as con:
            changed = con.execute(
                "UPDATE directives SET status='retired',updated_at=? "
                "WHERE id=? AND status='active'", (stamp, directive_id)).rowcount
        if not changed:
            raise KeyError(f"unknown active directive: {directive_id}")
        return self.directive(directive_id)

    def acquire(self, goal_id: str, holder: str, seconds: int = 60) -> bool:
        expires = (datetime.now(timezone.utc) + timedelta(seconds=seconds)).isoformat()
        stamp = now()
        with self.connect() as con:
            con.execute("DELETE FROM leases WHERE expires_at<=?", (stamp,))
            try:
                con.execute("INSERT INTO leases VALUES (?,?,?)", (goal_id, holder, expires))
                return True
            except sqlite3.IntegrityError:
                return False

    def release(self, goal_id: str, holder: str) -> None:
        with self.connect() as con:
            con.execute("DELETE FROM leases WHERE goal_id=? AND holder=?", (goal_id, holder))

    def live_lease(self, goal_id: str) -> dict | None:
        """The current non-expired lease for a goal, or None when free/stale.

        Read-only. A mid-flight cycle whose lease expired (or was never
        written) is treated as stale and resumable by the pull worker.
        """
        with self.connect() as con:
            row = con.execute(
                "SELECT holder, expires_at FROM leases WHERE goal_id=? AND expires_at>?",
                (goal_id, now())).fetchone()
        if row is None:
            return None
        return {"holder": row[0], "expires_at": row[1]}

    def open_work_order(self, *, goal_id: str, run_id: str, employee_id: str,
                        needed: int = 1, accepts_evidence: list | None = None,
                        workflow_id: str | None = None, step_id: str | None = None,
                        brief: dict | None = None) -> dict:
        """Create or refresh one open employee assignment for a goal run.

        Idempotent per (goal_id, run_id, employee_id) while status is open so
        re-persisting a blocked ACT does not duplicate work for the same employee.
        """

        accepts = list(accepts_evidence or [])
        needed = max(1, int(needed))
        brief = dict(brief or {})
        stamp = now()
        with self.connect() as con:
            row = con.execute("""SELECT * FROM work_orders
                WHERE goal_id=? AND run_id=? AND employee_id=?
                  AND COALESCE(workflow_id,'')=COALESCE(?,'')
                  AND COALESCE(step_id,'')=COALESCE(?,'')
                  AND status IN ('open','claimed')
                ORDER BY created_at DESC LIMIT 1""", (
                    goal_id, run_id, employee_id, workflow_id, step_id)).fetchone()
            if row:
                con.execute("""UPDATE work_orders SET needed=?,accepts_evidence_json=?,
                    workflow_id=COALESCE(?,workflow_id),step_id=COALESCE(?,step_id),
                    brief_json=?,updated_at=? WHERE id=?""", (
                    needed, json.dumps(accepts), workflow_id, step_id,
                    json.dumps(brief), stamp, row["id"]))
                order_id = row["id"]
            else:
                order_id = f"work-{uuid.uuid4().hex[:12]}"
                con.execute("""INSERT INTO work_orders(
                    id,goal_id,run_id,employee_id,workflow_id,step_id,needed,
                    accepts_evidence_json,brief_json,status,claimed_by,claimed_at,
                    result_evidence_ids_json,created_at,updated_at)
                    VALUES (?,?,?,?,?,?,?,?,?,'open',NULL,NULL,'[]',?,?)""", (
                    order_id, goal_id, run_id, employee_id, workflow_id, step_id, needed,
                    json.dumps(accepts), json.dumps(brief), stamp, stamp))
                con.execute(
                    "INSERT INTO events(goal_id,cycle_id,kind,payload_json,created_at) VALUES (?,?,?,?,?)",
                    (goal_id, run_id, "work_order.opened",
                     json.dumps({"work_order_id": order_id, "employee_id": employee_id,
                                 "needed": needed, "accepts_evidence": accepts}), stamp))
        return self.work_order(order_id)

    def work_order(self, work_order_id: str) -> dict:
        with self.connect() as con:
            row = con.execute("SELECT * FROM work_orders WHERE id=?", (work_order_id,)).fetchone()
        value = self._decode(row)
        if not value:
            raise KeyError(f"unknown work order: {work_order_id}")
        return value

    def work_orders(self, *, status: str | None = "open", goal_id: str | None = None,
                    run_id: str | None = None, limit: int = 50) -> list[dict]:
        clauses, parameters = [], []
        if status == "active":
            clauses.append("w.status IN ('open','claimed')")
        elif status:
            clauses.append("w.status=?")
            parameters.append(status)
        if goal_id:
            clauses.append("w.goal_id=?")
            parameters.append(goal_id)
        if run_id:
            clauses.append("w.run_id=?")
            parameters.append(run_id)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        parameters.append(max(1, min(int(limit), 100)))
        with self.connect() as con:
            rows = con.execute(f"""SELECT w.*,g.name AS goal_name,g.owner_id,g.goal_status
                FROM work_orders w JOIN goals g ON g.id=w.goal_id
                {where}
                ORDER BY CASE lower(CAST(json_extract(g.config_json,'$.priority') AS TEXT))
                    WHEN 'critical' THEN 100 WHEN 'high' THEN 75
                    WHEN 'normal' THEN 50 WHEN 'low' THEN 25
                    WHEN 'deferred' THEN 0
                    ELSE COALESCE(CAST(json_extract(g.config_json,'$.priority') AS REAL),50)
                END DESC,w.created_at,w.id LIMIT ?""", parameters).fetchall()
        values = []
        for row in rows:
            item = self._decode(row)
            if item["status"] == "open":
                item["why_next"] = (
                    f"open — {item['employee_id']} must produce "
                    f"{item['needed']} accepted artifact(s); then `company retry {item['goal_id']}`")
            elif item["status"] == "claimed":
                item["why_next"] = (
                    f"claimed by {item['claimed_by']} — complete this exact assignment "
                    "with linked evidence")
            elif item["status"] == "done":
                item["why_next"] = "done — accepted evidence recorded; retry the goal if still blocked"
            else:
                item["why_next"] = f"{item['status']} — no further employee action"
            values.append(item)
        return values

    def claim_work_order(self, work_order_id: str, worker_id: str) -> dict:
        """Atomically assign one open work order to exactly one host worker."""

        worker_id = str(worker_id or "").strip()
        if not worker_id:
            raise ValueError("worker_id is required")
        stamp = now()
        with self.connect() as con:
            current = con.execute(
                "SELECT * FROM work_orders WHERE id=?", (work_order_id,)).fetchone()
            if current is None:
                raise KeyError(f"unknown work order: {work_order_id}")
            if current["status"] == "claimed" and current["claimed_by"] == worker_id:
                return self._decode(current)
            if current["status"] != "open":
                owner = current["claimed_by"] or current["status"]
                raise RuntimeError(f"work order is not available (owned by {owner})")
            changed = con.execute("""UPDATE work_orders
                SET status='claimed',claimed_by=?,claimed_at=?,updated_at=?
                WHERE id=? AND status='open'""",
                (worker_id, stamp, stamp, work_order_id)).rowcount
            if changed != 1:
                raise RuntimeError("work order was claimed by another worker")
            row = con.execute(
                "SELECT * FROM work_orders WHERE id=?", (work_order_id,)).fetchone()
            con.execute(
                "INSERT INTO events(goal_id,cycle_id,kind,payload_json,created_at) VALUES (?,?,?,?,?)",
                (row["goal_id"], row["run_id"], "work_order.claimed",
                 json.dumps({"work_order_id": work_order_id, "worker_id": worker_id}), stamp))
        return self._decode(row)

    def complete_work_order(self, work_order_id: str, evidence_ids: list | None = None,
                            worker_id: str | None = None) -> dict:
        stamp = now()
        with self.connect() as con:
            current = con.execute("SELECT * FROM work_orders WHERE id=?", (work_order_id,)).fetchone()
            if current is None:
                raise KeyError(f"unknown work order: {work_order_id}")
            if current["status"] != "open":
                if current["status"] == "done":
                    return self._decode(current)
                if current["status"] != "claimed":
                    raise RuntimeError(f"work order cannot complete from {current['status']}")
            if current["status"] == "claimed" and current["claimed_by"] != worker_id:
                raise RuntimeError(
                    f"work order is claimed by {current['claimed_by']}; {worker_id!r} cannot complete it")
            con.execute("""UPDATE work_orders SET status='done',result_evidence_ids_json=?,
                updated_at=? WHERE id=? AND status='open'""",
                        (json.dumps(list(evidence_ids or [])), stamp, work_order_id))
            if current["status"] == "claimed":
                con.execute("""UPDATE work_orders SET status='done',result_evidence_ids_json=?,
                    updated_at=? WHERE id=? AND status='claimed' AND claimed_by=?""",
                    (json.dumps(list(evidence_ids or [])), stamp, work_order_id, worker_id))
            row = con.execute("SELECT * FROM work_orders WHERE id=?", (work_order_id,)).fetchone()
        value = self._decode(row)
        self.event(value["goal_id"], value["run_id"], "work_order.done",
                   {"work_order_id": work_order_id,
                    "evidence_ids": list(evidence_ids or [])})
        return value

    def refresh_work_orders_for_run(self, goal_id: str, run_id: str) -> list[dict]:
        """Mark open work orders done when accepted evidence meets the needed count.

        Linked evidence (payload.work_order_id) always wins. The unlinked
        fallback is deliberately conservative: it applies ONLY when exactly
        one typed assignment (one that declares accepted evidence kinds) is
        active on this run — capability orders without evidence kinds are
        excluded from that count, so a mixed run still completes its single
        typed order while multi-order runs never guess which evidence belongs
        to whom.
        """

        evidence = self.evidence(run_id)
        completed = []
        active = self.work_orders(status="active", goal_id=goal_id, run_id=run_id, limit=100)
        typed = [order for order in active if order.get("accepts_evidence")]
        for order in active:
            accepts = set(order.get("accepts_evidence") or [])
            if not accepts:
                continue
            linked = [item for item in evidence
                      if (item.get("payload") or {}).get("work_order_id") == order["id"]]
            if linked:
                matched = [item for item in linked if item.get("kind") in accepts]
            elif len(typed) == 1:
                # Conservative unlinked-evidence fallback: exactly one typed
                # assignment on the run, so accepted kinds are unambiguous.
                matched = [item for item in evidence if item.get("kind") in accepts]
            else:
                matched = []
            if len(matched) >= int(order.get("needed") or 1):
                completed.append(self.complete_work_order(
                    order["id"], [item["id"] for item in matched[: int(order["needed"])]],
                    worker_id=order.get("claimed_by")))
        return completed
