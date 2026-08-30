"""Canonical company agent catalog.

Codex and OpenCode manifests are client adapters. These records are the stable
company identities that Workgroups reference in durable Workflow requests.

Built-in employees live in AGENTS. Installed Lego packages may add more under
agents/installed/*.json; those are merged at load time (installed wins on id clash
only when not already built-in — built-ins are protected).
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from ..runtime.models import AgentSpec


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
            skill_ids=("outbound-email", "copywriting-en", "copywriting-fa"),
            permissions=("read_strategy", "read_lead_evidence", "write_drafts"),
            produces=("email_draft", "dm_draft"),
        ),
        AgentSpec(
            id="content-strategist",
            description="Turns the selected ICP, strategy, and evidence into a worldview and locked Content Brief.",
            skill_ids=("copywriting-en", "seo", "analytics"),
            permissions=("read_strategy", "read_company_evidence", "write_briefs"),
            produces=("content_worldview", "content_brief", "content_package"),
        ),
        AgentSpec(
            id="content-writer",
            description="Turns a locked Content Brief into platform-native posts, narrations, articles, and captions.",
            skill_ids=("copywriting-en", "copywriting-fa", "translation-fa"),
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
            skill_ids=("video-creation", "copywriting-en"),
            permissions=("read_strategy", "read_approved_assets", "render_video"),
            produces=("video", "poster", "render_report"),
        ),
        AgentSpec(
            id="publisher",
            description="Validates, dispatches, and verifies approved content through registered publishing Connections.",
            skill_ids=("copywriting-en", "analytics"),
            permissions=("read_content_packages", "request_publish_approval", "use_publishing_connections"),
            produces=("publication_receipt",),
        ),
        AgentSpec(
            id="analytics-operator",
            description="Validates and reports company, funnel, attribution, and Workgroup metrics.",
            skill_ids=("analytics",),
            permissions=("read_analytics", "query_posthog", "write_metric_evidence"),
            produces=("company_scorecard", "funnel_report", "workgroup_evidence"),
        ),
        AgentSpec(
            id="cro-optimizer",
            description="Turns a validated funnel drop-off into one bounded conversion experiment.",
            skill_ids=("analytics", "copywriting-en", "spielos-ui"),
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
    )
}

_INSTALLED_DIR = Path(__file__).resolve().parent / "installed"

# Skills live in two namespaces under .agents/skills/: company/ (harness
# operation: Director and system improvement) and website/ (site-bound methods).
# Resolution is recursive so callers never depend on the namespace layout.
# Skill discovery: skills live INSIDE the thing that uses them.
#
#   company/skills/<id>/SKILL.md                   operator methods (director,
#                                                  workgroup-runner, system-improvement)
#   company/workgroups/<id>/skills/<id>/SKILL.md   Workgroup-bound methods
#   company/workgroups/_shared/skills/<id>/        shared by Workgroups
#                                                  (e.g. copywriting-en/fa)
#
# Vendored homes may also carry the legacy .agents/skills/{company,website}/
# layout; those roots are still scanned for backward compatibility.

_PACKAGE_ROOT = Path(__file__).resolve().parents[1]
_WORKGROUPS_ROOT = _PACKAGE_ROOT / "workgroups"
_OPERATOR_SKILLS_ROOT = _PACKAGE_ROOT / "skills"
_LEGACY_SKILLS_ROOT = _PACKAGE_ROOT.parents[1] / ".agents" / "skills"


def _skill_search_roots() -> list[Path]:
    roots = [root for root in (
        _OPERATOR_SKILLS_ROOT,
        _WORKGROUPS_ROOT / "_shared" / "skills",
        *sorted(_WORKGROUPS_ROOT.glob("*/skills")),
    ) if root.is_dir()]
    if _LEGACY_SKILLS_ROOT.is_dir():
        roots.extend(sorted(_LEGACY_SKILLS_ROOT.glob("*")))
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
    """Skill ids Workgroups may bind — every discovered skill.

    Workgroups own their methods, so the historical company/website
    namespace split no longer exists; all discoverable skills are bindable.
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
    """Directory of installed Lego employees; tests may redirect it."""

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
    """Built-in roster plus any installed Lego employees."""

    roster = dict(AGENTS)
    for agent_id, agent in _load_installed_agents().items():
        # Protect core identities; installed packages may only fill new ids.
        if agent_id not in roster:
            roster[agent_id] = agent
    return roster
