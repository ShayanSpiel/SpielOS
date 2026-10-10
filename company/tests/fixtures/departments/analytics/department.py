'Synthetic product acceptance fixture; never installed or executed as owner work.'

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
    'Synthetic product acceptance fixture; never installed or executed as owner work.'

    department_id = "analytics"
    id = "analytics"
    version = "3.4.0"
    description = (
        'Synthetic Department for runtime acceptance checks.'
    )
    agent_ids = ("analytics-operator", "cro-optimizer")
    production_ready = False

    workflows = (
        Workflow(
            "company-scorecard",
            'Synthetic workflow shape; no production implementation.',
            (
                _step("collect", "analytics-operator",
                      'Exercise this step using synthetic input; record fixture evidence only.',
                      skill_ids=(),
                      connection_ids=()),
                _step("validate", "analytics-operator",
                      'Exercise this step using synthetic input; record fixture evidence only.',
                      skill_ids=()),
                _step("calculate", "analytics-operator",
                      'Exercise this step using synthetic input; record fixture evidence only.',
                      skill_ids=()),
                _step("report", "analytics-operator",
                      'Exercise this step using synthetic input; record fixture evidence only.',
                      evidence_kind="company_scorecard",
                      skill_ids=(),
                      connection_ids=()),
            ),
            department_id="analytics",
        ),
        Workflow(
            "funnel-analysis",
            'Synthetic workflow shape; no production implementation.',
            (
                _step("validate", "analytics-operator",
                      'Exercise this step using synthetic input; record fixture evidence only.',
                      skill_ids=()),
                _step("query", "analytics-operator",
                      'Exercise this step using synthetic input; record fixture evidence only.',
                      evidence_kind="posthog_query",
                      skill_ids=(),
                      connection_ids=()),
                _step("segment", "analytics-operator",
                      'Exercise this step using synthetic input; record fixture evidence only.',
                      skill_ids=()),
                _step("diagnose", "analytics-operator",
                      'Exercise this step using synthetic input; record fixture evidence only.',
                      skill_ids=()),
                _step("report", "analytics-operator",
                      'Exercise this step using synthetic input; record fixture evidence only.',
                      evidence_kind="funnel_report",
                      skill_ids=(),
                      connection_ids=()),
            ),
            department_id="analytics",
        ),
        Workflow(
            "cro-experiment",
            'Synthetic workflow shape; no production implementation.',
            (
                _step("diagnose", "cro-optimizer",
                      'Exercise this step using synthetic input; record fixture evidence only.',
                      skill_ids=()),
                _step("hypothesis", "cro-optimizer",
                      'Exercise this step using synthetic input; record fixture evidence only.',
                      skill_ids=()),
                _step("approve", "cro-optimizer",
                      'Exercise this step using synthetic input; record fixture evidence only.',
                      approval_key="start_experiment"),
                _step("run", "cro-optimizer",
                      'Exercise this step using synthetic input; record fixture evidence only.',
                      evidence_kind="cro_experiment",
                      skill_ids=(),
                      connection_ids=()),
                _step("evaluate", "cro-optimizer",
                      'Exercise this step using synthetic input; record fixture evidence only.',
                      skill_ids=()),
            ),
            department_id="analytics",
        ),
        Workflow(
            "department-insight",
            'Synthetic workflow shape; no production implementation.',
            (
                _step("request", "analytics-operator",
                      'Exercise this step using synthetic input; record fixture evidence only.',
                      skill_ids=()),
                _step("query", "analytics-operator",
                      'Exercise this step using synthetic input; record fixture evidence only.',
                      skill_ids=(),
                      connection_ids=()),
                _step("validate", "analytics-operator",
                      'Exercise this step using synthetic input; record fixture evidence only.',
                      skill_ids=()),
                _step("attach", "analytics-operator",
                      'Exercise this step using synthetic input; record fixture evidence only.',
                      evidence_kind="department_evidence",
                      skill_ids=()),
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
