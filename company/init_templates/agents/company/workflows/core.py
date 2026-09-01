from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone

from ..state import Database


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class WorkflowStep:
    id: str
    agent_id: str
    instruction: str
    evidence_kind: str
    approval_key: str | None = None
    skill_ids: tuple[str, ...] = ()
    connection_ids: tuple[str, ...] = ()
    requirements: dict = field(default_factory=dict)


@dataclass(frozen=True)
class Workflow:
    id: str
    name: str
    steps: tuple[WorkflowStep, ...]
    department_id: str | None = None
    version: int = 1


@dataclass(frozen=True)
class WorkflowRun:
    id: str
    workflow_id: str
    goal_id: str
    run_id: str
    intervention_id: str
    workflow_version: int
    steps: tuple[WorkflowStep, ...]
    current_step: int
    status: str


class WorkflowRepository:
    def __init__(self, database: Database):
        self.database = database

    def save(self, workflow: Workflow) -> Workflow:
        stamp = _now()
        steps_json = json.dumps([asdict(step) for step in workflow.steps], sort_keys=True)
        with self.database.connect() as connection:
            current = connection.execute(
                "SELECT department_id,name,steps_json FROM core_workflows WHERE id=?",
                (workflow.id,)).fetchone()
            if current is None:
                connection.execute("""INSERT INTO core_workflows
                    (id,department_id,name,steps_json,version,created_at,updated_at)
                    VALUES (?,?,?,?,?,?,?)""",
                    (workflow.id, workflow.department_id, workflow.name,
                     steps_json, workflow.version, stamp, stamp))
            elif (current["department_id"], current["name"], current["steps_json"]) != (
                    workflow.department_id, workflow.name, steps_json):
                connection.execute("""UPDATE core_workflows
                    SET department_id=?,name=?,steps_json=?,version=version+1,updated_at=?
                    WHERE id=?""", (workflow.department_id, workflow.name,
                                     steps_json, stamp, workflow.id))
        return self.get(workflow.id)

    def get(self, workflow_id: str) -> Workflow:
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT * FROM core_workflows WHERE id=?", (workflow_id,)
            ).fetchone()
        if row is None:
            raise KeyError(f"unknown workflow: {workflow_id}")
        return Workflow(row["id"], row["name"],
                        tuple(WorkflowStep(**item) for item in json.loads(row["steps_json"])),
                        row["department_id"], row["version"])

    def start(self, workflow_id: str, *, goal_id: str, run_id: str,
              intervention_id: str) -> WorkflowRun:
        self.get(workflow_id)
        workflow = self.get(workflow_id)
        workflow_run_id = f"workflow-run-{uuid.uuid4().hex[:12]}"
        stamp = _now()
        with self.database.connect() as connection:
            connection.execute("""INSERT INTO core_workflow_runs
                (id,workflow_id,goal_id,run_id,intervention_id,workflow_version,
                 steps_json,current_step,status,created_at,updated_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                (workflow_run_id, workflow_id, goal_id, run_id, intervention_id,
                 workflow.version,
                 json.dumps([asdict(step) for step in workflow.steps], sort_keys=True),
                 0, "running", stamp, stamp))
        return self.run(workflow_run_id)

    def run(self, workflow_run_id: str) -> WorkflowRun:
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT * FROM core_workflow_runs WHERE id=?", (workflow_run_id,)
            ).fetchone()
        if row is None:
            raise KeyError(f"unknown workflow run: {workflow_run_id}")
        steps = tuple(WorkflowStep(**item) for item in json.loads(row["steps_json"]))
        return WorkflowRun(row["id"], row["workflow_id"], row["goal_id"],
                           row["run_id"], row["intervention_id"],
                           row["workflow_version"], steps,
                           row["current_step"], row["status"])

    def active_for_intervention(self, intervention_id: str) -> WorkflowRun | None:
        with self.database.connect() as connection:
            row = connection.execute("""SELECT id FROM core_workflow_runs
                WHERE intervention_id=? AND status IN ('running','waiting','complete')
                ORDER BY created_at DESC LIMIT 1""", (intervention_id,)).fetchone()
        return None if row is None else self.run(row[0])

    def advance(self, workflow_run_id: str) -> WorkflowRun:
        current = self.run(workflow_run_id)
        next_step = current.current_step + 1
        status = "complete" if next_step >= len(current.steps) else "running"
        with self.database.connect() as connection:
            connection.execute("""UPDATE core_workflow_runs
                SET current_step=?,status=?,updated_at=? WHERE id=?""",
                (next_step, status, _now(), workflow_run_id))
        return self.run(workflow_run_id)

    def set_status(self, workflow_run_id: str, status: str) -> WorkflowRun:
        with self.database.connect() as connection:
            connection.execute(
                "UPDATE core_workflow_runs SET status=?,updated_at=? WHERE id=?",
                (status, _now(), workflow_run_id))
        return self.run(workflow_run_id)
