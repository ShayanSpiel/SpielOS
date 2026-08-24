"""Eval suite registry with department auto-discovery.

Discovery mirrors the Department registry: every `departments/<name>/evals.py`
module that exports `EVAL_SUITES` (a list/tuple of EvalSuite) registers its
suites.  This makes an eval suite a first-class, duplicatable Lego piece:
a department adds one file and its standards are immediately visible to
`company eval list`, the catalog, and the machine-step quality gates.
"""

from __future__ import annotations

import importlib
import pkgutil

from .. import departments as department_package
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
    """Scan department dirs for `evals.py` modules exporting EVAL_SUITES."""
    global _DISCOVERED
    if _DISCOVERED:
        return _REGISTRY
    for module_info in pkgutil.iter_modules(department_package.__path__):
        if module_info.name.startswith("_"):
            continue
        module_name = f"{department_package.__name__}.{module_info.name}.evals"
        try:
            module = importlib.import_module(module_name)
        except ModuleNotFoundError as error:
            if error.name == module_name:
                continue
            raise
        suites = tuple(getattr(module, "EVAL_SUITES", ()) or ())
        for suite in suites:
            register_suite(suite)
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
