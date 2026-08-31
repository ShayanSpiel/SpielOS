#!/usr/bin/env python3
"""Outbound email ACT helper: PREPARE builds the batch, EXECUTE sends it.

PREPARE applies the intervention's levers (cohort filters, subject rotation),
composes per-lead emails in STRICT mode (unprepared leads are skipped), and
dedupes domains within the batch. Batches fill to the block-size floor by
walking the whole queue with a limit (owner order 2026-08-11) — the daily cap
still bounds the fill. Every prepare persists a unique registered batch id
that claims its lead set until execution (idempotency repair 2026-08-15:
never the shared "unset" fallback, and concurrent prepares get disjoint
sets). EXECUTE dispatches to background for non-blocking sends: daily cap
honored, sent-log + provider dedupe, transient retries with backoff, quota
errors switch providers, every send is recorded in the sent log, the action
ledger, and the durable per-lead submission registry (in_flight before the
first attempt; resolved to accepted/failed/submitted_unknown; a 12h cooldown
blocks re-submission by any execution or generation).
"""

import threading
import time
import uuid
from datetime import datetime, timezone

from . import compose, config, content as content_bank, outbound, providers, validators
from .templates import SIGNATURE_HTML, SIGNATURE_TEXT

FAILED_RETRY_SECONDS = 300  # grace before a failed background dispatch retries

# Idempotency repair (goal-email-send-idempotency-20260815): the durable
# per-lead submission registry keeps an in_flight marker from the moment a
# provider attempt starts until its outcome is recorded. A lead whose entry
# is in_flight/accepted/submitted_unknown inside this window is never
# submitted again by any execution, generation, or Goal.
SUBMISSION_COOLDOWN_SECONDS = 12 * 3600  # 12 hours
STATUS_IN_FLIGHT = "in_flight"
STATUS_ACCEPTED = "accepted"
STATUS_FAILED = "failed"
STATUS_SUBMITTED_UNKNOWN = "submitted_unknown"

# Provider-side accepts with no local success (hung transport capped by
# _send_with_cap) resolve to submitted_unknown — the provider may hold a
# submission the ledger cannot see, so a local "failed" record must never
# cause an immediate re-submission.
HUNG_CAP_PREFIX = "send exceeded"


def prepare(ctx, intervention: dict) -> dict:
    knobs = ctx.control.knobs()
    filters = dict(knobs.get("cohort_filters") or {})
    levers = intervention.get("levers") or {}
    if "cohort_filters" in levers:
        filters.update(levers["cohort_filters"])

    if levers.get("rotate_subjects"):
        for seg in (levers.get("subject_rotation") or {}):
            content_bank.rotate_bank(seg, note="act: subject lever applied")

    cap, phase = outbound.daily_cap()
    knob_cap = knobs.get("daily_cap")
    if knob_cap:
        cap = min(cap, int(knob_cap))
    used_today = outbound.sent_today(outbound.load_sent_log())
    slice_size = min(knobs.get("block_size") or config.BLOCK_SIZE,
                     max(0, cap - used_today))

    store = getattr(ctx, "store", None)
    requested_id = intervention.get("batch_id")
    owner = _goal_id(ctx) or ""
    hypothesis = intervention.get("prediction") or "research-first: per-lead hook + pain hypothesis"

    if store is None:
        # Legacy callers (unit tests) without a store keep the historical
        # behavior: no registration, id from the intervention or "unset".
        queue = compose.pick_queue(filters)
        batch_id = requested_id or "unset"
    else:
        # Idempotency repair: every prepare persists a unique registered
        # batch id (never the shared "unset" fallback that let goals b4–b7
        # dispatch the same leads under one identity).
        if requested_id and store.batch_registered(requested_id):
            raise ValueError(
                f"batch_id {requested_id!r} is already registered — a batch "
                "id belongs to exactly one prepared batch")
        if slice_size <= 0:
            # Daily cap reached: still allocate a unique id so the persisted
            # row is never "unset"; the empty batch claims no leads.
            batch_id = requested_id or f"send-{uuid.uuid4().hex[:12]}"
            store.register_batch(batch_id, owner=owner, lead_ids=[])
            queue = compose.pick_queue(filters)
        else:
            # Claim a disjoint lead set: re-pick with the freshly reserved
            # ids and retry on a reservation race (up to 10 re-picks). Claims
            # are the leads the batch actually composed, so a concurrent
            # prepare walks past them and composes the remainder. An
            # explicitly requested id is never retried — any ValueError
            # (already registered, or overlapping another pending batch) is
            # a hard rejection.
            for _ in range(10):
                reserved = store.reserved_lead_ids()
                queue = compose.pick_queue(filters, reserved_lead_ids=reserved)
                candidate = requested_id or f"send-{uuid.uuid4().hex[:12]}"
                built = compose.build_batch_emails(candidate, queue,
                                                   hypothesis, limit=slice_size)
                try:
                    store.register_batch(
                        candidate, owner=owner,
                        lead_ids=[e["lead_id"] for e in built["emails"]])
                except ValueError:
                    if requested_id:
                        raise
                    continue
                batch_id = candidate
                break
            else:
                raise ValueError(
                    "could not allocate a disjoint batch after 10 re-picks")

    if slice_size <= 0:
        return {"id": batch_id, "emails": [],
                "skipped": [], "emails_count": 0, "queue_size": len(queue),
                "limit": slice_size, "queue_exhausted": True,
                "reason": "daily cap reached"}

    if store is None:
        # Batch floor (owner order 2026-08-11): walk the WHOLE queue with
        # limit=slice_size so skips inside the first block (unprepared leads,
        # same-domain duplicates) cannot shrink the batch below block_size. The
        # daily cap is still honored — slice_size is min(block_size, cap
        # remaining) and the fill never exceeds it.
        built = compose.build_batch_emails(batch_id, queue, hypothesis,
                                           limit=slice_size)
    return {"id": batch_id, "hypothesis": hypothesis,
            "emails": built["emails"], "skipped": built["skipped"],
            "emails_count": len(built["emails"]),
            "queue_size": len(queue),
            "limit": slice_size,
            "queue_exhausted": built.get("queue_exhausted", False),
            "filters": filters, "cap": {"cap": cap, "phase": phase,
                                        "used_today": used_today},
            "intervention": intervention}


def _send_with_cap(provider, to_email, subject, body_html, body_text, reply_to, cap_s=180):
    box = {}

    def _run():
        box["r"] = providers.send_email_via(provider, to_email, subject, body_html,
                                             body_text, reply_to=reply_to)

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    t.join(cap_s)
    if t.is_alive():
        return {"error": True, "status": 0,
                "message": f"send exceeded {cap_s}s cap (hung transport); not sent"}
    return box.get("r", {"error": True, "status": 0, "message": "no result"})


def _provider_sent_id(email, hours=24):
    """Provider-side dedupe guard: has this address received a send in the
    last `hours`? Returns provider id, None (clean), or "unknown" (check
    failed)."""
    try:
        r = providers._open(
            "https://api.resend.com/emails?limit=100",
            headers={"Authorization": f"Bearer {providers.RESEND_API_KEY}"},
        )
        if r.get("error"):
            return "unknown"
        cutoff = time.time() - hours * 3600
        for e in r.get("data", []):
            raw = ((e.get("created_at") or "")[:19]).replace("T", " ", 1)
            try:
                ts = time.mktime(time.strptime(raw, "%Y-%m-%d %H:%M:%S"))
            except ValueError:
                continue
            if ts < cutoff:
                continue
            tos = e.get("to") or []
            tos = tos if isinstance(tos, list) else [tos]
            if email in tos:
                return e.get("id") or "?"
        return None
    except Exception:
        return "unknown"


def _goal_id(ctx):
    """Resolve the goal identity used for dispatch bookkeeping.

    The email workflow stamps `outbound.goal_id` before execution; the
    legacy workflow path calls with the GoalContext (ctx.goal.id). Callers
    with neither keep the pre-dispatch synchronous behavior.
    """
    return (getattr(ctx, "goal_id", None)
            or getattr(getattr(ctx, "goal", None), "id", None))


def is_pending(ctx, batch_id: str) -> bool:
    """Check if there's a pending background dispatch for this batch."""
    from .....runtime.async_dispatch import is_pending as _is_pending
    goal_id = _goal_id(ctx)
    if goal_id and batch_id:
        return _is_pending(goal_id, batch_id)
    return False


def _failed_within_grace(result: dict) -> bool:
    """A failed dispatch file is retryable only after FAILED_RETRY_SECONDS
    have elapsed since it completed, so a fresh execution failure is parked
    (run WAITING, re-ticked) instead of being hot-looped. A record without a
    usable completed_at is treated as immediately retryable."""
    from .....runtime.async_dispatch import failed_age_seconds
    age = failed_age_seconds(result)
    return age is not None and age < FAILED_RETRY_SECONDS


def execute(ctx, batch: dict, dry: bool = False) -> dict:
    """Dispatch email sending to background instead of blocking the runner."""
    batch_id = batch.get("id", "UNNAMED")
    emails = batch.get("emails", [])
    if not emails:
        # Nothing to send now or on any resume — release the batch's lead
        # claims so a later prepare can re-claim them (dry runs are NOT
        # released: the real execution may still come).
        store = getattr(ctx, "store", None)
        if store is not None and batch_id:
            store.mark_batch_executed(batch_id)
        return {"sent": 0, "failed": 0, "deduped": 0, "note": "empty batch"}

    if dry:
        return {"sent": 0, "failed": 0, "deduped": 0,
                "note": f"DRY RUN — {len(emails)} emails validated, nothing sent"}

    from .....runtime.async_dispatch import check, cleanup, dispatch, is_pending as _is_pending
    goal_id = _goal_id(ctx)
    if goal_id and batch_id:
        if _is_pending(goal_id, batch_id):
            return {"dispatched": True, "batch_id": batch_id, "note": "already dispatched"}
        previous_error = None
        result = check(goal_id, batch_id)
        if result and result.get("status") == "done":
            return result.get("result", {})
        elif result and result.get("status") == "failed":
            if _failed_within_grace(result):
                # Fresh failure: keep the error evidence in the file and park
                # the run (dispatched contract -> WAITING) so the next tick
                # retries only after the grace window — never a hot loop.
                return {"dispatched": True, "batch_id": batch_id,
                        "note": "background execution failed; retrying after grace",
                        "error": result.get("error")}
            # Grace elapsed: a failed execution is retryable, not terminal.
            # Preserve the error evidence, clear the file, and fall through
            # to a fresh dispatch below.
            previous_error = result.get("error")
            cleanup(goal_id, batch_id)
        elif result and result.get("status") == "stale":
            cleanup(goal_id, batch_id)

        dispatch_result = dispatch(goal_id, batch_id, _execute_emails, ctx, batch)

        outcome = {
            "dispatched": True,
            "batch_id": batch_id,
            "note": "dispatched to background",
            "details": dispatch_result,
        }
        if previous_error:
            outcome["previous_error"] = previous_error
            outcome["note"] = "re-dispatched after previous failure"
        return outcome

    # No goal identity to reconcile against: fall back to the previous
    # synchronous behavior so legacy/direct callers keep working.
    return _execute_emails(ctx, batch)


def _execute_emails(ctx, batch: dict) -> dict:
    """The actual email sending logic, run in background thread."""
    batch_id = batch.get("id", "UNNAMED")
    store = getattr(ctx, "store", None)
    try:
        return _execute_emails_inner(ctx, store, batch_id, batch)
    finally:
        # Whatever happens — success, failure, an exception, or an
        # entirely-deduped batch — the batch has been taken and its lead
        # claims are released so later prepares can re-claim them.
        if store is not None and batch_id:
            store.mark_batch_executed(batch_id)


def _execute_emails_inner(ctx, store, batch_id: str, batch: dict) -> dict:
    emails = batch.get("emails", [])
    if not emails:
        return {"sent": 0, "failed": 0, "deduped": 0, "note": "empty batch"}

    log = outbound.load_sent_log()

    # Hard dedup process gate (goal-4357632a68): fail fast BEFORE any
    # provider send — before contacts are read, claims taken, or a single
    # email dispatches. Any batch email whose recipient (case-insensitive)
    # or lead_id is already in the sent log blocks the whole batch; an
    # already-sent lead can never be dispatched again by any path.
    resend = [e for e in emails
              if validators.sent_log_matches(e.get("email"), e.get("lead_id"), log)]
    if resend:
        raise RuntimeError(
            "resend_guard: %d already-sent lead(s) in batch %s: %s"
            % (len(resend), batch_id,
               ", ".join(str(e.get("lead_id") or "?") for e in resend)))

    contacts = outbound.read_contacts(lang_filter=None, tier_filter=None)
    by_id = {c["lead_id"]: c for c in contacts}

    cap, phase = outbound.daily_cap()
    used_today = outbound.sent_today(log)
    if used_today + len(emails) > cap:
        return {"sent": 0, "failed": 0, "deduped": 0,
                "note": f"batch would exceed daily cap ({used_today} + {len(emails)} > {cap})"}

    kept = []
    pre_deduped = 0
    for e in emails:
        c = by_id.get(e["lead_id"])
        if c is None:
            return {"sent": 0, "failed": 0, "deduped": 0,
                    "note": f"lead_id {e['lead_id']} not found in the contact list"}
        if outbound.already_sent(e["lead_id"], log):
            pre_deduped += 1
            continue
        if not e.get("subject") or not e.get("body_html") or not e.get("body_text"):
            return {"sent": 0, "failed": 0, "deduped": 0,
                    "note": f"lead_id {e['lead_id']}: subject/body_html/body_text all required"}
        kept.append(e)
    emails = kept
    if pre_deduped and not emails:
        return {"sent": 0, "failed": 0, "deduped": pre_deduped,
                "note": "entire batch already in the sent log — nothing to send"}

    sent_count = 0
    fail_count = 0
    deduped_count = pre_deduped
    excluded = set()

    for i, e in enumerate(emails):
        c = by_id[e["lead_id"]]
        feat = e.get("features", {})
        provider = providers.pick_provider(log, exclude=excluded)
        log = outbound.load_sent_log()
        if outbound.already_sent(c["lead_id"], log):
            deduped_count += 1
            continue
        pri = _provider_sent_id(c["email"])
        if pri not in (None, "unknown"):
            log.setdefault("sent", []).append({
                "lead_id": c["lead_id"], "email": c["email"], "company": c["company"],
                "contact_name": c["contact_name"], "variant": "researched-personal",
                "batch": batch_id, "subject": e["subject"],
                "provider": config.EMAIL_PROVIDER, "provider_id": str(pri),
                "resend_id": str(pri), "deduped": True,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                **{f"feat_{k}": v for k, v in feat.items()},
            })
            outbound.save_sent_log(log)
            # Provider-side truth becomes locally visible in the registry
            # too — the acceptance may predate this execution's own attempt.
            if store is not None:
                store.record_submission(
                    c["lead_id"], c["email"], provider,
                    attempted_at=datetime.now(timezone.utc).isoformat(),
                    status=STATUS_ACCEPTED, provider_id=str(pri),
                    message="provider pre-check dedupe")
            deduped_count += 1
            continue

        # Idempotency repair: claim the lead in the durable submission
        # registry BEFORE the first provider attempt. An active entry
        # (in_flight/accepted/submitted_unknown inside the cooldown) means
        # another execution or generation already holds this lead — skip it.
        if store is not None:
            claim = store.claim_or_active(
                c["lead_id"], c["email"], provider,
                cooldown_seconds=SUBMISSION_COOLDOWN_SECONDS)
            if not claim["claimed"]:
                deduped_count += 1
                continue

        body_html = e["body_html"].replace("{SIGNATURE_HTML}", SIGNATURE_HTML).replace("{SIGNATURE_TEXT}", SIGNATURE_TEXT)
        body_text = e["body_text"].replace("{SIGNATURE_HTML}", SIGNATURE_HTML).replace("{SIGNATURE_TEXT}", SIGNATURE_TEXT)

        _TRANSIENT_MARKERS = ("transport", "timeout", "timed out", "hung",
                              "temporarily", "5", "no result")
        result = None
        attempts = 0
        while True:
            # Refresh the in_flight marker on every attempt so the registry
            # mirrors the provider actually called (quota switching changes
            # provider mid-loop) and the attempted-at time stays current.
            if store is not None:
                store.record_submission(
                    c["lead_id"], c["email"], provider,
                    attempted_at=datetime.now(timezone.utc).isoformat(),
                    status=STATUS_IN_FLIGHT, attempts=None)
            result = _send_with_cap(
                provider, c["email"], e["subject"], body_html, body_text,
                reply_to=config.REPLY_TO,
            )
            if not (result.get("error") or not str(result.get("id") or "").strip()):
                break
            err_msg = str(result.get("message", ""))
            is_quota = ("daily_quota_exceeded" in err_msg or "monthly_quota_exceeded" in err_msg
                        or result.get("status") == 429)
            is_transient = result.get("status") == 0 or any(
                m in err_msg.lower() for m in _TRANSIENT_MARKERS)
            attempts += 1
            if is_quota or not is_transient or attempts >= 3:
                break
            time.sleep(10 * attempts)

        if result.get("error") or not str(result.get("id") or "").strip():
            err_msg = str(result.get("message", ""))
            if ("daily_quota_exceeded" in err_msg or "monthly_quota_exceeded" in err_msg
                    or result.get("status") == 429):
                excluded.add(provider)
            log.setdefault("failed", []).append({
                "lead_id": c["lead_id"], "email": c["email"], "company": c["company"],
                "provider": provider, "error": result.get("message", "unknown"),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })
            fail_count += 1
            ctx.store.record_action(c["lead_id"], "email", "send_email", "failed",
                                    str(result.get("message", "unknown"))[:200])
            if store is not None:
                # Definite failures stay retryable (failed entries never
                # block). A hung-cap response means the provider may have
                # accepted the submission — resolve to submitted_unknown so
                # the cooldown blocks a blind re-submission.
                if str(err_msg).startswith(HUNG_CAP_PREFIX):
                    store.record_submission(
                        c["lead_id"], c["email"], provider,
                        attempted_at=datetime.now(timezone.utc).isoformat(),
                        status=STATUS_SUBMITTED_UNKNOWN, provider_id=None,
                        message=err_msg[:200])
                else:
                    store.record_submission(
                        c["lead_id"], c["email"], provider,
                        attempted_at=datetime.now(timezone.utc).isoformat(),
                        status=STATUS_FAILED, provider_id=None,
                        message=err_msg[:200])
        else:
            for f in log.get("failed", []):
                if isinstance(f, dict) and f.get("lead_id") == c["lead_id"] and not f.get("resolved_at"):
                    f["resolved_at"] = datetime.now(timezone.utc).isoformat()
            log.setdefault("sent", []).append({
                "lead_id": c["lead_id"], "email": c["email"], "company": c["company"],
                "contact_name": c["contact_name"], "variant": "researched-personal",
                "batch": batch_id, "subject": e["subject"],
                "provider": provider, "provider_id": result.get("id"),
                "resend_id": result.get("id"),
                "timestamp": datetime.now(timezone.utc).isoformat(),
                **{f"feat_{k}": v for k, v in feat.items()},
            })
            outbound.save_sent_log(log)
            sent_count += 1
            ctx.store.record_action(c["lead_id"], "email", "send_email", "sent",
                                    f"batch {batch_id}")
            if store is not None:
                store.record_submission(
                    c["lead_id"], c["email"], provider,
                    attempted_at=datetime.now(timezone.utc).isoformat(),
                    status=STATUS_ACCEPTED, provider_id=str(result.get("id")),
                    message=None)

        if i < len(emails) - 1:
            time.sleep(config.THROTTLE_SECONDS)

    outbound.save_sent_log(log)
    return {"sent": sent_count, "failed": fail_count, "deduped": deduped_count,
            "note": f"cap {used_today + sent_count}/{cap} after this batch ({phase})"}
