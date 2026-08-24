"""Content Department eval suites — grounded quality standards for campaign copy.

`content-copy-top10` is the judge-enforced content/ICP standard: ten criteria
grounded in the canonical strategy files and skills, judged PER ITEM against
the item's brief AND both platform renditions (threads + youtube copy).  The
content-campaign quality_gate requires a passing eval_report for this suite
before a campaign can advance to campaign_ready.

`content-story-whole` is the whole-narration gate introduced with the
storytelling-architecture change (goal-content-storytelling-architecture-v1-20260820):
campaign Shorts narration is judged as ONE complete story BEFORE design, so a
fragment-by-fragment script can never reach a template.

Adding a suite to ANY department follows the same Lego contract:
1. create `departments/<name>/evals.py` exporting EVAL_SUITES
2. register criteria with source-file grounding (strategy/skill paths)
3. declare `eval_suites = (...)` on the Department class
4. require a passing eval_report evidence in the machine step that gates
"""

from ...evals.models import EvalCriterion, EvalSuite

ICPC = "company/strategy/icp.md"
VOICE = "company/strategy/voice.md"
CONTENT_README = "company/departments/content/README.md"
COPYWRITING_EN = ".agents/skills/website/copywriting-en/SKILL.md"

CONTENT_COPY_TOP10 = EvalSuite(
    id="content-copy-top10",
    name="Content copy vs the ICP quality standard (top 10)",
    scope="content-copy",
    department_id="content",
    payload_kind="campaign_manifest",
    description=(
        "Ten ICP-grounded criteria judged per item against the item brief and "
        "both platform renditions. Every criterion must pass (all_pass, "
        "min_score 1.0) before campaign copy can advance through the quality gate."
    ),
    validity="business",
    thresholds={"all_pass": True, "min_score": 1.0},
    payload_id_selector=lambda payload: str(payload.get("batch_id") or payload.get("id") or "payload"),
    item_selector=lambda payload: [
        (item["item_id"], item) for item in (payload.get("items") or [])
    ],
    criteria=(
        EvalCriterion(
            id="one_reader",
            name="One ICP reader",
            description=(
                "The piece addresses exactly one ICP segment from icp.md: an "
                "established business operator/owner ($1M-25M+ revenue) fighting "
                "repetitive knowledge-work. Never developers, AI builders, or "
                "harness-obsessed audiences. The reader must match the brief."
            ),
            source=ICPC,
        ),
        EvalCriterion(
            id="one_moment",
            name="One recognized customer moment",
            description=(
                "The piece opens in (or immediately grounds in) a situation the "
                "reader recognizes from their own work — the brief's "
                "customer_moment — not in SpielOS's internal activity. The "
                "moment must be concrete and specific to the brief, never a "
                "generic AI complaint."
            ),
            source=CONTENT_README,
        ),
        EvalCriterion(
            id="one_idea",
            name="Exactly one useful idea",
            description=(
                "The piece carries exactly one useful point (the brief's "
                "one_idea); every sentence, bullet, and bridge serves that point. "
                "No second topic sneaks in."
            ),
            source=COPYWRITING_EN,
        ),
        EvalCriterion(
            id="cold_audience_clarity",
            name="Cold-audience clarity",
            description=(
                "Understandable to a cold audience that has never heard of "
                "SpielOS. No internal production vocabulary: batch, campaign, "
                "hook, review gate, Department, Artifact, runtime, harness rule, "
                "approval record, creative signature, content dispatch. No "
                "machinery words used as product features: instruction, public "
                "record, external confirmation, returned proof, ungrounded 'live "
                "record'. A first-time viewer must follow the whole piece and "
                "the benefit it names."
            ),
            source=COPYWRITING_EN,
        ),
        EvalCriterion(
            id="buyer_language",
            name="Concrete buyer language",
            description=(
                "The piece uses the buyer's concrete words — staff time, missed "
                "details, slow replies, repeated work, delivery speed, cost, "
                "capacity, errors — at a 3rd-5th grade reading level. Workflows "
                "are explained through the real work around them, not through "
                "product abstractions."
            ),
            source=VOICE,
        ),
        EvalCriterion(
            id="sharp_opening",
            name="Sharp, immediately understood opening",
            description=(
                "The first statement is understood immediately on first read. No "
                "theatrical contrast formulas, no vague SaaS claims, no jargon "
                "gate between the reader and the idea. (The locked hook line is "
                "part of the brief and is not re-scored as writer vocabulary.)"
            ),
            source=COPYWRITING_EN,
        ),
        EvalCriterion(
            id="honest_claims",
            name="Honest, supported claims",
            description=(
                "No unsupported claim and no fabricated numbers. Every claim is "
                "supported by strategy, assets, voice, or the item's own brief "
                "and proof. No implied complete autonomy or instant "
                "company-wide transformation."
            ),
            source=VOICE,
        ),
        EvalCriterion(
            id="platform_native",
            name="Platform-native shape",
            description=(
                "Threads: real paragraphs and bullets, each bullet on its own "
                "line, and any link on its own line after the CTA. YouTube "
                "Shorts: concise description, 'Link in bio.' for a CTA, and "
                "never a UTM URL in the description. Never literal \\n or \\r "
                "markers."
            ),
            source=COPYWRITING_EN,
        ),
        EvalCriterion(
            id="flow_brevity",
            name="Flow and brevity",
            description=(
                "Short sentences, active voice, present tense where possible, no "
                "filler, no repetition. Every sentence serves the one idea; any "
                "sentence that does not strengthen the idea is removed."
            ),
            source=VOICE,
        ),
        EvalCriterion(
            id="fifth_item_reminder",
            name="Fifth-item canonical reminder",
            description=(
                "Every fifth paired idea uses the canonical short reminder "
                "'SpielOS is running itself — an AI company.' as the brand "
                "closer (NOT the opener) and is not an internal run log. The "
                "reminder may cite one public proof point. Non-fifth items do "
                "not use the reminder; CTA is optional elsewhere."
            ),
            source=VOICE,
        ),
    ),
)


CONTENT_STORY_WHOLE = EvalSuite(
    id="content-story-whole",
    name="Short-form narration judged as one complete story (whole-story gate)",
    scope="content-story",
    department_id="content",
    payload_kind="campaign_manifest",
    description=(
        "Six whole-story criteria judged PER ITEM against the item's complete "
        "YouTube narration (`narration.script` + its ordered scenes), NOT "
        "against isolated clips. The narration must be written as one complete "
        "story BEFORE scene-splitting, cover the conversion arc Hook -> "
        "Pain/Context -> Why it matters -> AI/workflow mechanism -> SpielOS "
        "role -> Outcome -> CTA, and only then be assigned to a template. Every "
        "criterion must pass (all_pass, min_score 1.0) before design is locked."
    ),
    validity="business",
    thresholds={"all_pass": True, "min_score": 1.0},
    payload_id_selector=lambda payload: str(payload.get("batch_id") or payload.get("id") or "payload"),
    item_selector=lambda payload: [
        (item["item_id"], item) for item in (payload.get("items") or [])
    ],
    criteria=(
        EvalCriterion(
            id="cold_audience_context",
            name="Cold-audience context first",
            description=(
                "The hook scene opens in (or immediately establishes) a "
                "context a cold audience recognizes from their own work — the "
                "brief's customer_moment — BEFORE any SpielOS claim. A viewer "
                "who has never seen SpielOS must follow the first scene and "
                "want the next."
            ),
            source=CONTENT_README,
        ),
        EvalCriterion(
            id="causal_flow",
            name="Causal conversion arc",
            description=(
                "The whole narration follows the conversion arc in order: "
                "Hook -> Pain/Context -> Why it matters -> AI/workflow mechanism "
                "-> SpielOS role -> Outcome -> CTA. Each scene causes the next; "
                "no scene is a disconnected fragment and the script never "
                "restarts or backtracks."
            ),
            source=CONTENT_README,
        ),
        EvalCriterion(
            id="solution_clarity",
            name="Concrete solution clarity",
            description=(
                "The mechanism is concrete: what the workflow is, who reviews "
                "it, what visibly changes. No vague SaaS claims and no implied "
                "complete company-wide autonomy."
            ),
            source=VOICE,
        ),
        EvalCriterion(
            id="spielos_relevance",
            name="SpielOS relevance earned, not repeated",
            description=(
                "The story lands on the SpielOS role named by the brief's "
                "spielos_relevance: supervised workflows that turn repeated "
                "knowledge-work into owned operations. The bridge is natural to "
                "the mechanism and never repeats the same headline mechanically."
            ),
            source=CONTENT_README,
        ),
        EvalCriterion(
            id="earned_cta",
            name="CTA earned by the outcome",
            description=(
                "The final CTA follows from the story's outcome: the viewer "
                "knows what they would book and why it follows from the "
                "mechanism shown. No forced CTA on a story that gave no reason."
            ),
            source=VOICE,
        ),
        EvalCriterion(
            id="founder_personality",
            name="One founder voice throughout",
            description=(
                "The narration sounds like ONE founder who owns the room "
                "(voice.md): short punchy lines, deliberate pauses, zero "
                "formality. A single consistent narrator across every scene; no "
                "generic commercial voice and no tone drift or silent switch "
                "between scenes."
            ),
            source=VOICE,
        ),
    ),
)

EVAL_SUITES = (CONTENT_COPY_TOP10, CONTENT_STORY_WHOLE)
