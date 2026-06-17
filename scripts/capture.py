#!/usr/bin/env python3
"""capture.py — Session transcript parsing.

Usage:
    from capture import parse_transcript, write_session_log
"""

import re
from datetime import datetime
from pathlib import Path


SESSION_SCHEMA_FIELDS = [
    "source", "topic", "decisions", "lessons", "numbers", "artifacts_shipped",
]


def parse_transcript(text: str) -> dict:
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
            lesson = re.sub(r"^[-*•]\s*", "", stripped)
            if lesson:
                result["lessons"].append(lesson.lower())
            continue
        if current_section == "numbers":
            result["numbers"].append(stripped)
            continue
        if current_section == "decisions":
            shipped_match = re.match(r"^(?:shipped|ship):\s*(.*)", stripped, re.IGNORECASE)
            if shipped_match:
                artifacts = [a.strip() for a in shipped_match.group(1).split(",")]
                result["artifacts_shipped"].extend(a for a in artifacts if a)
            else:
                result["decisions"].append(stripped)
            continue
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


def write_session_log(path: Path, data: dict) -> None:
    for field in SESSION_SCHEMA_FIELDS:
        if field not in data:
            data[field] = "" if field in ("source", "topic") else []
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
