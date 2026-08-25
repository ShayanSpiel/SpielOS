"""Editorial gates for Content.

These gates judge message quality. The campaign contract owns artifact shape and
platform safety; the writer skill owns drafting guidance.
"""

from ...evals.models import EvalCriterion, EvalSuite

ICP = "company/strategy/icp.md"
VOICE = "company/strategy/voice.md"
CONTRACT = "company/departments/campaign_contract.py"


def _items(payload):
    return [(item["item_id"], item) for item in (payload.get("items") or [])]


CONTENT_COPY_TOP10 = EvalSuite(
    id="content-copy-top10",
    name="Content editorial review",
    scope="content-copy",
    department_id="content",
    payload_kind="campaign_manifest",
    description="Judge each rendition for buyer relevance, one clear idea, supported claims, and native form.",
    validity="business",
    thresholds={"all_pass": True, "min_score": 1.0},
    payload_id_selector=lambda payload: str(payload.get("batch_id") or payload.get("id") or "payload"),
    item_selector=_items,
    criteria=(
        EvalCriterion("buyer", "Right buyer", "Matches the item brief and canonical ICP, not an internal-operations audience.", ICP),
        EvalCriterion("idea", "One useful idea", "The copy makes one concrete point in the buyer's language.", VOICE),
        EvalCriterion("claims", "Supported claims", "Claims follow the supplied proof and do not imply unsupported autonomy or outcomes.", VOICE),
        EvalCriterion("native", "Native form", "The rendition is clear and follows its platform contract.", CONTRACT),
    ),
)

CONTENT_STORY_WHOLE = EvalSuite(
    id="content-story-whole",
    name="Narration editorial review",
    scope="content-story",
    department_id="content",
    payload_kind="campaign_manifest",
    description="Judge the complete narration before Design selects a template or scenes.",
    validity="business",
    thresholds={"all_pass": True, "min_score": 1.0},
    payload_id_selector=lambda payload: str(payload.get("batch_id") or payload.get("id") or "payload"),
    item_selector=_items,
    criteria=(
        EvalCriterion("context", "Recognizable context", "A cold viewer can recognize the customer moment before the product bridge.", ICP),
        EvalCriterion("flow", "Complete story", "The script moves from context to consequence, mechanism, outcome, and an earned CTA.", VOICE),
        EvalCriterion("role", "Earned relevance", "SpielOS appears as the brief's relevant supervised-workflow role, not a repeated slogan.", VOICE),
    ),
)

EVAL_SUITES = (CONTENT_COPY_TOP10, CONTENT_STORY_WHOLE)
