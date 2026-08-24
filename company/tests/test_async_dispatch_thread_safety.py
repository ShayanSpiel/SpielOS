"""Async-dispatch thread-safety regression tests.

Bounded repair goal-async-dispatch-sqlite-thread-20260815 (change_kind=repair,
from_version 6.5.0 -> target 6.6.0): the async-dispatch background worker
thread crashed on cross-thread SQLite access. OutboundStore opened its
connection with sqlite3.connect(path) (thread-bound), and the dispatch worker
then called ctx.store.record_action and died with "SQLite objects created in a
thread can only be used in that same thread", leaving the dispatch file
status=failed and flipping the goal run to FAILED. The repair: the store
connection is opened with check_same_thread=False and serialized by a
re-entrant lock, and failed dispatch files are retryable after a grace window
instead of terminal.

Regression coverage:
  1. a store opened in one thread is usable from a worker thread
     (record_action succeeds), and concurrent writers are serialized;
  2. a failed dispatch file transitions to a fresh re-dispatch after the
     grace window — actor.execute does not raise, error evidence is kept, the
     file is cleaned, and a fresh worker starts; a fresh failure is parked
     (dispatched contract), not hot-looped;
  3. done files still short-circuit to the stored result (no re-execute).

Hermetic: DISPATCH_DIR is patched to a temp directory; stores use temp
sqlite files; no network, no real master, no real sent log.
"""

import json
import sys
import tempfile
import threading
import time
import unittest
import unittest.mock
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from company.runtime import async_dispatch  # noqa: E402
from company.departments.outbound.data import OutboundStore  # noqa: E402
from company.departments.outbound.models import Lead, LeadState  # noqa: E402
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


class OutboundStoreThreadSafetyTests(unittest.TestCase):
    """Regression: a store opened by the tick/main thread must be usable from
    the dispatch worker thread (record_action), and concurrent writers must
    be serialized by the connection lock."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.store = OutboundStore(self.tmp / "outbound.sqlite")
        self.store.upsert_leads([
            Lead(lead_id="L1", name="Ada", company="ACME",
                 state=LeadState.READY, icp_score=90),
            Lead(lead_id="L2", name="Bob", company="Beta",
                 state=LeadState.READY, icp_score=85),
        ])

    def tearDown(self):
        self.store.close()

    def test_store_opened_in_main_thread_usable_from_worker(self):
        """record_action from a different thread must not raise the SQLite
        thread error."""
        errors = []

        def worker():
            try:
                for _ in range(3):
                    self.store.record_action(
                        "L1", "email", "send_email", "sent", "batch b")
            except Exception as e:  # pragma: no cover
                errors.append(e)

        t = threading.Thread(target=worker)
        t.start()
        t.join(10)
        self.assertFalse(t.is_alive(), "worker thread must finish")
        self.assertEqual(errors, [],
                         "worker-thread record_action must not raise")
        self.assertEqual(
            self.store.action_count("email", "send_email", "sent"), 3)

    def test_concurrent_record_actions_are_serialized(self):
        """The connection lock must serialize execute/commit sequences: every
        recorded action lands exactly once under contention."""
        errors = []

        def worker(lead_id):
            try:
                for _ in range(5):
                    self.store.record_action(
                        lead_id, "email", "send_email", "sent", "batch c")
            except Exception as e:  # pragma: no cover
                errors.append(e)

        threads = [threading.Thread(target=worker, args=("L1",)) for _ in range(2)]
        threads += [threading.Thread(target=worker, args=("L2",)) for _ in range(2)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(10)
        self.assertEqual(errors, [], "concurrent writers must not raise")
        self.assertEqual(
            self.store.action_count("email", "send_email", "sent"), 20,
            "every serialized action must be recorded exactly once")


class FailedDispatchRetryTests(unittest.TestCase):
    """Failed dispatch files are retryable, not terminal: after the grace
    window actor.execute cleans the file and starts a fresh worker; a fresh
    failure is parked (no hot loop); done files keep short-circuiting."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.dispatch_dir = self.tmp / "async"
        patcher = unittest.mock.patch.object(
            async_dispatch, "DISPATCH_DIR", self.dispatch_dir)
        patcher.start()
        self.addCleanup(patcher.stop)

    def _ctx(self, goal_id):
        return SimpleNamespace(goal_id=goal_id, store=object())

    def _write_failed(self, goal_id, batch_id, age_seconds=None,
                      error="SQLite objects created in a thread can only be "
                            "used in that same thread"):
        path = async_dispatch._get_result_path(goal_id, batch_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"status": "failed", "error": error}
        if age_seconds is not None:
            payload["completed_at"] = (
                datetime.now(timezone.utc) - timedelta(seconds=age_seconds)
            ).isoformat()
        path.write_text(json.dumps(payload))
        return path

    def test_failed_dispatch_re_dispatches_after_grace(self):
        """An old failure must not raise: the error evidence is preserved in
        the result, the file is cleaned, and a fresh worker starts."""
        ctx = self._ctx("goal-f1")
        batch = {"id": "b-f1", "emails": [{"lead_id": "L1"}]}
        self._write_failed("goal-f1", "b-f1", age_seconds=600)
        calls = []

        def work(_ctx, _batch):
            calls.append(1)
            time.sleep(0.3)  # keep the fresh dispatch pending while asserted
            return {"sent": 1, "failed": 0, "deduped": 0, "note": "done"}

        with unittest.mock.patch.object(actor, "_execute_emails", side_effect=work):
            result = actor.execute(ctx, batch, dry=False)
        self.assertTrue(result["dispatched"])
        self.assertEqual(result["note"], "re-dispatched after previous failure")
        self.assertIn("previous_error", result,
                      "error evidence must be preserved across the retry")
        self.assertTrue(async_dispatch.is_pending("goal-f1", "b-f1"),
                        "a fresh worker must be pending after re-dispatch")
        done = _wait_done("goal-f1", "b-f1")
        self.assertEqual(done["status"], "done")
        self.assertEqual(calls, [1], "exactly one fresh worker must start")

    def test_failed_dispatch_without_timestamp_is_retryable(self):
        """A failed record with no usable completed_at is immediately
        retryable so a worker failure can always recover."""
        ctx = self._ctx("goal-f4")
        batch = {"id": "b-f4", "emails": [{"lead_id": "L1"}]}
        self._write_failed("goal-f4", "b-f4", age_seconds=None)
        with unittest.mock.patch.object(
                actor, "_execute_emails",
                return_value={"sent": 1, "failed": 0, "deduped": 0, "note": "done"}):
            result = actor.execute(ctx, batch, dry=False)
        self.assertTrue(result["dispatched"])
        self.assertIn("previous_error", result)
        done = _wait_done("goal-f4", "b-f4")
        self.assertEqual(done["status"], "done")

    def test_fresh_failure_is_parked_not_hot_looped(self):
        """A failure younger than the grace window must not re-dispatch: the
        run is parked via the dispatched contract and the error evidence
        stays in the file, so the retry only happens after the grace."""
        ctx = self._ctx("goal-f2")
        batch = {"id": "b-f2", "emails": [{"lead_id": "L1"}]}
        path = self._write_failed("goal-f2", "b-f2", age_seconds=30)
        calls = []

        def work(_ctx, _batch):
            calls.append(1)
            return {"sent": 1, "failed": 0, "deduped": 0, "note": "done"}

        with unittest.mock.patch.object(actor, "_execute_emails", side_effect=work):
            result = actor.execute(ctx, batch, dry=False)
        self.assertTrue(result["dispatched"],
                        "parked result keeps the WAITING contract")
        self.assertIn("retrying after grace", result["note"])
        self.assertFalse(async_dispatch.is_pending("goal-f2", "b-f2"),
                         "no fresh worker may start inside the grace window")
        self.assertEqual(calls, [], "the batch must not re-execute fresh")
        data = json.loads(path.read_text())
        self.assertEqual(data["status"], "failed",
                         "error evidence must stay on disk during the grace")

    def test_done_file_still_short_circuits(self):
        """Done files keep the reconciled short-circuit: the stored result is
        returned and the batch is never re-executed."""
        ctx = self._ctx("goal-f3")
        batch = {"id": "b-f3", "emails": [{"lead_id": "L1"}]}
        path = async_dispatch._get_result_path("goal-f3", "b-f3")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({
            "status": "done",
            "result": {"sent": 4, "failed": 0, "deduped": 0, "note": "done"},
            "completed_at": datetime.now(timezone.utc).isoformat(),
        }))
        with unittest.mock.patch.object(
                actor, "_execute_emails",
                side_effect=AssertionError(
                    "done reconciliation must not re-execute the batch")):
            result = actor.execute(ctx, batch, dry=False)
        self.assertNotIn("dispatched", result)
        self.assertEqual(result["sent"], 4)
        self.assertEqual(result["note"], "done")


if __name__ == "__main__":
    unittest.main()
