from dataclasses import dataclass
from typing import Any

from ..evidence import Evidence
from ..goals import Goal
from ..memory import Memory


@dataclass(frozen=True)
class GoalContext:
    goal: Goal
    run_id: str
    evidence: tuple[Evidence, ...] = ()
    memory: tuple[Memory, ...] = ()


def codex_hook_output(projection: dict[str, Any], event_name: str) -> dict[str, Any]:
    """Render clean context for the Codex host hook."""

    return {"continue": True, "hookSpecificOutput": {
        "hookEventName": event_name,
        "additionalContext": projection["context"],
    }}
