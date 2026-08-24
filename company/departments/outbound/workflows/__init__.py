"""Named Outbound playbooks. These are steps, not independent state machines."""

from dataclasses import dataclass
from typing import Callable

REGISTRY: dict[str, "Workflow"] = {}


@dataclass
class Workflow:
    name: str
    goal: dict
    observe: Callable
    decide: Callable
    prepare: Callable
    validate: Callable
    execute: Callable
    measure: Callable
    goal_check: Callable
    policy: Callable
    learn: Callable | None = None
    report_lines: Callable | None = None
    report: Callable | None = None
    describe: str = ""


def register(workflow: Workflow) -> Workflow:
    REGISTRY[workflow.name] = workflow
    return workflow


def import_all() -> None:
    from . import email
    _ = email


def get(name: str) -> Workflow:
    if name not in REGISTRY:
        raise KeyError(f"workflow '{name}' is not registered (registered: {sorted(REGISTRY)})")
    return REGISTRY[name]
