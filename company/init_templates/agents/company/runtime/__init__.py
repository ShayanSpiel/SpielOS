"""Canonical clean Goal runtime plus the bounded legacy-home adapter."""

from .loop import Runtime as LegacyRuntime
from .engine import Decision, Evaluation, GoalRuntime, GoalStage
from .models import EvidenceValidity, GoalStatus, RunStatus, RunType, Stage

Runtime = GoalRuntime

__all__ = [
    "Decision", "Evaluation", "EvidenceValidity", "GoalRuntime", "GoalStage",
    "GoalStatus", "LegacyRuntime", "RunStatus", "RunType", "Stage", "Runtime",
]
