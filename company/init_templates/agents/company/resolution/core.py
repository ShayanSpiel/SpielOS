"""Execute, fix, retry, and validate an Intervention without spawning Goals."""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum

from ..agents.core import Agent, AgentExecutor
from ..evidence import EvidenceRepository
from ..memory import MemoryRepository
from ..state import Database
from ..work_orders import WorkOrderRepository
from ..workflows import WorkflowRepository


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class ResolutionOutcome(str, Enum):
    CONTINUE_LOCAL = "CONTINUE_LOCAL"
    RETURN_TO_GOAL = "RETURN_TO_GOAL"
    ESCALATE_TO_GOAL = "ESCALATE_TO_GOAL"
    ASK_USER = "ASK_USER"


@dataclass(frozen=True)
class Intervention:
    id: str
    goal_id: str
    run_id: str
    kind: str
    description: str
    status: str
    context: dict
    resolution_outcome: str | None = None


@dataclass(frozen=True)
class ResolutionResult:
    outcome: ResolutionOutcome
    intervention: Intervention
    message: str = ""


class InterventionRepository:
    def __init__(self, database: Database):
        self.database = database

    def create(self, *, goal_id: str, run_id: str, kind: str,
               description: str, context: dict | None = None) -> Intervention:
        intervention_id = f"intervention-{uuid.uuid4().hex[:12]}"
        stamp = _now()
        with self.database.connect() as connection:
            connection.execute("INSERT INTO core_interventions VALUES (?,?,?,?,?,?,?,?,?,?)",
                (intervention_id, goal_id, run_id, kind, description, "running", None,
                 json.dumps(context or {}), stamp, stamp))
        return self.get(intervention_id)

    def get(self, intervention_id: str) -> Intervention:
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT * FROM core_interventions WHERE id=?", (intervention_id,)
            ).fetchone()
        if row is None:
            raise KeyError(f"unknown intervention: {intervention_id}")
        return Intervention(row["id"], row["goal_id"], row["run_id"], row["kind"],
                            row["description"], row["status"],
                            json.loads(row["context_json"]), row["resolution_outcome"])

    def active_for_run(self, run_id: str) -> Intervention | None:
        with self.database.connect() as connection:
            row = connection.execute("""SELECT id FROM core_interventions
                WHERE run_id=? AND status IN ('running','waiting')
                ORDER BY created_at DESC LIMIT 1""", (run_id,)).fetchone()
        return None if row is None else self.get(row[0])

    def finish(self, intervention_id: str, outcome: ResolutionOutcome,
               *, message: str = "") -> Intervention:
        status = "complete" if outcome == ResolutionOutcome.RETURN_TO_GOAL else (
            "waiting" if outcome in {ResolutionOutcome.CONTINUE_LOCAL, ResolutionOutcome.ASK_USER}
            else "escalated")
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT context_json FROM core_interventions WHERE id=?", (intervention_id,)
            ).fetchone()
            if row is None:
                raise KeyError(f"unknown intervention: {intervention_id}")
            context = json.loads(row[0])
            if message:
                context["resolution_message"] = message
            connection.execute("""UPDATE core_interventions
                SET status=?,resolution_outcome=?,context_json=?,updated_at=? WHERE id=?""",
                (status, outcome.value, json.dumps(context), _now(), intervention_id))
        return self.get(intervention_id)


class ApprovalRepository:
    def __init__(self, database: Database):
        self.database = database

    def status(self, run_id: str, key: str) -> str | None:
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT status FROM core_approvals WHERE run_id=? AND key=?", (run_id, key)
            ).fetchone()
        return None if row is None else row[0]

    def grant(self, *, goal_id: str, run_id: str, key: str,
              intervention_id: str | None = None, note: str | None = None) -> None:
        stamp = _now()
        with self.database.connect() as connection:
            connection.execute("""INSERT INTO core_approvals
                VALUES (?,?,?,?,?,?,?,?,?)
                ON CONFLICT(run_id,key) DO UPDATE SET status='approved',
                    note=excluded.note,updated_at=excluded.updated_at""",
                (f"approval-{uuid.uuid4().hex[:12]}", goal_id, run_id,
                 intervention_id, key, "approved", note, stamp, stamp))


class ResolutionCycle:
    """Own Workflow execution until a meaningful boundary is reached."""

    def __init__(self, database: Database, executor: AgentExecutor, *,
                 agents: dict[str, Agent] | None = None, max_local_iterations: int = 50):
        self.database = database
        self.executor = executor
        self.agents = dict(agents or {})
        self.max_local_iterations = max_local_iterations
        self.interventions = InterventionRepository(database)
        self.workflows = WorkflowRepository(database)
        self.work_orders = WorkOrderRepository(database)
        self.evidence = EvidenceRepository(database)
        self.memory = MemoryRepository(database, self.evidence)
        self.approvals = ApprovalRepository(database)

    def resolve(self, intervention_id: str) -> ResolutionResult:
        intervention = self.interventions.get(intervention_id)
        workflow_id = intervention.context.get("workflow_id")
        if not workflow_id:
            return self._resolve_direct(intervention)
        workflow_run = self.workflows.active_for_intervention(intervention.id)
        if workflow_run is None:
            workflow_run = self.workflows.start(
                workflow_id, goal_id=intervention.goal_id, run_id=intervention.run_id,
                intervention_id=intervention.id)

        for _ in range(self.max_local_iterations):
            workflow_run = self.workflows.run(workflow_run.id)
            workflow = self.workflows.get(workflow_run.workflow_id)
            if workflow_run.status == "complete" or workflow_run.current_step >= len(workflow.steps):
                return self._finish(intervention, ResolutionOutcome.RETURN_TO_GOAL,
                                    "workflow completed and validated")
            step = workflow.steps[workflow_run.current_step]
            if step.approval_key and self.approvals.status(
                    intervention.run_id, step.approval_key) != "approved":
                self.workflows.set_status(workflow_run.id, "waiting")
                return self._finish(intervention, ResolutionOutcome.ASK_USER,
                                    f"approval required: {step.approval_key}")

            prior = self.work_orders.for_workflow_run(workflow_run.id)
            completed = [item for item in prior
                         if item.step_id == step.id and item.status == "completed"]
            if completed:
                self.workflows.set_status(workflow_run.id, "running")
                self.workflows.advance(workflow_run.id)
                continue

            order = self.work_orders.open(
                goal_id=intervention.goal_id, run_id=intervention.run_id,
                intervention_id=intervention.id, workflow_run_id=workflow_run.id,
                step_id=step.id, agent_id=step.agent_id,
                brief={"instruction": step.instruction, "evidence_kind": step.evidence_kind})
            if order.status == "open":
                order = self.work_orders.claim(order.id, f"executor:{step.agent_id}")
            agent = self.agents.get(step.agent_id, Agent(step.agent_id))
            result = self.executor.execute(agent, order)
            if result.status == "completed":
                order = self.work_orders.complete(
                    order.id, result.payload, executor_id=order.claimed_by or "")
                evidence = self.evidence.record(
                    goal_id=intervention.goal_id, run_id=intervention.run_id,
                    intervention_id=intervention.id, workflow_run_id=workflow_run.id,
                    work_order_id=order.id, kind=result.evidence_kind or step.evidence_kind,
                    payload=result.payload)
                if result.workflow_learning:
                    self.memory.remember(
                        "workflow", result.workflow_learning,
                        evidence_ids=(evidence.id,), goal_id=intervention.goal_id,
                        run_id=intervention.run_id, intervention_id=intervention.id,
                        workflow_id=workflow.id)
                self.workflows.advance(workflow_run.id)
                continue
            if result.status == "fixable":
                self.work_orders.fail(order.id, result.message or "local failure",
                                      executor_id=order.claimed_by or "")
                self.evidence.record(
                    goal_id=intervention.goal_id, run_id=intervention.run_id,
                    intervention_id=intervention.id, workflow_run_id=workflow_run.id,
                    work_order_id=order.id, kind="resolution_iteration",
                    payload={"status": "fixed_locally", "message": result.message})
                continue
            if result.status == "escalate":
                return self._finish(intervention, ResolutionOutcome.ESCALATE_TO_GOAL,
                                    result.message or "Goal-level decision is invalid")
            return self._finish(intervention, ResolutionOutcome.ASK_USER,
                                result.message or "user context or authority required")

        return self._finish(intervention, ResolutionOutcome.CONTINUE_LOCAL,
                            "local iteration budget reached; resume Resolution")

    def _resolve_direct(self, intervention: Intervention) -> ResolutionResult:
        if intervention.context.get("result_ready"):
            return self._finish(intervention, ResolutionOutcome.RETURN_TO_GOAL,
                                "bounded intervention result is ready")
        agent_id = intervention.context.get("agent_id")
        if not agent_id:
            return self._finish(intervention, ResolutionOutcome.ASK_USER,
                                "intervention requires a Workflow or Agent")
        for _ in range(self.max_local_iterations):
            order = self.work_orders.open(
                goal_id=intervention.goal_id, run_id=intervention.run_id,
                intervention_id=intervention.id, agent_id=agent_id,
                step_id="direct", brief={"instruction": intervention.description,
                                         "evidence_kind": intervention.context.get(
                                             "evidence_kind", "intervention_result")})
            if order.status == "open":
                order = self.work_orders.claim(order.id, f"executor:{agent_id}")
            result = self.executor.execute(self.agents.get(agent_id, Agent(agent_id)), order)
            if result.status == "completed":
                order = self.work_orders.complete(
                    order.id, result.payload, executor_id=order.claimed_by or "")
                self.evidence.record(
                    goal_id=intervention.goal_id, run_id=intervention.run_id,
                    intervention_id=intervention.id, work_order_id=order.id,
                    kind=result.evidence_kind or intervention.context.get(
                        "evidence_kind", "intervention_result"), payload=result.payload)
                return self._finish(intervention, ResolutionOutcome.RETURN_TO_GOAL,
                                    "direct intervention completed and validated")
            if result.status == "fixable":
                self.work_orders.fail(order.id, result.message or "local failure",
                                      executor_id=order.claimed_by or "")
                self.evidence.record(
                    goal_id=intervention.goal_id, run_id=intervention.run_id,
                    intervention_id=intervention.id, work_order_id=order.id,
                    kind="resolution_iteration",
                    payload={"status": "fixed_locally", "message": result.message})
                continue
            if result.status == "escalate":
                return self._finish(intervention, ResolutionOutcome.ESCALATE_TO_GOAL,
                                    result.message or "Goal-level decision is invalid")
            return self._finish(intervention, ResolutionOutcome.ASK_USER,
                                result.message or "user context or authority required")
        return self._finish(intervention, ResolutionOutcome.CONTINUE_LOCAL,
                            "local iteration budget reached; resume Resolution")

    def _finish(self, intervention: Intervention, outcome: ResolutionOutcome,
                message: str) -> ResolutionResult:
        updated = self.interventions.finish(intervention.id, outcome, message=message)
        return ResolutionResult(outcome, updated, message)
