"""Discover Departments and the two internal control handlers."""

import importlib
import pkgutil

from .. import departments as department_package
from ..departments.outbound.email_workflow import EmailWorkflow
from .director import Director
from .models import Department, GoalHandler
from .system_improvement import SystemImprovement


def handlers() -> dict[str, GoalHandler]:
    """Internal lookup used by the loop; callers should use the catalog."""

    installed: dict[str, GoalHandler] = {
        "director": Director(),
        "system-improvement": SystemImprovement(),
        # Reads historical v4 goals. New email work is owned by Outbound.
        "email": EmailWorkflow(),
    }
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
            raise ValueError(f"duplicate goal owner: {instance.id}")
        installed[instance.id] = instance
    return installed


def departments() -> dict[str, Department]:
    return {key: value for key, value in handlers().items()
            if isinstance(value, Department)}
