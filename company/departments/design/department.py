"""Production Design Department — declarative Lego package."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

from .._evidence import EvidenceDepartment
from ..campaign_contract import PLATFORMS, advance_campaign, creative_signature, validate_campaign
from ...runtime.models import Department, WorkflowSpec, WorkflowStep

# Machine-readable creative authority (read-only registry; see README).
REGISTRY_PATH = Path(__file__).resolve().parent / "templates" / "registry.json"
# Which creative kind each channel platform draws from.
PLATFORM_TEMPLATE_KIND = {"threads": "social", "youtube": "shorts"}


def _registered_archetypes() -> list[dict[str, Any]]:
    """The registered creative archetypes in registry order (read-only)."""
    registry = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    return list(registry.get("archetypes") or [])


def _template_fit_errors(manifest: dict[str, Any], platform: str) -> list[str]:
    """Reject known-bad or semantically mismatched gallery choices before render.

    Rotation is a coverage rule, not a creative decision.  A template may be
    registered and still be wrong for the story, or quarantined after a real
    media failure.  This gate keeps the renderer from silently accepting that
    mismatch and makes the choice auditable in the campaign Artifact.
    """
    errors: list[str] = []
    if platform != "youtube":
        return errors
    archetypes = {str(item.get("id")): item for item in _registered_archetypes()}
    fit_terms = {
        "loop-rail": ("process", "loop", "goal", "observe", "decide", "act", "evaluate"),
        "heartbeat": ("live", "running", "status", "current", "heartbeat", "today"),
        "department-map": ("department", "harness", "system", "roles"),
        "agent-brief": ("brief", "request", "intake", "assessment"),
        "scenario-b": ("workflow", "coordination", "tools", "handoff", "status", "intake"),
        "scenario-c": ("department", "role", "workflow", "context", "standard", "status"),
    }
    for item in manifest.get("items") or []:
        item_id = str(item.get("item_id") or "?")
        rendition = ((item.get("renditions") or {}).get(platform) or {})
        design = rendition.get("design") or {}
        template_id = str(design.get("template_id") or "")
        archetype = archetypes.get(template_id) or {}
        if manifest.get("media_quality_gate") == "strict" and archetype.get("status") == "quarantined":
            errors.append(
                f"items.{item_id}.renditions.{platform}.design.template_id {template_id!r} is quarantined: "
                f"{archetype.get('quarantine_reason', 'media QA required')}")
            continue
        terms = fit_terms.get(template_id)
        if not terms:
            continue
        text_parts: list[str] = [str(design.get("eyebrow") or ""), str(design.get("supporting_text") or "")]
        narration = rendition.get("narration") or {}
        text_parts.append(str(narration.get("script") or ""))
        text_parts.extend(str(scene.get("text") or "") for scene in narration.get("scenes") or [])
        story = " ".join(text_parts).lower()
        if not any(term in story for term in terms):
            errors.append(
                f"items.{item_id}.renditions.{platform}.design.template_id {template_id!r} does not fit the story; "
                f"expected one of: {', '.join(terms)}")
    return errors


def _rotation_errors(manifest: dict[str, Any]) -> list[str]:
    """Mechanically enforce the per-item archetype selection rule.

    Owner directive 2026-08-17 (Design README "Per-item selection rule"):
    one registered archetype per item/platform, no batch repeats when the
    batch fits the registry count, bounded round-robin balance otherwise,
    and bounded cell balance so no experiment cell is starved of a template
    family. Violating orders are rejected here — Design never falls back to
    legacy templates silently.
    """
    errors: list[str] = []
    archetypes = _registered_archetypes()
    by_kind: dict[str, list[str]] = {}
    for entry in archetypes:
        by_kind.setdefault(str(entry.get("kind") or ""), []).append(str(entry.get("id") or ""))
    items = manifest.get("items") or []
    for platform in PLATFORMS:
        kind = PLATFORM_TEMPLATE_KIND[platform]
        registered = by_kind.get(kind, [])
        # 1. One registered archetype per item_id per platform.
        chosen = []
        for item in items:
            item_id = str((item or {}).get("item_id") or "")
            rendition = ((item or {}).get("renditions") or {}).get(platform) or {}
            template_id = ((rendition.get("design") or {}).get("template_id"))
            chosen.append(template_id)
            if template_id not in registered:
                errors.append(
                    f"items.{item_id}.renditions.{platform}.design.template_id must be a "
                    f"registered {kind} archetype (got {template_id!r})")
        # 2. No batch repeats when the batch fits the registry count.
        batch_size = len(items)
        if batch_size <= len(registered):
            seen: dict[Any, list[str]] = {}
            for item, template_id in zip(items, chosen):
                item_id = str((item or {}).get("item_id") or "")
                seen.setdefault(template_id, []).append(item_id)
            repeats = {tid: ids for tid, ids in seen.items() if len(ids) > 1}
            for template_id, ids in repeats.items():
                errors.append(
                    f"no batch repeats for {platform}: template_id {template_id!r} is used by "
                    + ", ".join(ids))
        else:
            # 3. Larger batches repeat by round-robin across ALL archetypes of
            # the kind: counts differ by at most one and no template repeats
            # twice in a row.
            counts = Counter(chosen)
            if counts and max(counts.values()) - min(counts.values()) > 1:
                summary = ", ".join(f"{template_id!r} x{count}" for template_id, count
                                    in sorted(counts.items(), key=lambda pair: str(pair[0])))
                errors.append(
                    f"{platform} batch exceeds the registered {kind} archetype count; "
                    f"round-robin balance requires every archetype to appear at most one more "
                    f"time than any other (got {summary})")
            if any(left == right for left, right in zip(chosen, chosen[1:])):
                errors.append(
                    f"never the same template twice in a row for {platform} "
                    "(round-robin across ALL registered archetypes)")
        # 4. Bounded cell balance: neither experiment cell is starved of a
        # template family. Cells with two or more items must see at least two
        # distinct archetypes per platform. Item-to-cell assignment follows
        # the declared cell list cycled in item order (alternating control/
        # variant for the two-cell campaigns the loop runs).
        experiment = manifest.get("experiment") or {}
        cells = [cell for cell in (experiment.get("cells") or []) if isinstance(cell, dict)]
        roles = [cell.get("role") for cell in cells]
        if roles.count("control") == 1 and roles.count("variant") == 1:
            cell_items: dict[str, list[dict[str, Any]]] = {}
            for index, item in enumerate(items):
                cell_id = str(cells[index % len(cells)].get("id") or "?")
                cell_items.setdefault(cell_id, []).append(item)
            for cell in cells:
                cell_id = str(cell.get("id") or "?")
                members = cell_items.get(cell_id) or []
                if len(members) < 2:
                    continue
                distinct = {
                    (((member.get("renditions") or {}).get(platform) or {}).get("design") or {})
                    .get("template_id")
                    for member in members
                }
                if len(distinct) < 2:
                    errors.append(
                        f"unbalanced experiment cells: {platform} cell {cell_id!r} collapses to "
                        f"a single archetype {next(iter(distinct))!r} and is starved of a "
                        "template family")
        errors.extend(_template_fit_errors(manifest, platform))
    return errors


def validate_design_order(manifest: dict[str, Any]) -> list[str]:
    """Accept only a strategy-complete shared campaign Artifact.

    The per-item archetype rotation rule is mechanically enforced here
    (registry membership, no batch repeats, round-robin balance, bounded
    cell balance); a violating design order is rejected with a clear error
    instead of any silent fallback to legacy templates.
    """
    errors = validate_campaign(manifest, "strategy")
    if manifest.get("phase") != "strategy":
        errors.append("Design accepts campaign Artifacts only at the strategy phase")
    errors.extend(_rotation_errors(manifest))
    return errors


def accept_design_order(manifest: dict[str, Any]) -> dict[str, Any]:
    """Record Design ownership before any renderer can run."""
    errors = validate_design_order(manifest)
    if errors:
        raise ValueError("invalid Design order: " + "; ".join(errors))
    return advance_campaign(manifest, "designed", {"department": "design", "accepted": True})


def render_report(manifest: dict[str, Any], assets: list[dict[str, Any]]) -> dict[str, Any]:
    """Create Design's typed handoff without copying campaign copy or strategy."""
    errors = validate_campaign(manifest, "designed")
    if errors:
        raise ValueError("invalid Design order: " + "; ".join(errors))
    expected = {(item["item_id"], platform) for item in manifest["items"] for platform in PLATFORMS}
    indexed = {(str(asset.get("item_id")), str(asset.get("platform"))): asset for asset in assets}
    if set(indexed) != expected:
        raise ValueError("Design render evidence must contain exactly one asset for every item/platform pair")
    renditions = []
    for item in manifest["items"]:
        for platform in PLATFORMS:
            asset = indexed[(item["item_id"], platform)]
            for field in ("local_path", "sha256", "render_report_id"):
                if not asset.get(field):
                    raise ValueError(f"Design asset {item['item_id']}/{platform} needs {field}")
            rendition = item["renditions"][platform]
            renditions.append({
                "item_id": item["item_id"], "platform": platform,
                "content_id": rendition["content_id"],
                "creative_signature": creative_signature(
                    manifest["campaign_id"], item["item_id"], platform, rendition["design"]),
                "template_id": rendition["design"]["template_id"],
                "size_preset": rendition["design"]["size_preset"],
                "asset": dict(asset),
            })
    return {"schema_version": manifest["schema_version"],
            "campaign_id": manifest["campaign_id"], "batch_id": manifest["batch_id"],
            "source_phase": "designed", "target_phase": "rendered",
            "department": "design", "renditions": renditions}


class DesignDepartment(EvidenceDepartment, Department):
    id = department_id = "design"
    version = "3.4.0"
    description = "Consumes a shared campaign Artifact and returns verified renditions whose spoken text, displayed copy, components, icons, labels, timing, and evidence remain controlled by that one campaign identity."
    agent_ids = ("designer", "video-producer")
    production_ready = True
    workflows = (
        WorkflowSpec(
            "social-visual",
            "Render a focused platform-ready social graphic.",
            ("idea_lock", "brief", "compose", "render", "qa"), ("designer",), ("spielos-ui",), (),
            ("design_brief", "render_report"), (),
            graph=(WorkflowStep("render", "employee", "designer",
                                produces=("approved_design",), skill_ids=("spielos-ui",)),),
        ),
        WorkflowSpec(
            "rendition-pack",
            "Render every typed campaign rendition without owning or duplicating campaign strategy.",
            ("accept_design_order", "compose", "render_sizes", "visual_qa", "handoff"), ("designer",), ("spielos-ui",), (),
            ("design_order", "render_report"), (),
            graph=(WorkflowStep("render_sizes", "employee", "designer",
                                produces=("render_report",), skill_ids=("spielos-ui",)),),
        ),
        WorkflowSpec(
            "video-render",
            "Render and verify a focused design-system-aligned video.",
            ("idea_lock", "brief", "script", "animate", "render", "audio_mix", "qa"),
            ("video-producer",), ("video-creation", "spielos-ui"), (),
            ("video_render", "render_report"), (),
            graph=(WorkflowStep("render", "employee", "video-producer",
                                produces=("video_render",),
                                skill_ids=("video-creation", "spielos-ui")),),
        ),
        WorkflowSpec(
            "video-order",
            "Take a video order end-to-end: intake request, lock the One Idea, generate one-persona narration, derive readable scene dwell and total duration from measured speech, render a stable hook thumbnail, verify audible narration and provenance, and deliver video/thumbnail/QA together beneath the campaign batch Artifact.",
            ("intake", "idea_lock", "scenario_script", "tts_chain", "narration_mix", "render", "qa", "deliverable"),
            ("video-producer",), ("video-creation", "spielos-ui"), (),
            ("video_render", "render_report"), (),
            graph=(WorkflowStep("render", "employee", "video-producer",
                                produces=("video_render",),
                                skill_ids=("video-creation", "spielos-ui")),),
        ),
    )
    goal_schema = {"metrics": ["approved_designs", "rendition_count", "video_renders", "video_orders"],
                   "config": {"workflow": {"enum": [w.id for w in workflows]},
                              "required_count": {"type": "integer"}}}
    eval_suites = ("video-cta-link", "video-text-sync", "video-media-qa")
    evidence_metrics = {"approved_designs": ("approved_design",),
                        "rendition_count": ("render_report",),
                        "video_renders": ("video_render",),
                        "video_orders": ("video_render",)}
    workflow_agents = {"social-visual": "designer", "rendition-pack": "designer",
                       "video-render": "video-producer", "video-order": "video-producer"}
