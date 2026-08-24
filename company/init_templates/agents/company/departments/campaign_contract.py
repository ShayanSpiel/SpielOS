"""Shared contract for one content campaign from strategy to attributed lead.

Departments exchange this Artifact instead of copying campaign facts into
their own templates or configuration.  Each handoff adds evidence to the same
campaign, batch, item, and rendition identifiers; it never creates a rival
record or changes upstream strategy fields.

Schema 1.2 (2026-08-20, goal-content-storytelling-architecture-v1-20260820):
the creative brief gains `intent` (value/proof/conversion) and
`spielos_relevance`, and a YouTube narration becomes ONE complete story —
`scene_control_version` "1.1" requires `narration.script` (the whole narration
written before scene-splitting) and a delivery `intent` on every scene. Schemas
1.0/1.1 stay valid so archived batches keep validating.
"""

from __future__ import annotations

import hashlib
import json
import re
from copy import deepcopy
from typing import Any
from urllib.parse import parse_qs, urlparse


SCHEMA_VERSION = "1.2"
COMPATIBLE_SCHEMA_VERSIONS = frozenset({"1.0", "1.1", "1.2"})
# Storytelling contract for schema 1.2: every brief locks a buyer intent and
# why the idea matters to SpielOS; every YouTube narration is ONE complete
# script (scene_control_version "1.1") whose scenes carry delivery intents.
BRIEF_INTENTS = {"value", "proof", "conversion"}
NARRATION_INTENTS = {"question/rising", "statement/falling", "command/falling"}
PLATFORMS = ("threads", "youtube")
PLATFORM_CONTRACT = {
    "threads": {"asset_type": "image", "size_preset": "threads-portrait", "link_placement": "caption"},
    "youtube": {"asset_type": "video", "size_preset": "youtube-shorts", "link_placement": "bio"},
}
PHASES = ("strategy", "designed", "rendered", "approved", "delivered", "measured", "evaluated")
SPIELOS_NOTE = "This is SpielOS, An AI company running itself."  # legacy packages
SPIELOS_REMINDER = "SpielOS is running itself — an AI company."
LINK_IN_BIO = "Link in bio."
YOUTUBE_CATEGORY_ID = "28"  # Science & Technology — Buffer YoutubePostMetadataInput.categoryId
INTERNAL_COPY_TERMS = {
    "approval record", "batch", "campaign artifact", "campaign handoff",
    "content dispatch", "content department", "creative signature", "harness rule",
    "review gate", "runtime",
}
STRATEGY_REFS = {
    "icp": "company/strategy/icp.md",
    "positioning": "company/strategy/positioning.md",
    "voice": "company/strategy/voice.md",
}
EXPERIMENT_TYPES = {"single-variable", "a/b", "factorial", "funnel"}
EXPERIMENT_SCOPES = {"cross-channel-creative", "website-cro"}
EXPERIMENT_VARIABLES = {
    "hook", "context_framing", "cta", "theme",
    "narration_opening", "offer_framing", "website_copy",
}
PRIMARY_METRICS = {
    "platform_views", "ctr", "service_intent_rate", "lead_conversion_rate", "leads",
}
VIDEO_COMPONENTS = {"statement", "signal", "current-system", "evidence", "decision", "cta"}
VIDEO_ICONS = {
    "bx-error", "bx-check-square", "bx-time-five", "bx-slider", "bx-group",
    "bx-link", "bx-network-chart", "bx-code-alt", "bx-layer", "bx-task",
    "bx-user", "bx-data", "bx-trending-up", "bx-globe",
}


def _text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip())


def _identifier(value: Any) -> bool:
    return bool(re.fullmatch(r"[a-z0-9][a-z0-9-]{2,79}", str(value or "")))


def _validate_copy(copy: Any, platform: str, destination: str,
                   reminder: bool, prefix: str, errors: list[str]) -> None:
    raw = str(copy or "").strip()
    compact = _text(raw)
    if not compact:
        errors.append(f"{prefix}.copy is required")
        return
    if "\\n" in raw or "\\r" in raw:
        errors.append(f"{prefix}.copy must use real line breaks, not literal escape markers")
    public_copy = re.sub(r"https?://\S+", "", compact, flags=re.IGNORECASE).casefold()
    for term in INTERNAL_COPY_TERMS:
        if re.search(rf"\b{re.escape(term)}\b", public_copy):
            errors.append(f"{prefix}.copy exposes internal production language: {term}")
    if any(line.rstrip() != line for line in raw.splitlines()):
        errors.append(f"{prefix}.copy must not contain trailing spaces")
    for line in raw.splitlines():
        if "•" in line and not line.lstrip().startswith("•"):
            errors.append(f"{prefix}.bullets must start on their own lines")
            break
    has_reminder = SPIELOS_REMINDER.casefold() in public_copy
    if reminder and not compact.endswith(SPIELOS_REMINDER):
        errors.append(f"{prefix}.copy must end with the fifth-item SpielOS reminder")
    if not reminder and has_reminder:
        errors.append(f"{prefix}.copy must not include the fifth-item SpielOS reminder")
    if platform == "threads":
        if destination:
            if destination not in raw:
                errors.append(f"{prefix}.copy must include its tracked Threads destination")
            elif destination not in {line.strip() for line in raw.splitlines()}:
                errors.append(f"{prefix}.Threads destination must be on its own line")
        elif "http://" in raw or "https://" in raw:
            errors.append(f"{prefix}.copy cannot contain an untracked Threads URL")
    elif platform == "youtube":
        if "http://" in raw or "https://" in raw or "utm_" in raw.lower():
            errors.append(f"{prefix}.YouTube Shorts copy must not contain a URL or UTM parameters")
        if destination and LINK_IN_BIO.casefold() not in raw.casefold():
            errors.append(f"{prefix}.YouTube Shorts copy must use 'Link in bio.'")


def creative_signature(campaign_id: str, item_id: str, platform: str,
                       design: dict[str, Any]) -> str:
    """Stable identity for the controlled creative variables."""
    controlled = {
        "campaign_id": campaign_id, "item_id": item_id, "platform": platform,
        "template_id": design.get("template_id"), "theme": design.get("theme"),
        "title_lines": design.get("title_lines"),
    }
    raw = json.dumps(controlled, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:20]


def _validate_destination(value: Any, platform: str, campaign_id: str,
                          content_id: str) -> list[str]:
    parsed = urlparse(str(value or ""))
    errors: list[str] = []
    if parsed.scheme != "https" or parsed.netloc != "spielos.xyz" or parsed.path.rstrip("/") not in {"/services", "/contact"}:
        return ["destination must be https://spielos.xyz/services/ or /contact/"]
    params = parse_qs(parsed.query)
    expected = {
        "utm_source": platform, "utm_medium": "social",
        "utm_campaign": campaign_id, "utm_content": content_id,
    }
    for key, wanted in expected.items():
        if (params.get(key) or [""])[0] != wanted:
            errors.append(f"destination needs {key}={wanted}")
    return errors


def _validate_strategy(manifest: dict[str, Any], errors: list[str]) -> None:
    strategy = manifest.get("strategy") or {}
    refs = strategy.get("references") or {}
    for key, expected in STRATEGY_REFS.items():
        if refs.get(key) != expected:
            errors.append(f"strategy.references.{key} must reference {expected}")
    for field in ("hypothesis", "controlled_variables", "changed_variables"):
        if not strategy.get(field):
            errors.append(f"strategy.{field} is required")
    experiment = manifest.get("experiment") or {}
    _validate_experiment(experiment, errors)
    if strategy.get("changed_variables") != experiment.get("variables"):
        errors.append("strategy.changed_variables must match experiment.variables")
    objective = manifest.get("objective") or {}
    expected_objective = {"qualified_visits_per_day": 200, "leads_per_day": 10,
                          "lead_conversion_rate": 0.05}
    for field, expected in expected_objective.items():
        if objective.get(field) != expected:
            errors.append(f"objective.{field} must be {expected}")


def _validate_experiment(experiment: dict[str, Any], errors: list[str]) -> None:
    """Validate one explicit control/variant design without authorizing mutation."""

    prefix = "experiment"
    if not _identifier(experiment.get("id")):
        errors.append(f"{prefix}.id must be a stable identifier")
    test_type = experiment.get("test_type")
    if test_type not in EXPERIMENT_TYPES:
        errors.append(f"{prefix}.test_type must be one of: {', '.join(sorted(EXPERIMENT_TYPES))}")
    scope = experiment.get("scope")
    if scope not in EXPERIMENT_SCOPES:
        errors.append(f"{prefix}.scope must distinguish cross-channel-creative or website-cro")
    if scope == "website-cro" and experiment.get("separate_approval_required") is not True:
        errors.append(f"{prefix}.website-cro requires a separate website-mutation approval")
    variables = experiment.get("variables")
    if not isinstance(variables, list) or not 1 <= len(variables) <= 3:
        errors.append(f"{prefix}.variables must declare one to three variables")
        variables = []
    elif len(set(variables)) != len(variables) or any(item not in EXPERIMENT_VARIABLES for item in variables):
        errors.append(f"{prefix}.variables contains duplicates or unsupported variables")
    if test_type in {"single-variable", "a/b"} and len(variables) != 1:
        errors.append(f"{prefix}.{test_type} must declare exactly one variable")
    if test_type == "factorial" and not 2 <= len(variables) <= 3:
        errors.append(f"{prefix}.factorial must declare two or three variables")
    assignment = experiment.get("assignment") or {}
    if assignment.get("method") not in {"randomized", "balanced", "sequential"}:
        errors.append(f"{prefix}.assignment.method must be randomized, balanced, or sequential")
    if assignment.get("unit") not in {"content_id", "item_id", "session"}:
        errors.append(f"{prefix}.assignment.unit must be content_id, item_id, or session")
    if experiment.get("primary_metric") not in PRIMARY_METRICS:
        errors.append(f"{prefix}.primary_metric is not a canonical funnel metric")
    guardrails = experiment.get("guardrails")
    if not isinstance(guardrails, list) or not guardrails or any(item not in PRIMARY_METRICS for item in guardrails):
        errors.append(f"{prefix}.guardrails must name canonical funnel metrics")
    minimum = experiment.get("minimum_evidence_per_cell")
    if not isinstance(minimum, int) or minimum < 1:
        errors.append(f"{prefix}.minimum_evidence_per_cell must be a positive integer")
    if not _text(experiment.get("analysis_method")):
        errors.append(f"{prefix}.analysis_method is required")
    cells = experiment.get("cells")
    if not isinstance(cells, list) or len(cells) < 2:
        errors.append(f"{prefix}.cells must contain one control and at least one variant")
        return
    roles = [cell.get("role") for cell in cells if isinstance(cell, dict)]
    if roles.count("control") != 1 or not any(role == "variant" for role in roles):
        errors.append(f"{prefix}.cells must contain exactly one control and at least one variant")
    ids: set[str] = set()
    value_signatures: set[str] = set()
    for cell in cells:
        if not isinstance(cell, dict) or not _identifier(cell.get("id")):
            errors.append(f"{prefix}.cells need stable ids")
            continue
        if cell["id"] in ids:
            errors.append(f"{prefix}.cell ids must be unique")
        ids.add(cell["id"])
        values = cell.get("values")
        if not isinstance(values, dict) or set(values) != set(variables) or any(not _text(value) for value in values.values()):
            errors.append(f"{prefix}.cell {cell['id']} must declare a value for every variable")
            continue
        signature = json.dumps(values, sort_keys=True, ensure_ascii=False)
        if signature in value_signatures:
            errors.append(f"{prefix}.cells must represent distinct variable combinations")
        value_signatures.add(signature)


def _validate_experiment_evidence(manifest: dict[str, Any], report: dict[str, Any],
                                  errors: list[str]) -> None:
    experiment = manifest.get("experiment") or {}
    evidence = report.get("experiment_evidence") or {}
    if evidence.get("experiment_id") != experiment.get("id"):
        errors.append("measurement.report.experiment_evidence must match experiment.id")
    rows = evidence.get("cells")
    if not isinstance(rows, list):
        errors.append("measurement.report.experiment_evidence.cells is required")
        return
    expected = {cell.get("id") for cell in experiment.get("cells") or []}
    observed = {cell.get("cell_id") for cell in rows if isinstance(cell, dict)}
    if observed != expected or len(rows) != len(expected):
        errors.append("measurement.report experiment evidence must cover every cell exactly once")
    minimum = experiment.get("minimum_evidence_per_cell") or 1
    sufficient = True
    for row in rows:
        count = row.get("sample_size") if isinstance(row, dict) else None
        if not isinstance(count, int) or count < 0:
            errors.append("measurement.report experiment cell sample_size must be non-negative")
            sufficient = False
        elif count < minimum:
            sufficient = False
    expected_sufficient = bool(report.get("evidence_complete")) and sufficient
    if evidence.get("evidence_sufficient") is not expected_sufficient:
        errors.append("measurement.report.experiment_evidence.evidence_sufficient does not match cell thresholds")
    analysis = evidence.get("analysis") or {}
    if analysis.get("method") != experiment.get("analysis_method"):
        errors.append("measurement.report experiment analysis must use the declared method")
    effects = analysis.get("effects")
    if not isinstance(effects, list):
        errors.append("measurement.report experiment analysis.effects is required")
        return
    configured = set(experiment.get("variables") or [])
    for effect in effects:
        variables = effect.get("variables") if isinstance(effect, dict) else None
        if (not isinstance(variables, list) or not variables
                or not set(variables).issubset(configured)
                or not isinstance(effect.get("supported"), bool)):
            errors.append("measurement.report effects need configured variables and a supported verdict")
            break


def _validate_optimization_decision(manifest: dict[str, Any], decision: dict[str, Any],
                                    errors: list[str]) -> None:
    for field in ("evidence_window", "verdict", "test_type", "scope",
                  "changed_variables", "next_batch_hypothesis"):
        if not decision.get(field):
            errors.append(f"optimization_decision.{field} is required")
    variables = decision.get("changed_variables")
    if not isinstance(variables, list) or not 1 <= len(variables) <= 3:
        errors.append("optimization_decision.changed_variables must contain one to three variables")
        return
    if len(set(variables)) != len(variables) or any(item not in EXPERIMENT_VARIABLES for item in variables):
        errors.append("optimization_decision.changed_variables contains duplicates or unsupported variables")
    if decision.get("test_type") not in EXPERIMENT_TYPES:
        errors.append("optimization_decision.test_type is invalid")
    if decision.get("scope") not in EXPERIMENT_SCOPES:
        errors.append("optimization_decision.scope must distinguish creative from website CRO")
    if decision.get("scope") == "website-cro" and decision.get("separate_approval_required") is not True:
        errors.append("optimization_decision website CRO requires a separate mutation approval")
    report = ((manifest.get("measurement") or {}).get("report") or {})
    evidence = report.get("experiment_evidence") or {}
    sufficient = evidence.get("evidence_sufficient") is True
    effects = ((evidence.get("analysis") or {}).get("effects") or [])
    if not sufficient and len(variables) > 1:
        errors.append("sparse evidence defaults the next experiment to one variable")
        return
    if len(variables) > 1:
        independent = all(any(
            effect.get("supported") is True and effect.get("variables") == [variable]
            for effect in effects if isinstance(effect, dict)) for variable in variables)
        interaction = any(
            effect.get("supported") is True and set(effect.get("variables") or []) == set(variables)
            for effect in effects if isinstance(effect, dict))
        if not (independent or interaction):
            errors.append("multiple changes require supported independent or interaction effects")


def _validate_design(design: dict[str, Any], platform: str, prefix: str,
                     errors: list[str]) -> None:
    rule = PLATFORM_CONTRACT[platform]
    required = ("template_id", "theme", "size_preset", "title_lines",
                "eyebrow", "supporting_text")
    for field in required:
        if not design.get(field):
            errors.append(f"{prefix}.design.{field} is required")
    if design.get("size_preset") != rule["size_preset"]:
        errors.append(f"{prefix}.design.size_preset must be {rule['size_preset']}")
    raw = json.dumps(design).lower()
    if "#" in raw or "rgb(" in raw or "hsl(" in raw:
        errors.append(f"{prefix}.design must not contain raw colors")
    public_design = _text(" ".join([
        str(design.get("eyebrow") or ""),
        " ".join(map(str, design.get("title_lines") or [])),
        str(design.get("supporting_text") or ""),
        " ".join(map(str, design.get("station_labels") or [])),
    ])).casefold()
    for term in INTERNAL_COPY_TERMS:
        if re.search(rf"\b{re.escape(term)}\b", public_design):
            errors.append(f"{prefix}.design exposes internal production language: {term}")
    lines = design.get("title_lines") or []
    if not isinstance(lines, list) or not 1 <= len(lines) <= 3 or any(not _text(line) for line in lines):
        errors.append(f"{prefix}.design.title_lines must contain one to three readable lines")
    if platform == "youtube":
        thumbnail_title = design.get("thumbnail_title")
        if thumbnail_title not in (None, ""):
            words = _text(thumbnail_title).split()
            if not 1 <= len(words) <= 5:
                errors.append(f"{prefix}.design.thumbnail_title must be 1-5 words")
            compact_title = _text(thumbnail_title).casefold()
            if re.search(r"https?://|utm_|\b[a-z0-9-]+\.(?:xyz|com|net|org|io|ai|dev|co)\b", compact_title):
                errors.append(f"{prefix}.design.thumbnail_title must not contain a URL or UTM parameters")
            for term in INTERNAL_COPY_TERMS:
                if re.search(rf"\b{re.escape(term)}\b", compact_title):
                    errors.append(f"{prefix}.design.thumbnail_title exposes internal production language: {term}")


def _validate_rendition(manifest: dict[str, Any], item: dict[str, Any],
                        platform: str, phase: str, errors: list[str]) -> None:
    item_id = str(item.get("item_id") or "")
    prefix = f"items.{item_id}.renditions.{platform}"
    rendition = (item.get("renditions") or {}).get(platform)
    if not isinstance(rendition, dict):
        errors.append(f"{prefix} is required")
        return
    if rendition.get("platform") != platform:
        errors.append(f"{prefix}.platform must be {platform}")
    destination = str(rendition.get("destination") or "")
    expected_placement = PLATFORM_CONTRACT[platform]["link_placement"] if destination else "none"
    if rendition.get("link_placement") != expected_placement:
        errors.append(f"{prefix}.link_placement must be {expected_placement}")
    content_id = str(rendition.get("content_id") or "")
    expected_content = f"{item_id}-{platform}"
    if content_id != expected_content:
        errors.append(f"{prefix}.content_id must be {expected_content}")
    if destination:
        errors.extend(f"{prefix}.{error}" for error in _validate_destination(
            destination, platform, str(manifest.get("campaign_id") or ""), content_id))
    _validate_copy(rendition.get("copy"), platform, destination,
                   item.get("sequence") == 5, prefix, errors)
    hook_text = _text((item.get("hook") or {}).get("text"))
    if hook_text and not _text(rendition.get("copy")).casefold().startswith(hook_text.casefold()):
        errors.append(f"{prefix}.copy must begin with the item's locked opening")
    design = rendition.get("design") or {}
    _validate_design(design, platform, prefix, errors)
    expected_signature = creative_signature(str(manifest.get("campaign_id") or ""), item_id, platform, design)
    if rendition.get("creative_signature") not in (None, "", expected_signature):
        errors.append(f"{prefix}.creative_signature does not match its design inputs")
    if platform == "youtube":
        narration = rendition.get("narration") or {}
        scenes = narration.get("scenes") or []
        if not isinstance(scenes, list) or len(scenes) < 4:
            errors.append(f"{prefix}.narration.scenes needs at least four complete scenes")
        scene_control_version = narration.get("scene_control_version")
        schema = str(manifest.get("schema_version") or "")
        if schema == SCHEMA_VERSION and scene_control_version != "1.1":
            errors.append(
                f"{prefix}.narration.scene_control_version must be \"1.1\" in "
                f"schema {SCHEMA_VERSION} (one complete narration + scene intents)")
        controlled_scenes = scene_control_version in ("1.0", "1.1")
        if scene_control_version == "1.1":
            if not _text(narration.get("script")):
                errors.append(
                    f"{prefix}.narration.script is required before scene-splitting "
                    "in scene_control_version 1.1")
        for index, scene in enumerate(scenes):
            if not _text((scene or {}).get("id")) or not _text((scene or {}).get("text")):
                errors.append(f"{prefix}.narration scenes need id and text")
                break
            if scene_control_version == "1.1" and (scene or {}).get("intent") not in NARRATION_INTENTS:
                errors.append(
                    f"{prefix}.narration scene {index + 1}.intent must be one of: "
                    f"{', '.join(sorted(NARRATION_INTENTS))}")
            if not controlled_scenes:
                continue
            visual = (scene or {}).get("visual") or {}
            for field in ("eyebrow", "headline", "supporting_text", "component", "icon", "labels"):
                if visual.get(field) in (None, "", []):
                    errors.append(f"{prefix}.narration scene {index + 1} visual.{field} is required")
            if visual.get("component") not in VIDEO_COMPONENTS:
                errors.append(f"{prefix}.narration scene {index + 1} visual.component is not registered")
            if visual.get("icon") not in VIDEO_ICONS:
                errors.append(f"{prefix}.narration scene {index + 1} visual.icon must be a registered Boxicon")
            labels = visual.get("labels")
            if not isinstance(labels, list) or not 1 <= len(labels) <= 4 or any(not _text(label) for label in labels):
                errors.append(f"{prefix}.narration scene {index + 1} visual.labels needs one to four labels")
            spoken = _text(scene.get("text")).casefold()
            displayed = _text(visual.get("headline")).casefold()
            url_aligned = (
                visual.get("spoken_display_alignment") == "url-pronunciation"
                and visual.get("component") == "cta"
                and displayed == "spielos.xyz/services"
                and spoken == "go to spielos dot xyz slash services."
            )
            if displayed != spoken and not url_aligned:
                errors.append(f"{prefix}.narration scene {index + 1} spoken text must equal its displayed headline")
        if scenes and hook_text and _text(scenes[0].get("text")).casefold() != hook_text.casefold():
            errors.append(f"{prefix}.narration must begin with the item's locked opening")
        title = _text(" ".join(design.get("title_lines") or []))
        if controlled_scenes and scenes and _text(scenes[0].get("text")).casefold() != title.casefold():
            errors.append(f"{prefix}.narration hook must equal the complete designed title")
    if PHASES.index(phase) >= PHASES.index("rendered"):
        asset = rendition.get("asset") or {}
        if asset.get("type") != PLATFORM_CONTRACT[platform]["asset_type"]:
            errors.append(f"{prefix}.asset.type must be {PLATFORM_CONTRACT[platform]['asset_type']}")
        for field in ("local_path", "sha256", "render_report_id"):
            if not asset.get(field):
                errors.append(f"{prefix}.asset.{field} is required after rendering")
    if PHASES.index(phase) >= PHASES.index("approved"):
        approval = rendition.get("approval") or {}
        if approval.get("status") != "approved" or not approval.get("approval_id"):
            errors.append(f"{prefix}.approval must record the explicit asset approval")
        public_url = str((rendition.get("asset") or {}).get("public_url") or "")
        if not public_url.startswith("https://"):
            errors.append(f"{prefix}.asset.public_url must be stable HTTPS before publishing")
    if PHASES.index(phase) >= PHASES.index("delivered"):
        delivery = rendition.get("delivery") or {}
        if not delivery.get("provider_post_id") or delivery.get("verified") is not True:
            errors.append(f"{prefix}.delivery needs a verified provider post ID")


def validate_campaign(manifest: dict[str, Any], phase: str | None = None) -> list[str]:
    """Validate the shared Artifact at a named handoff phase."""
    errors: list[str] = []
    phase = phase or str(manifest.get("phase") or "strategy")
    if phase not in PHASES:
        return [f"phase must be one of: {', '.join(PHASES)}"]
    if manifest.get("schema_version") not in COMPATIBLE_SCHEMA_VERSIONS:
        errors.append(
            f"schema_version must be {SCHEMA_VERSION} "
            f"(compatible: {', '.join(sorted(COMPATIBLE_SCHEMA_VERSIONS))})")
    for field in ("campaign_id", "batch_id"):
        if not _identifier(manifest.get(field)):
            errors.append(f"{field} must be a stable lowercase identifier")
    if manifest.get("phase") != phase:
        errors.append(f"manifest.phase must be {phase}")
    if manifest.get("daily_targets") != {"threads": 50, "youtube": 50}:
        errors.append("daily_targets must be 50 Threads and 50 YouTube")
    if manifest.get("batch_size") != 5:
        errors.append("batch_size must be 5")
    if not isinstance(manifest.get("batch_number"), int) or not 1 <= manifest["batch_number"] <= 10:
        errors.append("batch_number must be between 1 and 10")
    _validate_strategy(manifest, errors)
    items = manifest.get("items")
    if not isinstance(items, list) or len(items) != 5:
        return errors + ["items must contain exactly five paired ideas"]
    seen_ids: set[str] = set()
    seen_signatures: set[str] = set()
    for sequence, item in enumerate(items, start=1):
        if not isinstance(item, dict):
            errors.append(f"items.{sequence} must be an object")
            continue
        item_id = str(item.get("item_id") or "")
        if not _identifier(item_id) or item_id in seen_ids:
            errors.append(f"items.{sequence}.item_id must be unique and stable")
        seen_ids.add(item_id)
        if item.get("sequence") != sequence:
            errors.append(f"items.{item_id}.sequence must be {sequence}")
        brief = item.get("brief") or {}
        for field in ("reader", "customer_moment", "one_idea", "desired_result"):
            if not _text(brief.get(field)):
                errors.append(f"items.{item_id}.brief.{field} is required")
        if str(manifest.get("schema_version") or "") == SCHEMA_VERSION:
            if brief.get("intent") not in BRIEF_INTENTS:
                errors.append(
                    f"items.{item_id}.brief.intent must be one of: "
                    f"{', '.join(sorted(BRIEF_INTENTS))}")
            if not _text(brief.get("spielos_relevance")):
                errors.append(
                    f"items.{item_id}.brief.spielos_relevance is required in "
                    f"schema {SCHEMA_VERSION}")
        if _text(item.get("one_idea")) != _text(brief.get("one_idea")):
            errors.append(f"items.{item_id}.one_idea must match brief.one_idea")
        if len(_text(brief.get("one_idea"))) > 180:
            errors.append(f"items.{item_id}.brief.one_idea must stay under 180 characters")
        if len(_text(brief.get("customer_moment"))) > 240:
            errors.append(f"items.{item_id}.brief.customer_moment must stay under 240 characters")
        public_source = " ".join(
            _text(brief.get(field)) for field in
            ("customer_moment", "one_idea", "desired_result", "proof")
        ) + " " + _text((item.get("hook") or {}).get("text"))
        public_source = public_source.casefold()
        for term in INTERNAL_COPY_TERMS:
            if re.search(rf"\b{re.escape(term)}\b", public_source):
                errors.append(f"items.{item_id}.brief uses internal term: {term}")
        hook = item.get("hook") or {}
        cta = item.get("cta") or {}
        if not _identifier(hook.get("id")) or not _text(hook.get("text")):
            errors.append(f"items.{item_id}.hook needs a stable id and clear text")
        if cta and (not _identifier(cta.get("id")) or not _text(cta.get("text"))):
            errors.append(f"items.{item_id}.cta must be complete when present")
        for platform in PLATFORMS:
            _validate_rendition(manifest, item, platform, phase, errors)
            rendition = (item.get("renditions") or {}).get(platform) or {}
            signature = creative_signature(str(manifest.get("campaign_id") or ""), item_id,
                                           platform, rendition.get("design") or {})
            if signature in seen_signatures:
                errors.append(f"items.{item_id}.{platform} repeats a creative signature")
            seen_signatures.add(signature)
        if sequence == 5:
            reminder = item.get("reminder") or {}
            if item.get("narrative_type") != "spielos-reminder":
                errors.append("the fifth item must be a spielos-reminder")
            if reminder.get("text") != SPIELOS_REMINDER:
                errors.append("the fifth item must use the canonical SpielOS reminder")
            if not _text(reminder.get("proof")):
                errors.append("the fifth item reminder needs one short public proof point")
        elif item.get("narrative_type") == "spielos-reminder":
            errors.append("only the fifth item may be a spielos-reminder")
    measurement = manifest.get("measurement") or {}
    if measurement.get("join_keys") != ["campaign_id", "batch_id", "item_id", "content_id", "creative_signature"]:
        errors.append("measurement.join_keys must preserve the campaign-to-lead identity chain")
    if PHASES.index(phase) >= PHASES.index("measured"):
        report = measurement.get("report") or {}
        if report.get("evidence_complete") is not True:
            errors.append("measurement.report must be marked evidence_complete before learning")
        for field in ("platform_views", "content_landings", "service_cta_clicks", "leads"):
            if not isinstance(report.get(field), (int, float)) or report[field] < 0:
                errors.append(f"measurement.report.{field} must be a non-negative number")
        _validate_experiment_evidence(manifest, report, errors)
    if phase == "evaluated":
        decision = manifest.get("optimization_decision") or {}
        _validate_optimization_decision(manifest, decision, errors)
    return errors


def advance_campaign(manifest: dict[str, Any], target_phase: str,
                     evidence: dict[str, Any] | None = None) -> dict[str, Any]:
    """Return a copied Artifact advanced exactly one phase after validation."""
    current = str(manifest.get("phase") or "")
    if current not in PHASES or target_phase not in PHASES:
        raise ValueError("unknown campaign phase")
    if PHASES.index(target_phase) != PHASES.index(current) + 1:
        raise ValueError(f"campaign may advance only one phase ({current} -> {target_phase})")
    errors = validate_campaign(manifest, current)
    if errors:
        raise ValueError("current campaign Artifact is invalid: " + "; ".join(errors))
    result = deepcopy(manifest)
    result["phase"] = target_phase
    handoffs = list(result.get("handoffs") or [])
    handoffs.append({"from": current, "to": target_phase, "evidence": deepcopy(evidence or {})})
    result["handoffs"] = handoffs
    return result


def publication_package(manifest: dict[str, Any]) -> dict[str, Any]:
    """Build Buffer input only from one fully approved campaign Artifact."""
    errors = validate_campaign(manifest, "approved")
    if errors:
        raise ValueError("campaign is not approved for publishing: " + "; ".join(errors))
    posts: list[dict[str, Any]] = []
    for item in manifest["items"]:
        for platform in PLATFORMS:
            rendition = item["renditions"][platform]
            posts.append({
                "campaign_id": manifest["campaign_id"], "batch_id": manifest["batch_id"],
                "item_id": item["item_id"], "content_id": rendition["content_id"],
                "creative_signature": creative_signature(
                    manifest["campaign_id"], item["item_id"], platform, rendition["design"]),
                "platform": platform, "text": rendition["copy"],
                "destination": rendition["destination"],
                "approval_id": rendition["approval"]["approval_id"],
                "assets": [{"type": rendition["asset"]["type"],
                            "url": rendition["asset"]["public_url"]}],
                "mode": rendition.get("delivery_mode", "queue"),
                "metadata": (None if platform == "threads" else {
                    "youtube": {
                        "title": _text(" ".join(rendition["design"].get("title_lines") or [])),
                        "categoryId": YOUTUBE_CATEGORY_ID,
                    }
                }),
            })
    return {"schema_version": SCHEMA_VERSION, "campaign_id": manifest["campaign_id"],
            "batch_id": manifest["batch_id"], "approval_required": True, "posts": posts}


def apply_render_report(manifest: dict[str, Any], report: dict[str, Any]) -> dict[str, Any]:
    """Join Design evidence into the same Artifact and advance to rendered."""
    errors = validate_campaign(manifest, "designed")
    if errors:
        raise ValueError("campaign is not ready for render evidence: " + "; ".join(errors))
    if report.get("campaign_id") != manifest.get("campaign_id") or report.get("batch_id") != manifest.get("batch_id"):
        raise ValueError("render report identity does not match campaign")
    records = {(entry.get("item_id"), entry.get("platform")): entry
               for entry in report.get("renditions") or []}
    expected = {(item["item_id"], platform) for item in manifest["items"] for platform in PLATFORMS}
    if set(records) != expected:
        raise ValueError("render report must cover every campaign rendition exactly once")
    result = deepcopy(manifest)
    for item in result["items"]:
        for platform in PLATFORMS:
            record = records[(item["item_id"], platform)]
            rendition = item["renditions"][platform]
            if record.get("content_id") != rendition.get("content_id"):
                raise ValueError("render report content identity mismatch")
            rendition["asset"] = deepcopy(record.get("asset") or {})
            rendition["creative_signature"] = creative_signature(
                result["campaign_id"], item["item_id"], platform, rendition["design"])
    result["phase"] = "rendered"
    result.setdefault("handoffs", []).append({"from": "designed", "to": "rendered",
                                               "evidence": {"department": "design", "report": report}})
    errors = validate_campaign(result, "rendered")
    if errors:
        raise ValueError("rendered campaign is invalid: " + "; ".join(errors))
    return result


def approve_rendered_campaign(manifest: dict[str, Any], approvals: list[dict[str, Any]]) -> dict[str, Any]:
    """Apply the owner's per-rendition approval and stable hosted URLs."""
    errors = validate_campaign(manifest, "rendered")
    if errors:
        raise ValueError("campaign is not ready for approval: " + "; ".join(errors))
    records = {(entry.get("item_id"), entry.get("platform")): entry for entry in approvals}
    expected = {(item["item_id"], platform) for item in manifest["items"] for platform in PLATFORMS}
    if set(records) != expected:
        raise ValueError("approval must cover every campaign rendition exactly once")
    result = deepcopy(manifest)
    for item in result["items"]:
        for platform in PLATFORMS:
            record = records[(item["item_id"], platform)]
            if record.get("status") != "approved" or not record.get("approval_id"):
                raise ValueError("every rendition needs an explicit approved decision")
            item["renditions"][platform]["approval"] = {
                "status": "approved", "approval_id": record["approval_id"]}
            item["renditions"][platform]["asset"]["public_url"] = record.get("public_url")
    result["phase"] = "approved"
    result.setdefault("handoffs", []).append({"from": "rendered", "to": "approved",
                                               "evidence": {"approvals": deepcopy(approvals)}})
    errors = validate_campaign(result, "approved")
    if errors:
        raise ValueError("approved campaign is invalid: " + "; ".join(errors))
    return result


def apply_delivery_receipts(manifest: dict[str, Any], receipts: list[dict[str, Any]]) -> dict[str, Any]:
    """Attach verified Buffer identities without losing campaign join keys."""
    errors = validate_campaign(manifest, "approved")
    if errors:
        raise ValueError("campaign is not approved: " + "; ".join(errors))
    records = {(entry.get("item_id"), entry.get("platform")): entry for entry in receipts}
    expected = {(item["item_id"], platform) for item in manifest["items"] for platform in PLATFORMS}
    if set(records) != expected:
        raise ValueError("delivery receipts must cover every campaign rendition exactly once")
    result = deepcopy(manifest)
    for item in result["items"]:
        for platform in PLATFORMS:
            record = records[(item["item_id"], platform)]
            rendition = item["renditions"][platform]
            for field in ("campaign_id", "batch_id", "content_id", "creative_signature", "approval_id"):
                expected_value = {
                    "campaign_id": result["campaign_id"], "batch_id": result["batch_id"],
                    "content_id": rendition["content_id"],
                    "creative_signature": creative_signature(result["campaign_id"], item["item_id"], platform, rendition["design"]),
                    "approval_id": rendition["approval"]["approval_id"],
                }[field]
                if record.get(field) != expected_value:
                    raise ValueError(f"delivery receipt {field} mismatch")
            rendition["delivery"] = deepcopy(record)
    result["phase"] = "delivered"
    result.setdefault("handoffs", []).append({"from": "approved", "to": "delivered",
                                               "evidence": {"connection": "buffer", "receipts": deepcopy(receipts)}})
    errors = validate_campaign(result, "delivered")
    if errors:
        raise ValueError("delivered campaign is invalid: " + "; ".join(errors))
    return result


def apply_funnel_report(manifest: dict[str, Any], report: dict[str, Any]) -> dict[str, Any]:
    """Advance only with complete, identity-matched full-funnel evidence."""
    errors = validate_campaign(manifest, "delivered")
    if errors:
        raise ValueError("campaign is not delivered: " + "; ".join(errors))
    if report.get("campaign_id") != manifest.get("campaign_id") or report.get("batch_id") != manifest.get("batch_id"):
        raise ValueError("funnel report identity does not match campaign")
    result = deepcopy(manifest)
    result.setdefault("measurement", {})["report"] = deepcopy(report)
    result["phase"] = "measured"
    result.setdefault("handoffs", []).append({"from": "delivered", "to": "measured",
                                               "evidence": {"department": "analytics", "report": deepcopy(report)}})
    errors = validate_campaign(result, "measured")
    if errors:
        raise ValueError("measured campaign is invalid: " + "; ".join(errors))
    return result


def record_optimization_decision(manifest: dict[str, Any], decision: dict[str, Any]) -> dict[str, Any]:
    """Close the loop with one to three evidence-supported next changes."""
    errors = validate_campaign(manifest, "measured")
    if errors:
        raise ValueError("campaign cannot be evaluated: " + "; ".join(errors))
    result = deepcopy(manifest)
    result["optimization_decision"] = deepcopy(decision)
    result["phase"] = "evaluated"
    result.setdefault("handoffs", []).append({"from": "measured", "to": "evaluated",
                                               "evidence": {"decision": deepcopy(decision)}})
    errors = validate_campaign(result, "evaluated")
    if errors:
        raise ValueError("optimization decision is invalid: " + "; ".join(errors))
    return result


def funnel_metrics(report: dict[str, Any]) -> dict[str, float | int | None]:
    """Canonical content funnel math; missing denominators remain unknown."""
    views = report.get("platform_views") or 0
    landings = report.get("content_landings") or 0
    clicks = report.get("service_cta_clicks") or 0
    leads = report.get("leads") or 0
    return {
        "platform_views": views, "content_landings": landings,
        "service_cta_clicks": clicks, "leads": leads,
        "ctr": landings / views if views else None,
        "service_intent_rate": clicks / landings if landings else None,
        "lead_conversion_rate": leads / landings if landings else None,
    }
