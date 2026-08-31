#!/usr/bin/env python3
"""
Outbound Department — email analytics.

Pulls delivery/engagement status for every sent email from the provider and
stores per-email snapshots in metrics.json, then computes aggregates:
send rate, deliverability (delivered / bounced / complained=spam),
open rate, click rate, reply rate.

Reply detection is two-channel:
  1. Automatic — replies routed to a Resend receiving domain (set REPLY_TO
     to e.g. replies@in.spielos.xyz) or the unified Gmail IMAP capture
     (REPLY_CAPTURE=gmail_imap) are pulled on every scheduled `metrics` run
     and matched to the sent lead. Classification uses reliable signals —
     the 'Automatic reply:' OOO prefix, the Auto-Submitted header, an
     X-Autoreply header, and config.AUTO_REPLY_KEYWORDS; ordinary 'Re:'
     subjects default to reply. Classification inputs (subject, from,
     Auto-Submitted / X-Autoreply) are stored on every record so kinds can
     be re-examined: `replies --recheck [--dry-run]` re-runs classification,
     dedupes per lead (keep newest, merge metadata), and persists
     idempotently. Auto-replies are recorded as kind="auto" and excluded
     from the reply-rate goal.
  2. Manual — anything that lands in the normal inbox:
     `python3 outbound.py record-reply <email|lead_id>`.

Provider honesty:
  - last_event covers: sent, delivered, delivery_delayed, opened, clicked,
    complained (recipient marked it as spam), bounced, failed, suppressed.
  - Inbox folder placement (Gmail Primary/Promotions/Spam) is NOT exposed by
    any sending API. `complained` + `bounced` are the closest signals; true
    placement checks need Google Postmaster or a seed list.

Usage (via outbound.py):
  python3 outbound.py metrics [--force] [--quiet]
"""

import json
import os
import threading
import time as _time
from datetime import datetime, timedelta, timezone

from . import config, providers


def cap_status_supported() -> bool:
    return providers.cap_status()

# Wedge hardening (2026-08-15 incident): the campaign measure path calls
# collect() from the serial watch loop. Provider calls used to be unbounded —
# a stalled HTTPS connection held the daemon's only thread forever (the
# campaign lease was acquired and never renewed) and a killed daemon left
# metrics.json torn mid-write, which then silently killed the next daemon
# generation on json.load (JSONDecodeError with no traceback). Bounds:
#   - every provider call runs on a daemon thread with a hard timeout;
#   - the whole collect pass has a deadline and stops fetching past it;
#   - metrics.json is written atomically (tmp + rename) and read defensively.
PROVIDER_CALL_TIMEOUT_SECONDS = 12.0
COLLECT_DEADLINE_SECONDS = 40.0


def _bounded_call(fn, timeout: float, *args, **kwargs):
    """Run fn on a daemon thread with a hard timeout.

    Returns (result, timed_out). A timed-out thread is abandoned (daemon
    thread — same pattern as runtime.loop._bounded_sync): the caller treats
    the call as failed and moves on, so one stalled provider endpoint can
    never wedge the serial watch loop. Exceptions from the thread propagate
    to the caller exactly as a direct call would.
    """
    result: dict = {}

    def _run():
        try:
            result["value"] = fn(*args, **kwargs)
        except Exception as exc:  # propagate to the caller
            result["error"] = exc

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()
    thread.join(timeout=timeout)
    if thread.is_alive():
        return None, True
    if "error" in result:
        raise result["error"]
    return result.get("value"), False

# last_event values that mean the email reached the recipient's mail server
_DELIVERED = {"delivered", "opened", "clicked", "complained"}
# last_event values that mean the recipient engaged
_OPENED = {"opened", "clicked"}

_AUTO_REPLY_KEYWORDS = tuple(
    k.strip().casefold()
    for k in config.AUTO_REPLY_KEYWORDS.split(",")
    if k.strip()
)


# ── Persistence ───────────────────────────────────────────────────────────────

def load_metrics() -> dict:
    if config.METRICS_PATH.exists():
        try:
            with open(config.METRICS_PATH) as f:
                return json.load(f)
        except (OSError, ValueError):
            # A torn file (killed writer) or concurrent rewrite must never
            # crash the measure path: return the empty ledger and let the
            # next collect refetch and atomically rewrite it. Self-healing,
            # never a lie — aggregate treats missing records as unknown.
            return {"last_check": None, "emails": {}, "replies": [],
                    "collapsed_received_ids": []}
    return {"last_check": None, "emails": {}, "replies": [],
            "collapsed_received_ids": []}


def save_metrics(metrics: dict) -> None:
    """Atomic write (tmp + rename): a reader can never see a torn file.

    The 2026-08-15 incident killed daemon 69670 mid-write, leaving
    metrics.json torn; daemon 70146 then died silently on json.load
    (JSONDecodeError, no traceback). tmp + rename keeps the previous good
    file in place until the new one is complete.
    """
    tmp = config.METRICS_PATH.with_suffix(".json.tmp")
    with open(tmp, "w") as f:
        json.dump(metrics, f, indent=2, default=str)
    os.replace(tmp, config.METRICS_PATH)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _parse_dt(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def _parse_dt_utc(value):
    """Parse a stored timestamp, assuming UTC when no timezone is present
    (some manual reply records store naive datetimes)."""
    dt = _parse_dt(value)
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def _valid_id(email_id) -> bool:
    return bool(email_id) and len(str(email_id)) >= 32


def _tombstones(metrics: dict) -> set:
    """Received ids the recheck has collapsed away (metrics.collapsed_received_ids).

    The live sweep path must never capture these again — a collapsed duplicate
    would otherwise be re-added by the next provider listing and the ledger
    would oscillate recheck->collapsed, sweep->grown forever (owner evidence
    2026-08-11, change-b28800611b). Read-only helper: only recheck_replies
    ever grows the tombstone list."""
    return {str(x) for x in (metrics.get("collapsed_received_ids") or []) if x}


def _date_dist(a, b) -> float:
    pa, pb = _parse_dt(a), _parse_dt(b)
    if pa is None or pb is None:
        return float("inf")
    return abs((pa - pb).total_seconds())


def is_due(metrics: dict, force: bool = False) -> bool:
    """Scheduled check: only pull when the last check is older than
    METRICS_INTERVAL_HOURS (or never ran, or --force)."""
    if force or not metrics.get("last_check"):
        return True
    last = _parse_dt(metrics["last_check"])
    if last is None:
        return True
    return datetime.now(timezone.utc) - last >= timedelta(hours=config.METRICS_INTERVAL_HOURS)


# ── Collection ────────────────────────────────────────────────────────────────

def resolve_missing_ids(log: dict) -> dict:
    """Backfill missing/truncated provider ids by matching the provider's
    sent-email list on recipient + subject (resend only — see capabilities)."""
    if not providers.cap_list_sent():
        return {}
    missing = [s for s in log.get("sent", []) if not _valid_id(s.get("provider_id") or s.get("resend_id"))]
    if not missing:
        return {}
    listing, _timed_out = _bounded_call(
        providers.list_sent_emails, PROVIDER_CALL_TIMEOUT_SECONDS)
    if _timed_out or not listing or listing.get("error"):
        return {}
    resolved = {}
    for s in missing:
        candidates = [
            e for e in listing.get("data", [])
            if s.get("email") in (e.get("to") or [])
            and (s.get("subject") or "").casefold() == (e.get("subject") or "").casefold()
        ]
        if len(candidates) == 1:
            resolved[s["lead_id"]] = candidates[0]["id"]
        elif len(candidates) > 1:
            best = min(candidates, key=lambda e: _date_dist(e.get("created_at"), s.get("timestamp")))
            resolved[s["lead_id"]] = best["id"]
    return resolved


def collect(log: dict, force: bool = False, deadline: float = None):
    """Fetch the latest provider status for every sent email (and detect
    replies via the receiving API). Returns (metrics, ran) — ran is False
    when the scheduled check is not due yet.

    Wedge bound (2026-08-15 incident): every provider call runs through
    _bounded_call (PROVIDER_CALL_TIMEOUT_SECONDS) and the whole pass stops
    fetching past `deadline` (COLLECT_DEADLINE_SECONDS from entry), so a
    stalled HTTPS connection can slow a measure but never hold the serial
    watch loop forever."""
    metrics = load_metrics()
    if not is_due(metrics, force):
        return metrics, False

    if deadline is None:
        deadline = _time.time() + COLLECT_DEADLINE_SECONDS
    resolved = resolve_missing_ids(log)
    emails = metrics.setdefault("emails", {})
    checked_at = datetime.now(timezone.utc).isoformat()

    if not providers.cap_status():
        return metrics, True  # provider has no tracking; nothing to collect

    # Resend fast path: one list call carries last_event for every recent
    # send (~8s each individually was making a full collect take an hour).
    resend_map = {}
    try:
        listing, _timed_out = _bounded_call(
            providers.list_sent_emails, PROVIDER_CALL_TIMEOUT_SECONDS)
        if not _timed_out and listing and not listing.get("error"):
            resend_map = {
                e.get("id"): e.get("last_event")
                for e in (listing.get("data") or []) if e.get("id")
            }
    except Exception:
        pass

    # WINDOW BOUND (owner rule 2026-08-09): the gate judges the last 48h.
    # Sends older than the window with a settled status never re-fetch —
    # the per-email provider path (mailgun: up to 9 calls, brevo: 1, plus
    # 5s error sleeps) is what made a full collect take 15+ minutes. The
    # reply sync below is provider-side and covers ALL ages, so the reply
    # rate stays complete; open/click history is already on disk.
    window_start = (datetime.now(timezone.utc) - timedelta(hours=48)).isoformat()

    for s in log.get("sent", []):
        # DEADLINE (wedge hardening 2026-08-15): once the pass deadline is
        # past, stop fetching — remaining sends keep their stored status and
        # the next scheduled collect refetches them. The resend fast path and
        # reply sync above/below still run; only slow per-email fetches stop.
        if _time.time() >= deadline:
            break
        lead_id = s["lead_id"]
        email_id = s.get("provider_id") or s.get("resend_id")
        if not _valid_id(email_id):
            email_id = resolved.get(lead_id)
        if not _valid_id(email_id):
            rec = emails.setdefault(lead_id, {})
            rec["provider_id"] = None
            rec["status"] = "unresolved"
            rec["checked_at"] = checked_at
            continue

        provider = s.get("provider") or ""
        rec_prev = emails.get(lead_id, {})
        prev_status = str(rec_prev.get("status") or "")
        prev_check = rec_prev.get("checked_at") or ""
        settled_old = bool(
            str(s.get("timestamp") or "") < window_start
            and prev_status and not prev_status.startswith(
                ("unknown", "unresolved", "denied", "error"))
        )
        fresh = False
        try:
            prev_dt = datetime.fromisoformat(str(prev_check))
            fresh = (datetime.now(timezone.utc) - prev_dt).total_seconds() < 3600
        except Exception:
            fresh = False
        if provider == "resend" and email_id in resend_map:
            status = {"last_event": resend_map[email_id]}
        elif settled_old or (
                fresh and prev_status and not prev_status.startswith(
                    ("unknown", "unresolved", "denied", "error"))):
            # settled beyond the gate's window, or already resolved within
            # the hour — skip the slow per-email provider fetch. The cheap
            # resend fast path above still runs every collect.
            continue
        else:
            for _attempt in range(2):  # flaky outbound network — one cheap retry
                status, _timed_out = _bounded_call(
                    providers.fetch_email_status,
                    PROVIDER_CALL_TIMEOUT_SECONDS,
                    email_id, provider=provider or "")
                if _timed_out:
                    # Bound exceeded: abandon this email, keep its stored
                    # status, and move on — a stalled provider endpoint must
                    # never hold the serial watch loop (2026-08-15 incident).
                    # No retry: a timed-out call already burned the budget.
                    status = {"error": "timeout"}
                    break
                if not status.get("error"):
                    break
                _time.sleep(5)
        if status.get("error"):
            event = None
            if status.get("error") == "timeout":
                # Bound exceeded (2026-08-15 wedge): record WHY the status is
                # unknown instead of the previous "None:" noise — a silent
                # unknown was exactly how daemon 70146's death stayed
                # invisible in the metrics.
                code = "timeout"
                err = (f"timeout: provider call exceeded "
                       f"{PROVIDER_CALL_TIMEOUT_SECONDS:.0f}s")
            else:
                code = status.get("status")
                err = f"{code}:{status.get('message') or ''}"[:200]
            denied = code in (401, 403, 404)
        else:
            event = status.get("last_event") or "unknown"
            err = None
            denied = False

        rec = emails.setdefault(lead_id, {})
        rec["provider_id"] = email_id
        rec["checked_at"] = checked_at
        if event is None:
            if rec.get("status") and not str(rec.get("status")).startswith(("error", "unknown", "unresolved", "denied")):
                pass  # keep the last verified status
            else:
                rec["status"] = "denied" if denied else "unknown"
            rec["last_error"] = err
        else:
            rec["status"] = event
            rec.pop("last_error", None)
        rec.setdefault("history", []).append({"at": checked_at, "status": event or rec["status"]})
        # PROGRESS SAVE (owner rule 2026-08-09): a killed collect used to lose
        # the whole pass. Persist every 50 emails so a timeout only loses the
        # last slice, never the whole window.
        if len(emails) % 50 == 0:
            metrics["last_check"] = checked_at
            save_metrics(metrics)

    # Retry ledger reconciliation: a failed entry whose lead is now in sent[]
    # was retried successfully on a later block — mark it resolved so it stops
    # counting against the day and pick_provider stops banning the provider
    # for it (owner rule 2026-08-08: failed[] was write-only; 17 dead emails
    # counted against the goal forever).
    sent_ids = {s["lead_id"] for s in log.get("sent", [])}
    changed = False
    for f in log.get("failed", []):
        if isinstance(f, dict) and not f.get("resolved_at") and f.get("lead_id") in sent_ids:
            f["resolved_at"] = checked_at
            changed = True
    if changed:
        try:
            from outbound import save_sent_log
            save_sent_log(log)
        except Exception:
            pass

    metrics["last_check"] = checked_at
    sync_replies(log, metrics, deadline=deadline)
    save_metrics(metrics)
    return metrics, True


def classify_reply_kind(subject: str = "", auto_submitted=None, x_autoreply=None) -> str:
    """Classify a captured message as 'auto' or 'reply' from reliable signals.

    Strong auto signals (any one wins):
      1. the 'Automatic reply:' out-of-office subject prefix (Outlook/Exchange
         convention),
      2. an Auto-Submitted header other than 'no' (RFC 3834 — 'auto-replied',
         'auto-generated', ...),
      3. an X-Autoreply header (present on many autoresponder transports),
      4. a configured AUTO_REPLY_KEYWORDS hit anywhere in the subject.

    Ordinary 'Re:' subjects default to 'reply' unless a strong signal says
    auto. Missing headers are not signals.
    """
    subj = (subject or "").casefold()
    if subj.startswith("automatic reply:"):
        return "auto"
    auto_submitted = str(auto_submitted or "").strip().casefold()
    if auto_submitted and auto_submitted != "no":
        return "auto"
    if str(x_autoreply or "").strip():
        return "auto"
    if any(kw in subj for kw in _AUTO_REPLY_KEYWORDS):
        return "auto"
    return "reply"


def _is_auto_reply(subject: str) -> bool:
    """Subject-only auto check (legacy callers without header inputs)."""
    return classify_reply_kind(subject) == "auto"


def sync_replies(log: dict, metrics: dict, deadline: float = None) -> int:
    """Pull received emails from the provider and record those that match a
    sent lead as replies (deduped by received email id). Auto-replies are
    recorded with kind="auto" using reliable signals (subject prefix, subject
    keywords, Auto-Submitted / X-Autoreply headers when the capture path
    exposes them). Returns the number of newly recorded.

    Wedge bound (2026-08-15): the listing runs through _bounded_call, and
    when a collect deadline is supplied the fetch is skipped entirely once
    the deadline is past — a stalled measure must never hold the serial
    watch loop, and the reply sync is part of that measure pass.

    Tombstone guard (owner evidence 2026-08-11, change-b28800611b): a message
    whose received_id is in metrics.collapsed_received_ids was collapsed away
    by a prior `replies --recheck` and must be skipped BEFORE recording — the
    recheck has already merged its content into the kept per-lead record.
    This path only READS tombstones; only the recheck ever adds to them."""
    if not providers.cap_received():
        return 0
    if deadline is not None and _time.time() >= deadline:
        return 0  # collect pass deadline reached — no more fetching
    listing, _timed_out = _bounded_call(
        providers.list_received_emails, PROVIDER_CALL_TIMEOUT_SECONDS)
    if _timed_out or not listing or listing.get("error"):
        return 0

    sent_by_email = {s["email"]: s for s in log.get("sent", [])}
    replies = metrics.setdefault("replies", [])
    known = {r.get("received_id") for r in replies}
    tombstoned = _tombstones(metrics)
    added = 0

    for e in listing.get("data", []):
        eid = e.get("id")
        if not eid or eid in known or eid in tombstoned:
            continue
        sender = str(e.get("from") or "").strip().lower()
        if not sender or sender == config.FROM_EMAIL.lower():
            continue
        s = sent_by_email.get(sender)
        if not s:
            continue
        subject = str(e.get("subject") or "")
        # Classification inputs are stored with the record so a later
        # `replies --recheck` can re-run classification from stored signals
        # (owner evidence 2026-08-11: kinds were decided once at first capture
        # and never re-examined, so stale kinds persisted forever).
        auto_submitted = str(e.get("auto_submitted") or "")
        x_autoreply = str(e.get("x_autoreply") or "")
        replies.append({
            "received_id": eid,
            "lead_id": s["lead_id"],
            "email": sender,
            "from": sender,
            "company": s.get("company"),
            "variant": s.get("variant"),
            "subject": subject,
            "message_id": e.get("message_id"),
            "received_at": e.get("created_at"),
            "recorded_at": datetime.now(timezone.utc).isoformat(),
            "kind": classify_reply_kind(subject, auto_submitted, x_autoreply),
            "auto_submitted": auto_submitted,
            "x_autoreply": x_autoreply,
            "note": "",
        })
        known.add(eid)
        added += 1

    if added:
        save_metrics(metrics)
    return added


# ── Reconciliation (owner evidence 2026-08-11) ──────────────────────────────
# Reply kinds used to be decided once at first capture and never re-examined,
# and the same lead could be captured twice (gmail sweep + manual record, or
# two sweep passes through different transport headers). `replies --recheck`
# re-runs classification from the stored inputs, collapses per-lead duplicates
# (keeping the newest record and merging metadata), and persists idempotently.
# Every received_id the collapse removes is tombstoned in
# metrics.collapsed_received_ids (change-b28800611b) so a later sweep listing
# can never re-add the same message — sync_replies skips tombstoned ids
# before recording; only the recheck writes tombstones.

_IDENTITY_KEYS = {"received_id", "lead_id", "email", "from", "subject",
                  "message_id", "received_at", "recorded_at", "kind"}

# Identity fields that must survive a per-lead collapse even though they
# describe the lead, not the capture: the kept (newest) record's own value
# wins; a missing/empty value is backfilled from any record in the group.
# (Owner evidence 2026-08-11, change-d1459e3624: the kept AP-7d1096 record
# came out of the 3.3.0 merge with email=null because email was treated as a
# non-mergeable identity key.)
_MERGE_IDENTITY_KEYS = ("email", "contact_name", "company")


def _record_time(record: dict, key: str):
    """UTC-aware timestamp for a record field; None stays None (oldest)."""
    return _parse_dt_utc(record.get(key))


def _newer_record(a: dict, b: dict):
    """Return (winner, loser) — the newer of two reply records, by received_at
    (missing = oldest) then recorded_at; ties favor the later record in the
    list (the later capture)."""
    for key in ("received_at", "recorded_at"):
        ta, tb = _record_time(a, key), _record_time(b, key)
        if ta == tb:
            continue
        if ta is None:
            return b, a
        if tb is None:
            return a, b
        return (b, a) if tb > ta else (a, b)
    return b, a


def _merge_metadata(winner: dict, loser: dict) -> None:
    """Merge non-identity metadata from the dropped record into the kept one
    (notes are concatenated so owner context is never lost). Identity fields
    (email, contact_name, company) are preserved across the collapse: the
    newest (kept) record's own value wins; a missing/empty value is
    backfilled from any record in the group."""
    for key in _MERGE_IDENTITY_KEYS:
        if winner.get(key) in (None, "", []):
            value = loser.get(key)
            if value not in (None, "", []):
                winner[key] = value
    for key, value in loser.items():
        if key in _IDENTITY_KEYS or value in (None, "", []):
            continue
        if key == "note":
            w = str(winner.get("note") or "").strip()
            l = str(value or "").strip()
            if l and l not in w:
                winner["note"] = f"{w} | {l}" if w else l
        elif key not in winner or winner.get(key) in (None, "", []):
            winner[key] = value


def _record_identity(record: dict) -> dict:
    return {"lead_id": record.get("lead_id"),
            "received_id": record.get("received_id"),
            "subject": record.get("subject"),
            "received_at": record.get("received_at"),
            "kind": record.get("kind")}


def recheck_replies(metrics: dict, dry_run: bool = False) -> dict:
    """Reconcile the stored reply ledger.

    1. Re-runs classification on every record from its stored inputs
       (subject, from, Auto-Submitted / X-Autoreply headers) and corrects
       stale kinds.
    2. Dedupes per lead across capture paths — keeps the newest record
       (received_at, falling back to recorded_at) and merges metadata from
       the removed records (notes concatenated, identity fields email /
       contact_name / company backfilled when the kept record lacks them).
    3. Tombstones (owner evidence 2026-08-11, change-b28800611b): every
       received_id on a collapsed (removed) record is added to
       metrics.collapsed_received_ids so the live sweep path never re-captures
       it. Only ids actually collapsed are added; the list is stored sorted
       and unique, so repeated rechecks are idempotent with no unbounded
       growth.
    4. Persists only when not dry_run; idempotent — a second run over an
       already-reconciled ledger reports no changes and rewrites nothing.

    Returns a change report dict: records_before/after, reclassified,
    collapsed, unchanged, dry_run, tombstones_before/added/total.
    """
    replies = metrics.get("replies") or []
    tombstones = sorted(_tombstones(metrics))
    report = {
        "records_before": len(replies),
        "records_after": len(replies),
        "reclassified": [],
        "collapsed": [],
        "unchanged": 0,
        "dry_run": bool(dry_run),
        "tombstones_before": len(tombstones),
        "tombstones_added": [],
        "tombstones_total": len(tombstones),
    }
    if not replies:
        return report

    # Pass 1 — correct kinds from stored classification inputs.
    corrected = []
    for r in replies:
        old = str(r.get("kind") or "reply").strip().lower()
        new = classify_reply_kind(
            r.get("subject"), r.get("auto_submitted"), r.get("x_autoreply"))
        if old != new:
            corrected.append((r, old, new))
            report["reclassified"].append({
                "lead_id": r.get("lead_id"),
                "subject": r.get("subject"),
                "from": r.get("from") or r.get("email"),
                "received_id": r.get("received_id"),
                "old": old, "new": new,
            })
    report["unchanged"] = len(replies) - len(corrected)
    if not dry_run:
        for r, _old, new in corrected:
            r["kind"] = new

    # Pass 2 — dedupe per lead across capture paths, keep newest, merge.
    kept, removed_map, order = {}, {}, []
    for idx, r in enumerate(replies):
        key = r.get("lead_id") or f"__no_lead__{idx}"
        if key in kept:
            winner, loser = _newer_record(kept[key], r)
            if winner is loser:
                removed_map.setdefault(key, []).append(kept[key])
            else:
                removed_map.setdefault(key, []).append(loser)
            kept[key] = winner
            _merge_metadata(winner, loser)
        else:
            kept[key] = r
            order.append(key)

    after = [kept[key] for key in order]
    report["records_after"] = len(after)
    added_tombstones = []
    for key in order:
        removed = removed_map.get(key) or []
        if not removed:
            continue
        # Tombstone every received_id the collapse removes — those messages
        # must never be re-captured by a later sweep (their content now lives
        # in the kept per-lead record). None/empty ids (manual records) are
        # skipped: a provider listing can never carry them.
        for r in removed:
            rid = str(r.get("received_id") or "")
            if rid and rid not in tombstones:
                tombstones.append(rid)
                added_tombstones.append(rid)
        report["collapsed"].append({
            "lead_id": key if not str(key).startswith("__no_lead__") else None,
            "kept": _record_identity(kept[key]),
            "removed": [_record_identity(x) for x in removed],
        })
    report["tombstones_added"] = sorted(set(added_tombstones))
    report["tombstones_total"] = len(tombstones)
    if not dry_run:
        metrics["replies"] = after
        if tombstones:
            # Sorted unique — deterministic across runs, no unbounded growth.
            metrics["collapsed_received_ids"] = sorted(set(tombstones))
    return report


# ── Aggregation ───────────────────────────────────────────────────────────────

def _rec(metrics: dict, lead_id: str) -> dict:
    return metrics.get("emails", {}).get(lead_id) or {}


def _reply_ids(metrics: dict) -> set:
    """Real replies only: kind 'reply' counts toward the goal; kind 'auto'
    (out-of-office) never counts; our own tests never count (variant starts
    with 'TEST', e.g. loop tests recorded via record-reply)."""
    return {r["lead_id"] for r in metrics.get("replies", [])
            if r.get("kind") == "reply"
            and not str(r.get("variant", "")).upper().startswith("TEST")}


def aggregate(log: dict, metrics: dict, window_hours: float = 48.0, now: datetime = None) -> dict:
    """Aggregate per-send status + reply counts.

    - `replied` stays the goal metric: unique reply-kind leads attributed to
      sends in the log (windowed sends).
    - `replies_received` is inbox truth: unique reply-kind leads received
      within the window regardless of send date (owner evidence 2026-08-11).
    """
    sent = log.get("sent", [])
    replied_ids = _reply_ids(metrics)
    auto_count = sum(1 for r in metrics.get("replies", []) if r.get("kind") == "auto")
    window_start = (now or datetime.now(timezone.utc)) - timedelta(hours=window_hours)
    received_reply_leads = {
        r.get("lead_id") for r in metrics.get("replies", [])
        if r.get("kind") == "reply"
        and not str(r.get("variant", "")).upper().startswith("TEST")
        and (received := _parse_dt_utc(r.get("received_at"))) is not None
        and received >= window_start
    }

    counts = {
        "sent": len(sent),
        "delivered": 0, "bounced": 0, "complained": 0,
        "opened": 0, "clicked": 0, "unresolved": 0, "unknown": 0, "denied": 0,
        "pending": 0, "replied": 0, "auto": auto_count,
        "replies_received": len(received_reply_leads),
    }
    _PENDING = {"sent", "delivery_delayed"}
    for s in sent:
        status = str(_rec(metrics, s["lead_id"]).get("status") or "")
        if status in _DELIVERED:
            counts["delivered"] += 1
        if status in _PENDING:
            counts["pending"] += 1
        if status == "bounced":
            counts["bounced"] += 1
        if status == "complained":
            counts["complained"] += 1
        if status in _OPENED:
            counts["opened"] += 1
        if status == "clicked":
            counts["clicked"] += 1
        if status == "unresolved":
            counts["unresolved"] += 1
        if status == "denied":
            counts["denied"] += 1
        if status == "unknown" or status.startswith("error"):
            counts["unknown"] += 1
        if s["lead_id"] in replied_ids:
            counts["replied"] += 1

    def rate(part, whole):
        return (part / whole) if whole else 0.0

    d = counts["delivered"]
    return {
        **counts,
        "delivered_rate": rate(counts["delivered"], counts["sent"]),
        "bounce_rate": rate(counts["bounced"], counts["sent"]),
        "spam_rate": rate(counts["complained"], counts["sent"]),
        "open_rate": rate(counts["opened"], d),
        "click_rate": rate(counts["clicked"], d),
        "reply_rate": rate(counts["replied"], counts["sent"]),
    }


def by_variant(log: dict, metrics: dict) -> dict:
    groups = {}
    for s in log.get("sent", []):
        groups.setdefault(s.get("variant") or "?", []).append(s)

    replied_ids = _reply_ids(metrics)
    out = {}
    for variant, items in groups.items():
        sub = {"sent": len(items), "delivered": 0, "opened": 0, "clicked": 0, "replied": 0, "unresolved": 0}
        for s in items:
            status = str(_rec(metrics, s["lead_id"]).get("status") or "")
            if status in _DELIVERED:
                sub["delivered"] += 1
            if status in _OPENED:
                sub["opened"] += 1
            if status == "clicked":
                sub["clicked"] += 1
            if status == "unresolved":
                sub["unresolved"] += 1
            if s["lead_id"] in replied_ids:
                sub["replied"] += 1
        d = sub["delivered"]
        sub["open_rate"] = sub["opened"] / d if d else 0.0
        sub["click_rate"] = sub["clicked"] / d if d else 0.0
        sub["reply_rate"] = sub["replied"] / sub["sent"] if sub["sent"] else 0.0
        out[variant] = sub
    return out


# ── Report ────────────────────────────────────────────────────────────────────

def print_report(log: dict, metrics: dict) -> None:
    t = aggregate(log, metrics)
    checked = metrics.get("last_check") or "never"

    def pct(x):
        return f"{x * 100:.1f}%"

    print(f"\n{'='*60}")
    print(f"  EMAIL DATA — provider: {config.EMAIL_PROVIDER} · checked: {checked}")
    print(f"{'='*60}")
    print(f"  Send rate:     {t['sent']:>3}/{t['sent']:>3}  accepted by provider")
    print(f"  Delivered:     {t['delivered']:>3}/{t['sent']:>3}  ({pct(t['delivered_rate'])})")
    print(f"  Bounced:       {t['bounced']:>3}/{t['sent']:>3}  ({pct(t['bounce_rate'])})  limit {config.MAX_BOUNCE_RATE*100:.0f}%")
    print(f"  Marked spam:   {t['complained']:>3}/{t['sent']:>3}  ({pct(t['spam_rate'])})  limit {config.MAX_SPAM_RATE*100:.2f}%")
    print(f"  Opened:        {t['opened']:>3}/{t['delivered']:>3}  ({pct(t['open_rate'])} of delivered)  goal {config.GOAL_OPEN_RATE*100:.0f}%")
    print(f"  Clicked:       {t['clicked']:>3}/{t['delivered']:>3}  ({pct(t['click_rate'])} of delivered)  goal {config.GOAL_CLICK_RATE*100:.0f}%")
    print(f"  Replied:       {t['replied']:>3}/{t['sent']:>3}  ({pct(t['reply_rate'])} of sent)  GOAL >{config.GOAL_REPLY_RATE*100:.0f}%")
    print(f"  Replies received (48h inbox truth, any send): {t['replies_received']:>3}")
    if t["auto"]:
        print(f"  Auto-replies:  {t['auto']:>3} (excluded from reply rate)")
    if t["unknown"]:
        print(f"  Unverified:    {t['unknown']:>3} (provider fetch failed — re-run `metrics --force` when the network recovers)")
    if t["denied"]:
        print(f"  Read denied:   {t['denied']:>3} (API key cannot read email status — see `review`)")
    if t["unresolved"]:
        print(f"  Unresolved:    {t['unresolved']:>3} (no queryable provider id — see `review`)")
    print(f"{'='*60}")
    print(f"  Goal + next action: python3 outbound.py review")
    print(f"{'='*60}\n")
