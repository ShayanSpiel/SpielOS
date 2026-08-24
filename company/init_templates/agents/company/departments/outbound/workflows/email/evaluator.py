#!/usr/bin/env python3
"""Outbound email EVALUATE helper: measure, learn, and check the goal.

MEASURE compares the batch that carried the intervention against the batch
before it (sample-aware; "inconclusive" is the honest default). LEARN
persists the verdict into the STATE knowledge store. GOAL CHECK answers the
loop's termination branch: achieved / not_yet / blocked.
"""

from datetime import datetime, timezone

from . import analytics, goal, outbound


def evidence_window_hours(ctx) -> float:
    return float(ctx.control.goal().get("evidence_window_hours", 48))


def measure(ctx, batch: dict) -> dict:
    log = outbound.load_sent_log()
    metrics = analytics.load_metrics()
    totals = analytics.aggregate(log, metrics)
    prev = ctx.store.latest_batch()
    verdict = _verdict(prev, {"metrics": totals}, batch.get("intervention", {}))
    return {"metrics": {k: v for k, v in totals.items() if not isinstance(v, dict)},
            "verdict": verdict}


def _verdict(prev: dict | None, cur: dict, intervention: dict) -> dict:
    if prev is None or not prev.get("metrics"):
        return {"verdict": "inconclusive",
                "reason": "no previous batch to compare against (baseline)"}
    target = intervention.get("target_metric") or goal.META["goal"]["metric"]
    pm = prev["metrics"]
    cm = cur.get("metrics") or {}
    n_prev = pm.get("sent", 0)
    n_cur = cm.get("sent", 0)
    if n_prev < goal.MIN_COMPARE_SAMPLE or n_cur < goal.MIN_COMPARE_SAMPLE:
        return {"verdict": "inconclusive",
                "reason": f"sample too small (prev {n_prev}, cur {n_cur}; need >= {goal.MIN_COMPARE_SAMPLE} per batch)"}
    before = pm.get(target, 0.0)
    after = cm.get(target, 0.0)
    delta = after - before
    if delta >= goal.MIN_IMPROVEMENT:
        return {"verdict": "keep", "reason": f"{target} {before*100:.1f}% -> {after*100:.1f}%",
                "delta": delta}
    if delta <= -goal.MIN_IMPROVEMENT:
        return {"verdict": "reject", "reason": f"{target} {before*100:.1f}% -> {after*100:.1f}%",
                "delta": delta}
    return {"verdict": "inconclusive",
            "reason": f"{target} {before*100:.1f}% -> {after*100:.1f}% (within noise)",
            "delta": delta}


def learn(ctx, intervention: dict, verdict: dict) -> None:
    variable = intervention.get("variable")
    if not variable:
        return
    trial = {
        "at": datetime.now(timezone.utc).isoformat(),
        "batch": intervention.get("batch_id"),
        "variable": variable,
        "detail": intervention.get("detail"),
        "prediction": intervention.get("prediction"),
        "verdict": verdict.get("verdict"),
        "reason": verdict.get("reason"),
    }
    ctx.store.record_trial(variable, trial)


def goal_check(ctx, metrics: dict) -> dict:
    log = outbound.load_sent_log()
    snapshot_metrics = analytics.load_metrics()
    w_t = _window_totals(log, snapshot_metrics)
    meta = goal.META
    sent_total = metrics.get("sent", 0)

    g = meta["goal"]
    cur = w_t[g["metric"]]
    if cur >= g["target"] and sent_total >= goal.MIN_TRUSTED_SAMPLE:
        return {"state": "achieved",
                "detail": f"{g['name']} {cur*100:.1f}% >= {g['target']*100:.0f}% (window, n={sent_total})"}

    unverified = w_t.get("unknown", 0) + w_t.get("denied", 0) + w_t.get("unresolved", 0)
    if unverified >= max(5, w_t.get("sent", 0) * 0.1):
        return {"state": "blocked",
                "detail": f"data not trustworthy: {unverified} unverified/denied/unresolved"}

    return {"state": "not_yet",
            "detail": f"{g['name']} {cur*100:.1f}% vs target {g['target']*100:.0f}% (window, n={sent_total})"}


def _window_totals(log: dict, metrics: dict, hours: int = 48) -> dict:
    from datetime import timedelta
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
    window_log = {"sent": [s for s in log.get("sent", [])
                           if str(s.get("timestamp", "")) >= cutoff],
                  "failed": log.get("failed", [])}
    return analytics.aggregate(window_log, metrics)
