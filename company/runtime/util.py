"""Small neutral helpers for the clean runtime."""

from __future__ import annotations

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
