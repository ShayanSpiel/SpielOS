#!/usr/bin/env python3
"""capture_session.py — Dual-mode session input for ShayanWiki.

Parses session transcripts (structured or free-form) into a schema,
and writes session log files with YAML frontmatter.

Usage:
    from capture_session import parse_transcript, write_session_log
    data = parse_transcript(text)
    write_session_log(path, data)
"""

import re
from pathlib import Path
from logger import logged


SESSION_SCHEMA_FIELDS = [
    "source",
    "topic",
    "decisions",
    "lessons",
    "numbers",
    "artifacts_shipped",
]


@logged()
def parse_transcript(text: str) -> dict:
    """Parse a session transcript into a structured dict.

    Handles both structured transcripts (with ## sections) and
    free-form manual notes.
    """
    result = {
        "decisions": [],
        "lessons": [],
        "numbers": [],
        "artifacts_shipped": [],
    }

    lines = text.split("\n")
    current_section = None

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue

        # Detect section headers
        header_match = re.match(r"^##\s+(.+)$", stripped)
        if header_match:
            section_name = header_match.group(1).strip().lower()
            if "lesson" in section_name:
                current_section = "lessons"
            elif "number" in section_name or "metric" in section_name:
                current_section = "numbers"
            elif "session" in section_name or "log" in section_name:
                current_section = "decisions"
            else:
                current_section = None
            continue

        if current_section == "lessons":
            # Strip bullet markers and lowercase for consistent matching
            lesson = re.sub(r"^[-*•]\s*", "", stripped)
            if lesson:
                result["lessons"].append(lesson.lower())
            continue

        if current_section == "numbers":
            result["numbers"].append(stripped)
            continue

        if current_section == "decisions":
            # Check for shipped artifacts
            shipped_match = re.match(r"^(?:shipped|ship):\s*(.*)", stripped, re.IGNORECASE)
            if shipped_match:
                artifacts = [a.strip() for a in shipped_match.group(1).split(",")]
                result["artifacts_shipped"].extend(a for a in artifacts if a)
            else:
                result["decisions"].append(stripped)
            continue

        # Free-form parsing (no section header)
        if re.match(r"^shipped:\s*", stripped, re.IGNORECASE):
            artifacts = re.sub(r"^shipped:\s*", "", stripped, flags=re.IGNORECASE)
            result["artifacts_shipped"].extend(
                a.strip() for a in artifacts.split(",") if a.strip()
            )
        elif re.match(r"^lesson:?\s*", stripped, re.IGNORECASE):
            lesson = re.sub(r"^lesson:?\s*", "", stripped, flags=re.IGNORECASE)
            result["lessons"].append(lesson)
        elif re.match(r"^numbers?:?\s*", stripped, re.IGNORECASE):
            numbers_text = re.sub(r"^numbers?:?\s*", "", stripped, flags=re.IGNORECASE)
            result["numbers"].append(numbers_text)
        elif re.match(r"^(decided|chose|opted)\s", stripped, re.IGNORECASE):
            result["decisions"].append(stripped)

    return result


@logged()
def write_session_log(path: Path, data: dict) -> None:
    """Write a session log file with YAML frontmatter.

    Ensures all SESSION_SCHEMA_FIELDS are present in the frontmatter.
    """
    from datetime import datetime

    # Ensure all schema fields have defaults
    for field in SESSION_SCHEMA_FIELDS:
        if field not in data:
            data[field] = "" if field in ("source", "topic") else []

    # Build YAML frontmatter content manually (no pyyaml dependency needed)
    lines = ["---"]
    for field in SESSION_SCHEMA_FIELDS:
        value = data.get(field, "" if field in ("source", "topic") else [])
        if field in ("source", "topic"):
            lines.append(f"{field}: {value}")
        else:
            if value:
                lines.append(f"{field}:")
                for item in value:
                    lines.append(f"  - {item}")
            else:
                lines.append(f"{field}: []")
    lines.append("---")
    lines.append("")

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def main():
    import argparse
    import sys

    parser = argparse.ArgumentParser(description="Capture a session transcript")
    parser.add_argument("file", nargs="?", help="Transcript file to parse")
    parser.add_argument("--write", "-w", metavar="OUTPUT", help="Write session log to file")
    args = parser.parse_args()

    if not args.file:
        parser.print_help()
        return 0

    text = Path(args.file).read_text(encoding="utf-8")
    data = parse_transcript(text)

    if args.write:
        write_session_log(Path(args.write), data)
        print(f"Written: {args.write}")
    else:
        import json
        print(json.dumps(data, indent=2))

    return 0


if __name__ == "__main__":
    sys.exit(main())
