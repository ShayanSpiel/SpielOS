"""Organizational package manifest; Departments own no runtime."""

from dataclasses import dataclass


@dataclass(frozen=True)
class DepartmentManifest:
    id: str
    workflow_ids: tuple[str, ...] = ()
    agent_ids: tuple[str, ...] = ()
    skill_ids: tuple[str, ...] = ()
    connection_ids: tuple[str, ...] = ()
