"""Eligibility and bounded use rules for durable Memory claims."""

from __future__ import annotations

import re

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
    dimensions = ("metrics", "workflows", "steps", "icps", "offers", "channels",
                  "artifacts", "workgroups")
    raw_dimensions = {key: applies_to.get(key) or () for key in dimensions}
    if any(not isinstance(value, (list, tuple)) for value in raw_dimensions.values()):
        return None
    context = {key: [str(item) for item in value if item]
               for key, value in raw_dimensions.items()}
    if not any(context.values()):
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
            "applies_to": context,
            "share_scope": share_scope,
            "audience_departments": audience if share_scope == "company" else [],
            "topics": topics if share_scope == "company" else [],
            "support": (dict(learning.get("evidence") or {})
                        if isinstance(learning.get("evidence") or {}, dict) else {}),
        },
        "verdict": str(learning.get("verdict") or "observed"),
        "context": context,
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


def _terms(value: str | None) -> set[str]:
    return {item for item in re.findall(r"[a-z0-9][a-z0-9_-]+", (value or "").lower())
            if len(item) > 2}


def rank_experiment_memories(memory, *, prompt: str = "", owner_id: str | None = None,
                             workflow_id: str | None = None, step_id: str | None = None,
                             metric: str | None = None, limit: int = 3) -> list[dict]:
    """Return a tiny deterministic projection of relevant learned evidence.

    Typed exact matches dominate lexical fallback.  This intentionally avoids
    embeddings until a measured retrieval gap justifies them.
    """

    query = _terms(prompt)
    ranked = []
    for item in memory or ():
        if item.get("status", "active") != "active":
            continue
        if owner_id and item.get("owner_id") not in {None, owner_id}:
            continue
        context = item.get("context") or ((item.get("evidence") or {}).get("applies_to") or {})
        score = 0.0
        if workflow_id and workflow_id in set(context.get("workflows") or ()):
            score += 40
        if step_id and step_id in set(context.get("steps") or ()):
            score += 20
        if metric and metric in set(context.get("metrics") or ()):
            score += 12
        text = " ".join([str(item.get("claim") or ""),
                         " ".join(str(value) for values in context.values()
                                  for value in (values if isinstance(values, list) else [values]))])
        score += min(20, len(query.intersection(_terms(text))) * 4)
        score += float(item.get("confidence") or 0) * 10
        score += min(8, int(item.get("confirmations") or 0) * 2)
        score -= min(20, int(item.get("contradictions") or 0) * 6)
        if score > 0:
            ranked.append((score, item))
    ranked.sort(key=lambda pair: (pair[0], pair[1].get("updated_at") or
                                  pair[1].get("created_at") or ""), reverse=True)
    return [item for _, item in ranked[:max(0, min(int(limit), 5))]]


def rank_workflow_memories(memory, *, prompt: str = "", workflow_id: str | None = None,
                           limit: int = 2) -> list[dict]:
    query = _terms(prompt)
    ranked = []
    for item in memory or ():
        if item.get("status") not in {"candidate", "hardening", "promoted"}:
            continue
        score = 30 if workflow_id and item.get("workflow_id") == workflow_id else 0
        text = " ".join((str(item.get("title") or ""), str(item.get("workflow_id") or ""),
                         " ".join(str(value) for value in (item.get("instructions") or ()))))
        score += min(30, len(query.intersection(_terms(text))) * 5)
        score += min(10, int(item.get("occurrence_count") or 0) * 3)
        if item.get("status") == "hardening":
            score += 5
        if score > 0:
            ranked.append((score, item))
    ranked.sort(key=lambda pair: (pair[0], pair[1].get("updated_at") or ""), reverse=True)
    return [item for _, item in ranked[:max(0, min(int(limit), 3))]]
