"""Acceptance tests for goal-runner-persistence-20260815 (change_kind=repair).

Problem statement (the spec): "Runner process dies on reboot, no persistent
state, no notifications, watcher interval fixed at 2s with no retry-on-error
capability."

Intended API contract (implementer must make every test pass by editing ONLY
`company/runtime/service.py`, `company/runtime/notifications.py`,
`company/__main__.py`):

1. Persistent runner state + reboot recovery: all company state (goals, cycles,
   runs, approvals, notifications) and the runner switch (automation.json) live
   under `.spielos/state/` and survive process death; a fresh RunnerService on
   the same project root recovers the last known state. A stale `runner.pid`
   from a dead process must never report `running`, and `start()` must replace
   it with fresh metadata (reboot cleanup).

2. Notifications remain pending across runner ticks. Only a host that actually
   surfaces exact notification ids may acknowledge them.

3. Watcher: `Runner.watch(interval_seconds=..., goal_id=..., max_ticks=...)`
   keeps a configurable interval (not fixed at 2s) and stays bounded; the CLI
   `runner watch --interval X --max-ticks N` surfaces it. Retry-on-error for
   transient provider failures is owned by goal-transient-retry-20260815 and
   tested in company.tests.test_transient_retry.

Tests marked `# passes now` run green against the current runtime and pin the
existing contract. Tests marked `# expected after implementation` encode the
new behavior and fail/skip until the implementation above lands (missing
modules are reported as skips, never as import errors).
"""

import io
import json
import sys
import tempfile
import unittest
import unittest.mock
from contextlib import redirect_stdout
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from company.__main__ import main  # noqa: E402
from company.runtime.loop import Runtime  # noqa: E402
from company.runtime.models import (  # noqa: E402
    GoalHandler, GoalStatus, RunStatus, Stage, StageResult,
)
from company.runtime.runner import Runner  # noqa: E402
from company.runtime.service import RunnerService  # noqa: E402


class RestartHandler(GoalHandler):
    """One guarded action, so a parked run proves persisted state survived."""

    id = "restart_persist_test"

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
        validity = (ctx.cycle.get("run") or {}).get("evidence_validity") or "business"
        return StageResult(
            "goal_check", {"done": True}, RunStatus.IDLE,
            goal_status=GoalStatus.ACHIEVED,
            evaluation={"verdict": "goal_met", "goal_met": True,
                        "metrics": {ctx.goal.metric: True}, "validity": validity})


class RunnerPersistenceTests(unittest.TestCase):
    """Reboot recovery: state files + a fresh Runtime/RunnerService instance."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.db = self.root / ".spielos/state/company.sqlite"

    def runtime(self):
        return Runtime(self.db, {"restart_persist_test": RestartHandler()})

    def test_goal_run_and_approval_state_survive_restart(self):  # passes now
        first = self.runtime()
        goal = first.create_goal(name="Restart", owner_id="restart_persist_test",
                                 metric="done", operator="eq", target=True, config={})
        parked = first.once(goal["id"])
        self.assertEqual(parked["cycle"]["run_status"], "awaiting_approval")
        cycle_id = parked["cycle"]["id"]
        first.approve(goal["id"])
        # "Reboot": a brand-new Runtime on the same database, no memory of the
        # prior process. Cycle identity must be intact and resumable.
        second = self.runtime()
        state = second.status(goal["id"])
        self.assertEqual(state["cycle"]["id"], cycle_id)
        self.assertEqual(state["cycle"]["run_status"], "awaiting_approval")
        self.assertEqual(state["cycle"]["stage"], "ACT")
        done = second.once(goal["id"])
        self.assertEqual(done["goal"]["goal_status"], "achieved")

    def test_automation_switch_survives_service_restart(self):  # passes now
        service = RunnerService(self.root, self.db)
        self.assertTrue(service.enable()["enabled"])
        self.assertFalse(service.stop()["enabled"])  # persists automation.json
        # Reboot: a fresh service instance reads the same switch file.
        reboot = RunnerService(self.root, self.db)
        self.assertFalse(reboot.status()["enabled"])
        self.assertTrue(reboot.enable()["enabled"])
        self.assertTrue(RunnerService(self.root, self.db).status()["enabled"])

    def test_stale_pid_from_dead_process_is_not_running(self):  # passes now
        state_dir = self.root / ".spielos/state"
        state_dir.mkdir(parents=True, exist_ok=True)
        (state_dir / "runner.pid").write_text(
            json.dumps({"pid": 424242, "command": ["-m", "company"],
                        "db_path": str(self.db)}) + "\n")
        status = RunnerService(self.root, self.db).status()
        self.assertFalse(status["running"])
        self.assertIsNone(status["pid"])

    def test_start_recovers_stale_pid_and_persists_new_state(self):  # passes now
        service = RunnerService(self.root, self.db)
        state_dir = self.root / ".spielos/state"
        state_dir.mkdir(parents=True, exist_ok=True)
        (state_dir / "runner.pid").write_text(
            json.dumps({"pid": 424242, "command": [], "db_path": str(self.db)}) + "\n")
        with unittest.mock.patch(
                "company.runtime.service.subprocess.Popen",
                return_value=SimpleNamespace(pid=4242)), \
             unittest.mock.patch(
                "company.runtime.service._alive",
                side_effect=lambda pid: pid == 4242):
            status = service.start(interval=0.5)
            self.assertTrue(status["enabled"])
            self.assertTrue(status["running"], "the fresh pid must be live")
            self.assertEqual(status["pid"], 4242)
            metadata = json.loads((state_dir / "runner.pid").read_text())
            self.assertEqual(metadata["pid"], 4242,
                             "start() must replace the stale pid file")
            self.assertEqual(metadata["db_path"], str(self.db))
            # A second service instance (simulated reboot) sees the same state.
            again = RunnerService(self.root, self.db).status()
            self.assertTrue(again["running"])
            self.assertEqual(again["pid"], 4242)
            self.assertEqual(again["db_path"], str(self.db))

    def test_watcher_interval_is_configurable_and_bounded(self):  # passes now
        runtime = self.runtime()
        goal = runtime.create_goal(name="Watch", owner_id="restart_persist_test",
                                   metric="done", operator="eq", target=True, config={})
        # Park the goal so ticks have something to report; the watcher must
        # honor a non-default interval and max_ticks without hanging.
        runtime.once(goal["id"])
        sleeps = []
        with unittest.mock.patch(
                "company.runtime.runner.time.sleep",
                side_effect=lambda seconds: sleeps.append(seconds)):
            results = list(Runner(runtime).watch(
                interval_seconds=0.25, goal_id=goal["id"], max_ticks=3))
        self.assertLessEqual(len(results), 3)
        self.assertTrue(all(seconds == 0.25 for seconds in sleeps),
                        "watch must sleep exactly the configured interval")
        self.assertGreaterEqual(len(sleeps), 1)


class RunnerNotificationTests(unittest.TestCase):
    """Notifications: persisted by the runtime; delivered by the runner."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.runtime = Runtime(Path(self.temp.name) / "state.sqlite",
                               {"restart_persist_test": RestartHandler()})

    def capture(self, *arguments):
        output = io.StringIO()
        with redirect_stdout(output):
            code = main(["--db", str(self.runtime.store.path), *arguments])
        self.assertEqual(0, code)
        return output.getvalue()

    def parked_goal(self):
        goal = self.runtime.create_goal(
            name="Notify", owner_id="restart_persist_test",
            metric="done", operator="eq", target=True, config={})
        self.runtime.once(goal["id"])  # parks → approval_required notification
        return goal

    def test_runtime_persists_pending_notification(self):  # passes now
        goal = self.parked_goal()
        pending = [row for row in self.runtime.store.notifications("pending")
                   if row["goal_id"] == goal["id"]]
        self.assertEqual(1, len(pending))
        self.assertEqual("approval_required", pending[0]["kind"])
        # Approving resolves the actionable notification and the run completes.
        self.runtime.approve(goal["id"])
        done = self.runtime.once(goal["id"])
        self.assertEqual(done["goal"]["goal_status"], "achieved")
        pending = [row for row in self.runtime.store.notifications("pending")
                   if row["goal_id"] == goal["id"]
                   and row["kind"] == "approval_required"]
        self.assertEqual([], pending,
                         "the actionable approval notification must be resolved")

    def test_notifications_cli_lists_pending(self):  # passes now
        goal = self.parked_goal()
        output = self.capture("notifications", "list", "--status", "pending")
        self.assertIn(goal["id"], output)
        self.assertIn("approval_required", output)

    def test_runner_tick_reports_pending_notifications(self):  # passes now
        goal = self.parked_goal()
        result = Runner(self.runtime).tick(goal["id"])
        self.assertTrue(result["pending_notifications"])

    def test_notifications_require_an_exact_host_surface_receipt(self):
        try:
            from company.runtime import notifications
        except ImportError as exc:
            raise unittest.SkipTest(
                "company.runtime.notifications does not exist yet: %s" % exc)
        deliver = getattr(notifications, "deliver_pending", None)
        if deliver is None:
            self.fail("company.runtime.notifications must expose deliver_pending("
                      "store, limit=100) -> int")
        goal = self.parked_goal()
        count = deliver(self.runtime.store)
        self.assertGreaterEqual(int(count), 1)
        remaining = [row for row in self.runtime.store.notifications("pending")
                     if row["goal_id"] == goal["id"]
                     and row["kind"] == "approval_required"]
        self.assertEqual(1, len(remaining),
                         "discovery by the runner must not acknowledge unseen attention")
        deliver(self.runtime.store, surfaced_ids=[remaining[0]["id"]])
        remaining = [row for row in self.runtime.store.notifications("pending")
                     if row["goal_id"] == goal["id"]
                     and row["kind"] == "approval_required"]
        self.assertEqual([], remaining)


if __name__ == "__main__":
    unittest.main()
