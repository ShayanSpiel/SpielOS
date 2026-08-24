"""Production SEO Department — declarative Lego package."""

from .._evidence import EvidenceDepartment
from ...runtime.models import Department, WorkflowSpec, WorkflowStep


class SeoDepartment(EvidenceDepartment, Department):
    id = department_id = "seo"
    version = "2.0.0"
    description = "Researches search demand, improves technical and on-page SEO, and evaluates Search Console evidence."
    agent_ids = ("seo-researcher", "seo-operator")
    production_ready = True
    workflows = (
        WorkflowSpec(
            "keyword-research",
            "Build an evidence-backed ICP-aligned opportunity map without invented volume.",
            ("seeds", "query", "cluster", "score", "validate"), ("seo-researcher",), ("seo",), (),
            ("search_console_query", "keyword_opportunity"), ("search-console",),
            graph=(WorkflowStep("validate", "employee", "seo-researcher",
                                produces=("keyword_opportunity",), skill_ids=("seo",),
                                connection_ids=("search-console",)),),
        ),
        WorkflowSpec(
            "seo-content-brief",
            "Turn a validated opportunity into a content brief.",
            ("select", "intent", "serp_evidence", "outline", "review"), ("seo-researcher",),
            ("seo", "copywriting-en"), (), ("keyword_opportunity", "seo_brief"), (),
            graph=(WorkflowStep("outline", "employee", "seo-researcher",
                                produces=("seo_brief",),
                                requires=("keyword_opportunity",),
                                skill_ids=("seo", "copywriting-en")),),
        ),
        WorkflowSpec(
            "technical-audit",
            "Audit crawl, index, canonical, locale, schema, and performance contracts.",
            ("crawl", "inspect", "prioritize", "brief"), ("seo-operator",), ("seo",), (),
            ("site_audit", "search_console_query"), ("search-console",),
            graph=(WorkflowStep("brief", "employee", "seo-operator",
                                produces=("seo_audit",), skill_ids=("seo",)),),
        ),
        WorkflowSpec(
            "seo-improvement",
            "Apply one approved SEO change and measure its effect.",
            ("observe", "propose", "approve", "implement", "measure"), ("seo-operator",),
            ("seo", "analytics"), ("modify_site",), ("seo_change", "search_console_query"),
            ("website", "search-console"),
            graph=(
                WorkflowStep("approve", "approval"),
                WorkflowStep("implement", "employee", "seo-operator",
                             produces=("seo_change",), skill_ids=("seo", "analytics")),
            ),
        ),
        WorkflowSpec(
            "search-performance",
            "Monitor queries, pages, CTR, position, and indexing changes.",
            ("query", "validate", "compare", "report"), ("seo-operator",), ("seo", "analytics"), (),
            ("search_console_query", "seo_report"), ("search-console",),
            graph=(WorkflowStep("report", "employee", "seo-operator",
                                produces=("seo_report",), skill_ids=("seo", "analytics"),
                                connection_ids=("search-console",)),),
        ),
    )
    goal_schema = {"metrics": ["keyword_opportunities", "seo_briefs", "seo_reports", "indexed_pages"],
                   "config": {"workflow": {"enum": [w.id for w in workflows]},
                              "required_count": {"type": "integer"},
                              "connection": {"enum": ["search-console"]}}}
    evidence_metrics = {"keyword_opportunities": ("keyword_opportunity",),
                        "seo_briefs": ("seo_brief",), "seo_reports": ("seo_report",),
                        "indexed_pages": ("indexed_page",)}
    workflow_agents = {"keyword-research": "seo-researcher", "seo-content-brief": "seo-researcher",
                       "technical-audit": "seo-operator", "seo-improvement": "seo-operator",
                       "search-performance": "seo-operator"}
