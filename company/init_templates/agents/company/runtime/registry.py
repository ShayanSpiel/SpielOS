"""Discover Departments and the two internal control handlers."""

import importlib
import pkgutil

from .. import departments as department_package
from .director import Director
from .models import Department, GoalHandler
from .system_improvement import SystemImprovement


def handlers() -> dict[str, GoalHandler]:
    """Internal lookup used by the loop; callers should use the catalog."""

    installed: dict[str, GoalHandler] = {
        "director": Director(),
        "system-improvement": SystemImprovement(),
    }
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
        candidates = [
            value for value in vars(module).values()
            if isinstance(value, type)
            and issubclass(value, Department)
            and value is not Department
            and value.__module__ == module.__name__
        ]
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
