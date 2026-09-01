"""Small SQLite boundary shared by the clean-core repositories."""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator


class Database:
    """Connection lifecycle only. This class intentionally has no domain methods."""

    def __init__(self, path: str | Path, *, readonly: bool = False):
        self.path = Path(path)
        self.readonly = readonly
        if readonly:
            if not self.path.exists():
                raise FileNotFoundError(self.path)
        else:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self._initialize()

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        target = f"file:{self.path}?mode=ro" if self.readonly else str(self.path)
        connection = sqlite3.connect(target, timeout=30, uri=self.readonly)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        try:
            yield connection
            if self.readonly:
                connection.rollback()
            else:
                connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def _initialize(self) -> None:
        with self.connect() as connection:
            connection.executescript(SCHEMA)
            self._migrate(connection)
            connection.executescript(POST_MIGRATION_SCHEMA)

    @staticmethod
    def _migrate(connection: sqlite3.Connection) -> None:
        workflow_run_columns = {row[1] for row in connection.execute(
            "PRAGMA table_info(core_workflow_runs)")}
        for name, declaration in (
            ("workflow_version", "INTEGER NOT NULL DEFAULT 1"),
            ("steps_json", "TEXT NOT NULL DEFAULT '[]'"),
        ):
            if name not in workflow_run_columns:
                connection.execute(
                    f"ALTER TABLE core_workflow_runs ADD COLUMN {name} {declaration}")
        connection.execute("""UPDATE core_workflow_runs
            SET workflow_version=COALESCE((SELECT version FROM core_workflows w
                                           WHERE w.id=workflow_id),1),
                steps_json=COALESCE((SELECT steps_json FROM core_workflows w
                                     WHERE w.id=workflow_id),'[]')
            WHERE steps_json='[]'""")
        order_columns = {row[1] for row in connection.execute(
            "PRAGMA table_info(core_work_orders)")}
        for name, declaration in (
            ("claimed_at", "TEXT"),
            ("lease_expires_at", "TEXT"),
            ("attempt", "INTEGER NOT NULL DEFAULT 1"),
        ):
            if name not in order_columns:
                connection.execute(
                    f"ALTER TABLE core_work_orders ADD COLUMN {name} {declaration}")
        memory_columns = {row[1] for row in connection.execute(
            "PRAGMA table_info(core_memory)")}
        for name, declaration in (
            ("confidence", "REAL NOT NULL DEFAULT 1.0"),
            ("status", "TEXT NOT NULL DEFAULT 'active'"),
            ("supersedes_id", "TEXT REFERENCES core_memory(id)"),
        ):
            if name not in memory_columns:
                connection.execute(
                    f"ALTER TABLE core_memory ADD COLUMN {name} {declaration}")
        edge_sql = connection.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='core_goal_edges'"
        ).fetchone()[0]
        if "'blocks'" not in edge_sql:
            connection.executescript("""
                ALTER TABLE core_goal_edges RENAME TO core_goal_edges_legacy;
                CREATE TABLE core_goal_edges (
                    source_goal_id TEXT NOT NULL REFERENCES core_goals(id),
                    target_goal_id TEXT NOT NULL REFERENCES core_goals(id),
                    relation TEXT NOT NULL CHECK(relation IN ('supports','blocks')),
                    created_at TEXT NOT NULL,
                    PRIMARY KEY(source_goal_id, target_goal_id, relation),
                    CHECK(source_goal_id <> target_goal_id)
                );
                INSERT INTO core_goal_edges SELECT * FROM core_goal_edges_legacy;
                DROP TABLE core_goal_edges_legacy;
            """)
        approval_sql = connection.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='core_approvals'"
        ).fetchone()[0]
        if "UNIQUE(run_id,key)" in approval_sql.replace(" ", ""):
            connection.executescript("""
                ALTER TABLE core_approvals RENAME TO core_approvals_legacy;
                CREATE TABLE core_approvals (
                    id TEXT PRIMARY KEY,
                    goal_id TEXT NOT NULL REFERENCES core_goals(id),
                    run_id TEXT NOT NULL REFERENCES core_runs(id),
                    intervention_id TEXT REFERENCES core_interventions(id),
                    key TEXT NOT NULL,
                    status TEXT NOT NULL,
                    note TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(intervention_id, key)
                );
                INSERT INTO core_approvals SELECT * FROM core_approvals_legacy;
                DROP TABLE core_approvals_legacy;
            """)
        connection.execute("DROP TRIGGER IF EXISTS core_evidence_lineage_insert")


SCHEMA = """
PRAGMA journal_mode=WAL;

CREATE TABLE IF NOT EXISTS core_goals (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    metric TEXT NOT NULL,
    operator TEXT NOT NULL,
    target_json TEXT NOT NULL,
    parent_id TEXT REFERENCES core_goals(id),
    status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS core_goal_edges (
    source_goal_id TEXT NOT NULL REFERENCES core_goals(id),
    target_goal_id TEXT NOT NULL REFERENCES core_goals(id),
    relation TEXT NOT NULL CHECK(relation IN ('supports','blocks')),
    created_at TEXT NOT NULL,
    PRIMARY KEY(source_goal_id, target_goal_id, relation),
    CHECK(source_goal_id <> target_goal_id)
);

CREATE TABLE IF NOT EXISTS core_goal_metadata (
    goal_id TEXT PRIMARY KEY REFERENCES core_goals(id),
    owner_id TEXT NOT NULL,
    deadline TEXT,
    config_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS core_runs (
    id TEXT PRIMARY KEY,
    goal_id TEXT NOT NULL REFERENCES core_goals(id),
    sequence INTEGER NOT NULL,
    stage TEXT NOT NULL,
    status TEXT NOT NULL,
    observation_json TEXT,
    decision_json TEXT,
    evaluation_json TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(goal_id, sequence)
);

CREATE TABLE IF NOT EXISTS core_interventions (
    id TEXT PRIMARY KEY,
    goal_id TEXT NOT NULL REFERENCES core_goals(id),
    run_id TEXT NOT NULL REFERENCES core_runs(id),
    kind TEXT NOT NULL,
    description TEXT NOT NULL,
    status TEXT NOT NULL,
    resolution_outcome TEXT,
    context_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS core_workflows (
    id TEXT PRIMARY KEY,
    department_id TEXT,
    name TEXT NOT NULL,
    steps_json TEXT NOT NULL,
    version INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS core_workflow_runs (
    id TEXT PRIMARY KEY,
    workflow_id TEXT NOT NULL REFERENCES core_workflows(id),
    goal_id TEXT NOT NULL REFERENCES core_goals(id),
    run_id TEXT NOT NULL REFERENCES core_runs(id),
    intervention_id TEXT NOT NULL REFERENCES core_interventions(id),
    workflow_version INTEGER NOT NULL,
    steps_json TEXT NOT NULL,
    current_step INTEGER NOT NULL,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS core_work_orders (
    id TEXT PRIMARY KEY,
    goal_id TEXT NOT NULL REFERENCES core_goals(id),
    run_id TEXT NOT NULL REFERENCES core_runs(id),
    intervention_id TEXT NOT NULL REFERENCES core_interventions(id),
    workflow_run_id TEXT REFERENCES core_workflow_runs(id),
    agent_id TEXT NOT NULL,
    step_id TEXT,
    brief_json TEXT NOT NULL,
    status TEXT NOT NULL,
    claimed_by TEXT,
    claimed_at TEXT,
    lease_expires_at TEXT,
    attempt INTEGER NOT NULL DEFAULT 1,
    result_json TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS core_evidence (
    id TEXT PRIMARY KEY,
    goal_id TEXT NOT NULL REFERENCES core_goals(id),
    run_id TEXT NOT NULL REFERENCES core_runs(id),
    intervention_id TEXT REFERENCES core_interventions(id),
    workflow_run_id TEXT REFERENCES core_workflow_runs(id),
    work_order_id TEXT REFERENCES core_work_orders(id),
    kind TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS core_memory (
    id TEXT PRIMARY KEY,
    scope TEXT NOT NULL CHECK(scope IN ('owner','workflow','strategy')),
    claim TEXT NOT NULL,
    goal_id TEXT REFERENCES core_goals(id),
    run_id TEXT REFERENCES core_runs(id),
    intervention_id TEXT REFERENCES core_interventions(id),
    workflow_id TEXT,
    evidence_ids_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    confidence REAL NOT NULL DEFAULT 1.0 CHECK(confidence >= 0.0 AND confidence <= 1.0),
    status TEXT NOT NULL DEFAULT 'active' CHECK(status IN ('active','superseded')),
    supersedes_id TEXT REFERENCES core_memory(id)
);

CREATE TABLE IF NOT EXISTS core_approvals (
    id TEXT PRIMARY KEY,
    goal_id TEXT NOT NULL REFERENCES core_goals(id),
    run_id TEXT NOT NULL REFERENCES core_runs(id),
    intervention_id TEXT REFERENCES core_interventions(id),
    key TEXT NOT NULL,
    status TEXT NOT NULL,
    note TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(intervention_id, key)
);

CREATE TABLE IF NOT EXISTS core_notifications (
    id TEXT PRIMARY KEY,
    goal_id TEXT NOT NULL REFERENCES core_goals(id),
    run_id TEXT NOT NULL REFERENCES core_runs(id),
    intervention_id TEXT REFERENCES core_interventions(id),
    kind TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    acknowledged_at TEXT,
    UNIQUE(intervention_id, kind)
);

CREATE INDEX IF NOT EXISTS core_runs_ready ON core_runs(status, updated_at);
CREATE INDEX IF NOT EXISTS core_interventions_run ON core_interventions(run_id, status);
CREATE INDEX IF NOT EXISTS core_work_orders_ready ON core_work_orders(status, created_at);
CREATE INDEX IF NOT EXISTS core_evidence_lineage ON core_evidence(goal_id, run_id, intervention_id);
CREATE INDEX IF NOT EXISTS core_memory_scope ON core_memory(scope, goal_id, workflow_id);

-- Foreign keys prove that referenced rows exist. These triggers additionally
-- prove that every descendant names one coherent Goal/Run/Intervention chain.
CREATE TRIGGER IF NOT EXISTS core_intervention_lineage_insert
BEFORE INSERT ON core_interventions
WHEN NOT EXISTS (
    SELECT 1 FROM core_runs r
    WHERE r.id=NEW.run_id AND r.goal_id=NEW.goal_id
)
BEGIN
    SELECT RAISE(ABORT, 'intervention Goal/Run lineage mismatch');
END;

CREATE TRIGGER IF NOT EXISTS core_intervention_lineage_update
BEFORE UPDATE OF goal_id,run_id ON core_interventions
WHEN NOT EXISTS (
    SELECT 1 FROM core_runs r
    WHERE r.id=NEW.run_id AND r.goal_id=NEW.goal_id
)
BEGIN
    SELECT RAISE(ABORT, 'intervention Goal/Run lineage mismatch');
END;

CREATE TRIGGER IF NOT EXISTS core_workflow_run_lineage_insert
BEFORE INSERT ON core_workflow_runs
WHEN NOT EXISTS (
    SELECT 1 FROM core_interventions i
    WHERE i.id=NEW.intervention_id AND i.run_id=NEW.run_id
      AND i.goal_id=NEW.goal_id
)
BEGIN
    SELECT RAISE(ABORT, 'WorkflowRun lineage mismatch');
END;

CREATE TRIGGER IF NOT EXISTS core_workflow_run_lineage_update
BEFORE UPDATE OF goal_id,run_id,intervention_id ON core_workflow_runs
WHEN NOT EXISTS (
    SELECT 1 FROM core_interventions i
    WHERE i.id=NEW.intervention_id AND i.run_id=NEW.run_id
      AND i.goal_id=NEW.goal_id
)
BEGIN
    SELECT RAISE(ABORT, 'WorkflowRun lineage mismatch');
END;

CREATE TRIGGER IF NOT EXISTS core_work_order_lineage_insert
BEFORE INSERT ON core_work_orders
WHEN NOT EXISTS (
    SELECT 1 FROM core_interventions i
    WHERE i.id=NEW.intervention_id AND i.run_id=NEW.run_id
      AND i.goal_id=NEW.goal_id
) OR (NEW.workflow_run_id IS NOT NULL AND NOT EXISTS (
    SELECT 1 FROM core_workflow_runs w
    WHERE w.id=NEW.workflow_run_id AND w.intervention_id=NEW.intervention_id
      AND w.run_id=NEW.run_id AND w.goal_id=NEW.goal_id
))
BEGIN
    SELECT RAISE(ABORT, 'WorkOrder lineage mismatch');
END;

CREATE TRIGGER IF NOT EXISTS core_work_order_lineage_update
BEFORE UPDATE OF goal_id,run_id,intervention_id,workflow_run_id ON core_work_orders
WHEN NOT EXISTS (
    SELECT 1 FROM core_interventions i
    WHERE i.id=NEW.intervention_id AND i.run_id=NEW.run_id
      AND i.goal_id=NEW.goal_id
) OR (NEW.workflow_run_id IS NOT NULL AND NOT EXISTS (
    SELECT 1 FROM core_workflow_runs w
    WHERE w.id=NEW.workflow_run_id AND w.intervention_id=NEW.intervention_id
      AND w.run_id=NEW.run_id AND w.goal_id=NEW.goal_id
))
BEGIN
    SELECT RAISE(ABORT, 'WorkOrder lineage mismatch');
END;

CREATE TRIGGER IF NOT EXISTS core_evidence_lineage_insert
BEFORE INSERT ON core_evidence
WHEN NOT EXISTS (
    SELECT 1 FROM core_runs r
    WHERE r.id=NEW.run_id AND r.goal_id=NEW.goal_id
) OR (NEW.intervention_id IS NOT NULL AND NOT EXISTS (
    SELECT 1 FROM core_interventions i
    WHERE i.id=NEW.intervention_id AND i.run_id=NEW.run_id
      AND i.goal_id=NEW.goal_id
)) OR (NEW.workflow_run_id IS NOT NULL AND NOT EXISTS (
    SELECT 1 FROM core_workflow_runs w
    WHERE w.id=NEW.workflow_run_id AND w.intervention_id=NEW.intervention_id
      AND w.run_id=NEW.run_id AND w.goal_id=NEW.goal_id
)) OR (NEW.work_order_id IS NOT NULL AND NOT EXISTS (
    SELECT 1 FROM core_work_orders o
    WHERE o.id=NEW.work_order_id AND o.run_id=NEW.run_id
      AND o.goal_id=NEW.goal_id
      AND (NEW.intervention_id IS NULL OR o.intervention_id=NEW.intervention_id)
))
BEGIN
    SELECT RAISE(ABORT, 'Evidence lineage mismatch');
END;

CREATE TRIGGER IF NOT EXISTS core_evidence_immutable_update
BEFORE UPDATE ON core_evidence
BEGIN
    SELECT RAISE(ABORT, 'Evidence is immutable');
END;

CREATE TRIGGER IF NOT EXISTS core_evidence_immutable_delete
BEFORE DELETE ON core_evidence
BEGIN
    SELECT RAISE(ABORT, 'Evidence is immutable');
END;
"""

POST_MIGRATION_SCHEMA = """
CREATE UNIQUE INDEX IF NOT EXISTS core_work_order_step_attempt
ON core_work_orders(workflow_run_id,step_id,attempt)
WHERE workflow_run_id IS NOT NULL AND step_id IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS core_work_order_direct_attempt
ON core_work_orders(intervention_id,step_id,attempt)
WHERE workflow_run_id IS NULL AND step_id IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS core_run_approval_key
ON core_approvals(run_id,key) WHERE intervention_id IS NULL;

CREATE TRIGGER IF NOT EXISTS core_approval_lineage_insert
BEFORE INSERT ON core_approvals
WHEN NOT EXISTS (
    SELECT 1 FROM core_runs r WHERE r.id=NEW.run_id AND r.goal_id=NEW.goal_id
) OR (NEW.intervention_id IS NOT NULL AND NOT EXISTS (
    SELECT 1 FROM core_interventions i
    WHERE i.id=NEW.intervention_id AND i.run_id=NEW.run_id
      AND i.goal_id=NEW.goal_id
))
BEGIN
    SELECT RAISE(ABORT, 'Approval lineage mismatch');
END;

CREATE TRIGGER IF NOT EXISTS core_notification_lineage_insert
BEFORE INSERT ON core_notifications
WHEN NOT EXISTS (
    SELECT 1 FROM core_runs r WHERE r.id=NEW.run_id AND r.goal_id=NEW.goal_id
) OR (NEW.intervention_id IS NOT NULL AND NOT EXISTS (
    SELECT 1 FROM core_interventions i
    WHERE i.id=NEW.intervention_id AND i.run_id=NEW.run_id
      AND i.goal_id=NEW.goal_id
))
BEGIN
    SELECT RAISE(ABORT, 'Notification lineage mismatch');
END;

CREATE TRIGGER core_evidence_lineage_insert
BEFORE INSERT ON core_evidence
WHEN NOT EXISTS (
    SELECT 1 FROM core_runs r
    WHERE r.id=NEW.run_id AND r.goal_id=NEW.goal_id
) OR (NEW.intervention_id IS NOT NULL AND NOT EXISTS (
    SELECT 1 FROM core_interventions i
    WHERE i.id=NEW.intervention_id AND i.run_id=NEW.run_id
      AND i.goal_id=NEW.goal_id
)) OR (NEW.workflow_run_id IS NOT NULL AND NOT EXISTS (
    SELECT 1 FROM core_workflow_runs w
    WHERE w.id=NEW.workflow_run_id AND w.intervention_id=NEW.intervention_id
      AND w.run_id=NEW.run_id AND w.goal_id=NEW.goal_id
)) OR (NEW.work_order_id IS NOT NULL AND NOT EXISTS (
    SELECT 1 FROM core_work_orders o
    WHERE o.id=NEW.work_order_id AND o.run_id=NEW.run_id
      AND o.goal_id=NEW.goal_id
      AND (NEW.intervention_id IS NULL OR o.intervention_id=NEW.intervention_id)
))
BEGIN
    SELECT RAISE(ABORT, 'Evidence lineage mismatch');
END;
"""
