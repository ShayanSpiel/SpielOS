"""CLI adapter for the canonical clean core.

The adapter contains presentation compatibility only. Goal control remains in
``GoalRuntime`` and every write goes through a clean-core repository.
"""

from __future__ import annotations

import sqlite3
import time
from dataclasses import asdict
from pathlib import Path

from ..agents.core import AgentResult
from ..goals import GoalRepository
from ..resolution.core import ApprovalRepository
from ..state import Database
from ..work_orders import WorkOrderRepository
from ..workflows import Workflow, WorkflowRepository, WorkflowStep
from ..runtime.engine import Decision, Evaluation, GoalRuntime
from ..runtime.registry import departments
from ..runtime.util import compare


def goal_authority(path: str | Path) -> str:
    """Return the one Goal authority for this database without mutating it."""

    path = Path(path)
    if not path.exists():
        return "clean-core"
    connection = sqlite3.connect(path)
    try:
        tables = {row[0] for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        core = (connection.execute("SELECT COUNT(*) FROM core_goals").fetchone()[0]
                if "core_goals" in tables else 0)
        legacy = (connection.execute("SELECT COUNT(*) FROM goals").fetchone()[0]
                  if "goals" in tables else 0)
    finally:
        connection.close()
    return "clean-core" if core or not legacy else "compatibility"


class CatalogController:
    """Translate portable Department declarations into clean Workflows."""

    def __init__(self, database: Database):
        self.database = database
        self.goals = GoalRepository(database)
        self.workflows = WorkflowRepository(database)
        self.departments = departments()

    def observe(self, context) -> dict:
        goal = context.goal
        handler = self.departments.get(goal.owner_id)
        kinds = tuple((getattr(handler, "evidence_metrics", {}) or {}).get(goal.metric) or ())
        matching = [item for item in context.evidence if not kinds or item.kind in kinds]
        value = len(matching)
        for item in matching:
            candidate = item.payload.get(goal.metric)
            if isinstance(candidate, (int, float, bool)):
                value = candidate
        if goal.owner_id == "director" and goal.metric == "all_children_achieved":
            children = [item for item in self.goals.list() if item.parent_id == goal.id]
            value = bool(children) and all(item.status == "complete" for item in children)
        return {goal.metric: value, "evidence_ids": [item.id for item in matching]}

    def decide(self, context, observation: dict) -> Decision:
        goal = context.goal
        if compare(observation.get(goal.metric, 0), goal.operator, goal.target):
            return Decision("evaluate", "Goal evidence meets its target",
                            context={"result_ready": True})
        handler = self.departments.get(goal.owner_id)
        if handler is None:
            return Decision("request_agent", f"{goal.owner_id} must choose bounded work",
                            context={"agent_id": goal.owner_id,
                                     "evidence_kind": goal.metric})
        requested = (goal.config or {}).get("workflow")
        workflow_spec = next((item for item in handler.workflows
                              if item.id == requested), None)
        if workflow_spec is None:
            workflow_spec = handler.workflows[0] if handler.workflows else None
        if workflow_spec is None:
            return Decision("request_agent", f"{goal.owner_id} must produce {goal.metric}",
                            context={"agent_id": goal.owner_id,
                                     "evidence_kind": goal.metric})
        workflow_id = f"{goal.owner_id}:{workflow_spec.id}"
        steps = []
        pending_approval = None
        graph = tuple(workflow_spec.graph or ())
        for node in graph:
            if node.kind == "approval":
                pending_approval = f"step:{node.id}"
                continue
            agent_id = node.agent_id
            if not agent_id:
                if node.kind == "connection":
                    connection = (node.connection_ids or workflow_spec.connection_ids or
                                  ("connection",))[0]
                    agent_id = f"connection:{connection}"
                else:
                    agent_id = (workflow_spec.agent_ids or handler.agent_ids or
                                (goal.owner_id,))[0]
            evidence_kind = (node.produces or (goal.metric,))[0]
            steps.append(WorkflowStep(
                node.id, agent_id, f"Execute {workflow_spec.id} step {node.id}",
                evidence_kind, pending_approval))
            pending_approval = None
        if not steps:
            agent_id = (workflow_spec.agent_ids or handler.agent_ids or (goal.owner_id,))[0]
            evidence_kind = (workflow_spec.evidence_sources or (goal.metric,))[0]
            steps.append(WorkflowStep(
                workflow_spec.id, agent_id, workflow_spec.description,
                evidence_kind, pending_approval))
        self.workflows.save(Workflow(
            workflow_id, workflow_spec.description, tuple(steps), goal.owner_id))
        return Decision("execute_workflow", workflow_spec.description, workflow_id)

    def evaluate(self, context, decision: Decision, evidence: tuple) -> Evaluation:
        observation = self.observe(context)
        value = observation.get(context.goal.metric, 0)
        return Evaluation(
            compare(value, context.goal.operator, context.goal.target),
            {context.goal.metric: value}, "clean-core evidence evaluated",
            evidence_ids=tuple(observation["evidence_ids"]))


class AssignmentExecutor:
    """Park work for an external Host; never execute a capability implicitly."""

    def execute(self, agent, order) -> AgentResult:
        return AgentResult(
            "ask_user", message=f"WorkOrder {order.id} is ready for Agent {agent.id}")


class CleanCommandRuntime:
    """Legacy-shaped CLI projection backed exclusively by clean-core records."""

    def __init__(self, path: str | Path, *, readonly: bool = False):
        self.path = Path(path)
        self.readonly = readonly
        self.database = Database(path)
        self.runtime = GoalRuntime(path, CatalogController(self.database), AssignmentExecutor())
        self.goals = self.runtime.goals
        self.runs = self.runtime.runs
        self.interventions = self.runtime.interventions
        self.evidence = self.runtime.evidence
        self.work_orders_repository = WorkOrderRepository(self.database)
        self.approvals = ApprovalRepository(self.database)
        self.store = self

    @staticmethod
    def _operator(value: str) -> str:
        return {"ge": "ge", ">=": "ge", "gt": "gt", ">": "gt",
                "eq": "eq", "==": "eq", "le": "le", "<=": "le",
                "lt": "lt", "<": "lt"}.get(value, value)

    def create_goal(self, **values) -> dict:
        goal = self.runtime.create_goal(
            values["name"], values["metric"], self._operator(values["operator"]),
            values["target"], parent_id=values.get("parent_id"),
            goal_id=values.get("goal_id"), owner_id=values.get("owner_id") or "goal-runtime",
            deadline=values.get("deadline"), config=values.get("config") or {})
        for target in (values.get("config") or {}).get("supports_goal_ids") or ():
            self.goals.add_support(goal.id, target)
        return self._goal(goal)

    def _goal(self, goal) -> dict:
        run = self.runs.current(goal.id)
        return {"id": goal.id, "name": goal.name, "owner_id": goal.owner_id,
                "metric": goal.metric, "operator": goal.operator, "target": goal.target,
                "deadline": goal.deadline, "parent_id": goal.parent_id,
                "goal_status": "achieved" if goal.status == "complete" else goal.status,
                "config": goal.config or {}, "run_id": run.id, "run_type": "execution",
                "run_status": run.status, "stage": run.stage.value,
                "step": run.stage.value.lower(), "evidence_count": len(self.evidence.for_run(run.id)),
                "evidence_validity": "technical_only", "runtime_updated_at": "",
                "why_next": "Continue the persisted clean-core Run."}

    def status(self, goal_id: str) -> dict:
        goal = self.goals.get(goal_id); run = self.runs.current(goal_id)
        evidence = [asdict(item) for item in self.evidence.for_run(run.id)]
        goal_row = self._goal(goal)
        run_row = {"id": run.id, "sequence": run.sequence, "run_type": "execution",
                   "status": run.status, "evidence_validity": "technical_only"}
        cycle = {"id": run.id, "stage": run.stage.value, "step": run.stage.value.lower(),
                 "run_status": run.status, "data": {}}
        return {"goal": goal_row, "run": run_row, "cycle": cycle,
                "evidence": evidence, "evaluation": None if run.evaluation is None
                else asdict(run.evaluation), "pending_notifications": [], "attention": [],
                "work_orders": self.work_orders(status="active", goal_id=goal_id)}

    def goal_summary(self, goal_id: str) -> dict:
        return {"goal": self._goal(self.goals.get(goal_id)), "attention": [],
                "unread_results": [], "work_orders": self.work_orders(
                    status="active", goal_id=goal_id)}

    def goal_summaries(self, *, statuses=None, goal_id=None, limit=100):
        values = [self._goal(item) for item in self.goals.list()
                  if goal_id is None or item.id == goal_id]
        if statuses:
            values = [item for item in values if item["goal_status"] in statuses]
        return values[:limit]

    def list_goals(self):
        return [self.status(item.id) for item in self.goals.list()]

    def goal_history(self, limit=10):
        return self.goal_summaries(statuses=("achieved", "abandoned"), limit=limit)

    def company_snapshot(self, recent_limit=5):
        values = self.goal_summaries(limit=100)
        active = [item for item in values if item["goal_status"] == "active"]
        paused = [item for item in values if item["goal_status"] == "paused"]
        terminal = [item for item in values
                    if item["goal_status"] in {"achieved", "abandoned"}]
        counts = {key: sum(item["goal_status"] == key for item in values)
                  for key in ("active", "achieved", "abandoned", "expired")}
        counts["total"] = len(values)
        return {"counts": counts, "focus_goal": active[0] if active else None,
                "attention": [], "work_orders": self.work_orders(status="active", limit=20),
                "active_goals": active, "proposed_goals": [], "paused_goals": paused,
                "unread_results": [], "directives": [], "recent_memory": [],
                "support_links": [], "recent_results": terminal[:recent_limit]}

    def topology_audit(self):
        goals = self.goals.list(); roots = [item.id for item in goals if not item.parent_id]
        return {"goal_count": len(goals), "root_goal_ids": roots,
                "canonical_root_goal_id": roots[0] if len(roots) == 1 else None,
                "defects": [] if len(roots) == 1 else [
                    {"goal_id": item, "kind": "disconnected_non_primary_root"}
                    for item in roots], "migration_plan": {"safe_first": []}}

    def link_support(self, goal_id, target_id):
        self.goals.add_support(goal_id, target_id)
        return self.status(goal_id)

    def set_goal_status(self, goal_id, status):
        value = getattr(status, "value", status)
        value = {"achieved": "complete", "expired": "abandoned"}.get(value, value)
        self.goals.set_status(goal_id, value)
        return self.status(goal_id)

    def approve(self, goal_id, note="", scope=None):
        run = self.runs.current(goal_id)
        intervention = self.interventions.active_for_run(run.id)
        keys = {"execute"}
        if intervention is not None:
            workflow_run = self.runtime.resolution.workflows.active_for_intervention(
                intervention.id)
            if workflow_run is not None:
                workflow = self.runtime.resolution.workflows.get(workflow_run.workflow_id)
                if workflow_run.current_step < len(workflow.steps):
                    key = workflow.steps[workflow_run.current_step].approval_key
                    if key:
                        keys.add(key)
        for key in keys:
            self.approvals.grant(
                goal_id=goal_id, run_id=run.id, key=key,
                intervention_id=None if intervention is None else intervention.id,
                note=note)
        if run.status == "waiting":
            self.runtime.resume(goal_id)
        return self.status(goal_id)

    def add_evidence(self, goal_id, *, kind, source, payload, validity=None):
        run = self.runs.current(goal_id)
        intervention = self.interventions.active_for_run(run.id)
        self.evidence.record(goal_id=goal_id, run_id=run.id, kind=kind,
                             intervention_id=None if intervention is None else intervention.id,
                             payload={**payload, "source": source,
                                      "validity": validity or "technical_only"})
        return self.status(goal_id)

    def once(self, goal_id, holder=None):
        self.runtime.advance(goal_id)
        return self.status(goal_id)

    def next(self, goal_id, **_):
        return self.retry(goal_id)

    def retry(self, goal_id):
        self.runtime.resume(goal_id)
        return self.status(goal_id)

    def tick(self, max_advances=100):
        return self.runtime.tick(max_advances=max_advances)

    def watch(self, interval_seconds=5.0, goal_id=None, max_ticks=None):
        ticks = 0
        while max_ticks is None or ticks < max_ticks:
            result = (self.once(goal_id) if goal_id
                      else self.tick(max_advances=100))
            ticks += 1
            yield result
            if max_ticks is None or ticks < max_ticks:
                time.sleep(interval_seconds)

    def complete_change(self, *_args, **_kwargs):
        raise RuntimeError(
            "clean-core repairs are WorkOrders; complete them with `spielos tasks --complete`")

    def work_order(self, order_id):
        return self._order(self.work_orders_repository.get(order_id))

    def work_orders(self, status=None, goal_id=None, limit=100):
        with self.database.connect() as connection:
            clauses, args = [], []
            if goal_id:
                clauses.append("goal_id=?"); args.append(goal_id)
            if status in {"active", "open", "claimed"}:
                clauses.append("status IN ('open','claimed')" if status == "active" else "status=?")
                if status != "active": args.append(status)
            sql = "SELECT id FROM core_work_orders"
            if clauses: sql += " WHERE " + " AND ".join(clauses)
            sql += " ORDER BY created_at LIMIT ?"; args.append(limit)
            ids = [row[0] for row in connection.execute(sql, args)]
        return [self.work_order(item) for item in ids]

    def _order(self, order):
        return {**asdict(order), "needed": 1,
                "accepts_evidence": [order.brief.get("evidence_kind")]
                if order.brief.get("evidence_kind") else [], "why_next": "Agent assignment"}

    def claim_work_order(self, work_order_id, agent_id):
        return self._order(self.work_orders_repository.claim(work_order_id, agent_id))

    def complete_work_order(self, work_order_id, agent_id, evidence):
        order = self.work_orders_repository.get(work_order_id)
        if order.status == "open":
            order = self.work_orders_repository.claim(work_order_id, agent_id)
        elif order.claimed_by != agent_id:
            agent_id = order.claimed_by or agent_id
        order = self.work_orders_repository.complete(
            work_order_id, {"evidence": evidence}, executor_id=agent_id)
        for item in evidence:
            self.evidence.record(
                goal_id=order.goal_id, run_id=order.run_id,
                intervention_id=order.intervention_id,
                workflow_run_id=order.workflow_run_id, work_order_id=order.id,
                kind=item["kind"], payload=item.get("payload") or {})
        self.runs.update(order.run_id, status="ready")
        return {"work_order": self._order(order)}

    def events(self, *_args, **_kwargs): return []
    def memories(self, *_args, **_kwargs): return []
    def notifications(self, *_args, **_kwargs): return []
    def attention(self, *_args, **_kwargs): return []
    def unread_results(self, *_args, **_kwargs): return []
