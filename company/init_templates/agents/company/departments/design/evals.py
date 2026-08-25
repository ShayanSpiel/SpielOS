"""Design gates for visible, technically valid video renditions."""

from ...evals.models import EvalCriterion, EvalSuite

REGISTRY = "company/departments/design/templates/registry.json"
NARRATION = "company/departments/design/templates/video/narration.json"


def _items(payload):
    return [(item["item_id"], item) for item in (payload.get("items") or [])]


VIDEO_CTA_LINK = EvalSuite(
    id="video-cta-link", name="Video CTA review", scope="video-cta",
    department_id="design", payload_kind="campaign_manifest",
    description="The final visual CTA is readable and follows a clear product bridge.",
    validity="business", thresholds={"all_pass": True, "min_score": 1.0},
    payload_id_selector=lambda payload: str(payload.get("batch_id") or payload.get("id") or "payload"),
    item_selector=_items,
    criteria=(
        EvalCriterion("link", "Readable destination", "The CTA shows the canonical destination, not pronunciation guidance.", NARRATION),
        EvalCriterion("bridge", "Earned CTA", "The CTA follows the story's outcome and is visible long enough to read.", NARRATION),
    ),
)

VIDEO_TEXT_SYNC = EvalSuite(
    id="video-text-sync", name="Video visual review", scope="video-text",
    department_id="design", payload_kind="campaign_manifest",
    description="Visible text and components support the approved narration without clipping or placeholders.",
    validity="business", thresholds={"all_pass": True, "min_score": 1.0},
    payload_id_selector=lambda payload: str(payload.get("batch_id") or payload.get("id") or "payload"),
    item_selector=_items,
    criteria=(
        EvalCriterion("alignment", "Semantic alignment", "Each scene's visual supports its spoken line; literal repetition is not required.", NARRATION),
        EvalCriterion("visibility", "Complete visible text", "No expected visual text is clipped, hidden, or replaced by a template default.", REGISTRY),
    ),
)

VIDEO_MEDIA_QA = EvalSuite(
    id="video-media-qa", name="Video media QA", scope="video-media",
    department_id="design", payload_kind="video_render",
    description="The renderer-produced report confirms a complete, playable deliverable.",
    validity="technical_only", thresholds={"all_pass": True, "min_score": 1.0},
    payload_id_selector=lambda payload: str(payload.get("item_id") or payload.get("id") or "video-render"),
    criteria=(
        EvalCriterion("media", "Playable media", "The report confirms video and audio streams with the configured format.", NARRATION),
        EvalCriterion("timing", "Measured timing", "The report confirms measured scene timing and the configured duration limit.", NARRATION),
        EvalCriterion("thumbnail", "Stable thumbnail", "The report confirms a complete hook frame.", REGISTRY),
    ),
)

EVAL_SUITES = (VIDEO_CTA_LINK, VIDEO_TEXT_SYNC, VIDEO_MEDIA_QA)
