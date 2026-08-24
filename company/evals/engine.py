"""Eval engine: request rendering, verdict validation, and report computation.

The engine is connector-agnostic: any JudgeConnector renders through
`render_request` and validates through `validate_verdicts`; `run_suite` is the
one entry point that produces an EvalReport from a raw verdict document.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .judge import AgentJudgeConnector, JudgeConnector
from .models import (
    PASS_KEY,
    EvalReport,
    EvalSuite,
    EvalVerdict,
    report_to_evidence,
    suite_spec,
)

DEFAULT_JUDGE = AgentJudgeConnector()


def _item_verdict_rows(verdicts_raw: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Normalize the verdict document's per-item section."""
    items = verdicts_raw.get("items")
    if items is None:
        raise ValueError("judge response needs an 'items' object keyed by item_id")
    if not isinstance(items, dict):
        raise ValueError("judge response 'items' must be an object keyed by item_id")
    return items


def render_request(suite: EvalSuite, payload: dict[str, Any]) -> dict[str, Any]:
    """Structured EvalRequest: suite + per-item payload excerpts.

    The judge sees the full item slice (brief + renditions + locked creative)
    so verdicts are grounded in the item's own brief, not just the copy.
    """
    items = [
        {"item_id": item_id, "payload": item_slice}
        for item_id, item_slice in suite.select_items(payload)
    ]
    return {
        "suite": suite_spec(suite),
        "payload_id": suite.payload_id(payload),
        "payload_kind": suite.payload_kind,
        "judge_instructions": (
            "Judge every criterion for every item. Verdicts: {\"items\": {"
            "\"<item_id>\": {\"<criterion_id>\": {\"pass\": true|false, "
            "\"score\": 0..1, \"reason\": \"...\", \"evidence_refs\": [\"...\"]}}}}. "
            "pass=false with a reason is a failed criterion."
        ),
        "items": items,
    }


def validate_verdicts(suite: EvalSuite, payload: dict[str, Any],
                      verdicts_raw: dict[str, Any]) -> list[str]:
    """Shape validation for a raw verdict document (empty list = valid)."""
    errors: list[str] = []
    if not isinstance(verdicts_raw, dict):
        return ["judge response must be a JSON object"]
    items_raw = verdicts_raw.get("items")
    if not isinstance(items_raw, dict):
        return ["judge response needs an 'items' object keyed by item_id"]
    expected_items = [item_id for item_id, _ in suite.select_items(payload)]
    expected_ids = set(expected_items)
    for item_id in items_raw:
        if item_id not in expected_ids:
            errors.append(f"verdicts include unknown item '{item_id}'")
    criteria = {criterion.id for criterion in suite.criteria}
    for item_id in expected_items:
        entry = items_raw.get(item_id)
        if not isinstance(entry, dict):
            errors.append(f"item '{item_id}' needs a verdict object keyed by criterion_id")
            continue
        for criterion_id in criteria:
            verdict = entry.get(criterion_id)
            if not isinstance(verdict, dict):
                errors.append(f"item '{item_id}' is missing criterion '{criterion_id}'")
                continue
            passed = verdict.get(PASS_KEY)
            if not isinstance(passed, bool):
                errors.append(f"item '{item_id}' criterion '{criterion_id}' needs pass: true|false")
                continue
            score = verdict.get("score")
            if not isinstance(score, (int, float)) or not 0.0 <= float(score) <= 1.0:
                errors.append(f"item '{item_id}' criterion '{criterion_id}' needs score 0..1")
            if not isinstance(verdict.get("reason"), str) or not verdict.get("reason").strip():
                errors.append(f"item '{item_id}' criterion '{criterion_id}' needs a reason")
            refs = verdict.get("evidence_refs")
            if refs is not None and not isinstance(refs, list):
                errors.append(f"item '{item_id}' criterion '{criterion_id}' evidence_refs must be a list")
        for criterion_id in entry:
            if criterion_id not in criteria:
                errors.append(f"item '{item_id}' has unknown criterion '{criterion_id}'")
    return errors


def _item_passes(verdicts: tuple[EvalVerdict, ...], suite: EvalSuite) -> bool:
    """Threshold semantics: block criteria gate; warn criteria are advisory.

    When thresholds['all_pass'] is true, warn criteria also gate — that is the
    strict contract used by content-copy-top10 (all 10 criteria must pass).
    """
    thresholds = suite.thresholds or {}
    all_pass = bool(thresholds.get("all_pass", False))
    min_score = float(thresholds.get("min_score", 0.0))
    severity_by_id = {criterion.id: criterion.severity for criterion in suite.criteria}
    for verdict in verdicts:
        if severity_by_id.get(verdict.criterion_id) == "warn" and not all_pass:
            continue
        if not verdict.passed or verdict.score < min_score:
            return False
    return True


def compute_report(suite: EvalSuite, payload: dict[str, Any],
                   verdicts_raw: dict[str, Any],
                   judge_connector: str = DEFAULT_JUDGE.id,
                   validity: str | None = None,
                   generated_at: str | None = None) -> EvalReport:
    """Validate a raw verdict document and compute the EvalReport."""
    errors = validate_verdicts(suite, payload, verdicts_raw)
    if errors:
        raise ValueError("invalid judge response: " + "; ".join(errors))
    raw_items = _item_verdict_rows(verdicts_raw)
    criteria_by_id = {criterion.id: criterion for criterion in suite.criteria}
    expected_items = [item_id for item_id, _ in suite.select_items(payload)]
    per_item: dict[str, tuple[EvalVerdict, ...]] = {}
    per_item_pass: dict[str, bool] = {}
    for item_id in expected_items:
        entry = raw_items[item_id]
        verdicts = tuple(
            EvalVerdict(
                criterion_id=criterion_id,
                passed=bool(entry[criterion_id][PASS_KEY]),
                score=float(entry[criterion_id].get("score", 1.0)),
                reason=str(entry[criterion_id].get("reason") or "").strip(),
                evidence_refs=tuple(entry[criterion_id].get("evidence_refs") or ()),
            )
            for criterion_id, criterion in sorted(criteria_by_id.items())
        )
        per_item[item_id] = verdicts
        per_item_pass[item_id] = _item_passes(verdicts, suite)
    overall = all(per_item_pass.values())
    return EvalReport(
        suite_id=suite.id,
        payload_id=suite.payload_id(payload),
        payload_kind=suite.payload_kind,
        per_item=per_item,
        per_item_pass=per_item_pass,
        overall=overall,
        thresholds=dict(suite.thresholds or {}),
        generated_at=generated_at or datetime.now(timezone.utc).isoformat(),
        judge_connector=judge_connector,
        validity=validity or suite.validity,
    )


def run_suite(suite: EvalSuite, payload: dict[str, Any],
              verdicts_raw: dict[str, Any],
              judge: JudgeConnector | None = None,
              validity: str | None = None,
              generated_at: str | None = None) -> EvalReport:
    """The one engine entry point: render → validate → compute.

    `judge` is a JudgeConnector instance (default: honest AgentJudgeConnector).
    """
    connector = judge or DEFAULT_JUDGE
    errors = connector.validate(suite, payload, verdicts_raw)
    if errors:
        raise ValueError("invalid judge response: " + "; ".join(errors))
    report = compute_report(
        suite, payload, verdicts_raw,
        judge_connector=connector.id, validity=validity, generated_at=generated_at)
    return report


__all__ = [
    "compute_report", "render_request", "run_suite", "validate_verdicts",
    "report_to_evidence", "suite_spec",
]
