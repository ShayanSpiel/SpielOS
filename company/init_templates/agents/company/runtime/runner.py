"""Deterministic advancement of already-runnable persisted Goals.

Runner does not decide what the company should do, supervise outcomes, emit
digests, or maintain a HUD. Those are Director/session responsibilities.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone

from .alignment import approval_key, priority_score
from .loop import Runtime
from .service import automation_enabled
from .util import parse_dt

logger = logging.getLogger("company.runtime.runner")


class Runner:
    def __init__(self, runtime: Runtime):
        self.runtime = runtime

    def tick(self, goal_id: str | None = None, max_advances: int = 100) -> dict:
        """Advance runnable persisted work until it becomes quiescent."""
        if not automation_enabled(self.runtime.store.path.parent):
            return {"advanced": [], "pending_notifications": [],
                    "quiescent": True, "stopped": True}
        advanced = []
        for _ in range(max_advances):
            candidates = self._candidates(goal_id)
            if not candidates:
                break
            progress = False
            for candidate in candidates:
                before = self._signature(candidate)
                try:
                    self.runtime.once(candidate, holder="company-runner")
                except Exception as exc:
                    logger.warning("tick skipped goal %s: %s", candidate, exc)
                    continue
                after = self._signature(candidate)
                if after != before:
                    progress = True
                    advanced.append({"goal_id": candidate, "state": after})
            if not progress:
                break
        return {
            "advanced": advanced,
            "pending_notifications": self.runtime.store.notifications("pending"),
            "quiescent": not self._candidates(goal_id),
        }

    def watch(self, interval_seconds: float = 2.0,
              goal_id: str | None = None, max_ticks: int | None = None):
        """Repeatedly advance work; make no supervisory decisions."""
        ticks = 0
        while max_ticks is None or ticks < max_ticks:
            result = self.tick(goal_id)
            if result["advanced"]:
                yield result
            ticks += 1
            if max_ticks is None or ticks < max_ticks:
                time.sleep(interval_seconds)

    def _candidates(self, goal_id: str | None) -> list[str]:
        rows = self._scope_rows(goal_id, self.runtime.list_goals())
        runnable = [row for row in rows if self._runnable(row)]
        runnable.sort(key=lambda row: (
            -self._root_priority(row["goal"], rows),
            -priority_score(row["goal"]),
            -self._depth(row["goal"], rows),
            row["goal"]["created_at"]))
        return [row["goal"]["id"] for row in runnable]

    @staticmethod
    def _root_priority(goal: dict, rows: list[dict]) -> float:
        by_id = {row["goal"]["id"]: row["goal"] for row in rows}
        current, seen = goal, set()
        while current.get("parent_id") and current["parent_id"] not in seen:
            seen.add(current["id"])
            parent = by_id.get(current["parent_id"])
            if not parent:
                break
            current = parent
        return priority_score(current)

    def _runnable(self, row: dict) -> bool:
        if row["goal"]["goal_status"] != "active":
            return False
        cycle = row["cycle"]
        status = cycle["run_status"]
        if status == "idle":
            return True
        if status == "completed":
            return self.runtime.continuation_decision(row["goal"]["id"])["eligible"]
        if status in {"blocked", "failed"}:
            return self.runtime.repair_iteration_decision(row["goal"]["id"])["eligible"]
        if status == "awaiting_approval":
            return self.runtime._approval_status(
                row["goal"], cycle, approval_key(cycle)) == "approved"
        if status == "running":
            return self.runtime.store.live_lease(row["goal"]["id"]) is None
        if status != "waiting" or not cycle.get("resume_at"):
            return False
        resume_at = parse_dt(cycle["resume_at"])
        return resume_at is not None and resume_at <= datetime.now(timezone.utc)

    def _signature(self, goal_id: str):
        state = self.runtime.status(goal_id)
        return (state["goal"]["goal_status"], state["cycle"]["id"],
                state["cycle"]["stage"], state["cycle"]["step"],
                state["cycle"]["run_status"], state["cycle"].get("resume_at"),
                len(state["evidence"]), bool(state["evaluation"]))

    @staticmethod
    def _descendants(goal_id: str, rows: list[dict]) -> set[str]:
        found, frontier = set(), {goal_id}
        while frontier:
            children = {row["goal"]["id"] for row in rows
                        if row["goal"].get("parent_id") in frontier}
            children -= found
            found |= children
            frontier = children
        return found

    @staticmethod
    def _ancestors(goal_id: str, rows: list[dict]) -> set[str]:
        parents = {row["goal"]["id"]: row["goal"].get("parent_id") for row in rows}
        found, parent = set(), parents.get(goal_id)
        while parent:
            found.add(parent)
            parent = parents.get(parent)
        return found

    @staticmethod
    def _depth(goal: dict, rows: list[dict]) -> int:
        parents = {row["goal"]["id"]: row["goal"].get("parent_id") for row in rows}
        depth, parent = 0, goal.get("parent_id")
        while parent:
            depth += 1
            parent = parents.get(parent)
        return depth

    def _scope_rows(self, goal_id: str | None, rows: list[dict]) -> list[dict]:
        if not goal_id:
            return rows
        allowed = (self._descendants(goal_id, rows)
                   | self._ancestors(goal_id, rows) | {goal_id})
        return [row for row in rows if row["goal"]["id"] in allowed]
