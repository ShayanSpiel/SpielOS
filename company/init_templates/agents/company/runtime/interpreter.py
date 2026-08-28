"""Generic Department interpreter: WorkflowSpec graphs as Lego under one loop.

Departments declare package data. This interpreter runs:
  OBSERVE → count evidence + surface memory
  DECIDE  → goal met | next graph step | catalog agent shortfall
  ACT     → work order | approval | connection handoff | machine hook
  EVALUATE → metric check + durable learnings

Never a second lifecycle. Parent runtime still owns goals, approvals, and work orders.
"""

from __future__ import annotations

import math
from typing import Any

from ..connections import connection as resolve_connection
from .contracts import agent_shortfall, employee_for, workflow_by_id
from .models import GoalStatus, RunStatus, Stage, StageResult, WorkflowSpec, WorkflowStep
from .memory import apply_memory, relevant_memory
from .truth import countable_evidence, derive_evaluation_validity, is_business_outcome
from .util import compare as _shared_compare


def compare(value, operator, target):
    """The one shared goal-metric comparator; unknown operators fail (False)."""
    return _shared_compare(value, operator, target)


def _shortfall(target, current_value) -> int:
    """Whole artifacts still needed to reach the target.

    Float-safe: a fractional target (e.g. 2.5) rounds UP, and the old
    ``int(target) - int(current)`` truncation can never undercount.
    """
    return max(1, math.ceil(float(target) - float(current_value or 0)))


def _kinds_present(evidence: list[dict], kinds: tuple[str, ...] | list[str]) -> int:
    accept = set(kinds)
    if not accept:
        return 0
    return sum(1 for item in evidence if item.get("kind") in accept)


def _kinds_satisfied(evidence: list[dict], kinds: tuple[str, ...] | list[str]) -> bool:
    """True only when every declared kind is present at least once."""

    required = [kind for kind in kinds if kind]
    if not required:
        return True
    present = {item.get("kind") for item in evidence}
    return set(required) <= present


def _missing_kinds(evidence: list[dict], kinds: tuple[str, ...] | list[str]) -> list[str]:
    present = {item.get("kind") for item in evidence}
    return [kind for kind in kinds if kind and kind not in present]


def _evidence_ids(evidence: list[dict], kinds=()) -> list[str]:
    """IDs of the evidence records this decision branch actually inspected."""

    accepted = set(kinds or ())
    return [item["id"] for item in evidence
            if item.get("id") and (not accepted or item.get("kind") in accepted)]


def _memory_view(memory) -> list[dict[str, Any]]:
    values = []
    for item in tuple(memory or ())[:10]:
        values.append({
            "id": item.get("id"),
            "claim": item.get("claim"),
            "confidence": item.get("confidence"),
            "goal_id": item.get("goal_id"),
            "evidence": item.get("evidence") or {},
        })
    return values


def _strategy_view(strategy) -> dict[str, Any]:
    """The bounded strategy context that an employee may actually use.

    The runtime owns selection; this projection deliberately keeps the
    work-order contract explicit instead of asking an employee to rediscover
    strategy from local files.
    """
    value = dict(strategy or {})
    return {
        "state_hash": value.get("state_hash"),
        "current_intent": dict(value.get("current_intent") or {}),
        "sections": list(value.get("sections") or ()),
    }


def synthesize_graph(handler, workflow: WorkflowSpec | None, metric: str) -> tuple[WorkflowStep, ...]:
    """One employee step from catalog fields when a workflow has no explicit graph."""

    if workflow is None:
        return ()
    if workflow.graph:
        return workflow.graph
    employee_id = employee_for(handler, workflow)
    produces = tuple((getattr(handler, "evidence_metrics", None) or {}).get(metric) or ())
    if not produces:
        produces = tuple(workflow.evidence_sources)
    return (WorkflowStep(
        id=workflow.steps[-1] if workflow.steps else "produce",
        kind="employee",
        employee_id=employee_id,
        produces=produces,
        skill_ids=tuple(workflow.skill_ids),
        connection_ids=tuple(workflow.connection_ids),
    ),)


def next_incomplete_step(graph: tuple[WorkflowStep, ...], evidence: list[dict],
                         approval_status) -> WorkflowStep | None:
    """First graph node that still needs work (requires, approval, or produces)."""

    for node in graph:
        if node.requires and not _kinds_satisfied(evidence, node.requires):
            missing = _missing_kinds(evidence, node.requires)
            producers = [prior for prior in graph
                         if set(prior.produces) & set(missing)]
            for prior in producers:
                if not _kinds_satisfied(evidence, prior.produces):
                    return prior
            return node
        if node.kind == "approval":
            if approval_status(f"step:{node.id}") == "approved":
                continue
            return node
        if node.kind == "machine":
            if not node.produces:
                # Package-validation error, not a silent skip: a machine node
                # that declares no produced evidence kinds can never be
                # satisfied and would wedge the graph invisibly.
                raise ValueError(
                    f"invalid workflow package: machine step '{node.id}' "
                    "declares no `produces` evidence kinds; every machine "
                    "node must name the evidence it creates")
            if _kinds_present(evidence, node.produces) >= 1:
                continue
            return node
        if node.produces:
            if _kinds_present(evidence, node.produces) >= 1:
                continue
            return node
        if node.kind in {"employee", "connection"}:
            return node
    return None


class InterpretedDepartment:
    """Lego runtime for declarative Department packages."""

    evidence_metrics: dict = {}
    workflow_agents: dict = {}

    def observe(self, ctx):
        evidence = list(ctx.cycle.get("evidence") or ())
        counts = {metric: sum(1 for item in evidence if item.get("kind") in kinds)
                  for metric, kinds in self.evidence_metrics.items()}
        workflow_id = ctx.goal.config.get("workflow")
        workflow = workflow_by_id(self, workflow_id)
        graph = synthesize_graph(self, workflow, ctx.goal.metric)
        current = next_incomplete_step(graph, evidence, ctx.approval_status)
        memory = _memory_view(ctx.memory)
        payload = {
            "workflow": workflow_id or (workflow.id if workflow else None),
            "evidence": evidence,
            "memory": memory,
            "strategy": _strategy_view(ctx.strategy),
            "directives": [item.get("text") for item in ctx.directives if item.get("text")],
            "graph": [node.id for node in graph],
            "current_step": None if current is None else {
                "id": current.id, "kind": current.kind,
                "employee_id": current.employee_id,
                "produces": list(current.produces),
                "requires": list(current.requires),
            },
            **counts,
        }
        message = f"Observed {len(evidence)} evidence record(s)"
        if memory:
            message += f", {len(memory)} memory claim(s)"
        if current:
            message += f"; next step `{current.id}` ({current.kind})"
        return StageResult("collect", payload, message=message)

    def decide(self, ctx, observation):
        metric = ctx.goal.metric
        current_value = observation.get(metric, 0)
        evidence = list(observation.get("evidence") or ())
        workflow_id = observation.get("workflow") or ctx.goal.config.get("workflow")
        memory = relevant_memory(
            observation.get("memory") or (), metric=metric, workflow_id=workflow_id)
        if compare(current_value, ctx.goal.operator, ctx.goal.target):
            payload = {"action": "evaluate", "metric": metric, "value": current_value}
            metric_kinds = tuple(self.evidence_metrics.get(metric) or ())
            return StageResult("choose_intervention", payload,
                               decision=apply_memory({"type": "evaluate",
                                         "rationale": "Package evidence meets the goal",
                                         "evidence_ids": _evidence_ids(evidence, metric_kinds),
                                         "payload": payload}, memory))

        workflow = workflow_by_id(self, workflow_id)
        graph = synthesize_graph(self, workflow, metric)
        step = next_incomplete_step(graph, evidence, ctx.approval_status)

        if step is None:
            # Fall back to metric shortfall work order (classic evidence department).
            # Float-safe: fractional targets round UP to whole artifacts.
            needed = _shortfall(ctx.goal.target, current_value)
            payload = agent_shortfall(
                self, goal_id=ctx.goal.id, metric=metric, needed=needed,
                workflow_id=workflow_id, config=ctx.goal.config)
            return StageResult("choose_intervention", payload,
                               decision=apply_memory({"type": "request_agent",
                                         "rationale": "Catalog shortfall for the goal metric",
                                         "evidence_ids": _evidence_ids(
                                             evidence,
                                             tuple(self.evidence_metrics.get(metric) or ())),
                                         "payload": payload}, memory))

        # Missing prerequisites → request whatever evidence unlocks this step.
        if step.requires and not _kinds_satisfied(evidence, step.requires):
            missing = _missing_kinds(evidence, step.requires)
            needed = max(1, len(missing))
            payload = agent_shortfall(
                self, goal_id=ctx.goal.id, metric=metric, needed=needed,
                workflow_id=workflow_id, config=ctx.goal.config)
            payload["accepted_evidence_kinds"] = missing
            payload["step_id"] = step.id
            payload["required_user_action"] = (
                f"Produce prerequisite evidence: {', '.join(missing)}")
            return StageResult("choose_intervention", payload,
                               decision=apply_memory({"type": "request_agent",
                                         "rationale": f"Step `{step.id}` is waiting on prerequisites",
                                         "evidence_ids": _evidence_ids(evidence, step.requires),
                                         "payload": payload}, memory))

        if step.kind == "approval":
            payload = {"action": "request_approval", "workflow_id": workflow_id,
                       "step_id": step.id, "metric": metric, "value": current_value}
            return StageResult("choose_intervention", payload,
                               decision=apply_memory({"type": "request_approval",
                                         "rationale": f"Workflow step `{step.id}` requires approval",
                                         "evidence_ids": _evidence_ids(evidence, step.requires),
                                         "payload": payload}, memory))

        if step.kind == "connection":
            configured = ctx.goal.config.get("connection")
            connection_id = (
                configured if configured and (
                    not step.connection_ids or configured in step.connection_ids
                    or (workflow and configured in workflow.connection_ids)
                ) else None
            )
            if connection_id is None:
                connection_id = (
                    (step.connection_ids[0] if step.connection_ids else None)
                    or (workflow.connection_ids[0] if workflow and workflow.connection_ids else None)
                    or configured
                )
            require_kinds = step.requires or ("content_package",)
            package_evidence = [item for item in evidence if item.get("kind") in require_kinds]
            payload = {
                "action": "connection_dispatch",
                "workflow_id": workflow_id,
                "step_id": step.id,
                "connection": connection_id,
                "package": (package_evidence[-1].get("payload") if package_evidence else {}),
                "execution_mode": ctx.goal.config.get("execution_mode", "dry_run"),
                "required_evidence": list(step.produces or ("publication_receipt",)),
                "metric": metric,
            }
            return StageResult("choose_intervention", payload,
                               decision=apply_memory({"type": "connection_dispatch",
                                         "rationale": f"Workflow step `{step.id}` needs a Connection",
                                         "evidence_ids": ([package_evidence[-1]["id"]]
                                                          if package_evidence and package_evidence[-1].get("id")
                                                          else []),
                                         "payload": payload}, memory))

        if step.kind == "machine":
            payload = {"action": "run_machine_step", "workflow_id": workflow_id,
                       "step_id": step.id, "produces": list(step.produces),
                       "metric": metric}
            return StageResult("choose_intervention", payload,
                               decision=apply_memory({"type": "run_machine_step",
                                         "rationale": f"Workflow step `{step.id}` is machine-owned",
                                         "evidence_ids": _evidence_ids(evidence, step.requires),
                                         "payload": payload}, memory))

        # employee step
        needed = _shortfall(ctx.goal.target, current_value)
        if step.produces:
            have = _kinds_present(evidence, step.produces)
            needed = max(1, 1 - have)
        employee_id = step.employee_id or employee_for(self, workflow)
        payload = agent_shortfall(
            self, goal_id=ctx.goal.id, metric=metric, needed=needed,
            workflow_id=workflow_id, config=ctx.goal.config)
        if employee_id:
            payload["agent_id"] = employee_id
            payload["employee_id"] = employee_id
        if step.produces:
            payload["accepted_evidence_kinds"] = list(step.produces)
        if step.skill_ids:
            payload["skill_ids"] = list(step.skill_ids)
        payload["step_id"] = step.id
        payload["action"] = "request_agent"
        # These are not merely audit decoration: the exact bounded context is
        # copied into the durable work order below so the employee can apply it.
        payload["memory"] = list(observation.get("memory") or ())
        payload["strategy"] = dict(observation.get("strategy") or {})
        return StageResult("choose_intervention", payload,
                           decision=apply_memory({"type": "request_agent",
                                     "rationale": f"Workflow step `{step.id}` needs employee output",
                                     "evidence_ids": _evidence_ids(
                                         evidence, tuple(step.requires) + tuple(step.produces)),
                                     "payload": payload}, memory))

    def act(self, ctx, decision):
        action = decision.get("action")
        if action == "request_approval":
            approval_key = f"step:{decision.get('step_id')}"
            if ctx.approval_status(approval_key) == "approved":
                # Stay in the same run and re-enter DECIDE for the next graph node.
                return StageResult("approved", decision, next_stage=Stage.DECIDE,
                                   message="Approval recorded; continue workflow")
            return StageResult("review", decision, RunStatus.AWAITING_APPROVAL, Stage.ACT,
                               message=decision.get("required_user_action")
                               or "Approve the prepared workflow action")

        if action == "connection_dispatch":
            if ctx.approval_status("execute") != "approved":
                return StageResult("review", decision, RunStatus.AWAITING_APPROVAL, Stage.ACT,
                                   message="Approve the exact package, channel, timing, and destination")
            connection_id = decision.get("connection")
            try:
                selected = resolve_connection(connection_id)
            except KeyError as error:
                return StageResult("dispatch", {"error": str(error)}, RunStatus.FAILED, Stage.ACT)
            required = list(decision.get("required_evidence") or ["publication_receipt"])
            if selected.unattended and selected.id == "buffer":
                from ..connections.buffer import BufferError, dispatch
                try:
                    receipt = dispatch(decision.get("package") or {}, decision.get("execution_mode", "dry_run"))
                except BufferError as error:
                    receipt = {"ok": False, "message": str(error)}
                if receipt.get("ok"):
                    return StageResult("dispatch", {"publication_receipt": receipt, **decision}, next_stage=Stage.EVALUATE,
                                       evidence=[{"kind": required[0], "source": "buffer", "validity": "business", "payload": receipt}],
                                       message="Approved package was dispatched through direct Buffer")
                return StageResult("dispatch", {"connection_request": receipt, **decision}, RunStatus.BLOCKED, Stage.ACT,
                                   attention=receipt, message=receipt.get("message") or "Direct Buffer dispatch could not run")
            request = {
                "capability": "connection_execution",
                "connection_id": selected.id,
                "hosts": list(selected.hosts),
                "operation": "publish",
                "execution_mode": decision.get("execution_mode", "dry_run"),
                "package": decision.get("package") or {},
                "required_evidence": required[0] if required else "publication_receipt",
                "employee_id": "publisher",
                "accepted_evidence_kinds": required,
                "required_user_action": (
                    f"Use the available {selected.id} Connection and record its receipt"),
                "next_trigger": f"company retry {ctx.goal.id}",
                "workflow_id": decision.get("workflow_id"),
                "step_id": decision.get("step_id"),
            }
            return StageResult("dispatch", {"connection_request": request, **decision},
                               RunStatus.BLOCKED, Stage.ACT, attention=request,
                               message="Connection work is delegated to the active host")

        if action == "run_machine_step":
            runner = getattr(self, "run_machine_step", None)
            if not callable(runner):
                return StageResult("machine", decision, RunStatus.BLOCKED, Stage.ACT,
                                   message=f"No machine hook for step `{decision.get('step_id')}`",
                                   attention=decision)
            result = runner(ctx, decision) or {}
            if result.get("run_status") == "blocked":
                return StageResult("machine", {**decision, **result}, RunStatus.BLOCKED, Stage.ACT,
                                   message=result.get("message") or "Machine step blocked",
                                   attention=result.get("attention") or decision)
            return StageResult("machine", {**decision, **result},
                               next_stage=Stage.DECIDE,
                               evidence=list(result.get("evidence") or []),
                               message=result.get("message") or "Machine step completed")

        if action == "request_agent":
            employee = decision.get("agent_id") or decision.get("employee_id") or "employee"
            return StageResult("request_agent", decision, RunStatus.BLOCKED, Stage.ACT,
                               message=decision.get("required_user_action") or (
                                   f"{employee} must produce {decision.get('needed')} validated artifact(s)"),
                               attention=decision)

        return StageResult("collect_artifacts", decision, next_stage=Stage.EVALUATE)

    def evaluate(self, ctx, action_result):
        metric = action_result.get("metric", ctx.goal.metric)
        # Prefer live evidence counts over stale decide payload.
        run = ctx.cycle.get("run") or {}
        evidence = countable_evidence(list(ctx.cycle.get("evidence") or ()), ctx.goal, run)
        kinds = tuple(self.evidence_metrics.get(metric) or ())
        if kinds:
            value = _kinds_present(evidence, kinds)
        else:
            value = action_result.get("value", 0)
        # Connection success shortcut used by publish-style graphs.
        if action_result.get("publication_receipt", {}).get("ok"):
            value = max(int(value or 0), 1)
        met = compare(value, ctx.goal.operator, ctx.goal.target)
        validity = derive_evaluation_validity(evidence, ctx.goal, run)
        if is_business_outcome(ctx.goal, run) and validity != "business":
            met = False
        workflow_id = ctx.goal.config.get("workflow")
        evaluation = {"verdict": "goal_met" if met else "continue", "goal_met": met,
                      "metrics": {metric: value}, "validity": validity,
                      "contamination_reason": None,
                      "next_experiment": {} if met else {
                          "action": "continue_workflow",
                          "workflow_id": workflow_id,
                          "change_one_variable": "workflow_step_output"}}
        evidence_ids = [item["id"] for item in evidence if item.get("id")]
        learnings = []
        if not met and evidence_ids and validity in {"business", "technical_only"}:
            learnings.append({
                "reusable": True,
                "claim": (f"Workflow {workflow_id or 'default'} produced {metric}={value} "
                          f"against target {ctx.goal.operator} {ctx.goal.target}."),
                "decision_relevance": (
                    "Do not repeat the same workflow configuration expecting a different "
                    "result; change one declared variable or choose another workflow."),
                "evidence_ids": evidence_ids,
                "applies_to": {"metrics": [metric],
                               "workflows": [workflow_id] if workflow_id else []},
                "confidence": 0.8,
                "evidence": {"observed_value": value, "target": ctx.goal.target,
                             "run_id": ctx.cycle.get("id")},
            })
        return StageResult("goal_check", {metric: value}, RunStatus.COMPLETED,
                           goal_status=GoalStatus.ACHIEVED if met else None,
                           evaluation=evaluation,
                           learnings=learnings,
                           message=("Department package goal achieved" if met
                                    else "Department package run completed; more evidence required"))
