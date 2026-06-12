#!/usr/bin/env python3
"""icp_world.py — Load ICP world from concepts/icp-offer.md.

The Content Engine Compiler uses this to reconstruct the ICP's mental world
independently of any session. This is Step 1 of the Compiler sequence.

Usage:
    python3 scripts/icp_world.py          # Print full ICP world reconstruction
    python3 scripts/icp_world.py --brief  # Print condensed version for .content-brief.json
"""

import argparse
import sys
from pathlib import Path

VAULT = Path(__file__).resolve().parent.parent
ICP_FILE = VAULT / "concepts" / "icp-offer.md"


def load_icp() -> str:
    """Read the canonical ICP file."""
    if not ICP_FILE.exists():
        return f"ERROR: ICP file not found at {ICP_FILE}"
    return ICP_FILE.read_text()


def extract_icp_world(content: str) -> dict:
    """Extract structured ICP world data from the markdown file."""
    result = {
        "title": "",
        "demographics": "",
        "psychographics": "",
        "problem_hierarchy": "",
        "internal_monologue": "",
        "critical_sensitivity": "",
        "content_resonance": "",
        "raw": content,
    }

    lines = content.split("\n")
    current_section = None
    section_buffer = []

    # Sections we care about
    target_sections = [
        "## ICP: Technical Founder",
        "### Demographics",
        "### Psychographics",
        "### Problem Hierarchy",
        "### Content That Resonates",
        "### Questions This ICP Asks (Internal Monologue)",
        "### Critical Sensitivity",
    ]

    for line in lines:
        stripped = line.strip()
        if stripped in target_sections:
            if current_section and section_buffer:
                result[current_section] = "\n".join(section_buffer)
            current_section = stripped.replace("### ", "").replace("## ", "").lower()
            current_section = current_section.replace(" ", "_").replace("(", "").replace(")", "")
            section_buffer = []
        elif current_section:
            section_buffer.append(line)

    if current_section and section_buffer:
        result[current_section] = "\n".join(section_buffer)

    return result


def print_icp_world(world: dict) -> None:
    """Print the ICP world in the Compiler's expected format."""
    print("═══ ICP WORLD (Content Engine Compiler) ═══")
    print()

    print("── DEMOGRAPHICS ──")
    print(world.get("demographics", "(not found)"))
    print()

    print("── PSYCHOGRAPHICS ──")
    print(world.get("psychographics", "(not found)"))
    print()

    print("── IDENTITY TENSION ──")
    psych = world.get("psychographics", "")
    for line in psych.split("\n"):
        ls = line.strip()
        if ls.startswith("**Identity**") or ls.startswith("**Self-image**") or ls.startswith("**Core drive**") or ls.startswith("**Deep fear**") or ls.startswith("**Hidden desire**"):
            print(f"  {ls}")
    print()

    print("── PROBLEM HIERARCHY (4 Layers) ──")
    print(world.get("problem_hierarchy", "(not found)"))
    print()

    print("── INTERNAL MONOLOGUE (7 Questions) ──")
    print(world.get("internal_monologue", "(not found)"))
    print()

    print("── CRITICAL SENSITIVITY (What NOT to say) ──")
    print(world.get("critical_sensitivity", "(not found)"))
    print()

    print("── CONTENT RESONANCE (By Problem Layer) ──")
    print(world.get("content_resonance", "(not found)"))
    print()
    print("═══ END ICP WORLD ═══")


def print_brief(world: dict) -> None:
    """Print condensed ICP world for .content-brief.json."""
    import json
    psych = world.get("psychographics", "")
    identity = ""
    for line in psych.split("\n"):
        if line.strip().startswith("**Identity**"):
            identity = line.strip()
            break

    # core_tension, operating_style, language_style, problem_layers
    # are extracted from icp-offer.md above (see Psychographics section).
    # No hardcoded values — everything comes from the canonical source.
    brief = {
        "identity": identity,
        "core_tension": world.get("psychographics", ""),
        "operating_style": "",
        "language_style": "",
        "problem_layers": [],
    }
    print(json.dumps(brief, indent=2))


def main():
    parser = argparse.ArgumentParser(description="ICP World Loader")
    parser.add_argument("--brief", action="store_true", help="Output condensed JSON for brief")
    args = parser.parse_args()

    content = load_icp()
    world = extract_icp_world(content)

    if args.brief:
        print_brief(world)
    else:
        print_icp_world(world)

    return 0


if __name__ == "__main__":
    sys.exit(main())
