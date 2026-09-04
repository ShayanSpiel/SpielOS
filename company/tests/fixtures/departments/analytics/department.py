"""Analytics Department — clean migrated declaration (legacy v3.3.0 → clean core).

Migration notes (2026-09-03):
- Legacy ``campaign_funnel_report`` (strict delivered-identity funnel math)
  stays department-local in ``analytics/funnel.py`` as a pure function over
  the shared ``departments/campaign_contract.py``.
- ``posthog.py`` (read-only EU Query API client, HogQL helpers, honesty
  rules: missing stays missing, never zero) ported unchanged; it is the
  implementation behind the ``posthog`` Connection.
- ``funnel.json`` (funnel taxonomy v3.1.0, full-capture directive
  2026-08-18) ported unchanged.
- CRO experiments still need their own approval before any website change
  (approval key ``start_experiment``).
"""

from __future__ import annotations

from ...workflows import Workflow, WorkflowStep


def _step(step_id: str, agent_id: str, instruction: str, *,
          evidence_kind: str | None = None, approval_key: str | None = None,
          skill_ids: tuple[str, ...] = (), connection_ids: tuple[str, ...] = (),
          requirements: dict | None = None) -> WorkflowStep:
    return WorkflowStep(
        id=step_id, agent_id=agent_id, instruction=instruction,
        evidence_kind=evidence_kind, approval_key=approval_key,
        skill_ids=skill_ids, connection_ids=connection_ids,
        requirements=requirements or {})


class AnalyticsDepartment:
    """Declarative analytics capability; execution belongs to GoalRuntime."""

    department_id = "analytics"
    id = "analytics"
    version = "3.4.0"
    description = (
        "Joins full-funnel evidence by campaign identity: refreshed Buffer "
        "per-post engagement plus read-only PostHog warehouse events per "
        "batch, with evidence-scaled one-to-three-variable decisions and "
        "explicit cells, thresholds, and effect analysis."
    )
    agent_ids = ("analytics-operator", "cro-optimizer")
    production_ready = True

    workflows = (
        Workflow(
            "company-scorecard",
            "Report canonical business and Department metrics.",
            (
                _step("collect", "analytics-operator",
                      "Collect the metric inputs from PostHog (read-only "
                      "Query API) and department evidence; never invent "
                      "numbers.",
                      skill_ids=("analytics",),
                      connection_ids=("posthog",)),
                _step("validate", "analytics-operator",
                      "Validate completeness; missing data stays labeled "
                      "missing, never zero.",
                      skill_ids=("analytics",)),
                _step("calculate", "analytics-operator",
                      "Compute canonical funnel math from funnel.json "
                      "formulas (ctr, service_intent_rate, "
                      "lead_conversion_rate).",
                      skill_ids=("analytics",)),
                _step("report", "analytics-operator",
                      "Write the scorecard and record evidence "
                      "{'company_scorecard': {...}}.",
                      evidence_kind="company_scorecard",
                      skill_ids=("analytics",),
                      connection_ids=("posthog",)),
            ),
            department_id="analytics",
        ),
        Workflow(
            "funnel-analysis",
            "Measure one delivered campaign from platform view through "
            "attributed lead using refreshed Buffer per-post metrics and "
            "read-only PostHog warehouse events on its preserved join keys.",
            (
                _step("validate", "analytics-operator",
                      "Validate the campaign is a delivered shared Artifact "
                      "with complete rendition identity (all ten "
                      "threads/youtube content_ids); a missing identity "
                      "makes the report incomplete.",
                      skill_ids=("analytics",)),
                _step("query", "analytics-operator",
                      "Query Buffer per-post metrics and PostHog batch "
                      "events on the preserved join keys (campaign_id, "
                      "batch_id, item_id, content_id, creative_signature).",
                      evidence_kind="posthog_query",
                      skill_ids=("analytics",),
                      connection_ids=("posthog", "buffer")),
                _step("segment", "analytics-operator",
                      "Segment by template dimension (template_breakdown) "
                      "with honesty rules: missing stays missing, never "
                      "zero; website events stay batch-level only.",
                      skill_ids=("analytics",)),
                _step("diagnose", "analytics-operator",
                      "Diagnose the funnel stages (attention → revenue) "
                      "with labeled-missing stages kept explicit.",
                      skill_ids=("analytics",)),
                _step("report", "analytics-operator",
                      "Apply analytics/funnel.py campaign_funnel_report "
                      "(strict identity match) and record evidence "
                      "{'funnel_report': {...}}.",
                      evidence_kind="funnel_report",
                      skill_ids=("analytics",),
                      connection_ids=("posthog",)),
            ),
            department_id="analytics",
        ),
        Workflow(
            "cro-experiment",
            "Propose and evaluate one bounded single-variable, A/B, "
            "factorial, or funnel experiment.",
            (
                _step("diagnose", "cro-optimizer",
                      "Diagnose from complete funnel evidence; pick the "
                      "one variable to test.",
                      skill_ids=("analytics", "copywriting")),
                _step("hypothesis", "cro-optimizer",
                      "Write the hypothesis: cells (control/variant), "
                      "assignment, primary metric, guardrails, minimum "
                      "evidence per cell, analysis method.",
                      skill_ids=("analytics", "copywriting")),
                _step("approve", "cro-optimizer",
                      "Park for owner approval before any website mutation "
                      "or experiment start (approval key "
                      "'start_experiment').",
                      approval_key="start_experiment"),
                _step("run", "cro-optimizer",
                      "Run the approved experiment and collect cell "
                      "evidence to the declared minimum.",
                      evidence_kind="cro_experiment",
                      skill_ids=("analytics", "copywriting"),
                      connection_ids=("website", "posthog")),
                _step("evaluate", "cro-optimizer",
                      "Evaluate effects per the experiment contract (1-3 "
                      "variables only with supported independent or "
                      "interaction effects); record evidence "
                      "{'cro_experiment': {...}}.",
                      skill_ids=("analytics",)),
            ),
            department_id="analytics",
        ),
        Workflow(
            "department-insight",
            "Feed validated metrics to another Department goal.",
            (
                _step("request", "analytics-operator",
                      "Receive the department's metric request and its "
                      "accepted evidence kinds.",
                      skill_ids=("analytics",)),
                _step("query", "analytics-operator",
                      "Query PostHog read-only for the requested metric "
                      "window.",
                      skill_ids=("analytics",),
                      connection_ids=("posthog",)),
                _step("validate", "analytics-operator",
                      "Validate completeness and comparability.",
                      skill_ids=("analytics",)),
                _step("attach", "analytics-operator",
                      "Attach the validated evidence to the requesting "
                      "goal as {'department_evidence': {...}}.",
                      evidence_kind="department_evidence",
                      skill_ids=("analytics",)),
            ),
            department_id="analytics",
        ),
    )

    evidence_metrics = {
        "scorecards": ("company_scorecard",),
        "funnel_reports": ("funnel_report",),
        "cro_experiments": ("cro_experiment",),
        "attributed_conversions": ("attributed_conversion",),
    }

    goal_schema = {
        "metrics": ["scorecards", "funnel_reports", "cro_experiments",
                    "attributed_conversions"],
        "config": {
            "workflow": {"enum": ["company-scorecard", "funnel-analysis",
                                  "cro-experiment", "department-insight"]},
            "required_count": {"type": "integer"},
            "connection": {"enum": ["posthog"]},
        },
    }

    workflow_agents = {
        "company-scorecard": "analytics-operator",
        "funnel-analysis": "analytics-operator",
        "cro-experiment": "cro-optimizer",
        "department-insight": "analytics-operator",
    }
