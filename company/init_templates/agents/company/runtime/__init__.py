"""Canonical clean Goal runtime plus the bounded legacy-home adapter."""

from .loop import CompatibilityRuntime
from .engine import Decision, Evaluation, GoalRuntime, GoalStage
from .models import EvidenceValidity, GoalStatus, RunStatus, RunType, Stage

Runtime = GoalRuntime
LegacyRuntime = CompatibilityRuntime

__all__ = [
    "Decision", "Evaluation", "EvidenceValidity", "GoalRuntime", "GoalStage",
    "CompatibilityRuntime", "GoalStatus", "LegacyRuntime", "RunStatus", "RunType",
    "Stage", "Runtime",
]
