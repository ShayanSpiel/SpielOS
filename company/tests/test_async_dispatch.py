"""Async dispatch tests: non-blocking email batch execution.

Bounded repair goal-email-async-dispatch-20260815 (change_kind=repair): an
approved email batch must execute in a background worker (daemon thread +
status file) so `actor.execute()` returns immediately with
`{"dispatched": True, ...}`, `email_workflow.act()` parks the run in WAITING
while work is pending, and the next runner tick reconciles the stored result
(done) instead of re-sending or re-dispatching.

Coverage: dispatch pending file, double-dispatch prevention, check None while
pending, check done result, is_pending transitions, cleanup, stale detection,
actor.execute dispatch without blocking, actor.is_pending reflection,
email_workflow act() WAITING (both pending and just-dispatched branches).

Hermetic: DISPATCH_DIR is patched to a temp directory; no network, no real
master, no real sent log.
"""

import json
import sys
import tempfile
import time
import unittest
import unittest.mock
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from company.runtime import async_dispatch  # noqa: E402
from company.runtime.models import Goal, GoalContext, RunStatus, Stage  # noqa: E402
from company.departments.outbound.email_workflow import EmailWorkflow  # noqa: E402
from company.departments.outbound.workflows.email import actor  # noqa: E402


def _wait_done(goal_id, batch_id, timeout=5.0):
    """Poll check() until the dispatch file reaches a terminal state."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        result = async_dispatch.check(goal_id, batch_id)
        if result and result.get("status") != "pending":
            return result
        time.sleep(0.02)
    return None


class AsyncDispatchTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.dispatch_dir = self.tmp / "async"
        patcher = unittest.mock.patch.object(
            async_dispatch, "DISPATCH_DIR", self.dispatch_dir)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_dispatch_writes_pending_file(self):
        calls = []

        def work(_ctx, _batch):
            calls.append(1)
            time.sleep(0.3)  # keep the file pending while we assert its state
            return {"sent": 1, "failed": 0, "deduped": 0}

        result = async_dispatch.dispatch("g1", "b1", work, object(), {})
        self.assertTrue(result["dispatched"])
        self.assertFalse(result["already_pending"])
        path = self.dispatch_dir / "g1" / "b1.json"
        self.assertTrue(path.exists())
        data = json.loads(path.read_text())
        self.assertEqual(data["status"], "pending")
        # Work completes in the background and the file flips to done
        done = _wait_done("g1", "b1")
        self.assertIsNotNone(done)
        self.assertEqual(done["status"], "done")
        self.assertEqual(done["result"], {"sent": 1, "failed": 0, "deduped": 0})
        self.assertEqual(calls, [1])

    def test_double_dispatch_prevented(self):
        calls = []

        def work(_ctx, _batch):
            calls.append(1)
            time.sleep(0.3)  # keep the worker pending during the second dispatch
            return {"sent": 1, "failed": 0, "deduped": 0}

        first = async_dispatch.dispatch("g2", "b2", work, object(), {})
        second = async_dispatch.dispatch("g2", "b2", work, object(), {})
        self.assertTrue(first["dispatched"])
        self.assertTrue(second["dispatched"])
        self.assertTrue(second["already_pending"])
        done = _wait_done("g2", "b2")
        self.assertEqual(done["status"], "done")
        self.assertEqual(calls, [1], "second dispatch must not start another worker")

    def test_check_returns_none_while_pending(self):
        def work(_ctx, _batch):
            time.sleep(0.3)
            return {"sent": 0, "failed": 0, "deduped": 0}

        async_dispatch.dispatch("g3", "b3", work, object(), {})
        self.assertIsNone(async_dispatch.check("g3", "b3"))
        _wait_done("g3", "b3")
        self.assertIn(
            async_dispatch.check("g3", "b3").get("status"), {"done", "failed"})

    def test_check_returns_done_result(self):
        def work(_ctx, _batch):
            return {"sent": 3, "failed": 1, "deduped": 2}

        async_dispatch.dispatch("g4", "b4", work, object(), {})
        done = _wait_done("g4", "b4")
        self.assertEqual(done.get("status"), "done")
        self.assertEqual(
            done.get("result"), {"sent": 3, "failed": 1, "deduped": 2})
        self.assertIsNotNone(done.get("completed_at"))

    def test_is_pending_transitions(self):
        def work(_ctx, _batch):
            time.sleep(0.3)  # keep the worker pending while we assert
            return {"sent": 0, "failed": 0, "deduped": 0}

        self.assertFalse(async_dispatch.is_pending("g5", "b5"))
        async_dispatch.dispatch("g5", "b5", work, object(), {})
        self.assertTrue(async_dispatch.is_pending("g5", "b5"))
        _wait_done("g5", "b5")
        self.assertFalse(async_dispatch.is_pending("g5", "b5"))

    def test_cleanup_removes_file(self):
        async_dispatch.dispatch(
            "g6", "b6", lambda _ctx, _batch: {"sent": 0, "failed": 0, "deduped": 0},
            object(), {})
        _wait_done("g6", "b6")
        async_dispatch.cleanup("g6", "b6")
        self.assertFalse((self.dispatch_dir / "g6" / "b6.json").exists())
        self.assertIsNone(async_dispatch.check("g6", "b6"))
        self.assertFalse(async_dispatch.is_pending("g6", "b6"))

    def test_stale_pending_is_detected_and_not_pending(self):
        path = async_dispatch._get_result_path("g7", "b7")
        path.parent.mkdir(parents=True, exist_ok=True)
        started = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
        path.write_text(json.dumps({"status": "pending", "started_at": started}))
        result = async_dispatch.check("g7", "b7")
        self.assertEqual(result.get("status"), "stale")
        self.assertFalse(async_dispatch.is_pending("g7", "b7"))

    def test_actor_execute_dispatches_without_blocking(self):
        """A slow real send must not block execute(): the runner tick keeps
        the batch only as a pending dispatch file."""
        calls = []

        def slow_send(_ctx, _batch):
            calls.append(1)
            time.sleep(0.8)  # stands in for a real paced send (throttle)
            return {"sent": 2, "failed": 0, "deduped": 0, "note": "done"}

        ctx = SimpleNamespace(goal_id="goal-t", store=object())
        batch = {"id": "b-t", "emails": [{"lead_id": "L1"}, {"lead_id": "L2"}]}
        started = time.monotonic()
        with unittest.mock.patch.object(actor, "_execute_emails", side_effect=slow_send):
            result = actor.execute(ctx, batch, dry=False)
        elapsed = time.monotonic() - started
        self.assertTrue(result["dispatched"])
        self.assertLess(elapsed, 0.5, "execute must return before the send finishes")
        self.assertTrue(async_dispatch.is_pending("goal-t", "b-t"),
                        "dispatch file must exist right after execute")
        done = _wait_done("goal-t", "b-t")
        self.assertEqual(done["status"], "done")
        self.assertEqual(done["result"]["sent"], 2)
        self.assertEqual(calls, [1])

    def test_actor_is_pending_reflects_dispatch_file(self):
        ctx = SimpleNamespace(goal_id="goal-u", store=object())
        batch = {"id": "b-u", "emails": [{"lead_id": "L1"}]}

        def work(_ctx, _batch):
            time.sleep(0.3)  # keep the dispatch pending while we assert
            return {"sent": 1, "failed": 0, "deduped": 0}

        self.assertFalse(actor.is_pending(ctx, "b-u"))
        with unittest.mock.patch.object(actor, "_execute_emails", side_effect=work):
            result = actor.execute(ctx, batch, dry=False)
        self.assertTrue(result["dispatched"])
        self.assertTrue(actor.is_pending(ctx, "b-u"))
        _wait_done("goal-u", "b-u")
        self.assertFalse(actor.is_pending(ctx, "b-u"))

    def test_actor_execute_reconciles_done_result(self):
        ctx = SimpleNamespace(goal_id="goal-v", store=object())
        batch = {"id": "b-v", "emails": [{"lead_id": "L1"}]}
        calls = []
        with unittest.mock.patch.object(
                actor, "_execute_emails",
                side_effect=lambda _ctx, _batch: calls.append(1) or
                {"sent": 4, "failed": 0, "deduped": 0, "note": "done"}):
            first = actor.execute(ctx, batch, dry=False)
        self.assertTrue(first["dispatched"])
        _wait_done("goal-v", "b-v")
        # Next tick: pending cleared, stored result reconciled, no re-send
        second = actor.execute(ctx, batch, dry=False)
        self.assertNotIn("dispatched", second)
        self.assertEqual(second["sent"], 4)
        self.assertEqual(calls, [1], "reconciliation must not re-execute the batch")

    def test_actor_execute_stale_file_re_dispatches(self):
        ctx = SimpleNamespace(goal_id="goal-w", store=object())
        batch = {"id": "b-w", "emails": [{"lead_id": "L1"}]}
        path = async_dispatch._get_result_path("goal-w", "b-w")
        path.parent.mkdir(parents=True, exist_ok=True)
        started = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
        path.write_text(json.dumps({"status": "pending", "started_at": started}))
        with unittest.mock.patch.object(
                actor, "_execute_emails",
                return_value={"sent": 1, "failed": 0, "deduped": 0}):
            result = actor.execute(ctx, batch, dry=False)
        self.assertTrue(result["dispatched"])
        self.assertFalse(result["details"]["already_pending"],
                         "a fresh worker must start for a stale file")
        done = _wait_done("goal-w", "b-w")
        self.assertEqual(done["status"], "done")

    def test_actor_execute_without_goal_identity_stays_synchronous(self):
        """Legacy/direct callers (no goal id) keep the pre-dispatch
        synchronous send behavior and never touch the dispatch dir."""
        ctx = type("Ctx", (), {"store": object()})()
        batch = {"id": "b-x", "emails": [{"lead_id": "L1"}]}
        executed = []
        with unittest.mock.patch.object(
                actor, "_execute_emails",
                side_effect=lambda _ctx, _batch: executed.append(1) or
                {"sent": 1, "failed": 0, "deduped": 0, "note": "sync"}):
            result = actor.execute(ctx, batch, dry=False)
        self.assertEqual(result["sent"], 1)
        self.assertEqual(executed, [1])
        self.assertFalse(list(self.dispatch_dir.rglob("*.json")),
                         "no dispatch file may be written without a goal id")

    def test_actor_execute_dry_run_does_not_dispatch(self):
        ctx = SimpleNamespace(goal_id="goal-y", store=object())
        batch = {"id": "b-y", "emails": [{"lead_id": "L1"}]}
        with unittest.mock.patch.object(
                actor, "_execute_emails",
                side_effect=AssertionError("dry run must not send")):
            result = actor.execute(ctx, batch, dry=True)
        self.assertNotIn("dispatched", result)
        self.assertIn("DRY RUN", result["note"])
        self.assertFalse(list(self.dispatch_dir.rglob("*.json")))


class EmailWorkflowPendingTests(unittest.TestCase):
    """email_workflow.act() parks the run in WAITING with a resume_at while a
    dispatch is pending or was just dispatched, so the runner re-ticks and
    reconciles without the batch ever blocking a tick."""

    GOAL_CONFIG = {
        "execution_mode": "live",
        "evidence_window_hours": 24,
        "reply_capture": "manual_inbox",
    }
    BATCH_ID = "b-flow"

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.dispatch_dir = self.tmp / "async"
        patcher = unittest.mock.patch.object(
            async_dispatch, "DISPATCH_DIR", self.dispatch_dir)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.goal = Goal(
            "goal-flow", "Email", "email", "reply_rate", "ge", 0.3,
            None, None, "active", dict(self.GOAL_CONFIG))
        self.ctx = GoalContext(
            self.goal,
            {"data": {"action_result": {"batch_id": self.BATCH_ID,
                                        "preview_path": "/tmp/preview.md"}}},
            (), lambda key: "approved")
        self.row = {"id": self.BATCH_ID,
                    "batch": {"id": self.BATCH_ID,
                              "emails": [{"lead_id": "L1"}]}}
        self.outbound = SimpleNamespace(
            stop_file=self.tmp / "STOP",
            store=SimpleNamespace(get_batch=lambda batch_id: self.row))

    def _act(self, decision=None):
        with unittest.mock.patch(
                "company.departments.outbound.email_workflow.outbound_context",
                return_value=self.outbound):
            return EmailWorkflow().act(
                self.ctx, decision or {"action": "prepare_batch"})

    def test_act_waits_while_pending(self):
        async_dispatch.dispatch(
            "goal-flow", self.BATCH_ID,
            lambda _ctx, _batch: time.sleep(0.3) or
            {"sent": 0, "failed": 0, "deduped": 0},
            object(), {})
        self.assertTrue(actor.is_pending(self.ctx, self.BATCH_ID))
        with unittest.mock.patch(
                "company.departments.outbound.execution.execute",
                side_effect=AssertionError("execute must not run while pending")):
            result = self._act()
        self.assertEqual(result.run_status, RunStatus.WAITING)
        self.assertEqual(result.next_stage, Stage.ACT)
        self.assertIsNotNone(result.resume_at,
                             "WAITING must carry resume_at or the runner never re-ticks")
        self.assertEqual(result.payload.get("batch_id"), self.BATCH_ID)
        _wait_done("goal-flow", self.BATCH_ID)

    def test_act_waits_when_execute_dispatched(self):
        executed = []

        def fake_execute(outbound, row, dry=False):
            executed.append((outbound, row, dry))
            return {"dispatched": True, "batch_id": row["id"],
                    "note": "dispatched to background"}

        with unittest.mock.patch(
                "company.departments.outbound.execution.execute",
                side_effect=fake_execute):
            result = self._act()
        self.assertEqual(result.run_status, RunStatus.WAITING)
        self.assertEqual(result.next_stage, Stage.ACT)
        self.assertTrue(result.payload.get("dispatched"))
        self.assertIsNotNone(result.resume_at,
                             "dispatched WAITING must carry resume_at")
        # The goal identity must reach the actor's reconciliation key
        self.assertEqual(executed, [(self.outbound, self.row, False)])
        self.assertEqual(self.outbound.goal_id, "goal-flow")

    def test_act_proceeds_when_result_is_reconciled(self):
        """Once the dispatch is done, act() reconciles the stored result and
        proceeds to evidence collection (EVALUATE), not WAITING."""
        self.outbound.goal_id = "goal-flow"  # what act() stamps before execute
        with unittest.mock.patch.object(
                actor, "_execute_emails",
                return_value={"sent": 1, "failed": 0, "deduped": 0, "note": "done"}):
            dispatched = actor.execute(self.outbound, self.row["batch"], dry=False)
        self.assertTrue(dispatched["dispatched"])
        done = _wait_done("goal-flow", self.BATCH_ID)
        self.assertEqual(done["status"], "done")

        def real_execute(outbound, row, dry=False):
            return actor.execute(outbound, row["batch"], dry=dry)

        with unittest.mock.patch(
                "company.departments.outbound.execution.execute",
                side_effect=real_execute), \
             unittest.mock.patch(
                "company.departments.outbound.workflows.email.outbound.load_sent_log",
                return_value={"sent": [], "failed": []}):
            result = self._act()
        self.assertEqual(result.run_status, RunStatus.WAITING)
        self.assertEqual(result.next_stage, Stage.EVALUATE)
        self.assertFalse(result.payload.get("dispatched"))
        self.assertEqual(result.payload["execution"]["sent"], 1)


if __name__ == "__main__":
    unittest.main()