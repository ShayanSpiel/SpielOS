#!/usr/bin/env python3
"""state.py — Single source of truth for paths, paths, and frontmatter parsing.

Every other script imports from here. No more `Path(os.environ.get("VAULT_DIR", ...))`
sprinkled across 13 files.
"""

import os
import tempfile
from datetime import datetime
from pathlib import Path

import yaml


def _load_dotenv() -> None:
    """Load .env from vault root if present. Never overrides existing env vars."""
    env_path = Path(__file__).resolve().parent.parent / ".env"
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


_load_dotenv()
VAULT = Path(
    os.environ.get(
        "VAULT_DIR",
        Path(__file__).resolve().parent.parent,
    )
)

RULES_FILE = VAULT / "rules.yaml"
WIKI_STATE_FILE = VAULT / ".wiki-state"
LOCK_FILE = VAULT / ".wiki-state.lock"
CONTENT_BRIEF_FILE = VAULT / ".content-brief.json"
RAW_MANIFEST_FILE = VAULT / ".raw-manifest.json"
GATES_REPORT_FILE = VAULT / "logs" / ".gates-report.json"
CHECKPOINT_DIR = VAULT / ".checkpoints"
LOG_DIR = VAULT / "logs"
QUEUE_DIR = VAULT / "content" / "queue"
POSTED_DIR = VAULT / "content" / "posted"
REJECTED_DIR = VAULT / "content" / "rejected"
SESSIONS_DIR = VAULT / "content" / "sessions"
BANNERS_DIR = VAULT / "assets" / "banners"
SCREENSHOTS_DIR = VAULT / "assets" / "screenshots"
BRAND_CONFIG = VAULT / "assets" / "brand-config.json"
ENV_FILE = Path.home() / ".config" / "opencode" / ".env"


def load_rules() -> dict:
    """Load rules.yaml. Returns empty dict on failure (caller checks)."""
    if not RULES_FILE.exists():
        return {}
    try:
        with RULES_FILE.open() as f:
            return yaml.safe_load(f) or {}
    except Exception:
        return {}


def parse_frontmatter(content: str) -> tuple[dict, str]:
    """Parse YAML frontmatter from a markdown file.

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


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def atomic_write_json(path: Path, data: dict) -> None:
    """Write JSON atomically (temp + replace)."""
    import json
    tmp = tempfile.NamedTemporaryFile(
        mode="w", dir=str(path.parent), prefix=".tmp-", suffix=".json", delete=False
    )
    try:
        json.dump(data, tmp, indent=2, default=str)
        tmp.close()
        os.replace(tmp.name, str(path))
    except Exception:
        if os.path.exists(tmp.name):
            os.unlink(tmp.name)
        raise
