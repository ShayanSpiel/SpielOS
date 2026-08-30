"""Typed resolution for semantically extracted owner-memory candidates.

The host model interprets meaning and emits one structured candidate.  This
module never classifies prose: it validates that candidate and deterministically
routes it to temporary state, Company Profile, Directive, Workflow Memory,
Experiment Memory, or a canonical Workflow repair.
"""

from __future__ import annotations

from typing import Any, Callable


INTENTS = {
    "temporary_instruction", "profile_update", "directive",
    "workflow_instruction", "workflow_correction", "experiment_learning",
}
SCOPES = {"task", "run", "workflow", "goal", "company"}


def candidate_contract() -> dict[str, Any]:
    """Schema hints injected on user turns for host-side semantic extraction."""

    return {
        "intents": sorted(INTENTS),
        "required": ["intent", "scope", "confidence", "ambiguous", "payload"],
        "correction_diagnosis": [
            "corrected_behavior", "cause", "canonical_repair"],
        "workflow_identity": [
            "workflow_id", "behavior_key", "scope", "trigger"],
        "command": "company memory apply-candidate --candidate JSON",
    }


def apply_candidate(store, candidate: dict[str, Any], *,
                    canonical_repair: Callable[[dict[str, Any]], Any] | None = None) -> dict:
    """Validate and resolve one model-extracted candidate.

    Ambiguous criticism is audited but never promoted.  Explicit owner
    correction is authoritative immediately.  A diagnosed canonical Workflow
    defect routes to source repair and never creates contradictory memory.
    """

    if not isinstance(candidate, dict):
        raise ValueError("memory candidate must be a JSON object")
    intent = str(candidate.get("intent") or "").strip()
    scope = str(candidate.get("scope") or "").strip()
    payload = candidate.get("payload")
    if intent not in INTENTS:
        raise ValueError(f"unknown memory intent: {intent or '<empty>'}")
    if scope not in SCOPES:
        raise ValueError(f"unknown memory scope: {scope or '<empty>'}")
    if not isinstance(payload, dict):
        raise ValueError("memory candidate payload must be an object")
    try:
        confidence = float(candidate.get("confidence"))
    except (TypeError, ValueError) as exc:
        raise ValueError("memory candidate confidence must be numeric") from exc
    if not 0 <= confidence <= 1:
        raise ValueError("memory candidate confidence must be between 0 and 1")

    source = candidate.get("source") if isinstance(candidate.get("source"), dict) else {}
    source_ref = str(source.get("ref") or "").strip() or None
    source_excerpt = str(source.get("excerpt") or "").strip()
    explicit = candidate.get("explicit") is True

    def finish(status: str, result: dict) -> dict:
        audit = store.record_memory_candidate(
            candidate=candidate, status=status, result=result, source_ref=source_ref)
        return {**result, "candidate_id": audit["id"], "candidate_status": status}

    if candidate.get("ambiguous") is True or confidence < 0.65:
        return finish("rejected", {
            "route": "none", "persisted": False,
            "reason": "ambiguous_or_low_confidence",
        })

    if intent == "temporary_instruction" or scope in {"task", "run"}:
        return finish("temporary", {
            "route": "temporary", "persisted": False, "scope": scope,
        })

    if intent == "profile_update":
        required = ("namespace", "key", "value")
        if any(key not in payload for key in required):
            raise ValueError("profile_update requires namespace, key, and value")
        claim = store.set_profile_claim(
            namespace=str(payload["namespace"]), claim_key=str(payload["key"]),
            value=payload["value"], scope=scope,
            goal_id=payload.get("goal_id"), workflow_id=payload.get("workflow_id"),
            authority="owner_explicit" if explicit else "owner_interpreted",
            source_ref=source_ref, source_excerpt=source_excerpt,
            confidence=confidence)
        return finish("applied", {
            "route": "profile", "persisted": True, "record": claim})

    if intent == "directive":
        text = str(payload.get("text") or "").strip()
        if not text:
            raise ValueError("directive requires payload.text")
        directive_scope = "goal" if scope == "goal" else "company"
        directive = store.record_directive(
            text, scope=directive_scope, goal_id=payload.get("goal_id"))
        return finish("applied", {
            "route": "directive", "persisted": True, "record": directive})

    if intent == "experiment_learning":
        evidence_ids = payload.get("evidence_ids")
        if not isinstance(evidence_ids, list) or not evidence_ids:
            raise ValueError("experiment_learning requires evidence_ids")
        required = ("owner_id", "goal_id", "run_id", "claim")
        if any(not str(payload.get(key) or "").strip() for key in required):
            raise ValueError(
                "experiment_learning requires owner_id, goal_id, run_id, and claim")
        memory = store.record_experiment_memory(
            owner_id=str(payload.get("owner_id") or ""),
            goal_id=str(payload.get("goal_id") or ""),
            run_id=str(payload.get("run_id") or ""),
            claim=str(payload.get("claim") or ""),
            verdict=str(payload.get("verdict") or "observed"),
            context=dict(payload.get("context") or {}),
            evidence_ids=[str(item) for item in evidence_ids],
            confidence=confidence)
        return finish("applied", {
            "route": "experiment_memory", "persisted": True, "record": memory})

    diagnosis = (candidate.get("diagnosis")
                 if isinstance(candidate.get("diagnosis"), dict) else {})
    if intent == "workflow_correction":
        if not explicit or not str(diagnosis.get("corrected_behavior") or "").strip():
            return finish("rejected", {
                "route": "none", "persisted": False,
                "reason": "workflow_correction_requires_explicit_owner_diagnosis",
            })
        if diagnosis.get("cause") == "canonical_workflow_defect":
            repair = diagnosis.get("canonical_repair")
            if not isinstance(repair, dict) or not repair:
                raise ValueError("canonical Workflow defect requires canonical_repair")
            outcome = canonical_repair(repair) if canonical_repair else None
            return finish("routed", {
                "route": "canonical_workflow_repair",
                "persisted": False,
                "repair_status": "applied" if canonical_repair else "required",
                "repair": repair,
                "repair_result": outcome,
                "provenance": {"source_ref": source_ref,
                               "source_excerpt": source_excerpt,
                               "corrected_behavior": diagnosis["corrected_behavior"]},
            })

    instructions = payload.get("instructions")
    trigger = payload.get("trigger") or {}
    dependencies = payload.get("dependencies") or []
    if (not payload.get("workflow_id") or not payload.get("behavior_key")
            or not isinstance(instructions, list) or not instructions
            or not isinstance(trigger, dict) or not isinstance(dependencies, list)):
        raise ValueError(
            "Workflow memory requires workflow_id, behavior_key, instructions, "
            "object trigger, and array dependencies")
    memory = store.observe_workflow_memory(
        workflow_id=str(payload["workflow_id"]),
        behavior_key=str(payload["behavior_key"]),
        title=str(payload.get("title") or payload["behavior_key"]),
        instructions=[str(item) for item in instructions], trigger=trigger,
        dependencies=[str(item) for item in dependencies],
        workgroup_id=payload.get("workgroup_id"), source_ref=source_ref,
        scope="company" if scope == "company" else "workflow",
        authority="owner_explicit" if explicit else "observed",
        explicit_update=(intent == "workflow_correction"),
    )
    return finish("applied", {
        "route": "workflow_memory", "persisted": True, "record": memory})
