#!/usr/bin/env python3
"""engine_frontmatter.py — Parse, write, and validate YAML frontmatter.

Single source of truth for frontmatter operations across all tools.
"""

import os
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml


def parse_frontmatter(content: str) -> tuple[dict, str]:
    """Parse YAML frontmatter from markdown content.

    Returns (frontmatter_dict, body_string). If no frontmatter, returns ({}, content).
    """
    if not content.startswith("---"):
        return {}, content
    parts = content.split("---", 2)
    if len(parts) < 3:
        return {}, content
    try:
        fm = yaml.safe_load(parts[1]) or {}
    except yaml.YAMLError:
        fm = {}
    if not isinstance(fm, dict):
        fm = {}
    return fm, parts[2].strip()


def write_frontmatter(filepath: Path, fm: dict, body: str) -> None:
    """Atomically rewrite a markdown file with new frontmatter + body."""
    fm_str = yaml.dump(fm, default_flow_style=False, allow_unicode=True, sort_keys=False).strip()
    tmp = tempfile.NamedTemporaryFile(
        mode="w", dir=str(filepath.parent), prefix=".tmp-", suffix=".md", delete=False
    )
    try:
        tmp.write(f"---\n{fm_str}\n---\n\n{body.strip()}\n")
        tmp.close()
        os.replace(tmp.name, str(filepath))
    except Exception:
        if os.path.exists(tmp.name):
            os.unlink(tmp.name)
        raise


def validate_frontmatter(fm: dict, required_fields: list[str] | None = None) -> list[str]:
    """Validate frontmatter against required fields. Returns list of missing fields."""
    if required_fields is None:
        required_fields = ["title", "created", "tags", "platform"]
    missing = []
    for field in required_fields:
        if field not in fm or fm[field] is None:
            missing.append(field)
    return missing


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")
