"""Render a brief to the delivered markdown shape."""
from __future__ import annotations


def render_brief(brief: dict) -> str:
    lines = [f"# {brief.get('title', 'Weekly research brief')}", ""]
    for section in brief.get("sections", ()):
        lines.append(f"## {section['heading']}")
        lines.append(section["body"])
        lines.append("")
    return "\n".join(lines)
