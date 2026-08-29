"""Durable, goal-independent records of harness and instruction friction."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .paths import find_project_root


KINDS = {
    "command_mismatch", "tool_mismatch", "missing_instruction",
    "contradiction", "duplicate_instruction", "unexpected_result",
    "fallback_required", "silent_bug",
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def friction_path(project_root: str | Path | None = None) -> Path:
    root = Path(project_root or find_project_root()).resolve()
    return root / ".spielos" / "state" / "friction.jsonl"


def _fingerprint(value: dict[str, Any]) -> str:
    stable = "\n".join(str(value.get(key) or "").strip().lower() for key in (
        "kind", "source", "expected", "actual"))
    return hashlib.sha256(stable.encode()).hexdigest()[:16]


def record_friction(*, kind: str, source: str, expected: str, actual: str,
                    fallback: str = "", goal_id: str | None = None,
                    project_root: str | Path | None = None) -> dict[str, Any]:
    if kind not in KINDS:
        raise ValueError(f"unknown friction kind '{kind}'; choose from {sorted(KINDS)}")
    for name, value in (("source", source), ("expected", expected), ("actual", actual)):
        if not str(value).strip():
            raise ValueError(f"{name} is required")
    event = {
        "kind": kind,
        "source": source.strip(),
        "expected": expected.strip(),
        "actual": actual.strip(),
        "fallback": fallback.strip(),
        "goal_id": goal_id,
        "observed_at": _now(),
    }
    event["fingerprint"] = _fingerprint(event)
    path = friction_path(project_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n")
    return event


def friction_events(*, project_root: str | Path | None = None,
                    limit: int = 100) -> list[dict[str, Any]]:
    path = friction_path(project_root)
    if not path.is_file():
        return []
    values = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            values.append(value)
    return values[-max(1, min(int(limit), 500)):][::-1]


def friction_summary(*, project_root: str | Path | None = None) -> dict[str, Any]:
    events = friction_events(project_root=project_root, limit=500)
    grouped: dict[str, dict[str, Any]] = {}
    for item in reversed(events):
        fingerprint = item["fingerprint"]
        current = grouped.setdefault(fingerprint, {**item, "occurrences": 0})
        current.update(item)
        current["occurrences"] += 1
    recent = sorted(grouped.values(), key=lambda item: item["observed_at"], reverse=True)
    return {"event_count": len(events), "unique_count": len(recent), "recent": recent[:10]}
