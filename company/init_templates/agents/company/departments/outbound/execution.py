"""ACT — the composite step: PREPARE -> VALIDATE -> GATE -> REVIEW -> EXECUTE.

Each sub-step is its own artifact boundary. VALIDATE and GATE are the two
machine checkpoints; REVIEW is handled by the company runtime.

Row shape (persisted in the store): {id, workflow, phase, batch (payload),
intervention, preview_path, artifact_path, report_path, created_at,
updated_at}. The workflow sees only the payload; the Department owns
the row.
"""

import socket
import urllib.error
from datetime import datetime, timezone

from .models import Phase
from ...runtime.errors import (
    DNSError,
    RateLimitError,
    TimeoutError as TransientTimeout,
    UpstreamError,
)


def _classify_transport_failure(exc: Exception) -> None:
    """Re-raise a provider transport exception as its transient taxonomy class.

    Maps the failure vocabulary the email providers can surface onto
    ``company.runtime.errors``: HTTP 429 -> RateLimitError, HTTP 5xx ->
    UpstreamError, DNS resolution failures -> DNSError, request timeouts ->
    TimeoutError, connection-level failures (refused/reset/unreachable) ->
    UpstreamError. Everything else is re-raised unchanged so non-transient
    bugs keep today's behavior. Always raises; never returns.
    """
    if isinstance(exc, urllib.error.HTTPError):
        if exc.code == 429:
            retry_after = None
            raw = exc.headers.get("Retry-After") if exc.headers else None
            if raw is not None:
                try:
                    retry_after = float(str(raw).strip())
                except ValueError:
                    retry_after = None
            raise RateLimitError(str(exc), retry_after=retry_after) from exc
        if 500 <= exc.code < 600:
            raise UpstreamError(str(exc)) from exc
        raise exc
    if isinstance(exc, (socket.gaierror, socket.herror)):
        raise DNSError(str(exc)) from exc
    if isinstance(exc, (socket.timeout, TimeoutError)):
        raise TransientTimeout(str(exc)) from exc
    if isinstance(exc, ConnectionError):
        raise UpstreamError(str(exc)) from exc
    raise exc


def _guarded(call):
    """Run one provider-touching workflow step through the taxonomy."""
    try:
        return call()
    except Exception as exc:  # noqa: BLE001 - classified, then re-raised
        _classify_transport_failure(exc)


def prepare(ctx, intervention: dict) -> dict:
    payload = ctx.workflow.prepare(ctx, intervention)
    payload.setdefault("id", intervention.get("batch_id", "unset"))
    now = datetime.now(timezone.utc).isoformat()
    row = {
        "id": payload["id"],
        "workflow": ctx.workflow.name,
        "phase": Phase.PREPARE.value,
        "batch": payload,
        "intervention": intervention,
        "preview_path": ctx.artifacts.write_preview(payload, ctx.workflow.name),
        "artifact_path": ctx.artifacts.save_batch(payload),
        "created_at": now,
        "updated_at": now,
    }
    ctx.store.upsert_batch(row)
    ctx.store.set_current_batch(row["id"])
    ctx.artifacts.log(
        f"prepare: {row['id']} → {len(payload.get('emails', []))} emails, "
        f"{len(payload.get('skipped', []))} skipped")
    return row


def validate(ctx, row: dict) -> list:
    payload = row["batch"]
    issues = ctx.workflow.validate(ctx, payload)
    if issues:
        bad = {i["lead_id"] for i in issues}
        payload["emails"] = [e for e in payload.get("emails", [])
                             if e.get("lead_id") not in bad]
        payload["skipped"] = (payload.get("skipped") or []) + [
            {"lead_id": i["lead_id"], "reason": f"validation {i['code']}: {i['message']}"}
            for i in issues]
        row["updated_at"] = datetime.now(timezone.utc).isoformat()
        row["artifact_path"] = ctx.artifacts.save_batch(payload)
        ctx.store.upsert_batch(row)
    ctx.artifacts.log(f"validate: {len(issues)} issue(s) → {len(payload.get('emails', []))} emails kept")
    return issues


def gate(ctx) -> dict:
    fresh = _guarded(lambda: ctx.workflow.observe(ctx, quick=True))
    result = ctx.policy.check(ctx, fresh)
    result["guardrails"] = [g.get("name") for g in
                            (fresh.get("meta") or {}).get("guardrails", [])]
    ctx.artifacts.log(
        f"gate: ok={result.get('ok')} breaches={[b.get('name') for b in result.get('breaches', [])]} "
        f"problems={len(result.get('problems', []))}")
    return result


def execute(ctx, row: dict, dry: bool = False) -> dict:
    result = _guarded(lambda: ctx.workflow.execute(ctx, row["batch"], dry=dry))
    ctx.store.update_batch_metrics(row["id"], result)
    ctx.artifacts.log(
        f"execute{' (dry)' if dry else ''}: {row['id']} → sent {result.get('sent', 0)}, "
        f"failed {result.get('failed', 0)}, deduped {result.get('deduped', 0)} · {result.get('note', '')}")
    return result
