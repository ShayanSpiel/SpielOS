#!/usr/bin/env python3
"""compiler.py — Content Engine Compiler (8-step sequence).

Pure functions: format the compiler sequence, validate, and atomically write
the LLM's creative output (core_insight + 6 meanings + selected_meaning) to
.content-brief.json. No CLI, no file I/O side effects beyond write_brief().
"""

from pathlib import Path

from engine_state import (
    CONTENT_BRIEF_FILE,
    read_brief,
    write_brief,
    clear_handoff,
)


TOPIC_TYPES = ["announcement", "explainer", "opinion", "teardown", "case-study", "how-to"]

ANNOUNCEMENT_KEYWORDS = [
    "ship", "shipped", "release", "released", "launch", "launched", "v1", "v2", "v3",
    "feature", "added", "merged", "rolled out", "public beta", "open source",
    "now available", "just shipped", "announce", "announcing",
]


def _infer_topic_kind(topic_text: str) -> str:
    """Heuristic: is this an announcement, explainer, opinion, etc.?"""
    if not topic_text:
        return "announcement"
    lower = topic_text.lower()
    score = sum(1 for kw in ANNOUNCEMENT_KEYWORDS if kw in lower)
    if score >= 1:
        return "announcement"
    if any(w in lower for w in ["how to", "how do", "tutorial", "guide", "step by step"]):
        return "how-to"
    if any(w in lower for w in ["why", "vs", "versus", "comparison", "compare"]):
        return "opinion"
    if any(w in lower for w in ["breakdown", "teardown", "anatomy of", "under the hood"]):
        return "teardown"
    if any(w in lower for w in ["case study", "client", "customer story", "before/after"]):
        return "case-study"
    if any(w in lower for w in ["explain", "what is", "primer", "intro to"]):
        return "explainer"
    return "announcement"


def format_compiler_sequence(brief: dict, icp_world_text: str, session_evidence: str, meaning_axes: list[str]) -> str:
    """Render the Compiler handoff display. Two modes:
      - session: the build-to-public 8-step sequence (session IS evidence, ICP world IS subject)
      - topic:   the announcement/explainer 6-question sequence (topic IS the subject)
    Branch is read from brief["source"]["kind"] (set by cmd_content_post).
    """
    source = brief.get("source", {})
    kind = (source.get("kind") or "session").lower()
    if kind == "topic":
        return _format_topic_compiler(brief, source, icp_world_text, meaning_axes)
    return _format_session_compiler(brief, source, icp_world_text, session_evidence, meaning_axes)


def _format_session_compiler(brief, source, icp_world_text, session_evidence, meaning_axes):
    lines = []
    lines.append("═══ Content Engine Compiler — SESSION MODE ═══")
    lines.append("")
    lines.append("Follow this pipeline exactly. The session is NOT the subject.")
    lines.append("The ICP world is the subject. Session is evidence.")
    lines.append("")

    session_path = brief.get("session")
    if session_path:
        lines.append(f"  Session evidence: {session_path}")
    else:
        label = source.get("label", "topic mode")
        lines.append(f"  Topic evidence: {label}")
    lines.append("")

    lines.append("  (ICP world: see concepts/icp-offer.md for full profile)")
    lines.append("")
    lines.append("═══ SESSION (EVIDENCE ONLY) ═══")
    lines.append(session_evidence)
    lines.append("")
    lines.append("═══ END SESSION EVIDENCE ═══")
    lines.append("")

    lines.append("─" * 60)
    lines.append("COMPILER SEQUENCE — Run these 8 steps in order:")
    lines.append("─" * 60)
    lines.append("")
    lines.append("STEP 1: LOAD ICP WORLD (DO NOT USE SESSION YET)")
    lines.append("  Fully reconstruct the ICP as a living mental world:")
    lines.append("  - beliefs / frustrations / constraints / identity tension")
    lines.append("  - current confusion state / language style")
    lines.append("  This ICP world must exist independently of the session.")
    lines.append("")
    lines.append("STEP 2: SIMULATE ICP REALITY")
    lines.append("  Imagine ICP is actively experiencing their world TODAY.")
    lines.append("  They are NOT reading about your session.")
    lines.append("  They are living their problem space.")
    lines.append("")
    lines.append("STEP 3: LOAD SESSION AS PURE EVIDENCE (NOT TOPIC)")
    lines.append("  Session is NOT the subject.")
    lines.append("  Session is ONLY evidence that something in ICP world is true or false.")
    lines.append("")
    lines.append("STEP 4: MAP SESSION \u2192 ICP WORLD (NOT ICP \u2192 SESSION)")
    lines.append("  Ask: what ICP belief does this contradict / frustration expose / mental model break?")
    lines.append("")
    lines.append("─" * 60)
    lines.append("PHASE 1: DIVERGENT MEANING EXTRACTION \u2014 6 axes")
    lines.append("─" * 60)
    lines.append("")
    lines.append("STEP 5: EXTRACT 6 MEANINGS (one sentence per axis)")
    for axis in meaning_axes:
        lines.append(f"")
        lines.append(f"  {axis.capitalize()} Meaning:")
        if axis == "systemic":
            lines.append("    The system/invariant mechanics \u2014 what structural truth does")
            lines.append("    the session reveal about how content/publishing/expertise works?")
        elif axis == "behavioral":
            lines.append("    What builders do and why \u2014 the pattern of behavior this session exposes.")
        elif axis == "philosophical":
            lines.append("    The deeper truth about knowledge, information, or creation.")
            lines.append("    What universal principle does this session touch?")
        elif axis == "contrarian":
            lines.append("    The industry assumption this session inverts.")
        elif axis == "leverage":
            lines.append("    The highest-leverage action this session points to.")
        elif axis == "human":
            lines.append("    The psychological/emotional layer \u2014 human need, fear, or identity tension.")
    lines.append("")
    lines.append("─" * 60)
    lines.append("PHASE 2: SELECTION GATE")
    lines.append("─" * 60)
    lines.append("")
    lines.append("STEP 6: SELECT ONE MEANING (axis + rationale)")
    lines.append("  Choose which axis carries the most tension for the ICP.")
    lines.append("")
    lines.append("─" * 60)
    lines.append("PHASE 3: COMPRESSION")
    lines.append("─" * 60)
    lines.append("")
    lines.append("STEP 7: EXTRACT SINGLE CORE INSIGHT")
    lines.append("  One sentence only. Must describe ICP world shift, not system mechanics.")
    lines.append("")
    lines.append("STEP 8: GENERATE CONTENT")
    lines.append("  Write content for ICP audience only.")
    lines.append("  Use the selected meaning axis to choose tone + framing.")
    lines.append("  Use core_insight as the lens.")
    lines.append("")
    lines.append("─" * 60)
    lines.append("HARD CONSTRAINTS (CRITICAL)")
    lines.append("─" * 60)
    lines.append("")
    lines.append("DO NOT mention: session structure, schema fields, pipeline, engine,")
    lines.append("  reader_failure_mode, belief/consequence/mapping as labels, build logs")
    lines.append("DO NOT write: 'we added', 'we changed the system', 'in this session'")
    lines.append("ONLY output: ICP world insights, human-level narrative, lived experience framing")
    lines.append("")
    lines.append("─" * 60)
    lines.append("AFTER RUNNING ALL 8 STEPS")
    lines.append("─" * 60)
    lines.append("")
    lines.append("Write to .content-brief.json:")
    lines.append("  1. core_insight (string) \u2014 one sentence from Step 7")
    lines.append("  2. meanings (object) \u2014 all 6 axes from Step 5")
    lines.append("  3. selected_meaning (object) \u2014 axis + rationale from Step 6")
    lines.append("")

    lines.append("─" * 60)
    lines.append("CURRENT BRIEF STATE")
    lines.append("─" * 60)
    core_insight = brief.get("core_insight", "")
    meanings = brief.get("meanings", {})
    selected = brief.get("selected_meaning", {})
    if core_insight:
        lines.append(f"  core_insight: {core_insight}")
    else:
        lines.append("  core_insight: (empty \u2014 must be filled)")
    for axis in meaning_axes:
        val = meanings.get(axis, "")
        if val:
            lines.append(f"  meanings.{axis}: {val[:60]}...")
        else:
            lines.append(f"  meanings.{axis}: (empty \u2014 must be filled)")
    axis_sel = selected.get("axis", "")
    rationale = selected.get("rationale", "")
    empty_label = "empty \u2014 must be filled"
    lines.append(f"  selected_meaning.axis: {axis_sel or '(' + empty_label + ')'}")
    lines.append(f"  selected_meaning.rationale: {(rationale[:60] + '...') if rationale else '(' + empty_label + ')'}")

    return "\n".join(lines)


def _format_topic_compiler(brief, source, icp_world_text, meaning_axes):
    """Topic-mode compiler: the topic IS the subject. Used for announcements,
    explainers, opinions, teardowns, case-studies, how-tos.

    Different from session mode in three ways:
      1. Topic is the SUBJECT, not evidence. Announce the thing.
      2. core_insight = "the one thing the reader walks away knowing" (not
         "ICP world shift"). For announcements, this is the value proposition.
      3. Hard constraints are relaxed: "we shipped" / "we added" / "now
         available" / partner mentions (e.g. @buffer) are ENCOURAGED.
    """
    lines = []
    topic_label = source.get("label") or "(no topic)"
    topic_text = source.get("text") or ""
    topic_kind = source.get("topic_kind") or _infer_topic_kind(topic_text)
    strategy = brief.get("strategy") or {}

    arch = strategy.get("archetype") or "?"
    arch_label = strategy.get("archetype_label") or ""
    vertical = strategy.get("vertical") or "?"
    funnel = strategy.get("funnel_stage") or "?"
    layer = strategy.get("icp_layer") or "?"

    lines.append("═══ Content Engine Compiler — TOPIC MODE ═══")
    lines.append("")
    lines.append("The topic IS the subject. Announce it, explain it, defend it.")
    lines.append("Reader outcome, not ICP world shift.")
    lines.append("")
    lines.append(f"  Topic:        {topic_label}")
    lines.append(f"  Topic kind:   {topic_kind}")
    lines.append(f"  Archetype:    {arch} ({arch_label})")
    lines.append(f"  Vertical:     {vertical}")
    lines.append(f"  Funnel:       {funnel}")
    lines.append(f"  ICP layer:    {layer}")
    lines.append("")
    lines.append("  (ICP profile for TONE: see concepts/icp-offer.md — use it for")
    lines.append("   language register, not to suppress the announcement itself.)")
    lines.append("")
    try:
        from engine_config import Config
        mode_routing = (Config()._load().get("compiler") or {}).get("mode_routing") or {}
        topic_routing = mode_routing.get("topic") or {}
        if topic_routing:
            default_axis = topic_routing.get("default_axis", "leverage")
            default_funnel = topic_routing.get("default_funnel", "MOFU")
            cta = topic_routing.get("cta", "try-it")
            lines.append(f"  Topic-mode routing hint: default axis={default_axis}, funnel={default_funnel}, cta={cta}")
            override = topic_routing.get("archetype_funnel_override") or {}
            if arch in override:
                lines.append(f"  Override for {arch}: funnel={override[arch]} (announcements drive installs/usage, not passive authority).")
            lines.append("")
    except Exception:
        pass
    lines.append("═══ TOPIC (THE SUBJECT) ═══")
    lines.append(topic_text or "(empty topic)")
    lines.append("")
    lines.append("═══ END TOPIC ═══")
    lines.append("")

    lines.append("─" * 60)
    lines.append("COMPILER SEQUENCE — Run these 6 questions in order:")
    lines.append("─" * 60)
    lines.append("")
    lines.append("Q1: POST TYPE")
    lines.append("  What kind of post is this? Pick one:")
    lines.append("    - announcement  → we shipped / launched / released X")
    lines.append("    - explainer     → teach the reader how/why something works")
    lines.append("    - opinion       → take a side on a debate")
    lines.append("    - teardown      → dissect a real artifact in public")
    lines.append("    - case-study    → show a result with permission")
    lines.append("    - how-to        → step-by-step instructions")
    lines.append("")
    lines.append("Q2: READER OUTCOME")
    lines.append("  In one sentence, what does the reader walk away knowing?")
    lines.append("  This is the takeaway, not the agenda. Concrete, not abstract.")
    lines.append("")
    lines.append("Q3: 6 ANGLES (one sentence per axis, reframed for the topic)")
    for axis in meaning_axes:
        lines.append(f"")
        lines.append(f"  {axis.capitalize()} angle:")
        if axis == "systemic":
            lines.append("    What system/invariant does this topic reveal?")
        elif axis == "behavioral":
            lines.append("    What does the reader's behavior change to after this?")
        elif axis == "philosophical":
            lines.append("    What principle about building/knowing/creating does this touch?")
        elif axis == "contrarian":
            lines.append("    What industry assumption does this topic contradict?")
        elif axis == "leverage":
            lines.append("    What is the highest-leverage thing the reader can do AFTER reading?")
        elif axis == "human":
            lines.append("    What identity shift or emotional beat does this topic carry?")
    lines.append("")
    lines.append("─" * 60)
    lines.append("Q4: PICK ONE AXIS")
    lines.append("  For announcements: usually 'leverage' (what it unlocks) or")
    lines.append("  'contrarian' (what's surprising). Default-funnel hint below.")
    lines.append("  For explainers: usually 'systemic' or 'behavioral'.")
    lines.append("  For opinions: usually 'contrarian' or 'philosophical'.")
    lines.append("")
    lines.append("─" * 60)
    lines.append("Q5: CORE_INSIGHT (the one sentence the post must deliver)")
    lines.append("  - For announcements: the value prop. What shipped, why it matters,")
    lines.append("    what the reader gets. Concrete, not abstract.")
    lines.append("  - For explainers: the mechanism. The one thing the reader 'gets'")
    lines.append("    that they didn't get before.")
    lines.append("  - For opinions: the take. The position, stated in one sentence.")
    lines.append("  This is NOT an 'ICP world shift' — it's the post's payload.")
    lines.append("")
    lines.append("Q6: HOOK + NEXT-STEP")
    lines.append("  - First 2 lines: name the topic. Reader knows in 5 sec what's new.")
    lines.append("  - Last 1-2 lines: a verb-driven next step (clone, install, try,")
    lines.append("    read, reply, sign up, comment).")
    lines.append("")
    lines.append("─" * 60)
    lines.append("HARD CONSTRAINTS (TOPIC MODE — CRITICAL)")
    lines.append("─" * 60)
    lines.append("")
    lines.append("ENCOURAGED in topic mode (this is the whole point):")
    lines.append("  - 'we shipped', 'we added', 'we released', 'now available'")
    lines.append("  - 'just shipped', 'just released', 'this week'")
    lines.append("  - Naming partners/credits: '@buffer', 'thanks to X', 'built with Y'")
    lines.append("  - Verb-driven CTAs: 'clone it', 'try the templates', 'reply with'")
    lines.append("  - Specific numbers: '3 channels', '3000 calls/month', 'v2.1'")
    lines.append("  - Naming what shipped: feature names, file paths, version numbers")
    lines.append("")
    lines.append("STILL BANNED in topic mode (same as session):")
    lines.append("  - 'i'm excited to share', 'hey friends', 'i'm thrilled'")
    lines.append("  - Engagement bait ('Like if you agree', 'Share if this resonates')")
    lines.append("  - Corporate buzzwords (utilize, leverage, optimize, facilitate)")
    lines.append("  - Em dashes (use →, colons, or commas)")
    lines.append("  - Internal labels (S1-S10, TOFU/MOFU/BOFU, L1-L4, 'the engine',")
    lines.append("    'the pipeline', 'session-as-content' as surface labels)")
    lines.append("  - Same noun 3+ times in a post")
    lines.append("")
    lines.append("─" * 60)
    lines.append("AFTER RUNNING ALL 6 QUESTIONS")
    lines.append("─" * 60)
    lines.append("")
    lines.append("Write to .content-brief.json (same shape as session mode):")
    lines.append("  1. core_insight (string) — the takeaway from Q5")
    lines.append("  2. meanings (object) — all 6 axes from Q3")
    lines.append("  3. selected_meaning (object) — axis + rationale from Q4")
    lines.append("")

    lines.append("─" * 60)
    lines.append("CURRENT BRIEF STATE")
    lines.append("─" * 60)
    core_insight = brief.get("core_insight", "")
    meanings = brief.get("meanings", {})
    selected = brief.get("selected_meaning", {})
    if core_insight:
        lines.append(f"  core_insight: {core_insight}")
    else:
        lines.append("  core_insight: (empty — must be filled)")
    for axis in meaning_axes:
        val = meanings.get(axis, "")
        if val:
            lines.append(f"  meanings.{axis}: {val[:60]}...")
        else:
            lines.append(f"  meanings.{axis}: (empty — must be filled)")
    axis_sel = selected.get("axis", "")
    rationale = selected.get("rationale", "")
    empty_label = "empty — must be filled"
    lines.append(f"  selected_meaning.axis: {axis_sel or '(' + empty_label + ')'}")
    lines.append(f"  selected_meaning.rationale: {(rationale[:60] + '...') if rationale else '(' + empty_label + ')'}")
    lines.append(f"  topic_kind: {topic_kind}")

    return "\n".join(lines)


def validate_brief(brief: dict, meaning_axes: list[str]) -> list[str]:
    missing = []
    if not brief.get("core_insight", "").strip():
        missing.append("core_insight")
    meanings = brief.get("meanings", {})
    for axis in meaning_axes:
        if not meanings.get(axis, "").strip():
            missing.append(f"meanings.{axis}")
    selected = brief.get("selected_meaning", {})
    if not selected.get("axis", "").strip():
        missing.append("selected_meaning.axis")
    if not selected.get("rationale", "").strip():
        missing.append("selected_meaning.rationale")
    return missing


def compile_write(
    core_insight: str,
    meanings: dict[str, str],
    selected_axis: str,
    selected_rationale: str,
    meaning_axes: list[str] | None = None,
) -> tuple[bool, str]:
    """Atomically merge the LLM's Compiler output into .content-brief.json.

    Validates that all required fields are non-empty, then writes. On success,
    clears the active handoff marker so the kernel can advance to SELECT.

    Returns (ok, message). On failure, message is a human-readable error;
    on success, message describes what was written.
    """
    axes = meaning_axes or MEANING_AXES_DEFAULT
    if not (core_insight or "").strip():
        return False, "core_insight is empty"
    for axis in axes:
        if not (meanings.get(axis) or "").strip():
            return False, f"meanings.{axis} is empty"
    if not (selected_axis or "").strip():
        return False, "selected_meaning.axis is empty"
    if not (selected_rationale or "").strip():
        return False, "selected_meaning.rationale is empty"

    brief = read_brief()
    if not brief:
        return False, "no .content-brief.json — run `engine.py content run` first"

    brief["core_insight"] = core_insight.strip()
    brief["meanings"] = {ax: (meanings.get(ax) or "").strip() for ax in axes}
    brief["selected_meaning"] = {
        "axis": selected_axis.strip(),
        "rationale": selected_rationale.strip(),
    }
    clear_handoff(brief)
    write_brief(brief)
    return True, (
        f"wrote core_insight + 6 meanings + selected_meaning[{selected_axis}] "
        f"to {CONTENT_BRIEF_FILE.relative_to(brief.get('_vault', '.')) if False else '.content-brief.json'}"
    )


MEANING_AXES_DEFAULT = [
    "systemic", "behavioral", "philosophical", "contrarian", "leverage", "human",
]
