"""Discover Workgroups and the two internal control handlers."""

from .director import Director
from .models import Department, GoalHandler
from .system_improvement import SystemImprovement
from ..workgroups.registry import WorkgroupHandler, workgroups as discover_workgroups


def workgroups() -> dict[str, WorkgroupHandler]:
    return discover_workgroups()


def handlers() -> dict[str, GoalHandler]:
    """Internal lookup used by the loop; callers should use the catalog."""

    installed: dict[str, GoalHandler] = {
        "director": Director(),
        "system-improvement": SystemImprovement(),
    }
    for instance in workgroups().values():
        if instance.id in installed:
            raise ValueError(f"duplicate goal owner: {instance.id}")
        installed[instance.id] = instance
    return installed


def departments() -> dict[str, Department]:
    """Compatibility alias. New code should call :func:`workgroups`."""
    return {key: value for key, value in handlers().items()
            if isinstance(value, Department)}
