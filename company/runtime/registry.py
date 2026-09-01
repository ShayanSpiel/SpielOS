"""Discover declarative Department packages for the canonical clean core."""

import importlib
import pkgutil

from .. import departments as department_package
from ..departments import DepartmentManifest


def departments() -> dict[str, DepartmentManifest]:
    """Return portable declarations only; execution belongs to GoalRuntime."""

    installed: dict[str, DepartmentManifest] = {}
    for module_info in pkgutil.iter_modules(department_package.__path__):
        if module_info.name.startswith("_"):
            continue
        module_name = f"{department_package.__name__}.{module_info.name}.department"
        try:
            module = importlib.import_module(module_name)
        except ModuleNotFoundError as error:
            if error.name == module_name:
                continue
            raise
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
            skill for workflow in workflows for skill in workflow.skill_ids))
        connection_ids = tuple(dict.fromkeys(
            connection for workflow in workflows for connection in workflow.connection_ids))
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


def handlers() -> dict[str, DepartmentManifest]:
    """Deprecated declaration alias; canonical entries are not GoalHandlers."""

    return departments()
