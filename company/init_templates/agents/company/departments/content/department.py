"""Production Content Department — declarative Lego package."""

from __future__ import annotations

import hashlib
import re
from typing import Any
from urllib.parse import parse_qs, urlparse

from ...runtime.evidence_department import EvidenceDepartment
from ...runtime.campaign_contract import (
    COMPATIBLE_SCHEMA_VERSIONS,
    SCHEMA_VERSION as CAMPAIGN_SCHEMA_VERSION,
    SPIELOS_NOTE,
    publication_package,
    validate_campaign,
)
# Compatibility export for older callers; rotation itself belongs to Design.
from ..design.department import _rotation_errors as _design_rotation_errors
from ...runtime.models import Department, WorkflowSpec, WorkflowStep


DAILY_PLATFORM_TARGET = 50
BATCH_SIZE = 5
PLATFORM_RULES = {
    "threads": {"asset_type": "image", "size_preset": "threads-portrait"},
    "youtube": {"asset_type": "video", "size_preset": "youtube-shorts"},
}
VARIATION_FIELDS = ("format", "layout", "theme", "background", "color_role", "alignment")
SEMANTIC_COLOR_ROLES = {"primary", "accent", "purple", "info", "success", "warning"}
SEMANTIC_BACKGROUNDS = {"background", "panel", "panel-raised", "panel-strong", "panel-deep"}

PUBLICATION_RECEIPT_CONTRACT = "publication_receipt is final; scheduled or sent is a commitment"


def _compact(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip().lower())


def _variation_signature(idea: str, item: dict[str, Any]) -> str:
    variation = item.get("creative_variation") or {}
    source = "|".join([_compact(idea), _compact(item.get("platform"))] + [
        _compact(variation.get(field)) for field in VARIATION_FIELDS
    ])
    return hashlib.sha256(source.encode("utf-8")).hexdigest()[:16]


def _validate_single_campaign(package: dict[str, Any], prior_packages: list[dict[str, Any]] | None = None) -> list[str]:
    errors: list[str] = []
    idea = str(package.get("one_idea") or package.get("idea") or "").strip()
    if not idea:
        errors.append("Campaign needs one locked buyer-relevant idea")
    items = package.get("platform_packages")
    if not isinstance(items, list) or not items:
        return errors + ["Campaign needs platform_packages for Threads and YouTube Shorts"]
    seen_platforms: set[str] = set()
    signatures: set[str] = set()
    prior_signatures = {
        str(item.get("creative_signature"))
        for prior in prior_packages or []
        for item in (prior.get("platform_packages") or [])
        if item.get("creative_signature")
    }
    for index, item in enumerate(items, start=1):
        if not isinstance(item, dict):
            errors.append(f"Platform package {index} must be an object")
            continue
        platform = _compact(item.get("platform"))
        rule = PLATFORM_RULES.get(platform)
        if not rule:
            errors.append(f"Platform package {index} must target threads or youtube")
            continue
        seen_platforms.add(platform)
        text = str(item.get("text") or item.get("description") or "").strip()
        if not text.endswith(SPIELOS_NOTE):
            errors.append(f"{platform} description must end with the SpielOS note")
        destination = str(item.get("destination") or "").strip()
        parsed = urlparse(destination)
        if parsed.scheme != "https" or parsed.netloc != "spielos.xyz" or parsed.path.rstrip("/") not in {"/services", "/contact"}:
            errors.append(f"{platform} destination must be a tracked https://spielos.xyz/services/ or /contact/ URL")
        else:
            params = parse_qs(parsed.query)
            required = {"utm_source": platform, "utm_medium": "social", "utm_campaign": None, "utm_content": None}
            for key, expected in required.items():
                actual = (params.get(key) or [""])[0]
                if not actual or (expected and actual != expected):
                    errors.append(f"{platform} destination needs {key}={expected or 'a unique value'}")
        if destination and destination not in text:
            errors.append(f"{platform} text must include its tracked destination")
        asset = item.get("asset") or {}
        if asset.get("type") != rule["asset_type"] or not str(asset.get("url") or "").startswith("https://"):
            errors.append(f"{platform} needs a public {rule['asset_type']} asset URL")
        variation = item.get("creative_variation") or {}
        missing = [field for field in VARIATION_FIELDS if not _compact(variation.get(field))]
        if missing:
            errors.append(f"{platform} creative variation is missing: {', '.join(missing)}")
        if variation.get("background") not in SEMANTIC_BACKGROUNDS:
            errors.append(f"{platform} background must use a website semantic surface token")
        if variation.get("color_role") not in SEMANTIC_COLOR_ROLES:
            errors.append(f"{platform} color_role must use a website semantic color role")
        if "#" in " ".join(map(str, variation.values())) or "rgb(" in " ".join(map(str, variation.values())).lower():
            errors.append(f"{platform} creative variation must not use raw colors")
        if variation.get("size_preset") and variation["size_preset"] != rule["size_preset"]:
            errors.append(f"{platform} must use the {rule['size_preset']} design rendition")
        signature = _variation_signature(idea, item)
        if signature in signatures or signature in prior_signatures:
            errors.append(f"{platform} repeats an existing creative template for this idea")
        signatures.add(signature)
    missing_platforms = set(PLATFORM_RULES) - seen_platforms
    if missing_platforms:
        errors.append("Campaign must include: " + ", ".join(sorted(missing_platforms)))
    return errors


def _prior_signatures(packages: list[dict[str, Any]] | None) -> set[str]:
    signatures = set()
    for package in packages or []:
        entries = package.get("batch_items") or [package]
        for entry in entries:
            idea = str(entry.get("one_idea") or entry.get("idea") or "")
            for item in entry.get("platform_packages") or []:
                signatures.add(str(item.get("creative_signature") or _variation_signature(idea, item)))
    return signatures


def _validate_batch(package: dict[str, Any], prior_packages: list[dict[str, Any]] | None) -> list[str]:
    errors: list[str] = []
    if package.get("daily_targets") != {"threads": DAILY_PLATFORM_TARGET, "youtube": DAILY_PLATFORM_TARGET}:
        errors.append("Batch must declare the 50 Threads and 50 YouTube daily targets")
    if package.get("batch_size") != BATCH_SIZE:
        errors.append("Batch size must be exactly five paired ideas")
    batch_number = package.get("batch_number")
    if not isinstance(batch_number, int) or not 1 <= batch_number <= DAILY_PLATFORM_TARGET // BATCH_SIZE:
        errors.append("Batch number must be between 1 and 10")
    entries = package.get("batch_items")
    if not isinstance(entries, list) or len(entries) != BATCH_SIZE:
        return errors + ["Batch must contain exactly five paired ideas"]
    signatures = _prior_signatures(prior_packages)
    for index, entry in enumerate(entries, start=1):
        if not isinstance(entry, dict):
            errors.append(f"Batch item {index} must be an object")
            continue
        for field in ("hook", "operator_context", "spielos_role", "cta"):
            if not _compact(entry.get(field)):
                errors.append(f"Batch item {index} needs a context-first {field}")
        if entry.get("batch_item") != index:
            errors.append(f"Batch item {index} must declare batch_item={index}")
        errors.extend(f"Batch item {index}: {error}" for error in _validate_single_campaign(entry))
        for platform_item in entry.get("platform_packages") or []:
            signature = _variation_signature(str(entry.get("one_idea") or entry.get("idea") or ""), platform_item)
            if signature in signatures:
                errors.append(f"Batch item {index} repeats an existing creative template")
            signatures.add(signature)
        if index == BATCH_SIZE:
            story = entry.get("live_story") or {}
            required_story = ("trigger", "tension", "decision", "tradeoff", "harness_rule", "next_step")
            missing_story = [field for field in required_story if not _compact(story.get(field))]
            if entry.get("narrative_type") != "live-journey" or missing_story:
                errors.append("Batch item 5 must be a complete live-journey story")
            if story.get("proof_url") != "https://spielos.xyz/live/":
                errors.append("Batch item 5 must link to https://spielos.xyz/live/ as proof")
    return errors


def validate_campaign_package(package: dict[str, Any], prior_packages: list[dict[str, Any]] | None = None) -> list[str]:
    if package.get("schema_version") in COMPATIBLE_SCHEMA_VERSIONS:
        return validate_campaign(package, str(package.get("phase") or "strategy"))
    return [
        "legacy campaign package is retired; migrate to campaign_contract "
        f"schema {CAMPAIGN_SCHEMA_VERSION}"
    ]


def ready_campaign_package(package: dict[str, Any]) -> dict[str, Any]:
    if package.get("schema_version") not in COMPATIBLE_SCHEMA_VERSIONS:
        raise ValueError(
            "legacy campaign package is retired; migrate to campaign_contract "
            f"schema {CAMPAIGN_SCHEMA_VERSION}")
    if package.get("phase") == "approved":
        return publication_package(package)
    if package.get("phase") == "strategy":
        errors = validate_campaign(package, "strategy")
        if errors:
            raise ValueError("campaign editorial review is invalid: " + "; ".join(errors))
        return {"schema_version": CAMPAIGN_SCHEMA_VERSION,
                "campaign_id": package["campaign_id"], "batch_id": package["batch_id"],
                "campaign_manifest": package, "quality_gate": "passed",
                "next_phase": "designed"}
    if package.get("phase") != "rendered":
        raise ValueError("campaign must be rendered before it can enter approval")
    errors = validate_campaign(package, "rendered")
    if errors:
        raise ValueError("campaign render handoff is invalid: " + "; ".join(errors))
    return {"schema_version": CAMPAIGN_SCHEMA_VERSION,
            "campaign_id": package["campaign_id"], "batch_id": package["batch_id"],
            "campaign_manifest": package, "review_required": True,
            "quality_gate": "passed", "next_phase": "approved"}


def _eval_gate_errors(evidence: list[dict[str, Any]], package: dict[str, Any],
                      suite_ids: tuple[str, ...] = ()) -> list[str]:
    errors: list[str] = []
    batch_id = str(package.get("batch_id") or "")
    reports = [item.get("payload") or {} for item in evidence
               if item.get("kind") == "eval_report"]
    for suite_id in suite_ids:
        matches = [report for report in reports if report.get("suite_id") == suite_id]
        if not matches:
            errors.append(
                f"eval_report for suite '{suite_id}' is required before content_ready")
            continue
        report = matches[-1]
        if report.get("payload_id") != batch_id:
            errors.append(
                f"eval_report '{suite_id}' payload_id must match batch_id {batch_id}")
        if not report.get("overall"):
            failed = [
                f"{item_id}:{criterion_id}"
                for item_id, verdicts in (report.get("per_item") or {}).items()
                for criterion_id, verdict in (verdicts or {}).items()
                if isinstance(verdict, dict) and not verdict.get("pass")
            ]
            detail = ", ".join(failed[:12]) if failed else "no criteria passed"
            errors.append(f"eval_report '{suite_id}' failed: {detail}")
    return errors


class ContentDepartment(EvidenceDepartment, Department):
    id = department_id = "content"
    version = "4.3.0"
    description = "Preserves simulated work scenes and discoveries through drafting, editorial gate, Design, approval, and delivery."
    agent_ids = ("content-strategist", "content-writer", "publisher", "video-producer")
    eval_suites = ("content-copy-top10", "content-story-whole")
    production_ready = True
    workflows = (
        WorkflowSpec(
            "content-package",
            "Coordinate one evidence-backed topic idea across formats.",
            ("evidence", "idea_lock", "brief", "produce", "review", "package"),
            ("content-strategist", "content-writer"), ("copywriting", "copywriting"),
            (), ("company_evidence", "content_package"), (),
            graph=(WorkflowStep("package", "agent", "content-strategist",
                                produces=("content_package",),
                                skill_ids=("copywriting", "copywriting")),),
        ),
        WorkflowSpec(
            "social-post",
            "Create a one-idea platform-native post from approved evidence.",
            ("idea_lock", "brief", "draft", "edit", "approve"), ("content-writer",),
            ("copywriting", "copywriting"), (), ("content_draft",), (),
            graph=(WorkflowStep("draft", "agent", "content-writer",
                                produces=("content_draft",),
                                skill_ids=("copywriting", "copywriting")),),
        ),
        WorkflowSpec(
            "article",
            "Create one evidence-backed, search-aware argument.",
            ("idea_lock", "brief", "draft", "edit", "seo_review", "approve"),
            ("content-writer",), ("copywriting", "seo"), (),
            ("article_draft", "seo_brief"), (),
            graph=(WorkflowStep("draft", "agent", "content-writer",
                                produces=("article_draft",),
                                skill_ids=("copywriting", "seo")),),
        ),
        WorkflowSpec(
            "content-campaign",
            "Preserve the work scene and discovery before drafting, then edit for platform, Design, approval, delivery, and measurement. " + PUBLICATION_RECEIPT_CONTRACT,
            ("simulation", "human_reality", "discovery", "draft", "platform_edit", "quality_gate", "render_handoff", "approve", "dispatch", "measure", "evaluate"),
            ("content-strategist", "content-writer", "video-producer", "publisher"), ("copywriting", "spielos-ui", "video-creation"),
            ("publish",), ("simulation", "human_reality", "discovery", "content_draft", "campaign_manifest", "design_order", "render_report", "campaign_ready", "publication_receipt", "funnel_report", "optimization_decision"), ("buffer",),
            graph=(
                WorkflowStep("simulation", "agent", "content-strategist",
                             produces=("simulation",),
                             skill_ids=("copywriting",)),
                WorkflowStep("human_reality", "agent", "content-strategist",
                             requires=("simulation",),
                             produces=("human_reality",),
                             skill_ids=("copywriting",)),
                WorkflowStep("discovery", "agent", "content-strategist",
                             requires=("simulation", "human_reality"),
                             produces=("discovery",),
                             skill_ids=("copywriting",)),
                WorkflowStep("draft", "agent", "content-writer",
                             requires=("simulation", "human_reality", "discovery"),
                             produces=("content_draft",),
                             skill_ids=("copywriting",)),
                WorkflowStep("platform_edit", "agent", "content-writer",
                             requires=("content_draft", "human_reality", "discovery"),
                             produces=("campaign_manifest", "design_order"),
                             skill_ids=("copywriting",)),
                WorkflowStep("quality_gate", "machine",
                             requires=("campaign_manifest",),
                             produces=("content_ready", "campaign_ready")),
                WorkflowStep("render_handoff", "agent", "video-producer",
                             requires=("content_ready", "design_order"),
                             produces=("render_report",),
                             skill_ids=("video-creation", "spielos-ui")),
                WorkflowStep("approve", "approval", requires=("content_ready", "render_report")),
                WorkflowStep("dispatch", "connection", requires=("content_ready", "render_report"), produces=("publication_receipt",),
                             connection_ids=("buffer",)),
            ),
        ),
        WorkflowSpec(
            "publish",
            "Publish or schedule an approved package through a Connection.",
            ("select", "validate", "approve", "dispatch", "verify"), ("publisher",), (),
            ("publish",), ("content_package", "publication_receipt"), ("buffer", "website"),
            graph=(
                WorkflowStep("approve", "approval", requires=("content_package",)),
                WorkflowStep("dispatch", "connection",
                             requires=("content_package",),
                             produces=("publication_receipt",),
                             connection_ids=("buffer", "website")),
            ),
        ),
    )
    goal_schema = {"metrics": ["content_packages", "approved_drafts", "published_items"],
                   "config": {"workflow": {"enum": [w.id for w in workflows]},
                              "required_count": {"type": "integer"},
                              "connection": {"enum": ["buffer", "website"]},
                              "execution_mode": {"enum": ["dry_run", "live"]}}}
    evidence_metrics = {"content_packages": ("content_package",),
                        "approved_drafts": ("content_draft", "article_draft"),
                        "published_items": ("publication_receipt",)}
    workflow_agents = {"content-package": "content-strategist", "content-campaign": "content-strategist", "social-post": "content-writer",
                       "article": "content-writer", "publish": "publisher"}

    def run_machine_step(self, ctx, decision):
        if decision.get("step_id") != "quality_gate":
            return {"run_status": "blocked", "message": "Unknown machine step"}
        evidence = list(ctx.cycle.get("evidence") or ())
        packages = [item.get("payload") or {} for item in evidence
                    if item.get("kind") in {"campaign_manifest", "content_package"}]
        package = packages[-1] if packages else {}
        errors = validate_campaign_package(package, packages[:-1])
        if errors:
            return {"run_status": "blocked", "message": "Campaign contract failed", "attention": {"errors": errors}}
        eval_errors = _eval_gate_errors(evidence, package, tuple(getattr(self, "eval_suites", ()) or ()))
        if eval_errors:
            return {"run_status": "blocked", "message": "Content eval failed", "attention": {"errors": eval_errors}}
        ready = ready_campaign_package(package)
        return {"message": "Campaign ready", "evidence": [
            {"kind": "content_ready", "source": "content-editorial-gate", "validity": "technical_only", "payload": ready},
            {"kind": "campaign_ready", "source": "content-editorial-gate", "validity": "technical_only", "payload": ready},
        ]}
