"""Delivery and payload assembly of persisted company notifications.

Notifications are durable rows in the SQLite store, accumulated by the runtime
while goals advance. Delivery marks a pending notification as delivered via
``store.acknowledge_notification`` so it stops piling up unseen while the
runner daemon is on. The daemon's watch loop (the CLI ``runner watch``
command spawned by ``RunnerService.start``) calls ``deliver_pending`` after
every tick.

Delivery only records that the notification was surfaced — it never changes
the goal's run state. An ``approval_required`` notification is *seen*, not
approved; ``company approve`` remains the only gate for the prepared action.

Besides delivery, this module assembles the payloads for the two chat-visible
supervision surfaces (goal-chat-visible-supervision-20260815):

* ``digest_payload`` — the company-wide progress digest (kind
  ``watchdog_digest``) emitted by the runner's watch loop at most once per
  ``DIGEST_INTERVAL_SECONDS`` while any goal is active. It summarizes active
  goals with stage/step, last tick and resume_at, pending approvals, recent
  terminal outcomes, and blockers.
* ``terminal_state_payload`` / ``followup_payload`` — the terminal-state
  follow-up (kind ``goal_completed_followup``) emitted next to the existing
  ``goal_<status>`` notification. Its payload carries a
  ``recommended_next_action`` derived from the goal context
  (``recommended_next_action``), so the chat never goes silent after a goal
  completes.
"""

from __future__ import annotations


def _goal_value(goal, key, default=None):
    """Read a field from a goal dict OR the ``Goal`` dataclass."""
    if isinstance(goal, dict):
        return goal.get(key, default)
    return getattr(goal, key, default)


def recommended_next_action(goal, goal_status: str) -> str:
    """Concrete next step for a terminal goal, derived from its context.

    Owner-specific, so the follow-up is actionable rather than generic:
    system-improvement goals need the approved change deployed/verified;
    outbound campaign goals need a resume/continue or Director-escalation
    decision; every other owner falls back to a review-and-decide
    recommendation. Always non-empty.
    """
    owner_id = _goal_value(goal, "owner_id", "")
    config = _goal_value(goal, "config") or {}
    if owner_id == "system-improvement":
        return ("Deploy or verify the approved change: review the acceptance "
                "evidence and complete the change task (`company change complete`), "
                "or open a follow-up system-improvement goal.")
    if owner_id == "outbound":
        return ("Review the campaign outcome and decide the next step: resume or "
                "continue the campaign, or escalate the outcome to the Director.")
    if owner_id == "director":
        return ("Review the outcome and decide the next goal: resume orchestration "
                "or open a new Department goal.")
    workflow = config.get("workflow")
    if workflow:
        return (f"Review the {workflow} outcome and either continue with the next "
                "step or escalate the decision to the Director.")
    return ("Review the outcome (`company status <goal id>`) and decide the next "
            "run, or escalate the decision to the Director.")


def terminal_state_payload(*, goal, cycle: dict, goal_status: str,
                           message: str) -> dict:
    """Standalone ``goal_<status>`` payload for terminal transitions that do
    not pass through a ``StageResult`` (deadline expiry, owner abandon).

    Mirrors the shape of the richer ``_notification_payload`` (goal/run/
    runtime/result) so the plugin's chat surface treats every terminal
    notification uniformly.
    """
    return {
        "goal": {"id": _goal_value(goal, "id"),
                 "name": _goal_value(goal, "name"),
                 "metric": _goal_value(goal, "metric"),
                 "operator": _goal_value(goal, "operator"),
                 "target": _goal_value(goal, "target"),
                 "owner_id": _goal_value(goal, "owner_id")},
        "run": {"id": cycle.get("id"), "sequence": cycle.get("sequence")},
        "runtime": {"stage": cycle.get("stage"), "step": cycle.get("step"),
                    "status": "completed"},
        "result": {"message": message, "goal_met": goal_status == "achieved"},
        "required_user_action": recommended_next_action(goal, goal_status),
        "next_trigger": "company status <goal id>",
    }


def followup_payload(payload: dict, *, goal, goal_status: str) -> dict:
    """The ``goal_completed_followup`` notification payload.

    Carries the same context as the ``goal_<status>`` payload plus a
    ``followup`` block with the recommended next action derived from the goal
    context, and makes that action the notification's
    ``required_user_action`` so the plugin's chat prompt shows a concrete
    step instead of going silent on goal completion.
    """
    action = recommended_next_action(goal, goal_status)
    result = dict(payload.get("result") or {})
    message = result.get("message") or f"goal reached {goal_status}"
    return {
        **payload,
        "followup": {"goal_status": goal_status,
                     "recommended_next_action": action},
        "result": {**result, "message": f"{message} Next: {action}"},
        "required_user_action": action,
        "next_trigger": payload.get("next_trigger") or "company status <goal id>",
    }


def digest_payload(*, emitted_at: str, interval_seconds: float,
                   active_goals: list, pending_approvals: list,
                   recent_terminal: list, blockers: list,
                   message: str | None = None) -> dict:
    """The ``watchdog_digest`` payload: active goals with stage/step and
    resume_at, pending approvals, recent terminal outcomes, and blockers,
    plus a numeric summary the plugin can turn into prompt text."""
    return {
        "watchdog": {"signal": "progress_digest", "generated_at": emitted_at,
                     "interval_seconds": interval_seconds},
        "goals": active_goals,
        "pending_approvals": pending_approvals,
        "recent_terminal": recent_terminal,
        "blockers": blockers,
        "summary": {"active_goals": len(active_goals),
                    "pending_approvals": len(pending_approvals),
                    "recent_terminal": len(recent_terminal),
                    "blockers": len(blockers)},
        "result": {"message": message or (
            f"Progress digest: {len(active_goals)} active goal(s), "
            f"{len(pending_approvals)} pending approval(s), "
            f"{len(blockers)} blocker(s), "
            f"{len(recent_terminal)} recent terminal outcome(s).")},
        "required_user_action": ("Review the digest; approve parked actions, "
                                 "resume waiting goals, or escalate to the Director."),
        "next_trigger": "company status <goal id>",
    }


def deliver_pending(store, limit: int = 100) -> int:
    """Deliver up to ``limit`` pending notifications; return how many.

    Delivery is persistent: every pending row (oldest first, matching the
    store's ordering) is marked ``delivered`` with a ``delivered_at``
    timestamp through the same store call the CLI ``notifications ack``
    command uses. The digest and terminal follow-up kinds ride this path like
    every other kind, so they never pile up unseen while the daemon is on.
    """
    pending = store.notifications("pending", limit)
    for row in pending:
        store.acknowledge_notification(row["id"])
    return len(pending)