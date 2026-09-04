"""Design Department video eval suites — copy, sync, and media gates.

Two judge-enforced gates that catch the exact regressions you flagged:
- CTA not showing as proper link (dot pronunciation leaking to screen)
- Lines cut and irrelevant components not sync with narration
- Actual MP4/thumbnail evidence satisfies the delivery contract

Gallery is source of truth; registry, brand-motion, video-creation SKILL are grounding.
"""
from ...evals.models import EvalCriterion, EvalSuite

REGISTRY = ".agents/company/departments/design/templates/registry.json"
BRAND_MOTION = ".agents/company/departments/design/templates/video/brand-motion.css"
VIDEO_CREATION = ".agents/company/skills/videography/SKILL.md"
NARRATION = ".agents/company/departments/design/templates/video/narration.json"
COPYWRITING_EN = ".agents/company/skills/copywriting/SKILL.md"

VIDEO_CTA_LINK = EvalSuite(
    id="video-cta-link",
    name="Video CTA link — proper link card, not spoken pronunciation",
    scope="video-cta",
    department_id="design",
    payload_kind="campaign_manifest",
    description=(
        "CTA scene must show the proper link card spielos.xyz/services (visual), "
        "not the spoken pronunciation, with workflow badge and 4s hold. Gallery-faithful."
    ),
    validity="business",
    thresholds={"all_pass": True, "min_score": 1.0},
    payload_id_selector=lambda payload: str(payload.get("batch_id") or payload.get("id") or "payload"),
    item_selector=lambda payload: [(item["item_id"], item) for item in (payload.get("items") or [])],
    criteria=(
        EvalCriterion(
            id="cta_visual_is_link",
            name="CTA visual is proper link",
            description=(
                "The CTA visual headline must be exactly `spielos.xyz/services` (lowercase site canonical, slash, no dot pronunciation). "
                "The spoken line is `Go to SpielOS dot xyz slash services.` with url-pronunciation alignment. Visual must not contain `dot` or `slash` words."
            ),
            source=NARRATION,
        ),
        EvalCriterion(
            id="cta_badge_is_workflow",
            name="CTA badge is workflow",
            description=(
                "CTA badge (ct0) must show the item's workflow eyebrow like `MAP ONE INTAKE FLOW`, not generic `AI agent implementation` or `Services`."
            ),
            source=REGISTRY,
        ),
        EvalCriterion(
            id="cta_holds_4s",
            name="CTA holds 4s",
            description=(
                "CTA scene visual window must be >=4.0s (CTA_MIN_VISUAL_DWELL) so the link card is readable, not clipped. Timing from narration.json scene_timing."
            ),
            source=BRAND_MOTION,
        ),
        EvalCriterion(
            id="cta_has_spielos_context_before",
            name="SpielOS context before CTA",
            description=(
                "The scene immediately before CTA must name SpielOS once and state what it is (operating system / loop), so CTA is not abrupt. No em dash, simple sentence."
            ),
            source=VIDEO_CREATION,
        ),
    ),
)

VIDEO_TEXT_SYNC = EvalSuite(
    id="video-text-sync",
    name="Video text sync — no cut lines, no irrelevant components",
    scope="video-text",
    department_id="design",
    payload_kind="campaign_manifest",
    description=(
        "On-screen text per scene must equal narration text (headline == text), no lines cut at arbitrary char, no default placeholder pills, labels match narration visual.labels and support sync."
    ),
    validity="business",
    thresholds={"all_pass": True, "min_score": 1.0},
    payload_id_selector=lambda payload: str(payload.get("batch_id") or payload.get("id") or "payload"),
    item_selector=lambda payload: [(item["item_id"], item) for item in (payload.get("items") or [])],
    criteria=(
        EvalCriterion(
            id="headline_equals_text",
            name="Headline equals narration text",
            description=(
                "For every non-CTA scene, visual.headline must equal scene.text exactly (case-insensitive, no truncation). This is the sceneCopyAligned contract in tts-gemini.js; mismatch means irrelevant copy is shown."
            ),
            source=NARRATION,
        ),
        EvalCriterion(
            id="lines_not_cut",
            name="Lines not cut",
            description=(
                "Headline must not be truncated at an arbitrary splitLines maxChars. The full headline must be injectable into the template slot without hiding the second line. No `...` or hidden overflow."
            ),
            source=VIDEO_CREATION,
        ),
        EvalCriterion(
            id="no_irrelevant_components",
            name="No irrelevant components",
            description=(
                "Template must not show default placeholder components (e.g., extra pills, count s, generic icons) when narration has fewer labels. Hidden slots must be `display:none`, not showing stale copy. Labels shown must exactly match narration visual.labels."
            ),
            source=REGISTRY,
        ),
        EvalCriterion(
            id="supporting_sync",
            name="Supporting text sync",
            description=(
                "visual.supporting_text per scene must be the scene's supporting copy from the manifest, not a hardcoded template default. CTA supporting explains the next step."
            ),
            source=COPYWRITING_EN,
        ),
        EvalCriterion(
            id="no_em_dash",
            name="No em dash in copy",
            description=(
                "No `—` (em dash) in any rendered headline, supporting, eyebrow, or badge. Copy uses period or comma per copywriting. Canonical `SpielOS is running itself — an AI company.` is the only exception and must appear exactly once per fifth item."
            ),
            source=COPYWRITING_EN,
        ),
    ),
)

VIDEO_MEDIA_QA = EvalSuite(
    id="video-media-qa",
    name="Video media QA — objective streams and stable thumbnail",
    scope="video-media",
    department_id="design",
    payload_kind="video_render",
    description=(
        "Judge the renderer-produced QA artifact, not the campaign manifest alone. "
        "The MP4, narration track, thumbnail, and schedule must pass objective checks."
    ),
    validity="technical_only",
    thresholds={"all_pass": True, "min_score": 1.0},
    payload_id_selector=lambda payload: str(payload.get("item_id") or payload.get("id") or "video-render"),
    criteria=(
        EvalCriterion(
            id="mp4_portrait_30fps",
            name="MP4 is portrait 30fps",
            description=(
                "The renderer QA object must report video_dimensions=true and video_fps=true: exactly 1080x1920 at 30fps."
            ),
            source=VIDEO_CREATION,
        ),
        EvalCriterion(
            id="narration_format",
            name="Narration is 48kHz mono AAC",
            description=(
                "The renderer QA object must report narration_aac=true, narration_48khz=true, and narration_mono=true."
            ),
            source=NARRATION,
        ),
        EvalCriterion(
            id="thumbnail_is_stable_and_complete",
            name="Thumbnail is a complete stable hook frame",
            description=(
                "The renderer QA object must report thumbnail_dimensions=true and a thumbnail_time inside the first scene after its full hook reveal. "
                "A partial title, blank scene, overlay card, or missing thumbnail is a failure."
            ),
            source=VIDEO_CREATION,
        ),
        EvalCriterion(
            id="media_gate_passed",
            name="All objective media checks pass",
            description=(
                "The renderer QA object must report passed=true. Any false check blocks delivery even if the copy manifest passes LLM judging."
            ),
            source=VIDEO_CREATION,
        ),
        EvalCriterion(
            id="scene_text_coverage",
            name="Every scene shows the complete expected text",
            description=(
                "The renderer QA object must report flow.scene_text_coverage_passed=true. "
                "Every scheduled scene is sampled in the browser and all expected visual words must be visible; missing words are a hard failure."
            ),
            source=VIDEO_CREATION,
        ),
        EvalCriterion(
            id="no_hidden_text_overflow",
            name="No hidden or clipped scene text",
            description=(
                "The renderer QA object must report flow.no_hidden_text_overflow=true. "
                "Visible text must remain inside the 1080x1920 viewport and must not exceed its DOM box; fixed template slots may not silently discard lines."
            ),
            source=VIDEO_CREATION,
        ),
        EvalCriterion(
            id="cta_layout",
            name="CTA lines are separated and readable",
            description=(
                "The renderer QA object must report flow.cta_layout_passed=true. "
                "The CTA title must render as two explicit block lines with no overlap, and the URL card must remain inside the viewport."
            ),
            source=VIDEO_CREATION,
        ),
        EvalCriterion(
            id="temporal_stability",
            name="Text does not flash or reappear",
            description=(
                "The renderer QA object must report temporal.passed=true. Capture must use deterministic motion, every scene must have one contiguous visibility interval, and boundary samples must not show the prior scene sentence after the next scene begins."
            ),
            source=VIDEO_CREATION,
        ),
    ),
)

EVAL_SUITES = (VIDEO_CTA_LINK, VIDEO_TEXT_SYNC, VIDEO_MEDIA_QA)
