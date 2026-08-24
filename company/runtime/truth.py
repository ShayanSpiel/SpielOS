"""Minimum business-truth discriminator. Not a Goal taxonomy."""

from __future__ import annotations

from typing import Any

from . import config

INVALID_VALIDITIES = frozenset({"invalid", "contaminated"})
HYPOTHESIS_OUTCOMES = frozenset({"supported", "rejected", "inconclusive"})
# Identity-owned vocabularies are user-layer configuration, not generic code
# (see runtime/config.py and config.user.json).
TECHNICAL_OWNERS = config.technical_owners()
TECHNICAL_RUN_TYPES = frozenset({"system_improvement", "system_test", "diagnostic"})
TECHNICAL_METRICS = frozenset({"acceptance_tests_passed"})
BUSINESS_OUTCOME_METRICS = config.business_outcome_metrics()
DIRECTOR_ROLLUPS = frozenset({"all_children_achieved", "achieved_children"})


def _field(obj: Any, name: str, default=None):
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


def is_explicitly_technical(goal, run=None) -> bool:
    return (
        _field(goal, "owner_id") in TECHNICAL_OWNERS
        or _field(run, "run_type") in TECHNICAL_RUN_TYPES
        or _field(goal, "metric") in TECHNICAL_METRICS
    )


def is_business_outcome(goal, run=None) -> bool:
    """True for market/outcome Goals. Config cannot convert these to technical."""

    if is_explicitly_technical(goal, run):
        return False
    metric = _field(goal, "metric")
    if metric in BUSINESS_OUTCOME_METRICS:
        return True
    return _field(goal, "owner_id") == "director" and metric in (
        DIRECTOR_ROLLUPS | BUSINESS_OUTCOME_METRICS)


def accepted_validities(goal, run=None) -> frozenset[str]:
    """Validities that may satisfy this Goal. Business outcomes stay business."""

    if is_explicitly_technical(goal, run):
        return frozenset({"technical_only", "business"})
    if is_business_outcome(goal, run):
        return frozenset({"business"})
    return frozenset({"business", "technical_only"})


def countable_evidence(evidence, goal, run=None) -> list[dict]:
    allowed = accepted_validities(goal, run)
    counted = []
    for item in evidence or ():
        validity = item.get("validity") or "business"
        if validity in INVALID_VALIDITIES or validity not in allowed:
            continue
        counted.append(item)
    return counted


def derive_evaluation_validity(countable, goal, run=None) -> str:
    """Label from evidence actually used, not from a boolean config."""

    if is_explicitly_technical(goal, run):
        return "technical_only"
    used = {item.get("validity") or "business" for item in countable}
    if "business" in used:
        return "business"
    return "technical_only"


def child_supports_parent(parent_metric: str, child: dict, allowed: frozenset[str]) -> bool:
    if child.get("goal_status") != "achieved":
        return False
    run_validity = (child.get("run") or {}).get("evidence_validity")
    evaluation = child.get("evaluation") or {}
    validity = evaluation.get("validity") or run_validity
    if validity in INVALID_VALIDITIES or validity not in allowed:
        return False
    if parent_metric in DIRECTOR_ROLLUPS:
        return True
    return (evaluation.get("metrics") or {}).get(parent_metric) is not None


def achievement_allowed(goal, run, evaluation: dict | None, *,
                        children: list[dict] | None = None) -> bool:
    """Reject ACHIEVED when the handler did not supply compatible metric proof."""

    if not evaluation or not evaluation.get("goal_met"):
        return False
    validity = evaluation.get("validity")
    if validity in INVALID_VALIDITIES:
        return False
    if validity not in accepted_validities(goal, run):
        return False
    metric = _field(goal, "metric")
    metrics = evaluation.get("metrics") or {}
    if metric == "all_children_achieved":
        kids = list(children or ())
        allowed = accepted_validities(goal, run)
        accepted = [child for child in kids if child_supports_parent(metric, child, allowed)]
        return bool(kids) and len(accepted) == len(kids)
    if metric not in metrics:
        return False
    return True


def hypothesis_resolution(goal, run, evaluation: dict | None) -> str | None:
    """Return a terminal result only for the hypothesis tested by this Run.

    The evaluation contract is deliberately explicit. Goal completion is not a
    proxy for testing a prediction, and technical-only evidence cannot settle a
    business hypothesis.
    """

    result = (evaluation or {}).get("hypothesis_result") or {}
    hypothesis_id = _field(run, "hypothesis_id")
    if (not hypothesis_id or result.get("hypothesis_id") != hypothesis_id
            or result.get("prediction_tested") is not True):
        return None
    outcome = result.get("status")
    if outcome not in HYPOTHESIS_OUTCOMES:
        return None
    validity = (evaluation or {}).get("validity") or _field(run, "evidence_validity")
    if validity in INVALID_VALIDITIES:
        return "inconclusive"
    if not is_explicitly_technical(goal, run) and validity != "business":
        return None
    if validity not in accepted_validities(goal, run):
        return None
    return outcome
