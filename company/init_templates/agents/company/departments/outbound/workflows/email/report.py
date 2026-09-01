#!/usr/bin/env python3
"""Outbound email report data for company-runtime evaluation artifacts.

The Department's report workflow renders the generic sections (batch, sends,
hypothesis vs goal) and asks the workflow bundle for the domain picture:
campaign totals, per-provider counts, one random example email (for
research/content quality checks), guardrails on the 48h window, and the
leads pipeline (total, next queue, needed to gather).

Everything here is defensive: a report must never break the loop. Reads are
local files only — no provider calls, no analytics collection.
"""

import random
from collections import Counter
from datetime import datetime, timedelta, timezone

from . import analytics, compose, config, goal, outbound


def _window_totals(log: dict, metrics: dict, hours: int = 48) -> dict:
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
    window_log = {"sent": [s for s in log.get("sent", [])
                           if str(s.get("timestamp", "")) >= cutoff],
                  "failed": log.get("failed", [])}
    return analytics.aggregate(window_log, metrics)


def _leads_picture(ctx) -> dict:
    knobs = ctx.control.knobs()
    filters = knobs.get("cohort_filters") or {}
    block = int(knobs.get("block_size") or config.BLOCK_SIZE)
    picture = {"total": 0, "queue": 0, "queue_english": 0, "queue_persian": 0,
               "needed_to_gather": block}
    try:
        picture["total"] = len(outbound.read_contacts())
    except Exception:
        pass
    try:
        q = compose.pick_queue(filters)
        picture["queue"] = len(q)
        picture["queue_english"] = sum(
            1 for c in q if str(c.get("language") or "").strip().lower() == "english")
        picture["queue_persian"] = len(q) - picture["queue_english"]
    except Exception:
        q = []
    picture["needed_to_gather"] = max(0, block - picture["queue"])
    return picture


def _example_email(batch: dict, log: dict) -> dict:
    """One random email from the batch (seeded by batch id so the journal is
    stable across re-reads) for research/content quality checks."""
    payload = batch.get("batch") or batch
    emails = payload.get("emails") or []
    if not emails:
        return {}
    rng = random.Random(str(batch.get("id") or "unseeded"))
    chosen = rng.choice(emails)
    sent = next((s for s in log.get("sent", [])
                 if s.get("lead_id") == chosen.get("lead_id")), {})
    return {
        "lead_id": chosen.get("lead_id", "?"),
        "company": sent.get("company") or "",
        "email": sent.get("email") or chosen.get("lead_id", ""),
        "contact_name": sent.get("contact_name") or "",
        "subject": chosen.get("subject", ""),
        "body": chosen.get("body_text", ""),
    }


def report(ctx, batch: dict, outcome: dict | None) -> dict:
    log = outbound.load_sent_log()
    metrics_data = analytics.load_metrics()
    totals = analytics.aggregate(log, metrics_data)
    window = _window_totals(log, metrics_data)
    cap, phase = outbound.daily_cap()
    sent_today = outbound.sent_today(log)

    batch_id = batch.get("id")
    batch_sends = [s for s in log.get("sent", []) if s.get("batch") == batch_id]
    provider_counts = Counter(s.get("provider") or "?" for s in batch_sends)

    try:
        health = [f"{p} enabled" for p in config.SEND_PROVIDERS]
    except Exception:
        health = []

    guardrails = []
    for g in goal.META.get("guardrails", []):
        cur = window.get(g["metric"], 0.0)
        guardrails.append({"name": g["name"], "current": cur,
                           "max": g["max"], "ok": cur <= g["max"]})

    return {
        "campaign": {
            "total_sent": totals.get("sent", 0),
            "sent_today": sent_today,
            "cap": cap,
            "cap_phase": phase,
            "remaining": max(0, cap - sent_today),
        },
        "providers": {"batch": dict(provider_counts), "health": health},
        "example": _example_email(batch, log),
        "guardrails": guardrails,
        "window": {k: v for k, v in window.items() if not isinstance(v, dict)},
        "leads": _leads_picture(ctx),
    }
