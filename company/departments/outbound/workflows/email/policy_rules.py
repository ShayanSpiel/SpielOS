#!/usr/bin/env python3
"""Email workflow — POLICY rules (guardrails, data-driven).

The company runtime enforces rules through the Department policy boundary; the rules are
workflow data. Evaluated on the 48h window at OBSERVE (soft awareness) and
re-evaluated at ACT/GATE on fresh state (hard veto). Any breach parks the
loop in HOLD with the breach listed; the owner resolves (sync bounces,
suppress senders, adjust cohort) and releases with `approve --next`.

Bounce is suppression-aware: a window bounce breach is downgraded ONLY when
every bounced address is already suppressed in the master (the fix actually
covers the evidence). Spam and delivered rate honour a time-boxed owner
override from control.json knobs. Delivered rate is only judgeable when
statuses are verified — noisy data is its own problem.
"""

from datetime import datetime, timedelta, timezone

from . import outbound


def _window(log: dict, hours: int = 48) -> dict:
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
    return {"sent": [s for s in log.get("sent", []) if str(s.get("timestamp", "")) >= cutoff],
            "failed": log.get("failed", [])}


def evaluate(snapshot: dict, control_knobs: dict | None = None) -> dict:
    """{ok, breaches, problems} from a snapshot's window totals."""
    knobs = control_knobs or {}
    totals = snapshot.get("window_totals") or {}
    meta = snapshot.get("meta") or {}

    breaches = []
    for gr in meta.get("guardrails", []):
        cur = totals.get(gr["metric"], 0.0)
        if cur > gr["max"]:
            breaches.append({"name": gr["name"], "metric": gr["metric"],
                             "current": cur, "max": gr["max"]})

    problems = []
    if totals.get("unknown"):
        problems.append(f"{totals['unknown']} emails unverified — metrics not trustworthy")
    if totals.get("denied"):
        problems.append(f"{totals['denied']} read-denied — API key lacks read access")
    if totals.get("unresolved"):
        problems.append(f"{totals['unresolved']} unresolved ids — no queryable provider id")

    # Bounce suppression downgrade: every window bounce must already be
    # suppressed in the master, else the breach stands.
    bounce = next((b for b in breaches if b["name"] == "bounce rate"), None)
    if bounce and snapshot.get("bounced_emails"):
        unsuppressed = _unsuppressed(snapshot["bounced_emails"])
        if not unsuppressed:
            breaches.remove(bounce)

    # Spam override (owner, time-boxed): demotes only the spam breach, only
    # until the timestamp. Never touches bounce/delivery/data.
    spam = next((b for b in breaches if b["name"] == "spam rate"), None)
    if spam:
        until = str(knobs.get("gate_spam_override_until") or "")
        if until:
            try:
                if datetime.now(timezone.utc) < datetime.fromisoformat(until):
                    breaches.remove(spam)
            except ValueError:
                pass

    # Delivered rate: judgeable only when statuses are verified and the
    # bounce doesn't already explain it (never double-report). A window
    # with zero sends has no rate to judge — a fresh campaign must start.
    if totals.get("sent", 0) > 0 and not any(b["name"] == "bounce rate" for b in breaches):
        # Provider-accepted sends awaiting a final event (sent/delivery_delayed)
        # are not failures: count them as delivered-equivalent for this rate.
        # Real bounces/complaints still depress the rate and keep the gate honest.
        pending = totals.get("pending", 0)
        # Suppressed-bounce parity (2026-08-11): when every window bounce is
        # already remediated in the master, exclude them from the judged
        # population so they do not double-block the gate via this rule.
        suppressed = 0
        if totals.get("bounced", 0) and snapshot.get("bounced_emails") \
                and not _unsuppressed(snapshot["bounced_emails"]):
            suppressed = totals["bounced"]
        denom = max(totals.get("sent", 0) - suppressed, 1)
        effective = (totals.get("delivered", 0) + pending) / denom
        unverified = totals.get("unknown", 0) + totals.get("denied", 0) + totals.get("unresolved", 0)
        if unverified < max(5, totals.get("sent", 0) * 0.1) and effective < 0.99:
            breaches.append({"name": "delivered rate", "metric": "delivered_rate",
                             "current": effective, "max": 0.99})

    # Delivered-rate override (owner, time-boxed): demotes only the delivered
    # rate breach, only until the timestamp. Never touches bounce/spam/data.
    delivered = next((b for b in breaches if b["name"] == "delivered rate"), None)
    if delivered:
        until = str(knobs.get("gate_delivered_override_until") or "")
        if until:
            try:
                if datetime.now(timezone.utc) < datetime.fromisoformat(until):
                    breaches.remove(delivered)
            except ValueError:
                pass

    noisy_data = (totals.get("unknown", 0) + totals.get("denied", 0)
                  + totals.get("unresolved", 0)) >= max(5, totals.get("sent", 0) * 0.1)
    return {"ok": not breaches and not noisy_data,
            "breaches": breaches,
            "problems": problems if noisy_data else []}


def _unsuppressed(bounced_emails: set) -> list:
    """Bounced addresses not marked suppressed in the master."""
    if not bounced_emails:
        return []
    master_status = {}
    for c in outbound.read_contacts():
        master_status[str(c.get("email") or "").lower()] = (c.get("email_status") or "").strip()
    return [e for e in bounced_emails
            if "suppressed" not in master_status.get(e, "").lower()]
