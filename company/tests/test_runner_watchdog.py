"""Regression tests for goal-runner-watchdog-supervision-20260815 (change_kind=repair).

Problem statement (the spec): "The runner watch loop cannot supervise itself.
When the runner daemon crashed on 2026-08-15 about 03:05Z (TypeError in
loop._persist) nothing alerted the owner for about 34 minutes; goals parked
mid-run (b6 and b7 async dispatch) sat unrecovered until the Director manually
inspected, and the owner had to ask whether the run was stuck. The watcher was
tasked with replacing the human observer."

Intended API contract (implementer must make every test pass by editing ONLY
`company/runtime/runner.py` and this module):

1. Heartbeat: `Runner.watch` stamps `.spielos/state/runner.heartbeat`
   (JSON with pid/last_tick/cycle) at the start of every watch cycle;
   `Runner.heartbeat_age()` reports its age and `Runner.runner_down()` (or the
   module-level `runner_down_signal`) yields the runner_down payload once the
   age exceeds the threshold. Standalone `Runner.tick()` calls must NOT refresh
   the heartbeat (a fallback tick must not mask a dead daemon).

2. Stall detection: `Runner._check_stalled` flags (a) an active goal whose
   `waiting` cycle has a `resume_at` in the past with no advancement since
   (cycle `updated_at` not after `resume_at`, past the grace window),
   (b) an active goal whose lease is held past the grace with no cycle
   advancement (wedged tick), and (c) an async dispatch file under
   `.spielos/state/outbound/async/` that is pending with no live worker
   (started before this runner generation, past the dead-worker grace) —
   removed for re-dispatch, or pending beyond the stale threshold — and
   emits an `action_required` notification whose payload carries
   `watchdog.signal == "stuck_goal"` plus the goal id, run id, why, and
   what to do.

3. Dead-daemon signal: a stale heartbeat age produces the `runner_down` signal
   via `runner_down_signal` / `Runner.runner_down`, and the watch loop emits a
   best-effort `runner_down` notification (kind `action_required`) before
   re-raising when a cycle fails.

Tests marked `# passes now` pin the current contract; `# expected after
implementation` encode the new watchdog behavior.
"""

import json
import sys
import tempfile
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
    HEARTBEAT_FILENAME, Runner, heartbeat_age, runner_down_signal,
)


class WatchdogHandler(GoalHandler):
    """One guarded action; a parked run keeps a goal around for stall checks."""

    id = "watchdog_test"

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


class WatchdogTests(unittest.TestCase):
    """Heartbeat + stall detection + runner_down signal."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.db = self.root / ".spielos/state/company.sqlite"
        self.runtime = Runtime(self.db, {"watchdog_test": WatchdogHandler()})
        self.runner = Runner(self.runtime)

    @property
    def heartbeat_path(self) -> Path:
        return self.runner.heartbeat_path()

    def parked_goal(self):
        goal = self.runtime.create_goal(
            name="Watchdog", owner_id="watchdog_test",
            metric="done", operator="eq", target=True, config={})
        self.runtime.once(goal["id"])  # parks awaiting approval
        return goal

    def backdate_cycle(self, goal_id: str, *, run_status: str, resume_at: datetime):
        """Force a cycle state with both resume_at and updated_at in the past."""
        cycle = self.runtime.store.cycle(goal_id)
        past = resume_at.isoformat()
        with self.runtime.store.connect() as con:
            con.execute(
                "UPDATE cycles SET run_status=?, resume_at=?, updated_at=? WHERE id=?",
                (run_status, past, past, cycle["id"]))
        return self.runtime.store.cycle(goal_id)

    # ------------------------------------------------------------------ #
    # Heartbeat                                                           #
    # ------------------------------------------------------------------ #

    def test_heartbeat_written_on_watch_cycle_and_age_readable(self):  # expected after implementation
        goal = self.parked_goal()
        with unittest.mock.patch("company.runtime.runner.time.sleep"):
            list(self.runner.watch(goal_id=goal["id"], max_ticks=3))
        self.assertTrue(
            self.heartbeat_path.is_file(),
            "watch must stamp the heartbeat file each cycle")
        data = json.loads(self.heartbeat_path.read_text())
        self.assertIn("pid", data)
        self.assertIn("last_tick", data)
        self.assertGreaterEqual(int(data["cycle"]), 3,
                                "heartbeat must be stamped on every watch cycle")
        age = self.runner.heartbeat_age()
        self.assertIsNotNone(age)
        self.assertLess(age, 60)
        self.assertIsNone(self.runner.runner_down(max_age_seconds=60),
                          "a fresh heartbeat must not produce the runner_down signal")

    def test_tick_alone_does_not_refresh_heartbeat(self):  # expected after implementation
        # A fallback `company runner tick` (plugin covers for a dead daemon)
        # must never mask a dead daemon by refreshing its heartbeat.
        goal = self.parked_goal()
        self.heartbeat_path.parent.mkdir(parents=True, exist_ok=True)
        old = {"pid": 1, "last_tick": "2026-08-15T00:00:00+00:00", "cycle": 1}
        self.heartbeat_path.write_text(json.dumps(old))
        self.runner.tick(goal["id"])
        data = json.loads(self.heartbeat_path.read_text())
        self.assertEqual(data["last_tick"], old["last_tick"])
        self.assertEqual(data["cycle"], 1)

    def test_stale_heartbeat_yields_runner_down_signal(self):  # expected after implementation
        self.heartbeat_path.parent.mkdir(parents=True, exist_ok=True)
        stale = datetime.now(timezone.utc) - timedelta(seconds=600)
        self.heartbeat_path.write_text(json.dumps({
            "pid": 1, "last_tick": stale.isoformat(), "cycle": 1}))
        signal = runner_down_signal(self.heartbeat_path, max_age_seconds=60)
        self.assertIsNotNone(signal)
        self.assertEqual(signal["signal"], "runner_down")
        self.assertGreaterEqual(signal["heartbeat_age_seconds"], 600)
        self.assertEqual(self.runner.heartbeat_age() >= 600, True)
        # A missing heartbeat file is NOT a runner_down signal on its own.
        self.heartbeat_path.unlink()
        self.assertIsNone(runner_down_signal(self.heartbeat_path, max_age_seconds=60))
        self.assertIsNone(heartbeat_age(self.heartbeat_path))

    # ------------------------------------------------------------------ #
    # Stall detection                                                     #
    # ------------------------------------------------------------------ #

    def test_stalled_resume_at_goal_emits_stuck_goal_notification(self):  # expected after implementation
        goal = self.parked_goal()
        due = datetime.now(timezone.utc) - timedelta(hours=2)
        self.backdate_cycle(goal["id"], run_status="waiting", resume_at=due)
        emitted = self.runner._check_stalled()
        self.assertEqual(emitted, [goal["id"]])
        pending = [row for row in self.runtime.store.notifications("pending")
                   if row["goal_id"] == goal["id"]
                   and row["kind"] == "action_required"]
        self.assertEqual(1, len(pending))
        self.assertEqual("action_required", pending[0]["kind"])
        payload = pending[0]["payload"]
        self.assertEqual(payload["watchdog"]["signal"], "stuck_goal")
        self.assertEqual(payload["watchdog"]["reason"],
                         "resume_at passed without advancement")
        # Actionable payload: goal id, run id, why, what to do.
        self.assertEqual(payload["goal"]["id"], goal["id"])
        self.assertEqual(payload["run"]["id"], self.runtime.store.cycle(goal["id"])["id"])
        self.assertIn("resume_at", payload["watchdog"])
        self.assertIn("company once " + goal["id"], payload["required_user_action"])

    def test_future_resume_at_is_not_stalled(self):  # expected after implementation
        goal = self.parked_goal()
        future = datetime.now(timezone.utc) + timedelta(hours=2)
        self.backdate_cycle(goal["id"], run_status="waiting", resume_at=future)
        self.assertEqual([], self.runner._check_stalled())

    def test_cycle_advanced_after_resume_at_is_not_stalled(self):  # expected after implementation
        goal = self.parked_goal()
        due = datetime.now(timezone.utc) - timedelta(hours=2)
        cycle = self.backdate_cycle(goal["id"], run_status="waiting", resume_at=due)
        # The cycle was touched again after resume_at passed (advanced): not stalled.
        later = (datetime.now(timezone.utc) - timedelta(minutes=30)).isoformat()
        with self.runtime.store.connect() as con:
            con.execute("UPDATE cycles SET updated_at=? WHERE id=?",
                        (later, cycle["id"]))
        self.assertEqual([], self.runner._check_stalled())

    def test_dead_worker_pending_dispatch_recovered_and_emitted(self):  # expected after implementation
        # Wedge hardening (2026-08-15): a pending dispatch older than the
        # dead-worker grace AND older than this runner generation has no live
        # worker thread — it is recovered immediately (removed for
        # re-dispatch) instead of parking until the 1-hour stale threshold.
        # The removal is exactly the manual cleanup from the incident, made
        # automatic; the notification explains why the file is gone.
        goal = self.parked_goal()
        dispatch_dir = self.runtime.store.path.parent / "outbound" / "async" / goal["id"]
        dispatch_dir.mkdir(parents=True, exist_ok=True)
        started = datetime.now(timezone.utc) - timedelta(hours=2)
        (dispatch_dir / "b6.json").write_text(json.dumps({
            "status": "pending", "started_at": started.isoformat()}))
        emitted = self.runner._check_stalled()
        self.assertEqual(emitted, [goal["id"]])
        self.assertFalse(
            (dispatch_dir / "b6.json").exists(),
            "dead-worker pending dispatch must be removed for re-dispatch")
        pending = [row for row in self.runtime.store.notifications("pending")
                   if row["goal_id"] == goal["id"]
                   and row["kind"] == "action_required"]
        self.assertEqual(1, len(pending))
        payload = pending[0]["payload"]
        self.assertEqual(payload["watchdog"]["signal"], "stuck_goal")
        self.assertEqual(payload["watchdog"]["reason"],
                         "async dispatch worker died; pending file removed for re-dispatch")
        self.assertEqual(payload["watchdog"]["batch_id"], "b6")
        self.assertIn("company once " + goal["id"], payload["required_user_action"])

    def test_fresh_pending_dispatch_is_not_stalled(self):  # expected after implementation
        goal = self.parked_goal()
        dispatch_dir = self.runtime.store.path.parent / "outbound" / "async" / goal["id"]
        dispatch_dir.mkdir(parents=True, exist_ok=True)
        (dispatch_dir / "b7.json").write_text(json.dumps({
            "status": "pending",
            "started_at": datetime.now(timezone.utc).isoformat()}))
        self.assertEqual([], self.runner._check_stalled())

    # ------------------------------------------------------------------ #
    # Watch loop death                                                    #
    # ------------------------------------------------------------------ #

    def test_watch_loop_death_emits_runner_down_notification(self):  # expected after implementation
        goal = self.parked_goal()

        def boom(goal_id):
            self.runner._active_goal_id = goal["id"]
            raise RuntimeError("watch loop exploded")

        with unittest.mock.patch.object(self.runner, "tick", side_effect=boom):
            with self.assertRaises(RuntimeError):
                list(self.runner.watch(max_ticks=1))
        pending = [row for row in self.runtime.store.notifications("pending")
                   if row["goal_id"] == goal["id"]
                   and row["kind"] == "action_required"]
        self.assertEqual(1, len(pending))
        self.assertEqual("action_required", pending[0]["kind"])
        payload = pending[0]["payload"]
        self.assertEqual(payload["watchdog"]["signal"], "runner_down")
        self.assertEqual(payload["watchdog"]["error"]["type"], "RuntimeError")
        self.assertIn("company runner start", payload["required_user_action"])
        # The failure must propagate exactly as before (daemon exits).
        self.assertTrue(self.heartbeat_path.is_file(),
                        "the heartbeat must be stamped before the failing cycle")


if __name__ == "__main__":
    unittest.main()
