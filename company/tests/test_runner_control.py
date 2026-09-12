"""Runner control semantics (audit ledger 5.1 / 5.2).

5.1: the automation switch is real — `runner stop` disables it and the
watch loop exits cleanly; `runner enable` re-arms it and the loop runs.
5.2: a runner child that dies immediately reports dead-on-arrival with
the log tail instead of a receipt claiming a running process.
"""

from __future__ import annotations

import json
import os
import tempfile
import time
import unittest
from pathlib import Path

from company.runtime.service import RunnerService, automation_enabled
from company.tests.test_update_preservation import (  # noqa: E402
    REAL_TEMPLATES,
    _TemplateEnv,
)


class AutomationSwitchTests(unittest.TestCase):
    """5.1 — the flag is a real control the loop honors."""

    def _service(self, root: Path, db: Path) -> RunnerService:
        return RunnerService(root, db)

    def test_stop_disables_and_enable_rearms(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            db = base / ".spielos" / "state" / "company.sqlite"
            db.parent.mkdir(parents=True, exist_ok=True)
            db.write_bytes(b"")  # placeholder; service never opens it here
            service = self._service(base, db)
            self.assertTrue(automation_enabled(service.state_dir))
            service._set_enabled(False)
            self.assertFalse(automation_enabled(service.state_dir))
            service._set_enabled(True)
            self.assertTrue(automation_enabled(service.state_dir))

    def test_watch_loop_exits_when_switched_off(self):
        """The watch generator must end, not sleep forever, once the
        automation switch is off."""
        from company.commands.goal_runtime import CleanCommandRuntime

        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            db = base / "company.sqlite"
            runtime = CleanCommandRuntime(db)
            state_dir = db.parent
            # Switch automation off BEFORE the loop starts.
            (state_dir / "automation.json").write_text(
                json.dumps({"enabled": False}) + "\n")
            ticks = 0
            for _ in runtime.watch(interval_seconds=0.01, max_ticks=None):
                ticks += 1
                self.fail("watch must yield nothing when disabled")
            self.assertEqual(ticks, 0, "a disabled switch means no ticks")

    def test_watch_loop_stops_mid_run_when_switched_off(self):
        """A loop already running ends at the next iteration after the
        switch flips off."""
        from company.commands.goal_runtime import CleanCommandRuntime

        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            db = base / "company.sqlite"
            runtime = CleanCommandRuntime(db)
            state_dir = db.parent
            # Enabled now; flip off after the first tick.
            (state_dir / "automation.json").write_text(
                json.dumps({"enabled": True}) + "\n")
            seen = 0
            for _ in runtime.watch(interval_seconds=0.01, max_ticks=None):
                seen += 1
                if seen == 1:
                    (state_dir / "automation.json").write_text(
                        json.dumps({"enabled": False}) + "\n")
            self.assertEqual(seen, 1, "the second iteration must not run")

    def test_runner_stop_enable_start_cycle_end_to_end(self):
        """Full lifecycle via the service on a real home-shaped tree:
        start -> running; stop -> not running, switch off, pid cleared;
        enable -> switch on; start -> running again."""
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            home = base / "home"
            # Scaffold a real vendored home so the spawned child finds
            # the spine under <home>/.agents exactly like production.
            import shutil as _shutil
            from company.runtime.bootstrap import scaffold

            with _TemplateEnv(REAL_TEMPLATES) as _:
                receipt = scaffold(home)
            db = home / ".spielos" / "state" / "company.sqlite"
            from company.commands.goal_runtime import CleanCommandRuntime

            CleanCommandRuntime(db).company_snapshot()
            service = self._service(home, db)

            started = service.start(interval=0.05)
            self.assertFalse("error" in started, started.get("error", ""))
            self.assertTrue(started["running"])
            self.assertTrue(automation_enabled(service.state_dir))

            time.sleep(0.3)  # let the loop tick at least once
            stopped = service.stop()
            self.assertFalse(stopped["running"])
            self.assertFalse(stopped["enabled"])
            self.assertFalse(service.pid_path.exists())
            time.sleep(0.2)  # the SIGTERM'd child reaps

            enabled = service.enable()
            self.assertTrue(enabled["enabled"])
            restarted = service.start(interval=0.05)
            self.assertFalse("error" in restarted, restarted.get("error", ""))
            self.assertTrue(restarted["running"])
            self.assertTrue(service.stop()["running"] is False)


class DeadOnArrivalTests(unittest.TestCase):
    """5.2 — dead children report honestly."""

    def test_start_reports_dead_on_arrival_with_log_tail(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            # A poisoned project root: PYTHONPATH points at .agents
            # which does not exist, so the child dies immediately.
            db = base / ".spielos" / "state" / "company.sqlite"
            db.parent.mkdir(parents=True, exist_ok=True)
            db.write_bytes(b"")
            service = RunnerService(base, db)
            receipt = service.start(interval=0.05)
            self.assertIn("error", receipt,
                          "a dead child must be reported, not claimed running")
            self.assertIn("exited immediately", receipt["error"])
            self.assertIn("last log lines", receipt["error"])
            self.assertFalse(receipt["running"])
            self.assertFalse(service.pid_path.exists(),
                             "a dead-on-arrival child leaves no pid file")


if __name__ == "__main__":
    unittest.main()
