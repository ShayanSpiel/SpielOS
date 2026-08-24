"""Email workflow bundle used by the Outbound Department.

The loop's contract lives in workflows/__init__.py; this module wires the
email domain machinery (outbound/leads/providers/analytics/verify) to it.
The company runtime owns the loop; this bundle supplies domain operations.
"""

from .. import Workflow, register
from . import actor, decider, evaluator, goal, observer, policy_rules, report as report_data, validators

_REPORT_LINE_KEYS = ("sent", "delivered_rate", "open_rate", "click_rate",
                     "reply_rate", "bounce_rate", "spam_rate")


def _report_lines(ctx, batch: dict, outcome: dict) -> list:
    m = outcome.get("metrics") or {}

    def _fmt(k, v):
        if "rate" in k and isinstance(v, (int, float)):
            return f"{k.replace('_rate', '')} {v*100:.1f}%"
        return f"{k} {v}"

    return ["- metrics: " + " · ".join(_fmt(k, m[k]) for k in _REPORT_LINE_KEYS if k in m)]


def _policy(ctx, snapshot: dict) -> dict:
    return policy_rules.evaluate(snapshot, ctx.control.knobs())


workflow = register(Workflow(
    name="email",
    describe="research-first personalized cold email: per-lead hook + pain hypothesis, supervised AI employees, paced sends",
    goal={
        "name": goal.META["goal"]["name"],
        "metric": goal.META["goal"]["metric"],
        "target": goal.META["goal"]["target"],
        "evidence_window_hours": 48,
        "min_sample": goal.MIN_COMPARE_SAMPLE,
    },
    observe=observer.observe,
    decide=decider.decide,
    prepare=actor.prepare,
    validate=validators.validate,
    execute=actor.execute,
    measure=evaluator.measure,
    learn=evaluator.learn,
    goal_check=evaluator.goal_check,
    policy=_policy,
    report_lines=_report_lines,
    report=report_data.report,
))
