"""Small SQLite boundary shared by the clean-core repositories."""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator


class Database:
    """Connection lifecycle only. This class intentionally has no domain methods."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def _initialize(self) -> None:
        with self.connect() as connection:
            connection.executescript(SCHEMA)


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
    relation TEXT NOT NULL CHECK(relation = 'supports'),
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
    created_at TEXT NOT NULL
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
    UNIQUE(run_id, key)
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
