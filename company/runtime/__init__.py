"""Canonical clean Goal runtime."""

from .engine import Decision, Evaluation, GoalRuntime, GoalStage

Runtime = GoalRuntime

__all__ = [
    "Decision", "Evaluation", "GoalRuntime", "GoalStage", "Runtime",
]
