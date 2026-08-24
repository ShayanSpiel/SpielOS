"""Director/Policy: when an unmet completed Run may start the next Run.

Not a scheduler, portfolio optimizer, or new table. Callers persist the
decision through existing events and the next cycle.
"""

from __future__ import annotations

from typing import Any

from . import config
from .truth import INVALID_VALIDITIES, _field

DEFAULT_MAX_RUNS = 32
BUSY_RUN_STATUSES = frozenset({"idle", "running", "awaiting_approval", "waiting"})
EXPERIMENT_FIELDS = ("action", "change_one_variable", "hypothesis", "variable")


def next_experiment_valid(evaluation) -> bool:
    experiment = _field(evaluation, "next_experiment") or {}
    if not isinstance(experiment, dict) or not experiment:
        return False
    if experiment.get("system_improvement"):
        return False
    return any(experiment.get(key) not in (None, "", {}, []) for key in EXPERIMENT_FIELDS)


def resource_key(goal) -> tuple:
    """The exclusive resource a goal occupies.

    Single derivation shared with the store's busy-goal projection via
    ``config.resource_key``; the two consumers can never disagree about
    channel groupings.
    """
    return config.resource_key(
        _field(goal, "owner_id"), _field(goal, "config") or {})


def declared_run_limit(goal) -> int:
    config = _field(goal, "config") or {}
    for key in ("max_runs", "run_limit", "attempt_limit"):
        value = config.get(key)
        if value is None:
            continue
        try:
            return max(1, int(value))
        except (TypeError, ValueError):
            continue
    return DEFAULT_MAX_RUNS


def continuation_decision(*, goal, cycle, evaluation, run_count: int,
                          ancestor_active: bool = True,
                          conflicting: dict | None = None) -> dict[str, Any]:
    """Whether the runtime may create the next Run without `company next`."""

    if _field(goal, "goal_status") != "active":
        return _result(False, "goal_not_active")
    if _field(cycle, "run_status") != "completed":
        return _result(False, "run_not_completed")
    if not ancestor_active:
        return _result(False, "ancestor_not_active")
    if not evaluation:
        return _result(False, "missing_evaluation")
    if _field(evaluation, "goal_met"):
        return _result(False, "goal_already_met")
    validity = _field(evaluation, "validity") or "business"
    if validity in INVALID_VALIDITIES:
        return _result(False, f"evaluation_{validity}")
    experiment = _field(evaluation, "next_experiment") or {}
    if isinstance(experiment, dict) and experiment.get("system_improvement"):
        return _result(False, "system_improvement_blocker")
    if not next_experiment_valid(evaluation):
        return _result(False, "invalid_next_experiment")
    limit = declared_run_limit(goal)
    if int(run_count or 0) >= limit:
        return _result(False, "run_limit_reached")
    if conflicting:
        return _result(False, "resource_conflict",
                       extra={"conflict_goal_id": conflicting.get("id")})
    return _result(True, "eligible", extra={"next_experiment": experiment})


def ancestors_allow(store, goal) -> bool:
    parent_id = _field(goal, "parent_id")
    while parent_id:
        try:
            parent = store.goal(parent_id)
        except KeyError:
            return False
        if parent.get("goal_status") != "active":
            return False
        parent_id = parent.get("parent_id")
    return True


def conflicting_goal(store, goal):
    key = resource_key(goal)
    for other in store.goals():
        if other["id"] == goal["id"] or other.get("goal_status") != "active":
            continue
        if resource_key(other) != key:
            continue
        try:
            status = store.cycle(other["id"])["run_status"]
        except KeyError:
            continue
        if status in BUSY_RUN_STATUSES:
            return other
    return None


def _result(eligible: bool, reason: str, extra: dict | None = None) -> dict[str, Any]:
    payload = {"eligible": eligible, "reason": reason}
    if extra:
        payload.update(extra)
    return payload
