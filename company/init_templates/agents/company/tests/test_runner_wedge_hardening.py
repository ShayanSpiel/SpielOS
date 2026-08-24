"""Regression tests for goal-runner-wedge-hardening-20260815 (change_kind=repair).

Problem statement (the spec): "The parent outbound campaign measure tick wedged
two daemon generations: daemon 69670 stopped completing watch cycles at
04:14Z (heartbeat stale; campaign lease acquired ~04:18Z never renewed) and
daemon 70146 died silently ~2 min after start (04:19:24Z) with no traceback
and no lease. ... a stalled HTTPS connection held the daemon's only thread
forever ... a killed daemon left metrics.json torn mid-write, which then
silently killed the next daemon generation on json.load (JSONDecodeError with
no traceback)."

Intended API contract (implementer must make every test pass by editing ONLY
the task's allowed files):

1. Bounded measure path: every provider call in `analytics` (list sent, list
   received, per-email status) runs through `analytics._bounded_call` with a
   hard timeout, and `analytics.collect` stops fetching past its deadline —
   a stalled provider endpoint can slow a measure but never hold the serial
   watch loop forever.

2. Resilient persistence: `analytics.save_metrics` writes atomically
   (tmp + rename) and `analytics.load_metrics` returns the empty ledger (not
   a crash) when the file is torn/unreadable.

3. Lease-held stuck detection: `Runner._check_stalled` flags an active goal
   whose cycle lease has been held past the grace with no advancement, while
   a fresh lease never trips it.

4. Dead-worker dispatch recovery: a pending async dispatch file whose worker
   thread died with a previous daemon generation is removed for re-dispatch
   (with a stuck_goal notification), instead of waiting for the 1-hour stale
   threshold.
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

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from company.runtime.loop import Runtime  # noqa: E402
from company.runtime.models import (  # noqa: E402
    GoalHandler, GoalStatus, RunStatus, Stage, StageResult,
)
from company.runtime.runner import (  # noqa: E402
    LEASE_HELD_GRACE_SECONDS, LEASE_TTL_SECONDS, Runner,
)


# ── Analytics: bounded measure path + resilient persistence ──────────────────

class AnalyticsWedgeTests(unittest.TestCase):
    """The campaign measure path (analytics.collect via observer) must be
    bounded and must survive a torn metrics.json."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.metrics_path = self.root / "metrics.json"
        self.providers_patch = unittest.mock.patch(
            "company.departments.outbound.workflows.email.analytics.providers")
        self.providers = self.providers_patch.start()
        self.addCleanup(self.providers_patch.stop)
        self.providers.cap_status.return_value = True
        self.providers.cap_list_sent.return_value = True
        self.providers.cap_received.return_value = True
        self.cfg_patch = unittest.mock.patch(
            "company.departments.outbound.workflows.email.analytics.config.METRICS_PATH",
            self.metrics_path)
        self.cfg_patch.start()
        self.addCleanup(self.cfg_patch.stop)
        self.metrics_path.write_text(json.dumps({
            "last_check": (datetime.now(timezone.utc)
                           - timedelta(hours=24)).isoformat(),
            "emails": {}, "replies": [], "collapsed_received_ids": [],
        }))

    @staticmethod
    def _valid_id(prefix: str = "abc") -> str:
        return (prefix + "x" * 40)[:40]

    def _log(self, count: int = 3) -> dict:
        return {"sent": [
            {"lead_id": f"L{i}", "email": f"lead{i}@example.com",
             "provider": "resend", "provider_id": self._valid_id(str(i)),
             "timestamp": datetime.now(timezone.utc).isoformat()}
            for i in range(count)],
            "failed": []}

    def test_collect_stops_fetching_past_deadline(self):
        # A deadline already in the past must mean ZERO provider status
        # fetches — the whole pass is bounded even if every endpoint stalls.
        self.providers.list_sent_emails.return_value = {"data": [], "error": None}
        self.providers.list_received_emails.return_value = {"data": [], "error": None}
        log = self._log()
        from company.departments.outbound.workflows.email import analytics
        metrics, ran = analytics.collect(log, force=True,
                                         deadline=time.time() - 1)
        self.assertTrue(ran)
        self.providers.fetch_email_status.assert_not_called()
        self.providers.list_received_emails.assert_not_called()
        # The pass still persisted its (empty) progress and stamped last_check.
        self.assertIsNotNone(metrics["last_check"])

    def test_bounded_call_abandons_stalled_worker(self):
        from company.departments.outbound.workflows.email import analytics

        def stall():
            threading.Event().wait(30)  # never returns on its own

        started = time.monotonic()
        result, timed_out = analytics._bounded_call(stall, 0.3)
        elapsed = time.monotonic() - started
        self.assertTrue(timed_out)
        self.assertIsNone(result)
        self.assertLess(elapsed, 5,
                        "_bounded_call must return at the timeout, not later")

    def test_collect_fetch_timeout_is_bounded_and_recorded(self):
        # A stalled per-email status endpoint must not hang collect; the
        # email is recorded as unknown (fetch timed out) and the pass
        # completes well under the deadline.
        def stall(*_args, **_kwargs):
            threading.Event().wait(30)  # never returns on its own

        self.providers.fetch_email_status.side_effect = stall
        self.providers.list_sent_emails.return_value = {"data": [], "error": None}
        from company.departments.outbound.workflows.email import analytics
        started = time.monotonic()
        metrics, ran = analytics.collect(self._log(1), force=True,
                                         deadline=time.time() + 30)
        elapsed = time.monotonic() - started
        self.assertTrue(ran)
        self.assertLess(elapsed, 15,
                        "a stalled fetch must not hold collect for minutes")
        rec = metrics["emails"]["L0"]
        self.assertEqual(rec["status"], "unknown")
        self.assertIn("timeout", str(rec.get("last_error") or ""))
    def test_sync_replies_listing_is_bounded(self):
        # A stalled received-email listing must not hang the reply sync.
        def stall(*_args, **_kwargs):
            threading.Event().wait(30)

        self.providers.list_received_emails.side_effect = stall
        from company.departments.outbound.workflows.email import analytics
        started = time.monotonic()
        added = analytics.sync_replies(self._log(1), {"replies": []})
        elapsed = time.monotonic() - started
        self.assertEqual(added, 0)
        self.assertLess(elapsed, 15, "stalled listing must not hang sync_replies")

    def test_metrics_save_is_atomic_and_load_survives_torn_file(self):
        from company.departments.outbound.workflows.email import analytics
        payload = {"last_check": None, "emails": {"L0": {"status": "delivered"}},
                   "replies": [], "collapsed_received_ids": []}
        analytics.save_metrics(payload)
        # Atomic: the tmp file is renamed away — no tmp residue, valid JSON.
        self.assertFalse(list(self.root.glob("*.tmp")))
        self.assertEqual(json.loads(self.metrics_path.read_text()), payload)
        # Torn file (daemon killed mid-write): load must not raise; the next
        # collect refetches and atomically rewrites (self-healing, honest).
        self.metrics_path.write_text('{"last_check": "2026-08-15T04:18', encoding="utf-8")
        loaded = analytics.load_metrics()
        self.assertEqual(loaded["emails"], {})
        self.assertIsNone(loaded["last_check"])
        # Unreadable file behaves the same.
        self.metrics_path.write_text("\x00\x01\x02", encoding="utf-8")
        loaded = analytics.load_metrics()
        self.assertEqual(loaded["emails"], {})


# ── Runner: lease-held stuck detection + dead-worker dispatch recovery ────────

class WedgeHandler(GoalHandler):
    """One guarded action; a parked run keeps a goal around for stall checks."""

    id = "wedge_test"

    def observe(self, ctx):
        return StageResult("collect", {"real": True})

    def decide(self, ctx, observation):
        return StageResult("diagnose", {"action": "execute_gated"})

    def act(self, ctx, decision):
        if ctx.approval_status("execute") != "approved":
            return StageResult(
                "review", {"prepared": True}, RunStatus.AWAITING_APPROVAL, Stage.ACT)
        return StageResult("execute", {"executed": True})

    def evaluate(self, ctx, action_result):
        return StageResult(
            "goal_check", {"done": True}, RunStatus.IDLE,
            goal_status=GoalStatus.ACHIEVED,
            evaluation={"verdict": "goal_met", "goal_met": True,
                        "metrics": {ctx.goal.metric: True}, "validity": "business"})


class RunnerWedgeTests(unittest.TestCase):
    """Watchdog extension: lease-held cycles and dead-worker dispatches."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.db = self.root / ".spielos/state/company.sqlite"
        self.runtime = Runtime(self.db, {"wedge_test": WedgeHandler()})
        self.runner = Runner(self.runtime)

    def parked_goal(self):
        goal = self.runtime.create_goal(
            name="Wedge", owner_id="wedge_test",
            metric="done", operator="eq", target=True, config={})
        self.runtime.once(goal["id"])  # parks awaiting approval
        return goal

    def insert_lease(self, goal_id: str, *, expires_at: datetime) -> None:
        with self.runtime.store.connect() as con:
            con.execute(
                "INSERT INTO leases(goal_id, holder, expires_at) VALUES (?,?,?) "
                "ON CONFLICT(goal_id) DO UPDATE SET holder=excluded.holder, "
                "expires_at=excluded.expires_at",
                (goal_id, "wedge-test", expires_at.isoformat()))

    def backdate_cycle(self, goal_id: str, *, updated_at: datetime) -> None:
        cycle = self.runtime.store.cycle(goal_id)
        with self.runtime.store.connect() as con:
            con.execute("UPDATE cycles SET updated_at=? WHERE id=?",
                        (updated_at.isoformat(), cycle["id"]))

    # ------------------------------------------------------------------ #
    # Lease-held stuck detection (2026-08-15 wedge)                       #
    # ------------------------------------------------------------------ #

    def test_lease_held_past_grace_without_advancement_emits_stuck_goal(self):
        goal = self.parked_goal()
        # Lease acquired LEASE_TTL_SECONDS before its expiry, still live:
        # acquired_at = now - (LEASE_TTL_SECONDS - 5) which is past the grace
        # only when the cycle has not advanced since acquisition.
        expires = datetime.now(timezone.utc) + timedelta(seconds=5)
        self.insert_lease(goal["id"], expires_at=expires)
        acquired = expires - timedelta(seconds=LEASE_TTL_SECONDS)
        self.backdate_cycle(goal["id"], updated_at=acquired - timedelta(seconds=1))
        self.assertGreater(
            (datetime.now(timezone.utc) - acquired).total_seconds(),
            LEASE_HELD_GRACE_SECONDS)
        emitted = self.runner._check_stalled()
        self.assertEqual(emitted, [goal["id"]])
        pending = [row for row in self.runtime.store.notifications("pending")
                   if row["goal_id"] == goal["id"]]
        self.assertTrue(pending, "wedged lease must produce a notification")
        payload = pending[-1]["payload"]
        self.assertEqual(payload["watchdog"]["signal"], "stuck_goal")
        self.assertIn("lease held without advancement",
                      payload["watchdog"]["reason"])
        self.assertIn("lease_held_seconds", payload["watchdog"])

    def test_fresh_lease_does_not_trip_stuck_detection(self):
        goal = self.parked_goal()
        self.insert_lease(goal["id"],
                          expires_at=datetime.now(timezone.utc)
                          + timedelta(seconds=LEASE_TTL_SECONDS))
        emitted = self.runner._check_stalled()
        self.assertEqual(emitted, [], "a just-acquired lease is not wedged")

    # ------------------------------------------------------------------ #
    # Dead-worker dispatch recovery                                       #
    # ------------------------------------------------------------------ #

    def _async_dir(self) -> Path:
        return self.runtime.store.path.parent / "outbound" / "async"

    def test_old_pending_dispatch_recovered_and_emitted(self):
        goal = self.parked_goal()
        # A pending dispatch file started before this Runner generation by
        # more than the dead-worker grace: its worker thread died with the
        # previous process, so it must be removed for re-dispatch.
        async_dir = self._async_dir() / goal["id"]
        async_dir.mkdir(parents=True, exist_ok=True)
        old_started = (datetime.now(timezone.utc)
                       - timedelta(minutes=10)).isoformat()
        (async_dir / "b1.json").write_text(json.dumps({
            "status": "pending", "started_at": old_started,
            "batch_id": "b1", "goal_id": goal["id"]}))
        self.runner._generation_started_at = datetime.now(timezone.utc)
        emitted = self.runner._check_stalled()
        self.assertIn(goal["id"], emitted)
        self.assertFalse(
            (async_dir / "b1.json").exists(),
            "dead-worker pending dispatch must be removed for re-dispatch")
        pending = [row for row in self.runtime.store.notifications("pending")
                   if row["goal_id"] == goal["id"]]
        payload = pending[-1]["payload"]
        self.assertEqual(payload["watchdog"]["signal"], "stuck_goal")
        self.assertIn("worker died", payload["watchdog"]["reason"])

    def test_fresh_pending_dispatch_kept(self):
        goal = self.parked_goal()
        async_dir = self._async_dir() / goal["id"]
        async_dir.mkdir(parents=True, exist_ok=True)
        started = datetime.now(timezone.utc).isoformat()
        dispatch_file = async_dir / "b1.json"
        dispatch_file.write_text(json.dumps({
            "status": "pending", "started_at": started,
            "batch_id": "b1", "goal_id": goal["id"]}))
        # This generation dispatched it: the worker thread is live.
        self.runner._generation_started_at = datetime.now(timezone.utc)
        emitted = self.runner._check_stalled()
        self.assertEqual(emitted, [], "a fresh dispatch has a live worker")
        self.assertTrue(dispatch_file.exists())


if __name__ == "__main__":
    unittest.main()
