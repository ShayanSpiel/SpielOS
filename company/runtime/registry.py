"""Discover declarative Department packages for the canonical clean core."""

import importlib
import os
import pkgutil

from .. import departments as department_package
from ..departments import DepartmentManifest


def _fixture_paths() -> list[str]:
    """Extra department package paths from ``SPIELOS_TEST_DEPARTMENTS_DIR``.

    The source product ships zero departments by design; behavioral tests
    point this variable at a fixture tree (``<id>/department.py``) and the
    declarations load under the real ``company.departments`` package so
    their relative imports resolve exactly like a home's. The variable is
    a test seam only — homes never set it.
    """
    fixture = os.environ.get("SPIELOS_TEST_DEPARTMENTS_DIR", "").strip()
    if not fixture:
        return []
    from pathlib import Path

    root = Path(fixture).expanduser().resolve()
    return [str(root)] if root.is_dir() else []


def _search_paths() -> list[str]:
    """Department package paths: the live layer plus the test overlay.

    Fixture paths are inserted into ``company.departments.__path__`` so
    ``import company.departments.<id>.department`` resolves there and the
    declarations' relative imports (``from ...workflows import ...``)
    behave exactly like in a home. The insertion is idempotent.
    """
    paths = [*department_package.__path__]
    for fixture in _fixture_paths():
        if fixture not in paths:
            # Prepend: the fixture tree wins over a same-named live module,
            # which never happens in a home (the source ships none).
            paths.insert(0, fixture)
            department_package.__path__ = paths
    return paths


def departments() -> dict[str, DepartmentManifest]:
    """Return portable declarations only; execution belongs to GoalRuntime."""

    installed: dict[str, DepartmentManifest] = {}
    for module_info in pkgutil.iter_modules(_search_paths()):
        if module_info.name.startswith("_"):
            continue
        module_name = f"{department_package.__name__}.{module_info.name}.department"
        try:
            module = importlib.import_module(module_name)
        except (ImportError, AttributeError, SyntaxError):
            # A declaration package that no longer imports against the clean
            # contracts is skipped, not fatal: the CLI must keep answering
            # while such packages await a clean rebuild.
            continue
        candidates = [value for value in vars(module).values()
                      if isinstance(value, type)
                      and value.__module__ == module.__name__
                      and getattr(value, "department_id", None)]
        if len(candidates) != 1:
            raise ValueError(f"{module.__name__} must export exactly one Department")
        declaration = candidates[0]()
        department_id = declaration.department_id or declaration.id
        workflows = tuple(getattr(declaration, "workflows", ()) or ())
        skill_ids = tuple(dict.fromkeys(
            skill for workflow in workflows
            for step in workflow.steps for skill in step.skill_ids))
        connection_ids = tuple(dict.fromkeys(
            connection for workflow in workflows
            for step in workflow.steps
            for connection in step.connection_ids))
        manifest = DepartmentManifest(
            department_id, getattr(declaration, "version", "0.0.0"),
            getattr(declaration, "description", ""), workflows,
            tuple(getattr(declaration, "agent_ids", ()) or ()), skill_ids,
            connection_ids,
            dict(getattr(declaration, "evidence_metrics", {}) or {}),
            dict(getattr(declaration, "goal_schema", {}) or {}),
            dict(getattr(declaration, "workflow_agents", {}) or {}))
        if manifest.id in installed:
            raise ValueError(f"duplicate Department: {manifest.id}")
        installed[manifest.id] = manifest
    return installed
