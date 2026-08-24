"""Regression tests for goal-send-activity-watchdog-20260815 (change_kind=repair).

Problem statement (the spec): "Verified silent stall 2026-08-15: outbound
batches b6/b7 sent EN-1446..EN-1463 (05:11-05:52Z) then hit provider
daily-quota exhaustion; the dispatch workers stayed alive, switched providers,
and backed off, but no send was recorded for about 6 hours (05:52-11:57Z)...
The runtime stayed healthy throughout, so NOTHING alerted." Every existing
watchdog signal (resume_at, stale dispatch files, lease-held cycles, dead
workers) needs a dead or wedged worker; a live-but-starved worker is
indistinguishable from normal slow sending.

Intended API contract (implementer must make every test pass by editing ONLY
`company/runtime/runner.py` and this module):

1. Send-activity liveness: `Runner._check_stalled` compares the newest send
   timestamp in the outbound sent ledger (`.spielos/state/outbound/sent.json`,
   entries carry `timestamp`, `sent_at` accepted) with each pending async
   dispatch's `started_at` and now. A dispatch pending longer than
   `SEND_STALL_GRACE_SECONDS` (default 900) whose newest ledger send is also
   older than the grace emits an `action_required` notification whose payload
   carries watchdog.signal == "stuck_goal", the goal id, run id, batch id,
   dispatch started_at, last-send time, both stall windows, and a likely-cause
   hint (quota exhaustion / provider rate limit / provider outage).

2. No false positives: fresh ledger sends do not fire; a young re-dispatch
   (started within the grace) does not fire; failed dispatch files do not fire
   (they re-dispatch via the 6.6.0 grace semantics); a missing or unreadable
   sent ledger is skipped quietly.

3. Rate limiting: a dedicated limiter (`SEND_ACTIVITY_CHECK_INTERVAL_SECONDS`,
   injectable as `send_activity_check_interval_seconds`) holds repeat emission
   within the limit window, and re-emission resumes once the limiter expires.

Tests marked `# expected after implementation` encode the new watchdog
behavior.
"""

import json
import sys
import tempfile
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
    SEND_ACTIVITY_CHECK_INTERVAL_SECONDS, SEND_STALL_GRACE_SECONDS,
    Runner, last_send_at,
)

# Test dispatches use ages inside (SEND_STALL_GRACE, DISPATCH_STALE_SECONDS)
# so ONLY the send-activity path can fire: the stale path (3600s) and the
# dead-worker recovery (this-generation files) must stay silent, keeping the
# `emitted` assertions exact.
STALLED_AGE = timedelta(minutes=40)  # 2400s: > 900s grace, < 3600s stale


class SendActivityHandler(GoalHandler):
    """One guarded action; a parked run keeps a goal around for stall checks."""

    id = "send_activity_test"

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


class SendActivityWatchdogTests(unittest.TestCase):
    """Send-activity liveness: alert on pending dispatches with no new sends."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.db = self.root / ".spielos/state/company.sqlite"
        self.runtime = Runtime(self.db, {"send_activity_test": SendActivityHandler()})
        self.runner = Runner(self.runtime)
        self.backdate_generation()

    def backdate_generation(self):
        """Simulate a long-lived daemon generation (the incident scenario).

        The dead-worker recovery removes pending files that PREDATE this
        runner generation; a dispatch started 40 minutes ago must read as a
        live worker of THIS generation (the 2026-08-15 daemon stayed up the
        whole stall), so the generation marker is backdated and the
        send-activity path — not the dead-worker path — owns the file.
        """
        self.runner._generation_started_at = (
            datetime.now(timezone.utc) - timedelta(hours=3))

    def parked_goal(self):
        goal = self.runtime.create_goal(
            name="Watchdog Send Activity", owner_id="send_activity_test",
            metric="done", operator="eq", target=True, config={})
        self.runtime.once(goal["id"])  # parks awaiting approval
        return goal

    # -- fixtures --------------------------------------------------------- #

    def write_sent_ledger(self, entries):
        """entries: list of (lead_id, datetime) send records."""
        path = self.runtime.store.path.parent / "outbound" / "sent.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({
            "sent": [{"lead_id": lid, "timestamp": ts.isoformat()}
                     for lid, ts in entries],
            "failed": [],
        }))

    def write_dispatch(self, goal_id, batch_id, started_at, status="pending"):
        d = self.runtime.store.path.parent / "outbound" / "async" / goal_id
        d.mkdir(parents=True, exist_ok=True)
        (d / f"{batch_id}.json").write_text(json.dumps(
            {"status": status, "started_at": started_at.isoformat()}))

    def pending_notifications(self, goal_id):
        return [row for row in self.runtime.store.notifications("pending")
                if row["goal_id"] == goal_id
                and row["kind"] == "action_required"]

    # -- liveness: fires with actionable payload --------------------------#

    def test_stalled_pending_dispatch_emits_stuck_goal_with_payload(self):  # expected after implementation
        goal = self.parked_goal()
        last_send = datetime.now(timezone.utc) - STALLED_AGE
        started = datetime.now(timezone.utc) - STALLED_AGE - timedelta(minutes=5)
        self.write_sent_ledger([("EN-1", last_send - timedelta(minutes=10)),
                                ("EN-2", last_send)])
        self.write_dispatch(goal["id"], "b6", started)
        emitted = self.runner._check_stalled()
        self.assertEqual(emitted, [goal["id"]])
        pending = self.pending_notifications(goal["id"])
        self.assertEqual(1, len(pending))
        self.assertEqual("action_required", pending[0]["kind"])
        payload = pending[0]["payload"]
        self.assertEqual(payload["watchdog"]["signal"], "stuck_goal")
        self.assertEqual(payload["watchdog"]["reason"],
                         "no send activity for pending async dispatch")
        # Actionable payload: goal id, run id, batch id, started_at, last send.
        self.assertEqual(payload["goal"]["id"], goal["id"])
        self.assertEqual(payload["run"]["id"], self.runtime.store.cycle(goal["id"])["id"])
        self.assertEqual(payload["watchdog"]["batch_id"], "b6")
        self.assertEqual(payload["watchdog"]["started_at"], started.isoformat())
        self.assertEqual(payload["watchdog"]["last_send_at"], last_send.isoformat())
        # Likely-cause category hint points the Director at provider limits.
        self.assertIn("quota", payload["watchdog"]["likely_cause"].lower())
        self.assertIn("rate limit", payload["watchdog"]["likely_cause"].lower())
        self.assertIn("company once " + goal["id"], payload["required_user_action"])

    # -- no false positives ----------------------------------------------- #

    def test_pending_dispatch_with_fresh_sends_does_not_fire(self):  # expected after implementation
        goal = self.parked_goal()
        started = datetime.now(timezone.utc) - STALLED_AGE
        recent = datetime.now(timezone.utc) - timedelta(minutes=2)
        self.write_sent_ledger([("EN-1", recent)])
        self.write_dispatch(goal["id"], "b6", started)
        self.assertEqual([], self.runner._check_stalled())
        self.assertEqual([], self.pending_notifications(goal["id"]))

    def test_young_redispatch_within_grace_does_not_fire(self):  # expected after implementation
        goal = self.parked_goal()
        young = datetime.now(timezone.utc) - timedelta(minutes=5)  # < 900s grace
        old = datetime.now(timezone.utc) - STALLED_AGE
        self.write_sent_ledger([("EN-1", old)])
        self.write_dispatch(goal["id"], "b6", young)
        self.assertEqual([], self.runner._check_stalled())
        self.assertEqual([], self.pending_notifications(goal["id"]))

    def test_failed_dispatch_files_do_not_fire(self):  # expected after implementation
        goal = self.parked_goal()
        old = datetime.now(timezone.utc) - STALLED_AGE
        self.write_sent_ledger([("EN-1", old)])
        self.write_dispatch(goal["id"], "b6", old, status="failed")
        self.assertEqual([], self.runner._check_stalled())
        self.assertEqual([], self.pending_notifications(goal["id"]))

    def test_missing_sent_ledger_skips_quietly(self):  # expected after implementation
        goal = self.parked_goal()
        started = datetime.now(timezone.utc) - STALLED_AGE
        self.write_dispatch(goal["id"], "b6", started)
        self.assertEqual([], self.runner._check_stalled())
        self.assertEqual([], self.pending_notifications(goal["id"]))

    # -- rate limiting ----------------------------------------------------- #

    def test_send_activity_check_is_rate_limited(self):  # expected after implementation
        goal = self.parked_goal()
        old = datetime.now(timezone.utc) - STALLED_AGE
        self.write_sent_ledger([("EN-1", old)])
        self.write_dispatch(goal["id"], "b6", old)
        # Long limiter window: the second scan must not re-emit.
        self.runner = Runner(self.runtime, send_activity_check_interval_seconds=3600)
        self.backdate_generation()
        with unittest.mock.patch.object(self.runner, "_emit_stuck_goal",
                                        wraps=self.runner._emit_stuck_goal) as emit:
            emitted = self.runner._check_stalled()
            self.assertEqual(emitted, [goal["id"]])
            self.assertEqual(1, emit.call_count)
            pending = self.pending_notifications(goal["id"])
            self.assertEqual(1, len(pending))
            created_first = pending[0]["created_at"]
            # Second scan within the window (bypass the generic scan limiter
            # only): the dedicated send-activity limiter must hold.
            self.runner._last_stall_check = 0.0
            self.assertEqual([], self.runner._check_stalled())
            self.assertEqual(1, emit.call_count,
                             "dedicated limiter must hold within the window")
            pending = self.pending_notifications(goal["id"])
            self.assertEqual(1, len(pending))
            self.assertEqual(created_first, pending[0]["created_at"],
                             "a held limiter must not re-stamp the notification")
            # Once the dedicated limiter expires, the stall re-emits.
            self.runner._last_stall_check = 0.0
            self.runner._last_send_activity_check = 0.0
            emitted = self.runner._check_stalled()
            self.assertEqual(emitted, [goal["id"]])
            self.assertEqual(2, emit.call_count)

    # -- ledger helper ------------------------------------------------------ #

    def test_last_send_at_helper(self):  # expected after implementation
        outbound = self.runtime.store.path.parent / "outbound"
        outbound.mkdir(parents=True, exist_ok=True)
        ledger = outbound / "sent.json"
        # Missing ledger and unreadable ledger -> None (skip quietly).
        self.assertIsNone(last_send_at(ledger))
        ledger.write_text("{not json")
        self.assertIsNone(last_send_at(ledger))
        # Empty sent list -> None.
        ledger.write_text(json.dumps({"sent": [], "failed": []}))
        self.assertIsNone(last_send_at(ledger))
        # `sent_at` fallback field is honored; newest entry wins.
        older = datetime.now(timezone.utc) - timedelta(hours=2)
        newer = datetime.now(timezone.utc) - timedelta(minutes=30)
        ledger.write_text(json.dumps({
            "sent": [{"lead_id": "A", "sent_at": older.isoformat()},
                     {"lead_id": "B", "timestamp": older.isoformat()},
                     {"lead_id": "C", "sent_at": newer.isoformat()}],
            "failed": [],
        }))
        self.assertEqual(last_send_at(ledger), newer)
        # Future timestamps (clock skew) yield no signal.
        future = datetime.now(timezone.utc) + timedelta(hours=1)
        ledger.write_text(json.dumps({"sent": [{"lead_id": "A",
                                                "timestamp": future.isoformat()}]}))
        self.assertIsNone(last_send_at(ledger))

    def test_constants_are_sane(self):  # expected after implementation
        self.assertGreaterEqual(SEND_STALL_GRACE_SECONDS, 900)
        self.assertGreater(SEND_ACTIVITY_CHECK_INTERVAL_SECONDS, 0)
        self.assertLess(SEND_STALL_GRACE_SECONDS, 3600,
                        "grace must sit below the stale-dispatch threshold so "
                        "the send-activity signal fires first")


if __name__ == "__main__":
    unittest.main()