#!/usr/bin/env python3
"""Outbound email DECIDE helper: the weakest-link diagnosis.

Consumes the snapshot (state + memory) and produces ONE intervention:
  {action: "prepare_batch"|"hold"|"stop", variable, detail, prediction,
   levers}
or None when no action is available. Diagnosis order never skips:
data problems -> guardrails -> primary goal -> open stage -> reply stage.
Knowledge vetoes a lever whose last verdict was "reject" — the loop needs
a NEW angle, not the same failed change.
"""

from . import content as content_bank
from . import goal


def weakest_link(window_totals: dict, meta: dict, sent: int,
                 skip_unverified: bool = False, breaches: list = None) -> dict | None:
    if sent < goal.MIN_TRUSTED_SAMPLE:
        return {"stage": "sample", "detail": f"only {sent} sent; need {goal.MIN_TRUSTED_SAMPLE}",
                "variable": None, "actionable": False}
    if breaches is None:
        breaches = [gr for gr in meta["guardrails"]
                    if window_totals[gr["metric"]] > gr["max"]]
    for b in breaches:
        if b["name"] == "bounce rate" and skip_unverified:
            break
        return {"stage": "guardrail", "detail": b["name"],
                "variable": "cohort_unverified" if b["name"] == "bounce rate" else "providers",
                "actionable": True}

    g = meta["goal"]
    cur = window_totals[g["metric"]]
    if cur >= g["target"]:
        return {"stage": "goal-met", "detail": f"reply rate {cur*100:.1f}% >= {g['target']*100:.0f}%",
                "variable": None, "actionable": False}

    open_target = 0.80
    for k in meta.get("supporting_kpis", []):
        if k["metric"] == "open_rate":
            open_target = k["target"]
            break
    if window_totals["open_rate"] < open_target:
        return {"stage": "open", "detail": f"open rate {window_totals['open_rate']*100:.1f}% < {open_target*100:.0f}%",
                "variable": "subject", "actionable": True}
    return {"stage": "reply",
            "detail": f"opens fine but reply {cur*100:.1f}% < {g['target']*100:.0f}%",
            "variable": "cta", "actionable": True}


def decide(ctx, snapshot: dict) -> dict | None:
    if not snapshot.get("config", {}).get("ok", True):
        return {"action": "hold",
                "reason": "config broken",
                "detail": snapshot["config"].get("error", "validation failed")}
    if not snapshot.get("gate", {}).get("ok"):
        return {"action": "hold",
                "reason": "gate blocked — resolve before any send",
                "detail": _gate_detail(snapshot)}
    if snapshot["cap"]["remaining"] <= 0:
        return {"action": "hold",
                "reason": "daily cap reached",
                "detail": f"{snapshot['cap']['sent_today']}/{snapshot['cap']['cap']} "
                          f"({snapshot['cap']['phase']})"}
    if snapshot["queue"]["size"] == 0:
        return {"action": "hold",
                "reason": "queue empty — research/qualify/ingest new leads",
                "detail": "no unsent leads in the master under current filters"}

    w_t = snapshot["window_totals"]
    sent_total = snapshot["totals"].get("sent", 0)
    knobs = ctx.control.knobs()
    filters = knobs.get("cohort_filters") or {}
    breaches = snapshot["gate"].get("breaches") or []
    weak = weakest_link(w_t, snapshot["meta"], sent_total,
                        bool(filters.get("skip_unverified")), breaches=breaches)
    if weak is None:
        return {"action": "prepare_batch", "variable": None,
                "detail": "no actionable weakness", "prediction": "keep sending"}
    if weak["stage"] == "sample":
        return {"action": "prepare_batch", "variable": None,
                "detail": weak["detail"],
                "prediction": "sample too small to judge — keep sending"}

    variable = weak.get("variable")
    knowledge = ctx.store.knowledge_for(variable) if variable else {"tried": [], "verdict": None}
    levers: dict = {}
    if variable == "subject":
        levers["rotate_subjects"] = True
        prediction = ("rotate the active subject bank per segment so open "
                      "rate improves; reason: repetitive subjects suppress opens")
    elif variable == "cta":
        prediction = ("shorten the question so a reply costs ~10s; reason: "
                      "opens fine but reply rate is the gap")
    elif variable == "cohort_unverified":
        levers["cohort_filters"] = {"skip_unverified": True}
        prediction = ("skip unverified role addresses; reason: bounces "
                      "suppress opens and replies")
    elif variable == "providers":
        prediction = ("review provider health and sending order; reason: "
                      "deliverability stage is the weakest link")
    else:
        prediction = "keep sending"

    if knowledge.get("verdict") == "reject":
        return {"action": "prepare_batch", "variable": variable,
                "detail": (f"{weak['detail']} — {variable} already tried & rejected "
                           f"({len(knowledge.get('tried', []))} trial(s)) — needs a NEW angle"),
                "prediction": prediction + " (do NOT repeat the same change)",
                "levers": levers}

    if variable == "subject" and levers.get("rotate_subjects"):
        levers["subject_rotation"] = {
            seg: content_bank.subject_bank_for(seg)[0]
            for seg in ("recruitment-workflow", "agency-delivery", "saas-ops", "generic-workflow")
            if len(content_bank.subject_bank_for(seg)) > 1
        }

    return {"action": "prepare_batch", "variable": variable,
            "detail": weak["detail"], "prediction": prediction,
            "levers": levers}


def _gate_detail(snapshot: dict) -> str:
    parts = [f"{b['name']} {b['current']*100:.2f}% > {b['max']*100:.2f}%"
             for b in snapshot["gate"].get("breaches") or []]
    parts += list(snapshot["gate"].get("problems") or [])
    return "; ".join(parts) or "policy gate not ok"
