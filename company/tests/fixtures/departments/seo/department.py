'Synthetic product acceptance fixture; never installed or executed as owner work.'

from __future__ import annotations

from ...workflows import Workflow, WorkflowStep


def _step(step_id: str, agent_id: str, instruction: str, *,
          evidence_kind: str | None = None, approval_key: str | None = None,
          skill_ids: tuple[str, ...] = (), connection_ids: tuple[str, ...] = (),
          requirements: dict | None = None) -> WorkflowStep:
    'Synthetic product acceptance fixture; never installed or executed as owner work.'
    return WorkflowStep(
        id=step_id, agent_id=agent_id, instruction=instruction,
        evidence_kind=evidence_kind, approval_key=approval_key,
        skill_ids=skill_ids, connection_ids=connection_ids,
        requirements=requirements or {})


class SeoDepartment:
    'Synthetic product acceptance fixture; never installed or executed as owner work.'

    department_id = "seo"
    id = "seo"
    version = "2.1.0"
    description = (
        'Synthetic Department for runtime acceptance checks.'
    )
    agent_ids = ("seo-researcher", "seo-operator")
    production_ready = False

    workflows = (
        Workflow(
            "keyword-research",
            'Synthetic workflow shape; no production implementation.',
            (
                _step("seeds", "seo-researcher",
                      'Exercise this step using synthetic input; record fixture evidence only.',
                      evidence_kind="seed_topics",
                      skill_ids=(),
                      connection_ids=()),
                _step("query", "seo-researcher",
                      'Exercise this step using synthetic input; record fixture evidence only.',
                      evidence_kind="search_console_query",
                      skill_ids=(),
                      connection_ids=()),
                _step("cluster", "seo-researcher",
                      'Exercise this step using synthetic input; record fixture evidence only.',
                      skill_ids=()),
                _step("score", "seo-researcher",
                      'Exercise this step using synthetic input; record fixture evidence only.',
                      skill_ids=()),
                _step("validate", "seo-researcher",
                      'Exercise this step using synthetic input; record fixture evidence only.',
                      evidence_kind="keyword_opportunity",
                      skill_ids=(),
                      connection_ids=()),
            ),
            department_id="seo",
        ),
        Workflow(
            "seo-content-brief",
            'Synthetic workflow shape; no production implementation.',
            (
                _step("select", "seo-researcher",
                      'Exercise this step using synthetic input; record fixture evidence only.',
                      skill_ids=()),
                _step("intent", "seo-researcher",
                      'Exercise this step using synthetic input; record fixture evidence only.',
                      skill_ids=()),
                _step("serp_evidence", "seo-researcher",
                      'Exercise this step using synthetic input; record fixture evidence only.',
                      skill_ids=(),
                      connection_ids=()),
                _step("outline", "seo-researcher",
                      'Exercise this step using synthetic input; record fixture evidence only.',
                      evidence_kind="seo_brief",
                      skill_ids=()),
                _step("review", "seo-researcher",
                      'Exercise this step using synthetic input; record fixture evidence only.',
                      skill_ids=()),
            ),
            department_id="seo",
        ),
        Workflow(
            "technical-audit",
            'Synthetic workflow shape; no production implementation.',
            (
                _step("crawl", "seo-operator",
                      'Exercise this step using synthetic input; record fixture evidence only.',
                      skill_ids=(),
                      connection_ids=()),
                _step("inspect", "seo-operator",
                      'Exercise this step using synthetic input; record fixture evidence only.',
                      skill_ids=()),
                _step("prioritize", "seo-operator",
                      'Exercise this step using synthetic input; record fixture evidence only.',
                      skill_ids=()),
                _step("brief", "seo-operator",
                      'Exercise this step using synthetic input; record fixture evidence only.',
                      evidence_kind="seo_audit",
                      skill_ids=()),
            ),
            department_id="seo",
        ),
        Workflow(
            "seo-improvement",
            'Synthetic workflow shape; no production implementation.',
            (
                _step("observe", "seo-operator",
                      'Exercise this step using synthetic input; record fixture evidence only.',
                      skill_ids=(),
                      connection_ids=()),
                _step("propose", "seo-operator",
                      'Exercise this step using synthetic input; record fixture evidence only.',
                      skill_ids=()),
                _step("approve", "seo-operator",
                      'Exercise this step using synthetic input; record fixture evidence only.',
                      approval_key="modify_site"),
                _step("implement", "seo-operator",
                      'Exercise this step using synthetic input; record fixture evidence only.',
                      evidence_kind="seo_change",
                      skill_ids=(),
                      connection_ids=()),
                _step("measure", "seo-operator",
                      'Exercise this step using synthetic input; record fixture evidence only.',
                      skill_ids=(),
                      connection_ids=()),
            ),
            department_id="seo",
        ),
        Workflow(
            "search-performance",
            'Synthetic workflow shape; no production implementation.',
            (
                _step("query", "seo-operator",
                      'Exercise this step using synthetic input; record fixture evidence only.',
                      evidence_kind="search_console_query",
                      skill_ids=(),
                      connection_ids=()),
                _step("validate", "seo-operator",
                      'Exercise this step using synthetic input; record fixture evidence only.',
                      skill_ids=()),
                _step("compare", "seo-operator",
                      'Exercise this step using synthetic input; record fixture evidence only.',
                      skill_ids=()),
                _step("report", "seo-operator",
                      'Exercise this step using synthetic input; record fixture evidence only.',
                      evidence_kind="seo_report",
                      skill_ids=(),
                      connection_ids=()),
            ),
            department_id="seo",
        ),
    )

    evidence_metrics = {
        "keyword_opportunities": ("keyword_opportunity",),
        "seo_briefs": ("seo_brief",),
        "seo_reports": ("seo_report",),
        "indexed_pages": ("indexed_page",),
        "seo_audits": ("seo_audit",),
        "seo_changes": ("seo_change",),
    }

    goal_schema = {
        "metrics": ["keyword_opportunities", "seo_briefs", "seo_reports",
                    "indexed_pages", "seo_audits", "seo_changes"],
        "config": {
            "workflow": {"enum": ["keyword-research", "seo-content-brief",
                                  "technical-audit", "seo-improvement",
                                  "search-performance"]},
            "required_count": {"type": "integer"},
            "connection": {"enum": ["search-console"]},
        },
    }

    workflow_agents = {
        "keyword-research": "seo-researcher",
        "seo-content-brief": "seo-researcher",
        "technical-audit": "seo-operator",
        "seo-improvement": "seo-operator",
        "search-performance": "seo-operator",
    }
