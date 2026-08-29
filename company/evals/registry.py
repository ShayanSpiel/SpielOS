"""Explicit registry for reusable evaluation suites."""

from __future__ import annotations

from .models import EvalSuite

_REGISTRY: dict[str, EvalSuite] = {}
_DISCOVERED = False


def register_suite(suite: EvalSuite) -> None:
    """Register one suite; duplicate ids are rejected loudly."""
    if not isinstance(suite, EvalSuite):
        raise TypeError("register_suite expects an EvalSuite")
    if suite.id in _REGISTRY:
        raise ValueError(f"eval suite '{suite.id}' is already registered")
    _REGISTRY[suite.id] = suite


def discover_suites() -> dict[str, EvalSuite]:
    """Return suites explicitly registered by runtime or Workgroup code."""
    global _DISCOVERED
    if _DISCOVERED:
        return _REGISTRY
    _DISCOVERED = True
    return _REGISTRY


def suites() -> dict[str, EvalSuite]:
    return discover_suites()


def get_suite(suite_id: str) -> EvalSuite:
    try:
        return discover_suites()[suite_id]
    except KeyError as exc:
        raise KeyError(
            f"unknown eval suite '{suite_id}'; registered: "
            f"{', '.join(sorted(discover_suites()))}") from exc


__all__ = ["discover_suites", "get_suite", "register_suite", "suites"]
