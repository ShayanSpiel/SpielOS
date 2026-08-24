"""Regression tests: _persist tolerates StageResult.evidence=None.

Bounded repair goal-async-dispatch-persist-20260815 (change_kind=repair): the
outbound email workflow intentionally returns evidence=None from ACT.execute on
the async-dispatch path (already-pending and dispatched-to-background resignals
with resume_at), because evidence only exists once the background worker
completes. runtime/loop.py `_persist` previously iterated `result.evidence`
unguarded, raising TypeError: 'NoneType' object is not iterable, which killed
the runner daemon tick and the in-process background sender threads.

Coverage: (1) a WAITING StageResult with evidence=None persists a run/cycle
without TypeError; (2) a StageResult with a normal evidence list still persists
each evidence item; (3) learnings=None (defensively tolerated like
evidence=None) persists cleanly.

Hermetic: each test uses its own temp SQLite store; no network, no real email
dispatch.
"""

import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from company.runtime.loop import Runtime
from company.runtime.models import GoalHandler, GoalStatus, RunStatus, Stage, StageResult


class AsyncPersistHandler(GoalHandler):
    """Configurable handler whose ACT stage mirrors the async-dispatch resignal.

    `act` returns one WAITING StageResult with the configured learnings and
    evidence and a resume_at in the future, exactly like email_workflow.act()
    on the already-dispatched / dispatched-to-background paths.
    """

    id = "async_persist_test"
    learnings = None
    evidence = None

    def observe(self, ctx):
        return StageResult("collect", {"ok": True})

    def decide(self, ctx, observation):
        return StageResult("diagnose", {"action": "dispatch"})

    def act(self, ctx, decision):
        return StageResult(
            "execute",
            {"dispatched": True, "batch_id": "b-regress"},
            RunStatus.WAITING, Stage.ACT,
            resume_at=(datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat(),
            learnings=self.learnings,
            evidence=self.evidence,
        )

    def evaluate(self, ctx, action_result):
        return StageResult("goal_check", action_result)


class AsyncDispatchPersistTests(unittest.TestCase):
    def runtime_with(self, evidence=None, learnings=None):
        handler = AsyncPersistHandler()
        handler.evidence = evidence
        handler.learnings = learnings
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        runtime = Runtime(Path(self.temp.name) / "state.sqlite", {handler.id: handler})
        goal = runtime.create_goal(name="Async persist", owner_id=handler.id,
                                   metric="sent", operator="ge", target=1, config={})
        return runtime, goal["id"]

    def test_waiting_result_with_evidence_none_persists_without_typeerror(self):
        """A WAITING async-dispatch resignal (evidence=None, learnings=None)
        must persist the run/cycle instead of crashing _persist."""
        runtime, goal_id = self.runtime_with(evidence=None, learnings=None)
        state = runtime.once(goal_id)  # must not raise TypeError
        self.assertEqual(state["cycle"]["run_status"], "waiting")
        self.assertEqual(state["cycle"]["stage"], "ACT")
        self.assertEqual(state["cycle"]["step"], "execute")
        self.assertIsNotNone(state["cycle"]["resume_at"],
                             "WAITING must carry resume_at or the runner never re-ticks")
        self.assertEqual(state["cycle"]["data"]["action_result"]["dispatched"], True)
        self.assertEqual(runtime.store.evidence(state["cycle"]["id"]), [])

    def test_normal_evidence_list_still_persists_each_item(self):
        """A result with evidence items keeps persisting every item."""
        evidence = [
            {"kind": "dispatch_planned", "source": "email_workflow",
             "payload": {"batch_id": "b-1"}, "validity": "technical_only"},
            {"kind": "dispatch_planned", "source": "email_workflow",
             "payload": {"batch_id": "b-2"}, "validity": "technical_only"},
        ]
        runtime, goal_id = self.runtime_with(evidence=evidence, learnings=None)
        state = runtime.once(goal_id)
        rows = runtime.store.evidence(state["cycle"]["id"])
        self.assertEqual([row["kind"] for row in rows], ["dispatch_planned", "dispatch_planned"])
        self.assertEqual([row["payload"] for row in rows],
                         [{"batch_id": "b-1"}, {"batch_id": "b-2"}])
        self.assertEqual([row["source"] for row in rows], ["email_workflow", "email_workflow"])

    def test_learnings_none_persists_cleanly(self):
        """learnings=None is defensively tolerated the same way as
        evidence=None (a result with learnings=None persists without error)."""
        runtime, goal_id = self.runtime_with(evidence=[], learnings=None)
        state = runtime.once(goal_id)  # must not raise TypeError
        self.assertEqual(state["cycle"]["run_status"], "waiting")
        self.assertEqual(state["cycle"]["data"]["action_result"]["batch_id"], "b-regress")


if __name__ == "__main__":
    unittest.main()