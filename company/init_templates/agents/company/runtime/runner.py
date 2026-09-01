"""Thin command adapter over the canonical GoalRuntime scheduler."""

from __future__ import annotations


class Runner:
    """Retained for callers; scheduling itself lives in GoalRuntime.tick/watch."""

    def __init__(self, runtime):
        self.runtime = runtime

    def tick(self, goal_id: str | None = None, max_advances: int = 100) -> dict:
        if goal_id is not None:
            return self.runtime.once(goal_id)
        return self.runtime.tick(max_advances)

    def watch(self, interval_seconds: float = 2.0,
              goal_id: str | None = None, max_ticks: int | None = None):
        yield from self.runtime.watch(interval_seconds, goal_id, max_ticks)
