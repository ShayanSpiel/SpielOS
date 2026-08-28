"""Discover Workgroups and the two internal control handlers."""

import importlib
import pkgutil

from .. import departments as department_package
from .director import Director
from .models import Department, GoalHandler
from .system_improvement import SystemImprovement
from ..workgroups.legacy import WorkgroupHandler, workgroup_from_legacy


def _legacy_departments() -> dict[str, Department]:
    """Load legacy packages during the Workgroup migration only."""

    installed: dict[str, Department] = {}
    for module_info in pkgutil.iter_modules(department_package.__path__):
        if module_info.name.startswith("_"):
            continue
        try:
            module = importlib.import_module(
                f"{department_package.__name__}.{module_info.name}.department")
        except ModuleNotFoundError as error:
            expected = f"{department_package.__name__}.{module_info.name}.department"
            if error.name == expected:
                continue
            raise
        candidates = [value for value in vars(module).values()
                      if isinstance(value, type) and issubclass(value, Department)
                      and value is not Department and value.__module__ == module.__name__]
        if len(candidates) != 1:
            raise ValueError(f"{module.__name__} must export exactly one Department")
        instance = candidates[0]()
        if instance.id in installed:
            raise ValueError(f"duplicate workgroup: {instance.id}")
        installed[instance.id] = instance
    return installed


def workgroups() -> dict[str, WorkgroupHandler]:
    """Canonical source discovery: Workgroups route to Worker-owned workflows."""

    return {
        department_id: WorkgroupHandler(workgroup_from_legacy(legacy), legacy)
        for department_id, legacy in _legacy_departments().items()
    }


def handlers() -> dict[str, GoalHandler]:
    """Internal lookup used by the loop; callers should use the catalog."""

    installed: dict[str, GoalHandler] = {
        "director": Director(),
        "system-improvement": SystemImprovement(),
    }
    try:
        from ..departments.outbound.email_workflow import EmailWorkflow
    except ModuleNotFoundError:
        pass  # minimal appliance without Outbound: no legacy alias to serve
    else:
        # Reads historical v4 goals. New email work is owned by Outbound.
        installed["email"] = EmailWorkflow()
    for instance in workgroups().values():
        if instance.id in installed:
            raise ValueError(f"duplicate goal owner: {instance.id}")
        installed[instance.id] = instance
    return installed


def departments() -> dict[str, Department]:
    """Compatibility alias. New code should call :func:`workgroups`."""
    return {key: value for key, value in handlers().items()
            if isinstance(value, Department)}
