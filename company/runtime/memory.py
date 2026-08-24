"""Eligibility and bounded use rules for durable Memory claims."""

from __future__ import annotations

from .truth import countable_evidence


def eligible_memory(learning: dict, evidence: list[dict], goal, run) -> dict | None:
    """Normalize a reusable, decision-relevant claim or reject it.

    Events and evaluations remain their own records. Memory requires exact
    valid Evidence from the current Run and an explicit future applicability.
    """

    if not isinstance(learning, dict):
        return None
    claim = str(learning.get("claim") or "").strip()
    relevance = str(learning.get("decision_relevance") or "").strip()
    applies_to = learning.get("applies_to") or {}
    raw_ids = learning.get("evidence_ids") or ()
    if (learning.get("reusable") is not True or not claim or not relevance
            or not isinstance(raw_ids, (list, tuple))
            or not isinstance(applies_to, dict)):
        return None
    requested = list(dict.fromkeys(
        item for item in raw_ids if isinstance(item, str) and item))
    metrics_raw = applies_to.get("metrics") or ()
    workflows_raw = applies_to.get("workflows") or ()
    if not isinstance(metrics_raw, (list, tuple)) or not isinstance(workflows_raw, (list, tuple)):
        return None
    metrics = [str(item) for item in metrics_raw if item]
    workflows = [str(item) for item in workflows_raw if item]
    if not metrics and not workflows:
        return None
    share_scope = learning.get("share_scope") or "department"
    audience_raw = learning.get("audience_departments") or ()
    topics_raw = learning.get("topics") or ()
    if (share_scope not in {"department", "company"}
            or not isinstance(audience_raw, (list, tuple))
            or not isinstance(topics_raw, (list, tuple))):
        return None
    audience = list(dict.fromkeys(
        str(item) for item in audience_raw if isinstance(item, str) and item))
    topics = list(dict.fromkeys(
        str(item) for item in topics_raw if isinstance(item, str) and item))
    if share_scope == "company" and (not audience or not topics):
        return None
    allowed = {item["id"] for item in countable_evidence(evidence, goal, run)}
    if any(item not in allowed for item in requested):
        return None
    try:
        confidence = float(learning.get("confidence", 0.5))
    except (TypeError, ValueError):
        return None
    if not 0.0 <= confidence <= 1.0:
        return None
    return {
        "claim": claim,
        "confidence": confidence,
        "evidence": {
            "evidence_ids": requested,
            "decision_relevance": relevance,
            "applies_to": {"metrics": metrics, "workflows": workflows},
            "share_scope": share_scope,
            "audience_departments": audience if share_scope == "company" else [],
            "topics": topics if share_scope == "company" else [],
            "support": (dict(learning.get("evidence") or {})
                        if isinstance(learning.get("evidence") or {}, dict) else {}),
        },
    }


def relevant_memory(memory: list[dict] | tuple[dict, ...], *,
                    metric: str, workflow_id: str | None) -> dict | None:
    """Select one newest claim explicitly applicable to this decision."""

    for item in memory or ():
        if item.get("id") is None:
            continue
        evidence = item.get("evidence") or {}
        applies_to = evidence.get("applies_to") or {}
        metrics = set(applies_to.get("metrics") or ())
        workflows = set(applies_to.get("workflows") or ())
        if metrics and metric not in metrics:
            continue
        if workflows and workflow_id not in workflows:
            continue
        if metrics or workflows:
            return item
    return None


def apply_memory(decision: dict, memory: dict | None) -> dict:
    """Make Memory use explicit in rationale and decision payload."""

    if not memory:
        return decision
    value = dict(decision)
    payload = dict(value.get("payload") or {})
    payload["memory_ids"] = [memory["id"]]
    value["payload"] = payload
    value["rationale"] = (
        f"{value.get('rationale') or 'Selected intervention'}; "
        f"Memory {memory['id']}: {memory['claim']}")
    return value
