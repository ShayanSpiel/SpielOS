"""Declarative workflow contracts: goal validation and agent shortfall briefs.

Departments declare WorkflowSpec + goal_schema. The runtime turns shortfalls
into durable work-order briefs without each Department inventing attention JSON.
"""

from __future__ import annotations

from typing import Any

from ..agents import agents as installed_agents
from .models import GoalHandler, WorkflowSpec


def approval_interaction(goal: Any, result: Any) -> dict[str, Any]:
    """Build the single host-neutral question for one parked action."""

    attention = result.attention if isinstance(result.attention, dict) else {}
    payload = result.payload if isinstance(result.payload, dict) else {}
    evaluation = result.evaluation if isinstance(result.evaluation, dict) else {}
    metrics = evaluation.get("metrics") if isinstance(evaluation.get("metrics"), dict) else {}
    task = metrics.get("task") if isinstance(metrics.get("task"), dict) else {}
    action = (attention.get("action") or payload.get("action") or task.get("problem")
              or result.message or "Execute the prepared action")
    artifact = (attention.get("artifact") or payload.get("preview_path")
                or payload.get("artifact") or task.get("id"))
    destination = attention.get("destination") or payload.get("destination") or "internal runtime"
    scope = (attention.get("scope") or payload.get("scope")
             or task.get("allowed_files") or "this exact parked action")
    risk = attention.get("risk") or payload.get("risk") or (
        "Only this prepared action is released; later actions require separate approval.")
    consequence = (attention.get("consequence") or attention.get("rejection_consequence")
                   or payload.get("consequence")
                   or "If rejected, the action remains parked and nothing executes.")
    goal_id = goal.id
    fallback = ("PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=.agents python3 -B -m company "
                f"approve {goal_id}")
    return {
        "id": f"approval:{goal_id}",
        "header": "Approval required",
        "question": f"Approve this action for {goal.name}?",
        "goal_id": goal_id,
        "action": action,
        "artifact": artifact,
        "destination": destination,
        "scope": scope,
        "risk": risk,
        "consequence": consequence,
        "options": [
            {"label": "Approve", "value": "approve", "command": fallback},
            {"label": "Reject", "value": "reject", "command": None},
        ],
        "fallback_command": fallback,
    }


def workflow_by_id(handler: GoalHandler, workflow_id: str | None) -> WorkflowSpec | None:
    workflows = tuple(getattr(handler, "workflows", ()) or ())
    if not workflows:
        return None
    if workflow_id:
        for item in workflows:
            if item.id == workflow_id:
                return item
        raise ValueError(
            f"workflow '{workflow_id}' is not on {handler.id}; "
            f"use: {', '.join(item.id for item in workflows)}")
    return workflows[0]


def validate_goal_request(handler: GoalHandler, *, metric: str,
                          config: dict | None = None) -> dict[str, Any]:
    """Validate metric/workflow/config against the owner catalog; fill defaults.

    Returns a possibly-updated config dict (e.g. default workflow). Handlers
    without a goal_schema or workflows are accepted as-is (test doubles, Director).
    """

    config = dict(config or {})
    schema = getattr(handler, "goal_schema", None) or {}
    metrics = list(schema.get("metrics") or [])
    if metrics and metric not in metrics:
        raise ValueError(
            f"metric '{metric}' is not supported by '{handler.id}'; "
            f"use: {', '.join(metrics)}")

    workflows = tuple(getattr(handler, "workflows", ()) or ())
    cfg_schema = dict(schema.get("config") or {})
    workflow_rule = cfg_schema.get("workflow") if isinstance(cfg_schema.get("workflow"), dict) else {}
    enum = list(workflow_rule.get("enum") or [])

    if workflows or enum:
        allowed = set(enum) if enum else {item.id for item in workflows}
        # Workflows listed on the Department remain valid even if schema enum lags.
        allowed |= {item.id for item in workflows}
        workflow_id = config.get("workflow")
        if not workflow_id:
            if enum:
                config["workflow"] = enum[0]
            elif workflows:
                config["workflow"] = workflows[0].id
        elif config["workflow"] not in allowed:
            raise ValueError(
                f"workflow '{config['workflow']}' is not supported by '{handler.id}'; "
                f"use: {', '.join(sorted(allowed))}")

    for key, rule in cfg_schema.items():
        if not isinstance(rule, dict) or key == "workflow":
            continue
        if key not in config:
            # required_when is enforced by Departments at ACT time; create only
            # demands unconditionally required fields.
            if rule.get("required") and not rule.get("required_when"):
                raise ValueError(f"config.{key} is required for '{handler.id}'")
            continue
        if "enum" in rule and config[key] not in rule["enum"]:
            raise ValueError(
                f"config.{key}={config[key]!r} is invalid for '{handler.id}'; "
                f"use: {', '.join(str(item) for item in rule['enum'])}")
    return config


def accepted_evidence_for(handler: GoalHandler, *, workflow: WorkflowSpec | None,
                          metric: str | None, employee_id: str | None) -> list[str]:
    """Prefer metric-specific kinds, then workflow sources, then agent produces."""

    metric = metric or ""
    evidence_metrics = getattr(handler, "evidence_metrics", None) or {}
    if metric and metric in evidence_metrics:
        kinds = list(evidence_metrics[metric])
    elif workflow and workflow.evidence_sources:
        kinds = list(workflow.evidence_sources)
    else:
        kinds = []

    agent = installed_agents().get(employee_id) if employee_id else None
    if agent and kinds:
        produces = set(agent.produces)
        narrowed = [kind for kind in kinds if kind in produces]
        if narrowed:
            return narrowed
    if agent and not kinds:
        return list(agent.produces)
    return kinds


def employee_for(handler: GoalHandler, workflow: WorkflowSpec | None) -> str | None:
    if workflow:
        mapping = getattr(handler, "workflow_agents", None) or {}
        if workflow.id in mapping:
            return mapping[workflow.id]
        if workflow.agent_ids:
            return workflow.agent_ids[0]
    agent_ids = tuple(getattr(handler, "agent_ids", ()) or ())
    return agent_ids[0] if agent_ids else None


def agent_shortfall(handler: GoalHandler, *, goal_id: str, metric: str,
                    needed: int, workflow_id: str | None = None,
                    config: dict | None = None) -> dict[str, Any]:
    """Build a catalog-backed request_agent payload for a typed shortfall."""

    config = config or {}
    workflow_id = workflow_id or config.get("workflow")
    workflow = workflow_by_id(handler, workflow_id)
    employee_id = employee_for(handler, workflow)
    if not employee_id:
        raise ValueError(f"department '{handler.id}' has no employee for workflow '{workflow_id}'")
    needed = max(1, int(needed))
    accepts = accepted_evidence_for(handler, workflow=workflow, metric=metric,
                                    employee_id=employee_id)
    skills = list(workflow.skill_ids) if workflow and workflow.skill_ids else []
    if not skills:
        agent = installed_agents().get(employee_id)
        skills = list(agent.skill_ids) if agent else []
    connections = list(workflow.connection_ids) if workflow else []
    return {
        "action": "request_agent",
        "workflow_id": workflow.id if workflow else workflow_id,
        "agent_id": employee_id,
        "employee_id": employee_id,
        "skill_ids": skills,
        "connection_ids": connections,
        "needed": needed,
        "accepted_evidence_kinds": accepts,
        "metric": metric,
        "required_user_action": (
            f"{employee_id} must produce {needed} validated artifact(s)"
            + (f" of kind {', '.join(accepts)}" if accepts else "")),
        "next_trigger": f"company retry {goal_id}",
        "completion_evidence": (
            f"{', '.join(accepts)} evidence" if accepts else "validated artifacts"),
    }


def enrich_work_order_source(handler: GoalHandler | None, goal: dict,
                             source: dict[str, Any]) -> dict[str, Any]:
    """Fill missing employee/evidence fields from the Department catalog."""

    out = dict(source)
    if handler is None:
        return out
    workflow_id = out.get("workflow_id") or (goal.get("config") or {}).get("workflow")
    try:
        workflow = workflow_by_id(handler, workflow_id)
    except ValueError:
        workflow = None
    employee_id = out.get("agent_id") or out.get("employee_id") or employee_for(handler, workflow)
    if employee_id:
        out.setdefault("agent_id", employee_id)
        out.setdefault("employee_id", employee_id)
    if not out.get("accepted_evidence_kinds") and not out.get("accepts_evidence"):
        accepts = accepted_evidence_for(
            handler, workflow=workflow,
            metric=out.get("metric") or goal.get("metric"),
            employee_id=employee_id)
        if accepts:
            out["accepted_evidence_kinds"] = accepts
    if workflow:
        out.setdefault("workflow_id", workflow.id)
        if workflow.skill_ids and not out.get("skill_ids"):
            out["skill_ids"] = list(workflow.skill_ids)
        if workflow.connection_ids and not out.get("connection_ids"):
            out["connection_ids"] = list(workflow.connection_ids)
    return out
