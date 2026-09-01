"""Canonical company agent catalog.

Codex and OpenCode manifests are client adapters. These records are the stable
company identities that Departments reference in durable Workflow requests.

Built-in Agents live in AGENTS. Installed Department packages may add more under
agents/installed/*.json; those are merged at load time (installed wins on id clash
only when not already built-in — built-ins are protected).
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from .core import Agent, AgentExecutor, AgentResult, AgentSpec, FunctionExecutor


AGENTS = {
    item.id: item for item in (
        AgentSpec(
            id="lead-researcher",
            description="Finds, qualifies, researches, and records prospects against the canonical ICP.",
            skill_ids=("outbound-email",),
            permissions=("read_public_sources", "write_lead_evidence"),
            produces=("social_prospect", "email_prospect", "lead_dossier"),
        ),
        AgentSpec(
            id="social-researcher",
            description="Researches qualified LinkedIn and X prospects and recent public signals without bulk messaging.",
            skill_ids=("outbound-email", "outbound"),
            permissions=("read_public_sources", "write_social_evidence"),
            produces=("social_prospect", "social_signal"),
        ),
        AgentSpec(
            id="outreach-writer",
            description="Writes and validates personalized email and platform-native DM drafts.",
            skill_ids=("outbound-email", "copywriting"),
            permissions=("read_strategy", "read_lead_evidence", "write_drafts"),
            produces=("email_draft", "dm_draft"),
        ),
        AgentSpec(
            id="content-strategist",
            description="Turns the selected ICP, strategy, and evidence into a worldview and locked Content Brief.",
            skill_ids=("copywriting", "seo", "analytics"),
            permissions=("read_strategy", "read_company_evidence", "write_briefs"),
            produces=("content_worldview", "content_brief", "content_package"),
        ),
        AgentSpec(
            id="content-writer",
            description="Turns a locked Content Brief into platform-native posts, narrations, articles, and captions.",
            skill_ids=("copywriting", "translation-fa"),
            permissions=("read_strategy", "read_approved_assets", "write_drafts"),
            produces=("content_copy", "content_draft", "article_draft", "campaign_manifest"),
        ),
        AgentSpec(
            id="designer",
            description="Produces token-aligned graphics and rendition packs from approved design templates.",
            skill_ids=("spielos-ui",),
            permissions=("read_design_system", "read_approved_assets", "render_graphics"),
            produces=("approved_design", "graphic_render", "render_report"),
        ),
        AgentSpec(
            id="video-producer",
            description="Builds and verifies videos from approved HTML templates and source assets.",
            skill_ids=("video-creation", "copywriting"),
            permissions=("read_strategy", "read_approved_assets", "render_video"),
            produces=("video", "poster", "render_report"),
        ),
        AgentSpec(
            id="publisher",
            description="Validates, dispatches, and verifies approved content through registered publishing Connections.",
            skill_ids=("copywriting", "analytics"),
            permissions=("read_content_packages", "request_publish_approval", "use_publishing_connections"),
            produces=("publication_receipt",),
        ),
        AgentSpec(
            id="analytics-operator",
            description="Validates and reports company, funnel, attribution, and Department metrics.",
            skill_ids=("analytics",),
            permissions=("read_analytics", "query_posthog", "write_metric_evidence"),
            produces=("company_scorecard", "funnel_report", "department_evidence"),
        ),
        AgentSpec(
            id="cro-optimizer",
            description="Turns a validated funnel drop-off into one bounded conversion experiment.",
            skill_ids=("analytics", "copywriting", "spielos-ui"),
            permissions=("read_analytics", "propose_site_changes"),
            produces=("cro_experiment",),
        ),
        AgentSpec(
            id="seo-researcher",
            description="Builds ICP-aligned keyword opportunity maps and briefs from measured search evidence.",
            skill_ids=("seo", "analytics"),
            permissions=("read_strategy", "query_search_console", "write_seo_briefs"),
            produces=("keyword_opportunity", "seo_brief"),
        ),
        AgentSpec(
            id="seo-operator",
            description="Audits and improves search performance using the canonical strategy and measured evidence.",
            skill_ids=("seo", "analytics"),
            permissions=("read_strategy", "read_analytics", "propose_site_changes"),
            produces=("seo_audit", "seo_change_brief", "seo_evidence"),
        ),
        AgentSpec(
            id="delivery-manager",
            description="Owns Client Delivery intake, scoping, organization, verification, and handoff.",
            skill_ids=("client-delivery",),
            permissions=("read_strategy", "use_connection:activepieces",
                         "use_connection:google-drive", "use_connection:google-sheets",
                         "write_evidence"),
            produces=("order_brief", "workflow_spec", "workflow_delivery_record",
                      "demo_delivery_record"),
        ),
        AgentSpec(
            id="workflow-builder",
            description="Builds ActivePieces flows for real and demo Client Delivery orders.",
            skill_ids=("client-delivery",),
            permissions=("read_strategy", "use_connection:activepieces", "write_evidence"),
            produces=("flow_receipt",),
        ),
        AgentSpec(
            id="videography-specialist",
            description="Authors and validates humanistic demo scenarios from Client Delivery records.",
            skill_ids=("videography",),
            permissions=("read_strategy", "write_evidence"),
            produces=("demo_scenario",),
        ),
        AgentSpec(
            id="videography-operator",
            description="Runs the humanized recorder and renders showcase videos from browser sessions.",
            skill_ids=("videography",),
            permissions=("read_strategy", "write_evidence"),
            produces=("showcase_video",),
        ),
    )
}

_INSTALLED_DIR = Path(__file__).resolve().parent / "installed"

# Skills live in exactly two scopes: reusable company methods and
# Department-local methods. Department-specific methods live
# with the portable Department that uses them. There is no second skill tree.
#
#   company/skills/<id>/SKILL.md                   operator methods (director,
#                                                  department-runner, system-improvement)
#   company/departments/<id>/skills/<id>/SKILL.md  Department-bound methods

_PACKAGE_ROOT = Path(__file__).resolve().parents[1]
_DEPARTMENTS_ROOT = _PACKAGE_ROOT / "departments"
_OPERATOR_SKILLS_ROOT = _PACKAGE_ROOT / "skills"


def _skill_search_roots() -> list[Path]:
    roots = [root for root in (
        _OPERATOR_SKILLS_ROOT,
        *sorted(_DEPARTMENTS_ROOT.glob("*/skills")),
    ) if root.is_dir()]
    return roots


def skill_files() -> list[Path]:
    """Every installed SKILL.md across all skill locations."""

    found: list[Path] = []
    seen: set[str] = set()
    for root in _skill_search_roots():
        for path in sorted(root.glob("*/SKILL.md")):
            key = str(path)
            if key not in seen:
                seen.add(key)
                found.append(path)
    return found


def known_skill_ids() -> set[str]:
    """Skill ids (directory names owning a SKILL.md) anywhere."""

    return {path.parent.name for path in skill_files()}


def known_company_skill_ids() -> set[str]:
    """Skill ids Departments may bind — every discovered skill.

    Company methods are reusable; Department-local methods travel with their
    package. All discoverable skills are bindable.
    """

    return known_skill_ids()


def find_skill_dir(skill_id: str) -> Path | None:
    """Locate one skill directory by id across all discovery roots."""

    for root in _skill_search_roots():
        candidate = root / skill_id
        if (candidate / "SKILL.md").is_file():
            return candidate
    return None


def installed_agents_dir() -> Path:
    """Directory of installed Department Agents; tests may redirect it."""

    override = os.environ.get("SPIELOS_AGENTS_INSTALLED_ROOT")
    return Path(override) if override else _INSTALLED_DIR


def _load_installed_agents() -> dict[str, AgentSpec]:
    values: dict[str, AgentSpec] = {}
    root = installed_agents_dir()
    if not root.is_dir():
        return values
    for path in sorted(root.glob("*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        agent_id = str(payload.get("id") or "").strip()
        if not agent_id:
            continue
        skill_ids = payload.get("skill_ids")
        if skill_ids is None:  # schema 1 compatibility
            skill_ids = payload.get("skills") or ()
        produces = payload.get("produces")
        if produces is None:  # schema 1 compatibility
            produces = payload.get("evidence_kinds") or ("artifact",)
        permissions = payload.get("permissions")
        if permissions is None:
            permissions = ["read_strategy", "write_evidence", *(
                f"use_connection:{item}" for item in (payload.get("connections") or ()))]
        values[agent_id] = AgentSpec(
            id=agent_id,
            description=str(payload.get("description") or agent_id),
            skill_ids=tuple(str(item) for item in skill_ids),
            permissions=tuple(str(item) for item in permissions),
            produces=tuple(str(item) for item in produces),
        )
    return values


def agents() -> dict[str, AgentSpec]:
    """Built-in roster plus any installed Department Agents."""

    roster = dict(AGENTS)
    for agent_id, agent in _load_installed_agents().items():
        # Protect core identities; installed packages may only fill new ids.
        if agent_id not in roster:
            roster[agent_id] = agent
    return roster
