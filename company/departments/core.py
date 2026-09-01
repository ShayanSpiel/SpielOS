"""Organizational package manifest; Departments own no runtime."""

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class DepartmentManifest:
    id: str
    version: str = "0.0.0"
    description: str = ""
    workflows: tuple[Any, ...] = ()
    agent_ids: tuple[str, ...] = ()
    skill_ids: tuple[str, ...] = ()
    connection_ids: tuple[str, ...] = ()
    evidence_metrics: dict[str, tuple[str, ...]] | None = None
    goal_schema: dict[str, Any] | None = None
    workflow_agents: dict[str, str] | None = None

    @property
    def department_id(self) -> str:
        return self.id

    @property
    def workflow_ids(self) -> tuple[str, ...]:
        return tuple(item.id for item in self.workflows)
