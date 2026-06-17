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


def format_compiler_sequence(brief: dict, icp_world_text: str, session_evidence: str, meaning_axes: list[str]) -> str:
    lines = []
    lines.append("═══ Content Engine Compiler ═══")
    lines.append("")
    lines.append("Follow this pipeline exactly. The session is NOT the subject.")
    lines.append("The ICP world is the subject. Session is evidence.")
    lines.append("")

    session_path = brief.get("session")
    if session_path:
        lines.append(f"  Session evidence: {session_path}")
    else:
        source = brief.get("source", {})
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
