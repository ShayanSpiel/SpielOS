#!/usr/bin/env python3
"""state_machine.py — State definitions + transition table for the Spiel Engine.

Both wiki management and content posting state machines are defined here.
The engine.py controller reads .wiki-state and validates transitions against
this table before executing any action.

Usage:
    from state_machine import WIKI_STATES, CONTENT_STATES, ALL_STATES, TRANSITIONS
    sm = StateMachine("WIKI")
    sm.validate_transition("IDLE", "INGESTING")  # True
    sm.validate_transition("IDLE", "DRAFTING")   # False (wrong loop)
"""

# Re-export path constants from state.py so existing imports keep working.
from state import VAULT, WIKI_STATE_FILE, LOCK_FILE  # noqa: F401

import os
import tempfile
from datetime import datetime
from pathlib import Path

import yaml

# ─── State Definitions ──────────────────────────────────────────────────────

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
    "STRATEGY_LOAD",
    "ICP_WORLD_BUILD",
    "DRAFTING",
    "GATE_CHECK",
    "REVISING",
    "QUEUE",
    "PUBLISHING",
    "ARCHIVING",
    "ANALYZING_POST",
    "COMPLETE_POST",
]

ALL_STATES = list(set(WIKI_STATES + CONTENT_STATES))

WIKI_TRANSITIONS = {
    "IDLE": ["INGESTING", "INDEXING", "VALIDATING"],
    "INGESTING": ["ANALYZING"],
    "ANALYZING": ["RECONCILING", "INDEXING"],
    "RECONCILING": ["LINKING", "INDEXING"],
    "LINKING": ["INDEXING"],
    "INDEXING": ["VALIDATING"],
    "VALIDATING": ["COMPLETE", "INGESTING", "IDLE"],
    "COMPLETE": ["IDLE"],
}

CONTENT_TRANSITIONS = {
    "IDLE": ["SESSION_CAPTURE", "QUEUE", "PUBLISHING"],
    "SESSION_CAPTURE": ["STRATEGY_LOAD"],
    "STRATEGY_LOAD": ["ICP_WORLD_BUILD"],
    "ICP_WORLD_BUILD": ["DRAFTING"],
    "DRAFTING": ["GATE_CHECK"],
    "GATE_CHECK": ["QUEUE", "REVISING"],
    "REVISING": ["GATE_CHECK"],
    "QUEUE": ["PUBLISHING", "IDLE"],
    "PUBLISHING": ["ARCHIVING"],
    "ARCHIVING": ["ANALYZING_POST"],
    "ANALYZING_POST": ["COMPLETE_POST"],
    "COMPLETE_POST": ["IDLE"],
}

ALL_TRANSITIONS = {}
for s, nexts in WIKI_TRANSITIONS.items():
    ALL_TRANSITIONS.setdefault(s, []).extend(nexts)
for s, nexts in CONTENT_TRANSITIONS.items():
    ALL_TRANSITIONS.setdefault(s, []).extend(nexts)


class StateMachine:
    """Validates and manages state transitions for both loops."""

    def __init__(self, loop="WIKI"):
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


# ─── State File Helpers ─────────────────────────────────────────────────────

def read_wiki_state() -> dict:
    default = {
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
    if not WIKI_STATE_FILE.exists():
        return default
    try:
        with WIKI_STATE_FILE.open() as f:
            data = yaml.safe_load(f)
        if not isinstance(data, dict):
            return default
        return data
    except Exception:
        return default


def write_wiki_state(state: dict) -> None:
    state["last_state_change"] = datetime.now().isoformat()
    tmp = tempfile.NamedTemporaryFile(
        mode="w", dir=str(VAULT), prefix=".wiki-state-", suffix=".tmp", delete=False
    )
    try:
        yaml.dump(state, tmp, default_flow_style=False, allow_unicode=True)
        tmp.close()
        os.replace(tmp.name, str(WIKI_STATE_FILE))
    except Exception:
        if os.path.exists(tmp.name):
            os.unlink(tmp.name)
        raise


def acquire_lock() -> bool:
    """Try to acquire a lock file. Returns True if acquired. 5-min TTL."""
    if LOCK_FILE.exists():
        import time
        age = time.time() - LOCK_FILE.stat().st_mtime
        if age < 300:
            return False
        LOCK_FILE.unlink(missing_ok=True)
    LOCK_FILE.write_text(str(os.getpid()))
    return True


def release_lock() -> None:
    LOCK_FILE.unlink(missing_ok=True)
