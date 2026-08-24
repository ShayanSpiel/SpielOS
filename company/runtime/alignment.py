"""Director/Policy: pursuit semantics and Goal-alignment judgment.

Not a schema, service, or portfolio optimizer. Callers persist the result
through existing decision, event, notification, and approval-note records.
"""

from __future__ import annotations

from typing import Any

from .truth import BUSINESS_OUTCOME_METRICS, TECHNICAL_OWNERS, _field

UNKNOWN = "unknown"

# Locked pursuit vocabulary from the strategic-cognition plan §3.
PURSUIT_KINDS = {
    "primary_goal": "Durable measurable business outcome selected from Intent",
    "supporting_goal": "Measurable business driver promoted because it is an active bottleneck",
    "system_improvement_goal": "Bounded technical or capability outcome that enables or restores trustworthy pursuit",
    "run": "One controlled attempt or experiment toward a Goal",
    "batch": "Bounded volume/time exposure inside one Run",
    "task": "Known bounded work inside execution",
    "guardrail": "Quality, risk, evidence, or authority constraint",
}

PURSUIT_INVARIANTS = (
    "Metric is not a Goal by default",
    "Run is not a Goal",
    "Batch is not a Goal",
    "Task is not a Goal",
    "Guardrail is not a Goal",
    "Dependency success is not parent success",
    "Run completion is not Goal completion",
    "Technical evidence is not business evidence",
    "Owner override is not strategic justification",
)

GOAL_PURSUIT_KINDS = frozenset({
    "primary_goal", "supporting_goal", "system_improvement_goal",
})
NON_GOAL_PURSUIT_KINDS = frozenset({"run", "batch", "task", "guardrail"})

ALIGNMENT_CLASSES = ("supports", "enables", "protects", "explores")
ALIGNMENT_JUDGMENTS = ("aligned", "defer_recommended")
ALIGNMENT_OVERRIDE_ACTIONS = frozenset({"alignment_override", "request_owner_override"})


def as_goal_record(goal) -> dict[str, Any]:
    if isinstance(goal, dict):
        return goal
    return {
        "id": _field(goal, "id"),
        "name": _field(goal, "name"),
        "owner_id": _field(goal, "owner_id"),
        "metric": _field(goal, "metric"),
        "operator": _field(goal, "operator"),
        "target": _field(goal, "target"),
        "goal_status": _field(goal, "goal_status"),
        "parent_id": _field(goal, "parent_id"),
        "config": _field(goal, "config") or {},
    }


def needs_alignment(request) -> bool:
    return _field(request, "owner_id") in TECHNICAL_OWNERS


def validate_goal_topology(request) -> None:
    """Reject explicit attempts to persist a non-Goal pursuit kind as a Goal.

    Existing records need no new taxonomy column. Callers may declare a
    `pursuit_kind` in config when the distinction matters; absence keeps the
    current inferred behavior.
    """

    config = dict(_field(request, "config") or {})
    kind = config.get("pursuit_kind")
    if kind is None:
        return
    if kind not in PURSUIT_KINDS:
        raise ValueError(f"unknown pursuit_kind: {kind}")
    if kind in NON_GOAL_PURSUIT_KINDS:
        raise ValueError(
            f"{kind} is not a Goal; persist it inside the current Run")
    parent_id = _field(request, "parent_id")
    if kind == "primary_goal" and parent_id:
        raise ValueError("a primary_goal cannot have a parent Goal")
    if kind == "supporting_goal" and not parent_id:
        raise ValueError("a supporting_goal requires a parent Goal")


def pursuit_kind(goal) -> str:
    """Project Goal topology from existing fields without persisting a graph."""

    config = dict(_field(goal, "config") or {})
    declared = config.get("pursuit_kind")
    if declared in GOAL_PURSUIT_KINDS:
        return declared
    if _field(goal, "owner_id") in TECHNICAL_OWNERS:
        return "system_improvement_goal"
    if _field(goal, "parent_id"):
        return "supporting_goal"
    return "primary_goal"


def is_market_outcome(goal) -> bool:
    """True only for real company outcomes, not rollups or repairs."""

    if _field(goal, "owner_id") in TECHNICAL_OWNERS:
        return False
    return _field(goal, "metric") in BUSINESS_OUTCOME_METRICS


def active_market_outcomes(goals) -> list[dict]:
    return [goal for goal in goals or ()
            if _field(goal, "goal_status") == "active" and is_market_outcome(goal)]


def present(value) -> str:
    text = str(value or "").strip()
    if not text or text.lower() == UNKNOWN:
        return ""
    return text


def explicit_owner_override(config: dict | None) -> bool:
    config = config or {}
    if config.get("owner_override") is True:
        return True
    alignment = config.get("alignment")
    return isinstance(alignment, dict) and alignment.get("owner_override") is True


def resolve_originating_goal(store, values: dict, config: dict | None):
    run_id = (
        values.get("resume_run_id")
        or values.get("parent_run_id")
        or (config or {}).get("originating_run_id")
        or (config or {}).get("resume_run_id")
    )
    if not run_id:
        return None
    try:
        run = store.run(run_id)
        return store.goal(run["goal_id"])
    except KeyError:
        return None


def judge_alignment(request, *, active_outcomes, parent=None,
                    originating_goal=None) -> dict[str, Any]:
    """Return an alignment record. Never invents a strategic justification."""

    config = dict(_field(request, "config") or {})
    declared = config.get("alignment") if isinstance(config.get("alignment"), dict) else {}
    outcomes = [as_goal_record(item) for item in (active_outcomes or ())]
    override = explicit_owner_override(config)
    parent = as_goal_record(parent) if parent is not None else None
    originating = as_goal_record(originating_goal) if originating_goal is not None else None

    def result(judgment: str, klass: str | None, outcome, rationale: str,
               extra: dict | None = None) -> dict[str, Any]:
        payload = {
            "judgment": judgment,
            "owner_override": override,
            "class": klass,
            "outcome_id": _field(outcome, "id") if outcome else declared.get("outcome_id"),
            "outcome_name": _field(outcome, "name") if outcome else None,
            "rationale": rationale,
            "opportunity_cost": _opportunity_cost(outcomes),
        }
        if extra:
            payload.update(extra)
        return payload

    if is_market_outcome(request):
        return result(
            "aligned", "supports", request,
            "This Goal is itself an active company outcome.")

    parent_ok = parent if parent and is_market_outcome(parent) and _field(
        parent, "goal_status") in (None, "active") else None
    if parent_ok:
        return result(
            "aligned", "enables", parent_ok,
            f"This work enables the active outcome '{parent_ok.get('name')}' "
            f"({parent_ok.get('id')}).")

    origin_ok = originating if originating and is_market_outcome(originating) and _field(
        originating, "goal_status") == "active" else None
    if origin_ok:
        return result(
            "aligned", "enables", origin_ok,
            f"This work enables the originating active outcome "
            f"'{origin_ok.get('name')}' ({origin_ok.get('id')}).")

    declared_class = declared.get("class")
    declared_outcome_id = declared.get("outcome_id")
    if declared_class in {"supports", "enables"} and declared_outcome_id:
        match = next((item for item in outcomes if item.get("id") == declared_outcome_id), None)
        if match:
            return result(
                "aligned", declared_class, match,
                present(declared.get("rationale"))
                or f"Declared {declared_class} the active outcome '{match.get('name')}'.")
        return result(
            "defer_recommended", None, None,
            f"Declared outcome {declared_outcome_id} is not an active company outcome.",
            extra={"defects": ["outcome_not_active"]})

    invariant = present(declared.get("invariant"))
    if declared_class == "protects" and invariant:
        return result(
            "aligned", "protects", None,
            present(declared.get("rationale")) or f"Protects required invariant: {invariant}.",
            extra={"invariant": invariant})

    exploration = present(declared.get("rationale"))
    if declared_class == "explores" and exploration:
        return result("aligned", "explores", None, exploration)

    rationale = (
        "This system improvement does not support, enable, or protect an active "
        "company outcome, and is not a justified bounded exploration.")
    cost = _opportunity_cost(outcomes)
    if cost:
        rationale += f" Opportunity cost: {cost}."
    else:
        rationale += " No active company outcome is currently in pursuit."
    return result("defer_recommended", None, None, rationale)


def alignment_override_interaction(goal, judgment: dict) -> dict[str, Any]:
    goal_id = _field(goal, "id")
    name = _field(goal, "name") or goal_id
    fallback = ("PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=.agents python3 -B -m company "
                f"approve {goal_id}")
    cost = judgment.get("opportunity_cost") or "no other active company outcome"
    return {
        "id": f"alignment:{goal_id}",
        "header": "Alignment override required",
        "question": f"Director recommends deferring {name}. Override and start it anyway?",
        "goal_id": goal_id,
        "action": "Owner override of recommended deferral",
        "artifact": name,
        "destination": "internal runtime",
        "scope": ("Start this Goal only. Does not approve sending, publishing, "
                  "spending, or code changes."),
        "risk": f"Company attention moves here instead of: {cost}",
        "consequence": ("If rejected, the Goal stays proposed and no work starts. "
                        "The record remains a recommended deferral, not a strategic justification."),
        "options": [
            {"label": "Override", "value": "approve", "command": fallback},
            {"label": "Keep deferred", "value": "reject", "command": None},
        ],
        "fallback_command": fallback,
    }


def approval_key(cycle: dict | None) -> str:
    data = (cycle or {}).get("data") or {}
    action = ((data.get("decision") or {}).get("action")
              or (data.get("action_result") or {}).get("action"))
    if action in ALIGNMENT_OVERRIDE_ACTIONS:
        return "alignment_override"
    return "execute"


def _opportunity_cost(outcomes: list[dict]) -> str:
    names = [f"{item.get('name')} ({item.get('id')})" for item in outcomes[:5]
             if item.get("id")]
    return "; ".join(names)
