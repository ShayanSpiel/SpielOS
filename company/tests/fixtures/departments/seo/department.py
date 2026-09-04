"""SEO Department — clean migrated declaration (legacy v2.0.0 → clean core).

Migration notes (2026-09-02):
- Legacy WorkflowSpec ``steps`` labels (seeds, query, cluster, …) became
  real agent-bound WorkflowSteps with instructions, evidence kinds, and
  approval keys on the new clean core.
- ``approval_points`` like "modify_site" now live as explicit per-step
  ``approval_key`` values ("modify_site") — external actions park first.
- Legacy ``keywords.py`` (evidence-first opportunity math: never invent
  demand volume) stays department-local at ``seo/keywords.py``; the
  workflow step instructions reference it.
- Connections used: search-console (evidence), website (publishing).
"""

from __future__ import annotations

from ...workflows import Workflow, WorkflowStep


def _step(step_id: str, agent_id: str, instruction: str, *,
          evidence_kind: str | None = None, approval_key: str | None = None,
          skill_ids: tuple[str, ...] = (), connection_ids: tuple[str, ...] = (),
          requirements: dict | None = None) -> WorkflowStep:
    """Bounded helper building one clean WorkflowStep."""
    return WorkflowStep(
        id=step_id, agent_id=agent_id, instruction=instruction,
        evidence_kind=evidence_kind, approval_key=approval_key,
        skill_ids=skill_ids, connection_ids=connection_ids,
        requirements=requirements or {})


class SeoDepartment:
    """Declarative SEO capability package; execution belongs to GoalRuntime."""

    department_id = "seo"
    id = "seo"
    version = "2.1.0"
    description = (
        "Researches search demand, improves technical and on-page SEO for "
        "the SpielOS website, and evaluates Search Console evidence."
    )
    agent_ids = ("seo-researcher", "seo-operator")
    production_ready = True

    workflows = (
        Workflow(
            "keyword-research",
            "Build an evidence-backed ICP-aligned opportunity map without invented volume.",
            (
                _step("seeds", "seo-researcher",
                      "Collect ICP-aligned seed topics from strategy/icp.md. "
                      "Output the seed list in the work-order result payload "
                      "as {'seeds': [...]} — no invented demand numbers.",
                      evidence_kind="seed_topics",
                      skill_ids=("seo",),
                      connection_ids=("web-research",)),
                _step("query", "seo-researcher",
                      "Pull real query rows (keys, clicks, impressions) for "
                      "the seeds through the search-console Connection. Never "
                      "fabricate volumes; missing data stays 'unknown'.",
                      evidence_kind="search_console_query",
                      skill_ids=("seo",),
                      connection_ids=("search-console",)),
                _step("cluster", "seo-researcher",
                      "Group matched rows into normalized keyword clusters "
                      "using seo/keywords.py build_opportunities. Mark each "
                      "cluster 'measured' only when Search Console rows matched.",
                      skill_ids=("seo",)),
                _step("score", "seo-researcher",
                      "Score clusters by ICP fit and measured demand; keep "
                      "unknown demand explicitly unknown.",
                      skill_ids=("seo",)),
                _step("validate", "seo-researcher",
                      "Validate the opportunity map against Search Console "
                      "evidence and record {'keyword_opportunity': ..., "
                      "'keyword_opportunities': <int>} as evidence.",
                      evidence_kind="keyword_opportunity",
                      skill_ids=("seo",),
                      connection_ids=("search-console",)),
            ),
            department_id="seo",
        ),
        Workflow(
            "seo-content-brief",
            "Turn a validated opportunity into a content brief.",
            (
                _step("select", "seo-researcher",
                      "Select one validated keyword_opportunity from prior "
                      "evidence; state which one and why.",
                      skill_ids=("seo",)),
                _step("intent", "seo-researcher",
                      "Classify search intent and reader awareness level for "
                      "the selected opportunity.",
                      skill_ids=("seo", "copywriting")),
                _step("serp_evidence", "seo-researcher",
                      "Collect public SERP evidence for the query through "
                      "web-research; record sources.",
                      skill_ids=("seo",),
                      connection_ids=("web-research",)),
                _step("outline", "seo-researcher",
                      "Write the content brief outline following the "
                      "copywriting skill rules (no invented facts), and record "
                      "evidence {'seo_brief': {...}}.",
                      evidence_kind="seo_brief",
                      skill_ids=("seo", "copywriting")),
                _step("review", "seo-researcher",
                      "Self-review the brief against ICP, intent, and real "
                      "capabilities; finalize.",
                      skill_ids=("seo", "copywriting")),
            ),
            department_id="seo",
        ),
        Workflow(
            "technical-audit",
            "Audit crawl, index, canonical, locale, schema, and performance contracts.",
            (
                _step("crawl", "seo-operator",
                      "Crawl the live site surface (spielos.xyz) and collect "
                      "the page inventory.",
                      skill_ids=("seo",),
                      connection_ids=("web-research",)),
                _step("inspect", "seo-operator",
                      "Inspect metadata, canonicals, hreflang clusters, "
                      "structured data, sitemap, robots per the SEO skill "
                      "invariants.",
                      skill_ids=("seo",)),
                _step("prioritize", "seo-operator",
                      "Rank findings by evidence severity (errors before "
                      "warnings) and ICP impact.",
                      skill_ids=("seo",)),
                _step("brief", "seo-operator",
                      "Write the audit brief and record evidence "
                      "{'seo_audit': [...findings]}.",
                      evidence_kind="seo_audit",
                      skill_ids=("seo",)),
            ),
            department_id="seo",
        ),
        Workflow(
            "seo-improvement",
            "Apply one approved SEO change and measure its effect.",
            (
                _step("observe", "seo-operator",
                      "Observe current Search Console + audit evidence; "
                      "state the observed baseline.",
                      skill_ids=("seo", "analytics"),
                      connection_ids=("search-console",)),
                _step("propose", "seo-operator",
                      "Propose exactly one bounded SEO change with expected "
                      "effect and rollback.",
                      skill_ids=("seo",)),
                _step("approve", "seo-operator",
                      "Park for owner approval before any site modification "
                      "(approval key 'modify_site').",
                      approval_key="modify_site"),
                _step("implement", "seo-operator",
                      "Implement the approved change on the website through "
                      "the website Connection and record evidence "
                      "{'seo_change': {...}}.",
                      evidence_kind="seo_change",
                      skill_ids=("seo",),
                      connection_ids=("website",)),
                _step("measure", "seo-operator",
                      "Measure the effect through Search Console after the "
                      "change and report the delta.",
                      skill_ids=("seo", "analytics"),
                      connection_ids=("search-console",)),
            ),
            department_id="seo",
        ),
        Workflow(
            "search-performance",
            "Monitor queries, pages, CTR, position, and indexing changes.",
            (
                _step("query", "seo-operator",
                      "Pull current query/page/CTR/position rows through the "
                      "search-console Connection.",
                      evidence_kind="search_console_query",
                      skill_ids=("seo",),
                      connection_ids=("search-console",)),
                _step("validate", "seo-operator",
                      "Validate row completeness against the site inventory; "
                      "missing data stays unknown.",
                      skill_ids=("seo",)),
                _step("compare", "seo-operator",
                      "Compare against the prior period snapshot.",
                      skill_ids=("seo", "analytics")),
                _step("report", "seo-operator",
                      "Write the performance report and record evidence "
                      "{'seo_report': {...}, 'seo_reports': <int>}.",
                      evidence_kind="seo_report",
                      skill_ids=("seo", "analytics"),
                      connection_ids=("search-console",)),
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
