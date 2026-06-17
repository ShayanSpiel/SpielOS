#!/usr/bin/env python3
"""engine_state.py — State machine + paths for Spiel Engine.

Single source of truth for:
- VAULT directory resolution
- All .wiki-state / .content-brief.json paths
- Wiki + Content state definitions and transitions
- Lock file (mutex for pipeline operations)
"""

import json
import os
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

import yaml

# ─── VAULT Resolution ────────────────────────────────────────────────────

ENV_FILE = Path.home() / ".config" / "opencode" / ".env"


def _load_dotenv() -> None:
    seen = set()
    vault_env = Path(__file__).resolve().parent.parent / ".env"
    for env_path in (vault_env, ENV_FILE):
        if env_path in seen or not env_path.exists():
            continue
        seen.add(env_path)
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

# ─── Path Constants ──────────────────────────────────────────────────────

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
RULES_FILE = VAULT / "rules.yaml"

# ─── State Definitions ───────────────────────────────────────────────────

WIKI_STATES = [
    "IDLE",
    "INGESTING",
    "ANALYZING",
    "RECONCILING",
    "LINKING",
    "INDEXING",
    "VALIDATING",
    "COMPLETE",
]

CONTENT_STATES = [
    "IDLE",
    "SESSION_CAPTURE",
    "COMPILE",
    "SELECT",
    "FORMAT_WIZARD",
    "DRAFTING",
    "BANNER",
    "GATE_CHECK",
    "QUEUE",
    "PUBLISHING",
    "ARCHIVING",
    "ANALYZING_POST",
    "COMPLETE_POST",
]

ALL_STATES = list(set(WIKI_STATES + CONTENT_STATES))

WIKI_TRANSITIONS: dict[str, list[str]] = {
    "IDLE": ["INGESTING", "INDEXING", "VALIDATING"],
    "INGESTING": ["ANALYZING"],
    "ANALYZING": ["RECONCILING", "INDEXING"],
    "RECONCILING": ["LINKING", "INDEXING"],
    "LINKING": ["INDEXING"],
    "INDEXING": ["VALIDATING"],
    "VALIDATING": ["COMPLETE", "INGESTING", "IDLE"],
    "COMPLETE": ["IDLE"],
}

CONTENT_TRANSITIONS: dict[str, list[str]] = {
    "IDLE": ["SESSION_CAPTURE", "QUEUE", "PUBLISHING"],
    "SESSION_CAPTURE": ["COMPILE", "IDLE"],
    "COMPILE": ["SELECT", "IDLE"],
    "SELECT": ["FORMAT_WIZARD", "IDLE"],
    "FORMAT_WIZARD": ["DRAFTING", "IDLE"],
    "DRAFTING": ["BANNER", "IDLE"],
    "BANNER": ["GATE_CHECK"],
    "GATE_CHECK": ["QUEUE", "DRAFTING", "IDLE"],
    "QUEUE": ["PUBLISHING", "IDLE"],
    "PUBLISHING": ["ARCHIVING"],
    "ARCHIVING": ["ANALYZING_POST"],
    "ANALYZING_POST": ["COMPLETE_POST"],
    "COMPLETE_POST": ["IDLE"],
}

ALL_TRANSITIONS: dict[str, list[str]] = {}
for s, nexts in WIKI_TRANSITIONS.items():
    ALL_TRANSITIONS.setdefault(s, []).extend(nexts)
for s, nexts in CONTENT_TRANSITIONS.items():
    ALL_TRANSITIONS.setdefault(s, []).extend(nexts)


class StateMachine:
    def __init__(self, loop: str = "WIKI"):
        self.loop = loop.upper()
        if self.loop == "WIKI":
            self.transitions = WIKI_TRANSITIONS
            self.states = WIKI_STATES
        elif self.loop == "CONTENT":
            self.transitions = CONTENT_TRANSITIONS
            self.states = CONTENT_STATES
        else:
            raise ValueError(f"Unknown loop: {loop}. Use WIKI or CONTENT.")

    def validate_transition(self, current: str, target: str) -> tuple[bool, str]:
        current = current.upper()
        target = target.upper()
        if current not in self.states:
            return False, f"Unknown state in {self.loop} loop: {current}"
        if target not in self.states:
            return False, f"Unknown state in {self.loop} loop: {target}"
        allowed = self.transitions.get(current, [])
        if target not in allowed:
            return False, (
                f"Invalid transition: {current} -> {target} in {self.loop} loop. "
                f"Allowed: {', '.join(allowed) if allowed else 'none'}"
            )
        return True, "ok"

    def all_transitions_from(self, state: str) -> list[str]:
        return ALL_TRANSITIONS.get(state.upper(), [])

    def next_states(self) -> list[str]:
        return list(self.transitions.get("IDLE", []))


# ─── Brief Handoff (LLM handoff points with 5-min TTL) ─────────────────

HANDOFF_TTL_MINUTES = 5
MEANING_AXES_DEFAULT = [
    "systemic", "behavioral", "philosophical", "contrarian", "leverage", "human",
]


def read_brief() -> dict:
    """Read .content-brief.json. Returns empty dict if missing or invalid."""
    if not CONTENT_BRIEF_FILE.exists():
        return {}
    try:
        data = json.loads(CONTENT_BRIEF_FILE.read_text())
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def write_brief(brief: dict) -> None:
    """Atomically write .content-brief.json."""
    CONTENT_BRIEF_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = CONTENT_BRIEF_FILE.with_suffix(CONTENT_BRIEF_FILE.suffix + ".tmp")
    try:
        tmp.write_text(json.dumps(brief, indent=2, default=str))
        os.replace(tmp, CONTENT_BRIEF_FILE)
    except Exception:
        if tmp.exists():
            tmp.unlink()
        raise


def set_handoff(brief: dict, stage: str) -> dict:
    """Mark a brief as awaiting LLM handoff at the given stage. 5-min TTL."""
    now = datetime.now()
    brief["handoff"] = {
        "stage": stage,
        "started_at": now.isoformat(timespec="seconds"),
        "expires_at": (now + timedelta(minutes=HANDOFF_TTL_MINUTES)).isoformat(timespec="seconds"),
    }
    return brief


def clear_handoff(brief: dict) -> dict:
    """Remove handoff marker from brief (caller has satisfied it)."""
    brief["handoff"] = None
    return brief


def check_handoff_expired(brief: dict) -> bool:
    """Return True if brief.handoff.expires_at is in the past."""
    h = brief.get("handoff")
    if not h:
        return False
    try:
        expires = datetime.fromisoformat(h["expires_at"])
    except (ValueError, TypeError, KeyError):
        return True
    return datetime.now() > expires


def get_active_handoff(brief: dict) -> dict | None:
    """Return the active handoff dict if not expired, else None."""
    h = brief.get("handoff")
    if not h:
        return None
    if check_handoff_expired(brief):
        return None
    return h


def validate_brief_for_transition(
    target: str, brief: dict, meaning_axes: list[str] | None = None
) -> tuple[bool, str]:
    """Check that brief has the artifacts required to transition into `target`.

    Returns (ok, reason). reason is empty when ok.
    This checks the brief only — file system checks live in engine.py.
    """
    axes = meaning_axes or MEANING_AXES_DEFAULT
    target = target.upper()
    if target == "SELECT":
        if not (brief.get("core_insight") or "").strip():
            return False, "core_insight is empty"
        meanings = brief.get("meanings") or {}
        for axis in axes:
            if not (meanings.get(axis) or "").strip():
                return False, f"meanings.{axis} is empty"
        sel = brief.get("selected_meaning") or {}
        if not (sel.get("axis") or "").strip():
            return False, "selected_meaning.axis is empty"
        if not (sel.get("rationale") or "").strip():
            return False, "selected_meaning.rationale is empty"
        return True, ""
    if target == "FORMAT_WIZARD":
        recs = (brief.get("template_selection") or {}).get("recommendations") or {}
        if not recs:
            return False, "template_selection.recommendations is empty (run content select first)"
        return True, ""
    if target == "DRAFTING":
        wiz = brief.get("wizard") or {}
        formats = wiz.get("formats") or []
        if not formats:
            return False, "wizard.formats is empty (run format wizard first)"
        return True, ""
    if target == "PUBLISHING":
        wiz = brief.get("wizard") or {}
        decisions = wiz.get("publish_decisions") or {}
        if not decisions:
            return False, "wizard.publish_decisions is empty (run publish wizard first)"
        for fname, decision in decisions.items():
            if decision not in ("publish", "hold", "skip"):
                return False, f"invalid publish decision for {fname}: {decision}"
        return True, ""
    return True, ""


# ─── State File I/O ──────────────────────────────────────────────────────

_DEFAULT_STATE: dict = {
    "current_state": "IDLE",
    "loop": "WIKI",
    "last_state_change": None,
    "pending_action": None,
    "last_validation": "passed",
    "validation_results": {
        "orphans": 0,
        "broken_links": 0,
        "stale": [],
        "warnings": [],
    },
    "last_ingest": None,
}


def read_wiki_state() -> dict:
    if not WIKI_STATE_FILE.exists():
        return dict(_DEFAULT_STATE)
    try:
        data = json.loads(WIKI_STATE_FILE.read_text())
        if not isinstance(data, dict):
            return dict(_DEFAULT_STATE)
        return data
    except (json.JSONDecodeError, OSError):
        pass
    try:
        data = yaml.safe_load(WIKI_STATE_FILE.read_text())
        if isinstance(data, dict):
            return data
    except Exception:
        pass
    return dict(_DEFAULT_STATE)


def write_wiki_state(state: dict) -> None:
    state["last_state_change"] = datetime.now().isoformat(timespec="seconds")
    tmp = tempfile.NamedTemporaryFile(
        mode="w", dir=str(VAULT), prefix=".wiki-state-", suffix=".tmp", delete=False
    )
    try:
        tmp.write(json.dumps(state, indent=2, default=str))
        tmp.close()
        os.replace(tmp.name, str(WIKI_STATE_FILE))
    except Exception:
        if os.path.exists(tmp.name):
            os.unlink(tmp.name)
        raise


# ─── Lock ────────────────────────────────────────────────────────────────

import time as _time


def acquire_lock() -> bool:
    if LOCK_FILE.exists():
        age = _time.time() - LOCK_FILE.stat().st_mtime
        if age < 300:
            return False
        LOCK_FILE.unlink(missing_ok=True)
    LOCK_FILE.write_text(str(os.getpid()))
    return True


def release_lock() -> None:
    LOCK_FILE.unlink(missing_ok=True)


# ─── Checkpoints ─────────────────────────────────────────────────────────

def save_checkpoint(state: dict) -> None:
    CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)
    cp = {
        "timestamp": datetime.now().isoformat(),
        "state": state.get("current_state"),
        "loop": state.get("loop"),
        "pending_action": state.get("pending_action"),
    }
    cp_file = CHECKPOINT_DIR / f"{state.get('loop', 'WIKI').lower()}-checkpoint.json"
    with open(cp_file, "w") as f:
        json.dump(cp, f, indent=2)


def load_checkpoint(loop: str = "WIKI") -> dict | None:
    cp_file = CHECKPOINT_DIR / f"{loop.lower()}-checkpoint.json"
    if not cp_file.exists():
        return None
    try:
        with open(cp_file) as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return None


def clear_checkpoint(loop: str = "WIKI") -> None:
    cp_file = CHECKPOINT_DIR / f"{loop.lower()}-checkpoint.json"
    cp_file.unlink(missing_ok=True)
