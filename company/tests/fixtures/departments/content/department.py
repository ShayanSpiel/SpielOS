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


class ContentDepartment:
    'Synthetic product acceptance fixture; never installed or executed as owner work.'

    department_id = "content"
    id = "content"
    version = "4.4.0"
    description = (
        'Synthetic Department for runtime acceptance checks.'
    )
    agent_ids = ("content-strategist", "content-writer", "publisher",
                 "video-producer")
    eval_suites = ("content-copy-top10", "content-story-whole")
    production_ready = False

    workflows = (
        Workflow(
            "content-package",
            'Synthetic workflow shape; no production implementation.',
            (
                _step("evidence", "content-strategist",
                      'Exercise this step using synthetic input; record fixture evidence only.',
                      evidence_kind="company_evidence",
                      skill_ids=()),
                _step("idea_lock", "content-strategist",
                      'Exercise this step using synthetic input; record fixture evidence only.',
                      skill_ids=()),
                _step("brief", "content-strategist",
                      'Exercise this step using synthetic input; record fixture evidence only.',
                      skill_ids=()),
                _step("produce", "content-writer",
                      'Exercise this step using synthetic input; record fixture evidence only.',
                      skill_ids=()),
                _step("review", "content-strategist",
                      'Exercise this step using synthetic input; record fixture evidence only.',
                      skill_ids=()),
                _step("package", "content-strategist",
                      'Exercise this step using synthetic input; record fixture evidence only.',
                      evidence_kind="content_package",
                      skill_ids=()),
            ),
            department_id="content",
        ),
        Workflow(
            "social-post",
            'Synthetic workflow shape; no production implementation.',
            (
                _step("idea_lock", "content-writer",
                      'Exercise this step using synthetic input; record fixture evidence only.',
                      skill_ids=()),
                _step("brief", "content-writer",
                      'Exercise this step using synthetic input; record fixture evidence only.',
                      skill_ids=()),
                _step("draft", "content-writer",
                      'Exercise this step using synthetic input; record fixture evidence only.',
                      evidence_kind="content_draft",
                      skill_ids=()),
                _step("edit", "content-writer",
                      'Exercise this step using synthetic input; record fixture evidence only.',
                      skill_ids=()),
                _step("approve", "content-writer",
                      'Exercise this step using synthetic input; record fixture evidence only.',
                      skill_ids=()),
            ),
            department_id="content",
        ),
        Workflow(
            "article",
            'Synthetic workflow shape; no production implementation.',
            (
                _step("idea_lock", "content-writer",
                      'Exercise this step using synthetic input; record fixture evidence only.',
                      skill_ids=()),
                _step("brief", "content-writer",
                      'Exercise this step using synthetic input; record fixture evidence only.',
                      skill_ids=()),
                _step("draft", "content-writer",
                      'Exercise this step using synthetic input; record fixture evidence only.',
                      evidence_kind="article_draft",
                      skill_ids=()),
                _step("edit", "content-writer",
                      'Exercise this step using synthetic input; record fixture evidence only.',
                      skill_ids=()),
                _step("seo_review", "content-writer",
                      'Exercise this step using synthetic input; record fixture evidence only.',
                      skill_ids=()),
                _step("approve", "content-writer",
                      'Exercise this step using synthetic input; record fixture evidence only.',
                      skill_ids=()),
            ),
            department_id="content",
        ),
        Workflow(
            "content-campaign",
            'Synthetic workflow shape; no production implementation.',
            (
                _step("simulation", "content-strategist",
                      'Exercise this step using synthetic input; record fixture evidence only.',
                      evidence_kind="simulation",
                      skill_ids=()),
                _step("human_reality", "content-strategist",
                      'Exercise this step using synthetic input; record fixture evidence only.',
                      evidence_kind="human_reality",
                      skill_ids=()),
                _step("discovery", "content-strategist",
                      'Exercise this step using synthetic input; record fixture evidence only.',
                      evidence_kind="discovery",
                      skill_ids=()),
                _step("draft", "content-writer",
                      'Exercise this step using synthetic input; record fixture evidence only.',
                      evidence_kind="content_draft",
                      skill_ids=()),
                _step("platform_edit", "content-writer",
                      'Exercise this step using synthetic input; record fixture evidence only.',
                      evidence_kind="campaign_manifest",
                      skill_ids=()),
                _step("quality_gate", "content-strategist",
                      'Exercise this step using synthetic input; record fixture evidence only.',
                      evidence_kind="campaign_ready",
                      skill_ids=(),
                      requirements={}),
                _step("render_handoff", "video-producer",
                      'Exercise this step using synthetic input; record fixture evidence only.',
                      evidence_kind="render_report",
                      skill_ids=(),
                      requirements={}),
                _step("approve", "content-strategist",
                      'Exercise this step using synthetic input; record fixture evidence only.',
                      approval_key="publish"),
                _step("dispatch", "publisher",
                      'Exercise this step using synthetic input; record fixture evidence only.',
                      evidence_kind="publication_receipt",
                      skill_ids=(),
                      connection_ids=()),
                _step("measure", "publisher",
                      'Exercise this step using synthetic input; record fixture evidence only.',
                      skill_ids=(),
                      connection_ids=()),
                _step("evaluate", "content-strategist",
                      'Exercise this step using synthetic input; record fixture evidence only.',
                      skill_ids=()),
            ),
            department_id="content",
        ),
        Workflow(
            "publish",
            'Synthetic workflow shape; no production implementation.',
            (
                _step("select", "publisher",
                      'Exercise this step using synthetic input; record fixture evidence only.',
                      skill_ids=()),
                _step("validate", "publisher",
                      'Exercise this step using synthetic input; record fixture evidence only.',
                      skill_ids=()),
                _step("approve", "publisher",
                      'Exercise this step using synthetic input; record fixture evidence only.',
                      approval_key="publish"),
                _step("dispatch", "publisher",
                      'Exercise this step using synthetic input; record fixture evidence only.',
                      evidence_kind="publication_receipt",
                      skill_ids=(),
                      connection_ids=()),
                _step("verify", "publisher",
                      'Exercise this step using synthetic input; record fixture evidence only.',
                      skill_ids=(),
                      connection_ids=()),
            ),
            department_id="content",
        ),
    )

    evidence_metrics = {
        "content_packages": ("content_package",),
        "approved_drafts": ("content_draft", "article_draft"),
        "published_items": ("publication_receipt",),
    }

    goal_schema = {
        "metrics": ["content_packages", "approved_drafts", "published_items"],
        "config": {
            "workflow": {"enum": ["content-package", "social-post", "article",
                                  "content-campaign", "publish"]},
            "required_count": {"type": "integer"},
            "connection": {"enum": ["buffer", "website"]},
            "execution_mode": {"enum": ["dry_run", "live"]},
        },
    }

    workflow_agents = {
        "content-package": "content-strategist",
        "content-campaign": "content-strategist",
        "social-post": "content-writer",
        "article": "content-writer",
        "publish": "publisher",
    }
