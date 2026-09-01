"""Thin command adapters; domain behavior lives in clean-core subsystems."""

from .goal_runtime import CleanCommandRuntime, goal_authority

__all__ = ["CleanCommandRuntime", "goal_authority"]
