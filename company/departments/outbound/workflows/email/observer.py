#!/usr/bin/env python3
"""Outbound email OBSERVE helper: produce the domain snapshot.

The snapshot is a pure, timestamped read of present state: totals (all-time
and 48h window), goal status, gate verdict, queue depth, caps, provider
health, and the experiment memory (knowledge). DECIDE consumes it; the
ACT/GATE re-runs it (quick=True) for a fresh pre-execution check.
"""

import json
from datetime import datetime, timedelta, timezone

from . import analytics, compose, config, goal, outbound, policy_rules
from . import providers


def _window_totals(log: dict, metrics: dict, hours: int = 48) -> dict:
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
    window_log = {"sent": [s for s in log.get("sent", [])
                           if str(s.get("timestamp", "")) >= cutoff],
                  "failed": log.get("failed", [])}
    return analytics.aggregate(window_log, metrics)


def _bounced_emails(log: dict, metrics: dict) -> set:
    id2email = {s.get("lead_id"): str(s.get("email") or "").lower()
                for s in log.get("sent", [])}
    out = set()
    for k, v in (metrics.get("emails") or {}).items():
        if v.get("status") == "bounced" and id2email.get(k):
            out.add(id2email[k])
    return out


def _queue_stats(cohort_filters: dict) -> dict:
    try:
        q = compose.pick_queue(cohort_filters)
    except Exception:
        return {"size": 0, "english": 0, "persian": 0}
    stats = {"size": len(q),
             "english": sum(1 for c in q if str(c.get("language") or "").strip().lower() == "english"),
             "persian": sum(1 for c in q if str(c.get("language") or "").strip().lower() != "english")}
    return stats


def _provider_health() -> dict:
    try:
        return providers.available_providers()
    except Exception as e:
        return {"error": f"unreachable: {e}"}


def observe(ctx, quick: bool = False) -> dict:
    log = outbound.load_sent_log()
    metrics = analytics.load_metrics()

    if not quick:
        try:
            metrics, _ran = analytics.collect(log, force=True)
        except Exception:
            pass

    totals = analytics.aggregate(log, metrics)
    window_totals = _window_totals(log, metrics)
    cap, phase = outbound.daily_cap()
    sent_today = outbound.sent_today(log)
    knobs = ctx.control.knobs() if hasattr(ctx, "control") else {}
    cohort_filters = knobs.get("cohort_filters") or {}

    bounced = _bounced_emails(log, metrics)
    snapshot = {
        "at": datetime.now(timezone.utc).isoformat(),
        "workflow": ctx.workflow.name if hasattr(ctx, "workflow") else "email",
        "config": {"ok": not config.CONFIG_ERROR, "error": config.CONFIG_ERROR},
        "totals": {k: v for k, v in totals.items() if not isinstance(v, dict)},
        "window_totals": {k: v for k, v in window_totals.items() if not isinstance(v, dict)},
        "bounced_emails": sorted(bounced),
        "meta": goal.META,
        "goal_status": _goals_status(totals),
        "problems": _data_problems(totals),
        "gate": policy_rules.evaluate(
            {"window_totals": window_totals, "meta": goal.META, "bounced_emails": bounced},
            knobs),
        "queue": _queue_stats(cohort_filters),
        "cap": {"cap": cap, "phase": phase, "sent_today": sent_today,
                "remaining": max(0, cap - sent_today)},
        "providers": _provider_health(),
        "knowledge": _knowledge(ctx),
        "last_batch": _last_batch(ctx),
    }
    return snapshot


def _goals_status(totals: dict) -> list:
    meta = goal.META
    out = []
    g = meta["goal"]
    out.append({**g, "current": totals[g["metric"]],
                "gap": (totals[g["metric"]] - g["target"]) / g["target"]})
    for k in meta["supporting_kpis"]:
        out.append({**k, "current": totals[k["metric"]],
                    "gap": (totals[k["metric"]] - k["target"]) / k["target"]})
    for gr in meta["guardrails"]:
        cur = totals[gr["metric"]]
        out.append({**gr, "current": cur, "gap": (gr["max"] - cur) / gr["max"]})
    return out


def _data_problems(totals: dict) -> list:
    probs = []
    if totals.get("unknown"):
        probs.append(f"{totals['unknown']} emails unverified — metrics not trustworthy")
    if totals.get("denied"):
        probs.append(f"{totals['denied']} read-denied — API key lacks read access")
    if totals.get("unresolved"):
        probs.append(f"{totals['unresolved']} unresolved ids — no queryable provider id")
    return probs


def _knowledge(ctx) -> dict:
    try:
        return ctx.store.all_knowledge()
    except Exception:
        return {}


def _last_batch(ctx) -> dict | None:
    try:
        last = ctx.store.latest_batch()
        if not last or not last.get("metrics"):
            return None
        return {"id": last["id"], "metrics": last["metrics"],
                "verdict": last.get("verdict")}
    except Exception:
        return None
