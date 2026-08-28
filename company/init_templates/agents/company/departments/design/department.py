"""Production Design Department — declarative Lego package."""

from __future__ import annotations

import json
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
    """Reject only templates explicitly quarantined after media failure.

    Story fit is editorial judgment, not a brittle keyword classifier.
    """
    errors: list[str] = []
    if platform != "youtube":
        return errors
    archetypes = {str(item.get("id")): item for item in _registered_archetypes()}
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
    return errors


def _rotation_errors(manifest: dict[str, Any]) -> list[str]:
    """Require registered templates and avoid repeats in a normal-size batch."""
    errors: list[str] = []
    archetypes = _registered_archetypes()
    by_kind: dict[str, list[str]] = {}
    for entry in archetypes:
        by_kind.setdefault(str(entry.get("kind") or ""), []).append(str(entry.get("id") or ""))
    items = manifest.get("items") or []
    for platform in PLATFORMS:
        kind = PLATFORM_TEMPLATE_KIND[platform]
        registered = by_kind.get(kind, [])
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
        if len(chosen) <= len(registered):
            for template_id in {item for item in chosen if chosen.count(item) > 1}:
                errors.append(f"no batch repeats for {platform}: template_id {template_id!r}")
        errors.extend(_template_fit_errors(manifest, platform))
    return errors


def validate_design_order(manifest: dict[str, Any]) -> list[str]:
    """Accept a Content-ready campaign and validate its selected templates."""
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
    version = "3.5.0"
    description = "Consumes Content-ready copy, selects registered templates, renders media, and returns verified evidence."
    agent_ids = ("designer", "video-producer")
    production_ready = True
    workflows = (
        WorkflowSpec(
            "social-visual",
            "Render a focused platform-ready social graphic.",
            ("idea_lock", "brief", "compose", "render", "qa"), ("designer",), ("spielos-ui",), (),
            ("design_brief", "render_report", "content_ready"), (),
            graph=(WorkflowStep("render", "employee", "designer",
                                produces=("approved_design",), skill_ids=("spielos-ui",)),),
        ),
        WorkflowSpec(
            "rendition-pack",
            "Turn a Content-ready campaign into verified renditions.",
            ("plan", "render", "verify", "handoff"), ("designer",), ("spielos-ui",), (),
            ("content_ready", "render_report"), (),
            graph=(WorkflowStep("render_sizes", "employee", "designer",
                                produces=("render_report",), skill_ids=("spielos-ui",)),),
        ),
        WorkflowSpec(
            "video-render",
            "Render and verify a focused design-system-aligned video.",
            ("idea_lock", "brief", "script", "animate", "render", "audio_mix", "qa"),
            ("video-producer",), ("video-creation", "spielos-ui"), (),
            ("video_render", "render_report", "content_ready"), (),
            graph=(WorkflowStep("render", "employee", "video-producer",
                                produces=("video_render",),
                                skill_ids=("video-creation", "spielos-ui")),),
        ),
        WorkflowSpec(
            "video-order",
            "Render one approved narration into a verified video rendition.",
            ("plan", "generate", "render", "verify", "deliver"),
            ("video-producer",), ("video-creation", "spielos-ui"), (),
            ("video_render", "render_report", "content_ready"), (),
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
