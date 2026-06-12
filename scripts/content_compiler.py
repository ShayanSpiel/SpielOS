#!/usr/bin/env python3
"""content_compiler.py — Content Engine Compiler (8-step sequence).

Runs the new Compiler format between STRATEGY_LOAD and DRAFTING.
Loads ICP world, presents session as evidence, and guides the LLM
through the 8-step sequence (Steps 1-8 including 6-meaning extraction
and selection gate). Validates core_insight + all 6 meanings + selection
exist in .content-brief.json before allowing drafting.

Usage:
    python3 scripts/content_compiler.py             # Print Compiler sequence (state: ICP_WORLD_BUILD)
    python3 scripts/content_compiler.py --validate   # Validate brief fields, exit 0 if ready
"""

import argparse
import json
import sys
from pathlib import Path

VAULT = Path(__file__).resolve().parent.parent
BRIEF_FILE = VAULT / ".content-brief.json"
ICP_SCRIPT = VAULT / "scripts" / "icp_world.py"
RULES_FILE = VAULT / "rules.yaml"


def _load_rules() -> dict:
    """Load rules.yaml for config values."""
    try:
        import yaml
        with RULES_FILE.open() as f:
            return yaml.safe_load(f) or {}
    except Exception:
        return {}


def _meaning_axes() -> list[str]:
    """Read meaning axes from rules.yaml with fallback."""
    rules = _load_rules()
    return rules.get("compiler", {}).get("meaning_axes", [
        "systemic", "behavioral", "philosophical", "contrarian", "leverage", "human",
    ])


def read_brief() -> dict:
    """Read .content-brief.json."""
    if not BRIEF_FILE.exists():
        return {}
    try:
        return json.loads(BRIEF_FILE.read_text())
    except json.JSONDecodeError:
        return {}


def write_brief(brief: dict) -> None:
    """Write .content-brief.json atomically."""
    import tempfile
    tmp = tempfile.NamedTemporaryFile(
        mode="w", dir=str(VAULT), prefix=".content-brief-", suffix=".tmp", delete=False
    )
    try:
        json.dump(brief, tmp, indent=2)
        tmp.close()
        import os
        os.replace(tmp.name, str(BRIEF_FILE))
    except Exception:
        if tmp and Path(tmp.name).exists():
            Path(tmp.name).unlink()
        raise


def load_icp_world() -> str:
    """Run icp_world.py and return its output."""
    import subprocess
    try:
        result = subprocess.run(
            [sys.executable, str(ICP_SCRIPT)],
            capture_output=True, text=True, timeout=30,
        )
        return result.stdout
    except subprocess.TimeoutExpired:
        return "ERROR: icp_world.py timed out"
    except Exception as e:
        return f"ERROR: {e}"


def load_session_evidence(brief: dict) -> str:
    """Extract session evidence from brief for the Compiler."""
    session_path = brief.get("session")
    if not session_path:
        return "(no session — topic mode: use topic as evidence instead)"

    session_full = Path(session_path)
    if not session_full.is_absolute():
        session_full = VAULT / session_path

    if not session_full.exists():
        return "(session file not found)"

    content = session_full.read_text()

    evidence_parts = []

    # Extract frontmatter
    if content.startswith("---"):
        parts = content.split("---", 2)
        if len(parts) >= 2:
            fm_lines = parts[1].strip().split("\n")
            # Pull title and key signal fields
            for line in fm_lines:
                for key in ("title:", "decision:", "number:", "lesson:", "pattern:", "ship:"):
                    if line.strip().startswith(key):
                        evidence_parts.append(f"  {line.strip()}")
                        break

    # Extract reader_failure_mode
    if content.startswith("---"):
        import yaml
        parts = content.split("---", 2)
        if len(parts) >= 2:
            try:
                fm_parsed = yaml.safe_load(parts[1])
                if isinstance(fm_parsed, dict):
                    rfm = fm_parsed.get("reader_failure_mode", {})
                    if isinstance(rfm, dict) and rfm.get("belief"):
                        evidence_parts.append(f"  reader_failure_mode:")
                        evidence_parts.append(f"    belief: {rfm['belief']}")
                    if isinstance(rfm, dict) and rfm.get("consequence"):
                        evidence_parts.append(f"    consequence: {rfm['consequence']}")
                    if isinstance(rfm, dict) and rfm.get("mapping"):
                        evidence_parts.append(f"    mapping: {rfm['mapping']}")
            except yaml.YAMLError:
                pass

    # Extract Divergent Meanings if present
    if "## Divergent Meanings Output" in content:
        dm_section = content.split("## Divergent Meanings Output", 1)[1]
        dm_section = dm_section.split("---", 1)[0] if "---" in dm_section else dm_section
        dm_section = dm_section.split("## ", 1)[0]
        evidence_parts.append("")
        evidence_parts.append("  Divergent Meanings Output (selected):")
        for line in dm_section.strip().split("\n")[:15]:
            evidence_parts.append(f"  {line}")

    return "\n".join(evidence_parts)


def print_compiler_sequence(brief: dict) -> None:
    """Print the 6-step Content Engine Compiler sequence."""
    print("═══ Content Engine Compiler ═══")
    print()
    print("Follow this pipeline exactly. The session is NOT the subject.")
    print("The ICP world is the subject. Session is evidence.")
    print()

    # Step 0: Validate evidence
    session_path = brief.get("session")
    if session_path:
        print(f"  Session evidence: {session_path}")
    else:
        source = brief.get("source", {})
        label = source.get("label", "topic mode")
        print(f"  Topic evidence: {label}")
    print()

    # Print ICP world
    icp_output = load_icp_world()
    print(icp_output)
    print()

    # Print session as evidence
    print("═══ SESSION (EVIDENCE ONLY) ═══")
    evidence = load_session_evidence(brief)
    print(evidence)
    print()
    print("═══ END SESSION EVIDENCE ═══")
    print()

    # Print the 6 Compiler steps
    print("─" * 60)
    print("COMPILER SEQUENCE — Run these 8 steps in order:")
    print("─" * 60)
    print()

    print("STEP 1: LOAD ICP WORLD (DO NOT USE SESSION YET)")
    print("  Fully reconstruct the ICP as a living mental world:")
    print("  - beliefs")
    print("  - frustrations")
    print("  - constraints")
    print("  - identity tension")
    print("  - current confusion state")
    print("  - language style")
    print("  This ICP world must exist independently of the session.")
    print()

    print("STEP 2: SIMULATE ICP REALITY")
    print("  Imagine ICP is actively experiencing their world TODAY.")
    print("  They are NOT reading about your session.")
    print("  They are living their problem space.")
    print()

    print("STEP 3: LOAD SESSION AS PURE EVIDENCE (NOT TOPIC)")
    print("  Session is NOT the subject.")
    print("  Session is NOT the story.")
    print("  Session is ONLY evidence that something in ICP world is true or false.")
    print()

    print("STEP 4: MAP SESSION → ICP WORLD (NOT ICP → SESSION)")
    print("  Ask:")
    print("  - What ICP belief does this contradict?")
    print("  - What ICP frustration does this expose?")
    print("  - What ICP mental model breaks because of this?")
    print()

    print("─" * 60)
    print("PHASE 1: DIVERGENT MEANING EXTRACTION — 6 axes")
    print("─" * 60)
    print()

    print("STEP 5: EXTRACT 6 MEANINGS (one sentence per axis)")
    print()
    print("  Systemic Meaning:")
    print("    The system/invariant mechanics — what structural truth does")
    print("    the session reveal about how content/publishing/expertise works?")
    print()
    print("  Behavioral Meaning:")
    print("    What builders do and why — the pattern of behavior this session")
    print("    exposes. Focus on the ICP's habits, instincts, blind spots.")
    print()
    print("  Philosophical Meaning:")
    print("    The deeper truth about knowledge, information, or creation.")
    print("    What universal principle does this session touch?")
    print()
    print("  Contrarian Meaning:")
    print("    The industry assumption this session inverts. What does everyone")
    print("    believe that this session proves wrong?")
    print()
    print("  Leverage Meaning:")
    print("    The highest-leverage action this session points to. If the ICP")
    print("    does ONE thing differently after reading, what should it be?")
    print()
    print("  HUMAN Meaning (ψ):")
    print("    The psychological/emotional layer. This is not about systems or")
    print("    strategy — it is about the human need, fear, or identity tension")
    print("    underneath. This is often the most resonant axis.")
    print()

    print("─" * 60)
    print("PHASE 2: SELECTION GATE")
    print("─" * 60)
    print()

    print("STEP 6: SELECT ONE MEANING (axis + rationale)")
    print("  Choose which axis carries the most tension for the ICP.")
    print("  Store the selected axis name and a rationale explaining why")
    print("  this axis was chosen over the others.")
    print()

    print("─" * 60)
    print("PHASE 3: COMPRESSION")
    print("─" * 60)
    print()

    print("STEP 7: EXTRACT SINGLE CORE INSIGHT")
    print("  One sentence only.")
    print("  Must describe ICP world shift, not system mechanics.")
    print("  This is the lens for ALL content produced in Step 8.")
    print()

    print("STEP 8: GENERATE CONTENT")
    print("  Write content for ICP audience only.")
    print('  Use the selected meaning axis to choose tone + framing.')
    print('  Use core_insight as the lens.')
    print('  Content must feel like: "this is about my world" (ICP)')
    print('  NOT: "this is about a system update"')
    print()

    # Hard constraints
    print("─" * 60)
    print("HARD CONSTRAINTS (CRITICAL)")
    print("─" * 60)
    print()
    print("❌ DO NOT mention:")
    print("  - session structure")
    print("  - schema fields")
    print("  - pipeline")
    print("  - engine")
    print("  - reader_failure_mode")
    print("  - belief/consequence/mapping as labels")
    print("  - system design")
    print("  - build logs")
    print("  - engineering implementation")
    print()
    print("❌ DO NOT write:")
    print('  - "we added"')
    print('  - "we changed the system"')
    print('  - "we updated the schema"')
    print('  - "in this session"')
    print()
    print("✔ ONLY output:")
    print("  - ICP world insights")
    print("  - human-level narrative")
    print("  - lived experience framing")
    print()

    # Quality test
    print("─" * 60)
    print("QUALITY TEST (must pass before output)")
    print("─" * 60)
    print()
    print("  - If reader can detect 'system talk' → FAIL")
    print("  - If content sounds like engineering notes → FAIL")
    print("  - If session is directly referenced → FAIL")
    print("  - If ICP feels absent or generic → FAIL")
    print("  - If insight is about your tool instead of their world → FAIL")
    print()

    # Instructions for saving results
    print("─" * 60)
    print("AFTER RUNNING ALL 8 STEPS")
    print("─" * 60)
    print()
    print("Write the following into .content-brief.json:")
    print()
    print("1. core_insight (string) — one sentence from Step 7")
    print("2. meanings (object) — all 6 axes from Step 5:")
    print("   - systemic (string)")
    print("   - behavioral (string)")
    print("   - philosophical (string)")
    print("   - contrarian (string)")
    print("   - leverage (string)")
    print("   - human (string)")
    print("3. selected_meaning (object) — selection from Step 6:")
    print("   - axis (string) — one of the 6 axes")
    print("   - rationale (string) — why this axis was chosen")
    print()
    print("Do NOT draft until all fields exist in .content-brief.json.")
    print()
    print("To save, update .content-brief.json with:")
    print('  {"core_insight": "<sentence>", "meanings": {"systemic": "...", ...}, "selected_meaning": {"axis": "human", "rationale": "..."}}')
    print()

    # Show current brief state
    print("─" * 60)
    print("CURRENT BRIEF STATE")
    print("─" * 60)
    core_insight = brief.get("core_insight", "")
    meanings = brief.get("meanings", {})
    selected = brief.get("selected_meaning", {})
    if core_insight:
        print(f"  core_insight: {core_insight}")
    else:
        print("  core_insight: (empty — must be filled)")
    meaning_axes = ["systemic", "behavioral", "philosophical", "contrarian", "leverage", "human"]
    for axis in meaning_axes:
        val = meanings.get(axis, "")
        if val:
            print(f"  meanings.{axis}: {val[:60]}...")
        else:
            print(f"  meanings.{axis}: (empty — must be filled)")
    axis_sel = selected.get("axis", "")
    rationale = selected.get("rationale", "")
    if axis_sel:
        print(f"  selected_meaning.axis: {axis_sel}")
    else:
        print("  selected_meaning.axis: (empty — must be filled)")
    if rationale:
        print(f"  selected_meaning.rationale: {rationale[:60]}...")
    else:
        print("  selected_meaning.rationale: (empty — must be filled)")
    print()


def validate_brief() -> bool:
    """Validate core_insight, all 6 meanings, and selection exist in brief."""
    brief = read_brief()
    if not brief:
        print("ERROR: No .content-brief.json found. Run 'engine.py content post' first.", file=sys.stderr)
        return False

    core_insight = brief.get("core_insight", "").strip()
    meanings = brief.get("meanings", {})
    selected = brief.get("selected_meaning", {})

    if not core_insight:
        print("❌ core_insight is MISSING from .content-brief.json.", file=sys.stderr)
        print("   Run 'engine.py content compile' and follow the 8-step sequence.", file=sys.stderr)
        print("   Then write core_insight to .content-brief.json.", file=sys.stderr)
        return False

    meaning_axes = _meaning_axes()
    for axis in meaning_axes:
        if not meanings.get(axis, "").strip():
            print(f"❌ meanings.{axis} is MISSING from .content-brief.json.", file=sys.stderr)
            print("   Run 'engine.py content compile' and complete Step 5.", file=sys.stderr)
            return False

    if not selected.get("axis", "").strip():
        print("❌ selected_meaning.axis is MISSING from .content-brief.json.", file=sys.stderr)
        print("   Run 'engine.py content compile' and complete Step 6.", file=sys.stderr)
        return False

    if not selected.get("rationale", "").strip():
        print("❌ selected_meaning.rationale is MISSING from .content-brief.json.", file=sys.stderr)
        print("   Run 'engine.py content compile' and complete Step 6.", file=sys.stderr)
        return False

    print(f"  ✓ core_insight: {core_insight[:80]}...")
    for axis in meaning_axes:
        val = meanings.get(axis, "")
        print(f"  ✓ meanings.{axis}: {val[:60]}...")
    print(f"  ✓ selected_meaning.axis: {selected.get('axis')}")
    print(f"  ✓ selected_meaning.rationale: {selected.get('rationale')[:60]}...")
    return True


def main():
    parser = argparse.ArgumentParser(description="Content Engine Compiler")
    parser.add_argument("--validate", action="store_true", help="Validate brief fields only")
    args = parser.parse_args()

    if args.validate:
        return 0 if validate_brief() else 1

    brief = read_brief()
    if not brief:
        print("ERROR: No .content-brief.json found. Run 'engine.py content post' first.", file=sys.stderr)
        return 1

    print_compiler_sequence(brief)

    # If already populated, note it
    core_insight = brief.get("core_insight", "").strip()
    meanings = brief.get("meanings", {})
    selected = brief.get("selected_meaning", {})
    meaning_axes = _meaning_axes()
    all_meanings_filled = all(meanings.get(a, "").strip() for a in meaning_axes)
    selection_filled = selected.get("axis", "").strip() and selected.get("rationale", "").strip()
    if core_insight and all_meanings_filled and selection_filled:
        print("═══ Compiler fields already populated ═══")
        print()
        validate_brief()
        print()
        print("All fields ready. Proceed to drafting.")
        return 0

    return 0


if __name__ == "__main__":
    sys.exit(main())
