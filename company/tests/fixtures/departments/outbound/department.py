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


class OutboundDepartment:
    'Synthetic product acceptance fixture; never installed or executed as owner work.'

    department_id = "outbound"
    id = "outbound"
    version = "4.0.0"
    description = (
        'Synthetic Department for runtime acceptance checks.'
    )
    agent_ids = ("lead-researcher", "social-researcher", "outreach-writer")
    production_ready = False

    workflows = (
        Workflow(
            "lead-research",
            'Synthetic workflow shape; no production implementation.',
            (
                _step("discover", "lead-researcher",
                      'Exercise this step using synthetic input; record fixture evidence only.',
                      skill_ids=(),
                      connection_ids=()),
                _step("qualify", "lead-researcher",
                      'Exercise this step using synthetic input; record fixture evidence only.',
                      skill_ids=()),
                _step("research", "lead-researcher",
                      'Exercise this step using synthetic input; record fixture evidence only.',
                      skill_ids=(),
                      connection_ids=()),
                _step("verify", "lead-researcher",
                      'Exercise this step using synthetic input; record fixture evidence only.',
                      evidence_kind="verification_result",
                      skill_ids=()),
                _step("record", "lead-researcher",
                      'Exercise this step using synthetic input; record fixture evidence only.',
                      evidence_kind="lead_dossier",
                      skill_ids=(),
                      connection_ids=()),
            ),
            department_id="outbound",
        ),
        Workflow(
            "email-outreach",
            'Synthetic workflow shape; no production implementation.',
            (
                _step("select", "lead-researcher",
                      'Exercise this step using synthetic input; record fixture evidence only.',
                      skill_ids=(),
                      connection_ids=()),
                _step("compose", "outreach-writer",
                      'Exercise this step using synthetic input; record fixture evidence only.',
                      skill_ids=()),
                _step("validate", "outreach-writer",
                      'Exercise this step using synthetic input; record fixture evidence only.',
                      skill_ids=()),
                _step("approve", "outreach-writer",
                      'Exercise this step using synthetic input; record fixture evidence only.',
                      approval_key="send"),
                _step("send", "outreach-writer",
                      'Exercise this step using synthetic input; record fixture evidence only.',
                      evidence_kind="provider_events",
                      skill_ids=(),
                      connection_ids=()),
                _step("measure", "lead-researcher",
                      'Exercise this step using synthetic input; record fixture evidence only.',
                      evidence_kind="reply",
                      skill_ids=(),
                      connection_ids=()),
            ),
            department_id="outbound",
        ),
        Workflow(
            "social-lead-research",
            'Synthetic workflow shape; no production implementation.',
            (
                _step("discover", "social-researcher",
                      'Exercise this step using synthetic input; record fixture evidence only.',
                      skill_ids=(),
                      connection_ids=()),
                _step("qualify", "social-researcher",
                      'Exercise this step using synthetic input; record fixture evidence only.',
                      skill_ids=()),
                _step("research", "social-researcher",
                      'Exercise this step using synthetic input; record fixture evidence only.',
                      skill_ids=(),
                      connection_ids=()),
                _step("validate", "social-researcher",
                      'Exercise this step using synthetic input; record fixture evidence only.',
                      skill_ids=()),
                _step("record", "social-researcher",
                      'Exercise this step using synthetic input; record fixture evidence only.',
                      evidence_kind="social_prospect",
                      skill_ids=(),
                      connection_ids=()),
            ),
            department_id="outbound",
        ),
        Workflow(
            "social-dm",
            'Synthetic workflow shape; no production implementation.',
            (
                _step("select", "social-researcher",
                      'Exercise this step using synthetic input; record fixture evidence only.',
                      skill_ids=(),
                      connection_ids=()),
                _step("draft", "outreach-writer",
                      'Exercise this step using synthetic input; record fixture evidence only.',
                      evidence_kind="dm_draft",
                      skill_ids=()),
                _step("validate", "outreach-writer",
                      'Exercise this step using synthetic input; record fixture evidence only.',
                      skill_ids=()),
                _step("approve", "outreach-writer",
                      'Exercise this step using synthetic input; record fixture evidence only.',
                      approval_key="external_send"),
                _step("export", "outreach-writer",
                      'Exercise this step using synthetic input; record fixture evidence only.',
                      skill_ids=()),
                _step("measure", "outreach-writer",
                      'Exercise this step using synthetic input; record fixture evidence only.',
                      evidence_kind="reply",
                      skill_ids=(),
                      connection_ids=()),
            ),
            department_id="outbound",
        ),
    )

    workflow_agents = {
        "lead-research": "lead-researcher",
        "email-outreach": "outreach-writer",
        "social-lead-research": "social-researcher",
        "social-dm": "outreach-writer",
    }

    evidence_metrics = {
        "qualified_social_leads": ("social_prospect",),
        "approved_dm_drafts": ("dm_draft",),
        "lead_dossiers": ("lead_dossier",),
        "email_batches_sent": ("provider_events",),
        "replies": ("reply",),
    }

    goal_schema = {
        "metrics": ["reply_rate", "positive_reply_rate", "booked_calls",
                    "sales", "qualified_social_leads", "approved_dm_drafts",
                    "lead_dossiers", "email_batches_sent", "replies"],
        "config": {
            "execution_mode": {"enum": ["dry_run", "live"],
                               "required_when": {"workflow": "email-outreach"}},
            "workflow": {"enum": ["email-outreach", "social-lead-research",
                                   "social-dm", "lead-research"]},
            "required_count": {"type": "integer"},
            "batch_size": {"type": "integer",
                           "description": "Required eligible leads for one "
                                          "complete run"},
            "evidence_window_hours": {"type": "number",
                                      "required_when": {"execution_mode": "live"}},
            "knobs": {"type": "object",
                      "description": "Per-goal overrides of Outbound "
                                     "campaign knobs"},
            "audience_type": {"enum": ["business", "test_inbox"]},
            "test_recipients": {"type": "array",
                                "required_when": {"audience_type": "test_inbox"}},
            "reply_capture": {"enum": ["manual_inbox", "resend_inbound",
                                       "gmail_inbox"]},
        },
    }
