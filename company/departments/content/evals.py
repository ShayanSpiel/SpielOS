"""Content eval registry. Criteria are identifiers with source references; rules live in text authorities."""

from ...evals.models import EvalCriterion, EvalSuite

ICPC = ".agents/company/strategy/icp.md"
VOICE = ".agents/company/strategy/voice.md"
COPYWRITING_EN = ".agents/company/skills/copywriting/SKILL.md"

def _criterion(identifier: str, name: str, source: str) -> EvalCriterion:
    return EvalCriterion(id=identifier, name=name, description=f"Source: {source}", source=source)

CONTENT_COPY_TOP10 = EvalSuite(
    id="content-copy-top10",
    name="Content copy quality",
    scope="content-copy",
    department_id="content",
    payload_kind="campaign_manifest",
    description="Ten criteria; all must pass.",
    validity="business",
    thresholds={"all_pass": True, "min_score": 1.0},
    payload_id_selector=lambda payload: str(payload.get("batch_id") or payload.get("id") or "payload"),
    item_selector=lambda payload: [(item["item_id"], item) for item in (payload.get("items") or [])],
    criteria=(
        _criterion("one_reader", "One ICP reader", ICPC),
        _criterion("one_moment", "One customer moment", ICPC),
        _criterion("one_idea", "One useful idea", COPYWRITING_EN),
        _criterion("cold_audience_clarity", "Cold-audience clarity", COPYWRITING_EN),
        _criterion("buyer_language", "Buyer language", VOICE),
        _criterion("sharp_opening", "Human opening", VOICE),
        _criterion("honest_claims", "Supported claims", VOICE),
        _criterion("platform_native", "Platform fit", COPYWRITING_EN),
        _criterion("flow_brevity", "Flow and brevity", VOICE),
        _criterion("fifth_item_reminder", "Fifth-item reminder", VOICE),
    ),
)

CONTENT_STORY_WHOLE = EvalSuite(
    id="content-story-whole",
    name="Short-form narration quality",
    scope="content-story",
    department_id="content",
    payload_kind="campaign_manifest",
    description="Six criteria; all must pass.",
    validity="business",
    thresholds={"all_pass": True, "min_score": 1.0},
    payload_id_selector=lambda payload: str(payload.get("batch_id") or payload.get("id") or "payload"),
    item_selector=lambda payload: [(item["item_id"], item) for item in (payload.get("items") or [])],
    criteria=(
        _criterion("cold_audience_context", "Cold-audience context", ICPC),
        _criterion("causal_flow", "Causal flow", COPYWRITING_EN),
        _criterion("solution_clarity", "Solution clarity", VOICE),
        _criterion("spielos_relevance", "SpielOS relevance", COPYWRITING_EN),
        _criterion("earned_cta", "Earned CTA", COPYWRITING_EN),
        _criterion("founder_personality", "Founder voice", VOICE),
    ),
)

EVAL_SUITES = (CONTENT_COPY_TOP10, CONTENT_STORY_WHOLE)
