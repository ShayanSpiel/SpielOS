#!/usr/bin/env python3
"""icp.py — Load ICP world from concepts/icp-offer.md.

Pure function: takes markdown content, returns structured ICP world dict.
"""


def extract_icp_world(content: str) -> dict:
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
    target_sections = [
        "## ICP: Technical Founder",
        "### Demographics",
        "### Psychographics",
        "### Problem Hierarchy",
        "### Content That Resonates",
        "### Questions This ICP Asks (Internal Monologue)",
        "### Critical Sensitivity",
    ]
    current_section = None
    section_buffer = []
    lines = content.split("\n")

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


def format_icp_world(world: dict) -> str:
    lines = []
    lines.append("═══ ICP WORLD (Content Engine Compiler) ═══")
    lines.append("")
    lines.append("── DEMOGRAPHICS ──")
    lines.append(world.get("demographics", "(not found)"))
    lines.append("")
    lines.append("── PSYCHOGRAPHICS ──")
    lines.append(world.get("psychographics", "(not found)"))
    lines.append("")
    lines.append("── IDENTITY TENSION ──")
    psych = world.get("psychographics", "")
    for line in psych.split("\n"):
        ls = line.strip()
        if ls.startswith("**Identity**") or ls.startswith("**Self-image**") or ls.startswith("**Core drive**") or ls.startswith("**Deep fear**") or ls.startswith("**Hidden desire**"):
            lines.append(f"  {ls}")
    lines.append("")
    lines.append("── PROBLEM HIERARCHY (4 Layers) ──")
    lines.append(world.get("problem_hierarchy", "(not found)"))
    lines.append("")
    lines.append("── INTERNAL MONOLOGUE (7 Questions) ──")
    lines.append(world.get("internal_monologue", "(not found)"))
    lines.append("")
    lines.append("── CRITICAL SENSITIVITY (What NOT to say) ──")
    lines.append(world.get("critical_sensitivity", "(not found)"))
    lines.append("")
    lines.append("── CONTENT RESONANCE (By Problem Layer) ──")
    lines.append(world.get("content_resonance", "(not found)"))
    lines.append("")
    lines.append("═══ END ICP WORLD ═══")
    return "\n".join(lines)
