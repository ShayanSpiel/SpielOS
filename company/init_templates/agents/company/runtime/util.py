"""Small shared runtime helpers.

Single source for the two implementations that used to be duplicated (and
occasionally disagree) across modules:

* ``parse_dt`` — tolerant ISO-8601 parsing that normalizes naive timestamps
  to UTC. Legacy ``resume_at`` values written without timezone information
  used to raise ``TypeError`` on comparison and kill a whole runner tick;
  every datetime read from persisted state must go through here.
* ``compare`` — the one goal-metric comparator. An unknown operator is a
  failed evaluation (False), never a raised KeyError; all three former
  copies (loop, director, interpreter) delegate to this function.
"""

from __future__ import annotations

from datetime import datetime, timezone


def parse_dt(value) -> datetime | None:
    """Parse an ISO-8601 timestamp into an aware UTC datetime.

    Returns None when the value is missing or unparsable. Naive timestamps
    (no tzinfo) are interpreted as UTC, matching how the runtime writes them.
    """
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


_COMPARE_OPERATORS = {
    "ge": lambda a, b: a >= b,
    "gt": lambda a, b: a > b,
    "eq": lambda a, b: a == b,
    "le": lambda a, b: a <= b,
    "lt": lambda a, b: a < b,
}


def compare(value, operator: str, target) -> bool:
    """Evaluate one metric against its target. Unknown operator -> False."""
    operation = _COMPARE_OPERATORS.get(operator)
    if operation is None:
        return False
    return operation(value, target)
