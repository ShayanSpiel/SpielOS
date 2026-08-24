"""P2.5C: one System Improvement Goal may retry inside the same approved scope."""

from __future__ import annotations

from typing import Any

from .truth import _field

DEFAULT_MAX_REPAIR_ATTEMPTS = 8
TECHNICAL_OWNER = "system-improvement"


def scope_fingerprint(source) -> tuple:
    config = source if isinstance(source, dict) else {}
    if "allowed_files" not in config and "config" in config:
        config = config.get("config") or {}
    files = tuple(sorted(str(item) for item in (config.get("allowed_files") or ())))
    return (
        str(config.get("owner_id") or ""),
        str(config.get("from_version") or ""),
        str(config.get("target_version") or ""),
        str(config.get("problem") or ""),
        str(config.get("change_kind") or "repair"),
        files,
    )


def same_scope(goal_config: dict | None, task: dict | None) -> bool:
    if not goal_config or not task:
        return False
    return scope_fingerprint(goal_config) == scope_fingerprint(task)


def declared_attempt_limit(goal) -> int:
    config = _field(goal, "config") or {}
    for key in ("max_attempts", "attempt_limit", "max_runs"):
        value = config.get(key)
        if value is None:
            continue
        try:
            return max(1, int(value))
        except (TypeError, ValueError):
            continue
    return DEFAULT_MAX_REPAIR_ATTEMPTS


def iteration_decision(*, goal, cycle, evaluation, tasks_for_goal,
                       last_task) -> dict[str, Any]:
    """Whether a failed repair may open a fresh attempt on the same Goal."""

    if _field(goal, "owner_id") != TECHNICAL_OWNER:
        return _result(False, "not_system_improvement")
    if _field(goal, "goal_status") != "active":
        return _result(False, "goal_not_active")
    if _field(cycle, "run_status") not in {"blocked", "failed"}:
        return _result(False, "run_not_retryable")
    if not last_task or last_task.get("status") != "failed":
        return _result(False, "no_failed_task")
    if not evaluation or _field(evaluation, "goal_met"):
        return _result(False, "no_failed_evaluation")
    if _field(evaluation, "validity") == "business":
        return _result(False, "business_evaluation")
    attempts = len(tasks_for_goal or ())
    if attempts >= declared_attempt_limit(goal):
        return _result(False, "attempt_limit_reached")
    carry = same_scope(_field(goal, "config") or {}, last_task)
    return _result(True, "eligible", extra={"carry_scope_approval": carry,
                                            "previous_task_id": last_task.get("id")})


def _result(eligible: bool, reason: str, extra: dict | None = None) -> dict[str, Any]:
    payload = {"eligible": eligible, "reason": reason}
    if extra:
        payload.update(extra)
    return payload
