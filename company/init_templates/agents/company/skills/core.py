"""Skill definitions are data consumed by Agents, never runtime loops."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Skill:
    id: str
    instructions: str
    version: int = 1
