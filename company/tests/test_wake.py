"""Deterministic foreground wake helper for attached SpielOS1 Director sessions."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from company.runtime.loop import Runtime
from company.runtime.models import GoalHandler, GoalStatus
from company.runtime.runner import Runner


class _WakeOwner(GoalHandler):
    id = "wake_owner"
    version = "1.0.0"


class WakeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.runtime = Runtime(Path(self.temp.name) / "state.sqlite", {
            "wake_owner": _WakeOwner(),
        })
        self.goal = self.runtime.create_goal(
            name="Wake an attached Director", owner_id="wake_owner",
            metric="done", operator="eq", target=True, config={})

    def test_wake_sleeps_then_emits_one_host_event_without_ticking(self):
        runner = Runner(self.runtime)
        with patch("company.runtime.runner.time.sleep") as sleep:
            events = list(runner.wake(
                self.goal["id"], every_seconds=60, max_wakes=1,
                instruction="Continue Cycle 7", runner_status=lambda: {"running": False}))
        sleep.assert_called_once_with(60)
        self.assertEqual("director_wake", events[0]["event"])
        self.assertEqual("Continue Cycle 7", events[0]["instruction"])
        self.assertFalse(events[0]["runner_running"])
        self.assertEqual("idle", events[0]["run_status"])

    def test_terminal_goal_stops_before_emitting_a_director_wake(self):
        self.runtime.set_goal_status(self.goal["id"], GoalStatus.ACHIEVED)
        with patch("company.runtime.runner.time.sleep"):
            events = list(Runner(self.runtime).wake(
                self.goal["id"], every_seconds=1, max_wakes=1))
        self.assertEqual([{"event": "wake_stopped", "goal_id": self.goal["id"],
                           "reason": "goal_achieved"}], events)


if __name__ == "__main__":
    unittest.main()
