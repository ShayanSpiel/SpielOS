"""Acceptance tests for goal-577aaacc7d / change-7cc84900b7 (Watchdog v2).

Problem statement (the spec): "Watchdog v2: (1) plugin still fails to load
post-6.12.0 ... (2) no external supervisor - the runner self-observes (writes
its own heartbeat, creates and delivers its own notifications); on
2026-08-15T13:40Z the daemon died and nothing detected it for over 12 minutes;
add an OS-level launchd-agent supervisor that checks heartbeat freshness from
outside, restarts the daemon on staleness, appends watchdog_incidents.jsonl,
and alerts via macOS notification. (3) no visible countdown/retry surface -
add live_status.json written each runner cycle (heartbeat ages, next digest,
goal resume countdowns, pending approvals, retry ledger), a plugin HUD ticker
line injected into the pinned session on a configurable cadence while goals
are active, and a dispatch retry ledger CLI recording attempts/next_retry_at
surfaced in the HUD."

NOTE (Director evidence 2026-08-15): the running app is opencode2 (V2,
0.0.0-next-17444), which supersedes the V1 loader premise in the problem
statement. The plugin rewrite and its contract tests (test_opencode_plugin_
contract.py) follow the V2 `{ id, setup }` contract; this suite covers the
external supervisor, the live HUD file, and the retry ledger.

Intended API contract (implementer must make every test pass by editing ONLY
files under the change task's allowed list — runtime/supervisor.py (new),
runtime/runner.py, runtime/store.py, tests/):

1. Supervisor: `company/runtime/supervisor.py --check` runs one
   external pass. With a fresh heartbeat + live PID it reports healthy and
   exits 0. With a stale heartbeat or dead PID it appends one line to
   ``watchdog_incidents.jsonl`` (signal ``runner_down``), restarts the daemon
   via RunnerService, records the attempt in ``supervisor.json``, alerts via
   macOS notification (best-effort), and exits 0 only when the restart
   brought the daemon back (1 otherwise).
2. ``alive_at`` staleness alone (with a live PID) is runner-down and forces a
   terminate-before-restart; ``last_tick`` staleness with a fresh ``alive_at``
   is loop-wedged (distinct signal).
3. A deliberately disabled runner (automation.json enabled=false) is never
   restarted or incident-logged.
4. Restart cooldown: a second pass inside the cooldown window skips the
   restart (incident action ``cooldown_skipped``).
5. Live HUD: the daemon watch loop writes ``live_status.json`` beside the
   heartbeat each cycle with the Watchdog v2 keys (heartbeat ages, next
   digest, active goals with resume countdowns, pending approvals, recent
   terminals, retry ledger, incidents tail).
6. Retry ledger: `company dispatch record` upserts (goal_id, run_id, attempt)
   preserving the FIRST error; `company dispatch list` returns newest-first.

Hermeticity: supervisor tests use temp state dirs and patched restart/terminate
actions (no real daemon, no real notifications). CLI tests run real
subprocesses against temp state/DB paths only. No live .spielos state is read
or written.
"""

import json
import os
import subprocess
import sys
import tempfile
import unittest
import unittest.mock
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from company.runtime.loop import Runtime  # noqa: E402
from company.runtime.runner import Runner  # noqa: E402
from company.runtime.store import Store  # noqa: E402
from company.runtime.supervisor import Supervisor  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]
SUPERVISOR_SCRIPT = REPO_ROOT / "company/runtime/supervisor.py"
PYTHON = sys.executable


def iso(delta_seconds: float) -> str:
    return (datetime.now(timezone.utc) + timedelta(seconds=delta_seconds)).isoformat()


def write_heartbeat(state_dir: Path, *, alive_ago: float | None, tick_ago: float | None,
                    pid: int | None = None) -> None:
    payload = {"pid": pid if pid is not None else os.getpid()}
    if alive_ago is not None:
        payload["alive_at"] = iso(-alive_ago)
    if tick_ago is not None:
        payload["last_tick"] = iso(-tick_ago)
    (state_dir / "runner.heartbeat").write_text(
        json.dumps(payload) + "\n", encoding="utf-8")


def write_pid(state_dir: Path, pid: int) -> None:
    (state_dir / "runner.pid").write_text(
        json.dumps({"pid": pid, "command": ["python3", "-B", "-m", "company"]}) + "\n",
        encoding="utf-8")


class SupervisorDetectionTests(unittest.TestCase):
    """T1: external heartbeat/PID detection, incidents, restart, cooldown."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.state_dir = self.root / ".spielos" / "state"
        self.state_dir.mkdir(parents=True)
        self.supervisor = Supervisor(
            self.root, state_dir=self.state_dir,
            db_path=self.state_dir / "company.sqlite")

    def incidents(self):
        path = self.supervisor.incidents_path
        if not path.is_file():
            return []
        return [json.loads(line)
                for line in path.read_text(encoding="utf-8").splitlines()
                if line.strip()]

    def test_fresh_heartbeat_and_live_pid_report_healthy(self):
        write_heartbeat(self.state_dir, alive_ago=2, tick_ago=1)
        write_pid(self.state_dir, os.getpid())
        result = self.supervisor.supervise_once(restart=False)
        self.assertTrue(result["healthy"])
        self.assertIsNone(result["signal"])
        self.assertEqual(result["exit_code"], 0)
        self.assertEqual(self.incidents(), [])
        self.assertFalse(self.supervisor.incidents_path.exists())

    def test_stale_alive_at_with_dead_pid_is_runner_down_and_recorded(self):
        write_heartbeat(self.state_dir, alive_ago=300, tick_ago=300)
        write_pid(self.state_dir, 999_999)  # almost certainly not alive
        result = self.supervisor.supervise_once(restart=False)
        self.assertFalse(result["healthy"])
        self.assertEqual(result["signal"], "runner_down")
        self.assertEqual(result["exit_code"], 1)
        incidents = self.incidents()
        self.assertEqual(len(incidents), 1)
        incident = incidents[0]
        self.assertEqual(incident["incident"], "runner_down")
        self.assertEqual(incident["signal"], "runner_down")
        self.assertEqual(incident["action"], "none")
        self.assertGreaterEqual(incident["heartbeat_age_seconds"], 300)
        self.assertIn("ts", incident)
        self.assertIn("pid", incident)

    def test_missing_heartbeat_with_dead_pid_is_runner_down(self):
        # A dead daemon with NO heartbeat file at all must still be caught:
        # the pid file is dead, and that alone is the signal.
        write_pid(self.state_dir, 999_999)
        result = self.supervisor.supervise_once(restart=False)
        self.assertEqual(result["signal"], "runner_down")
        self.assertEqual(result["exit_code"], 1)

    def test_fresh_alive_at_with_stale_last_tick_is_loop_wedged(self):
        write_heartbeat(self.state_dir, alive_ago=3, tick_ago=300)
        write_pid(self.state_dir, os.getpid())
        result = self.supervisor.supervise_once(restart=False)
        self.assertEqual(result["signal"], "loop_wedged")
        self.assertEqual(result["exit_code"], 1)
        incidents = self.incidents()
        self.assertEqual(len(incidents), 1)
        self.assertEqual(incidents[0]["incident"], "loop_wedged")

    def test_stale_alive_at_with_live_pid_terminates_before_restart(self):
        # Heartbeat thread silent but the process alive: hard terminate is
        # required because RunnerService.start will not replace a live process.
        write_heartbeat(self.state_dir, alive_ago=300, tick_ago=2)
        write_pid(self.state_dir, os.getpid())
        terminated = []
        with unittest.mock.patch.object(
                self.supervisor, "_terminate_pid",
                side_effect=lambda pid: terminated.append(pid) or True):
            result = self.supervisor.supervise_once(restart=False)
        self.assertEqual(result["signal"], "runner_down")
        self.assertEqual(terminated, [os.getpid()])

    def test_restart_brings_daemon_back_and_reports_recovered(self):
        write_heartbeat(self.state_dir, alive_ago=300, tick_ago=300)
        write_pid(self.state_dir, 999_999)
        with unittest.mock.patch.object(
                self.supervisor, "_restart",
                return_value={"running": True, "pid": 1234}) as restart:
            result = self.supervisor.supervise_once(restart=True, alert=False)
        restart.assert_called_once()
        self.assertTrue(result["healthy"])
        self.assertEqual(result["exit_code"], 0)
        self.assertEqual(result["signal"], "runner_down")
        incidents = self.incidents()
        self.assertEqual(incidents[0]["action"], "restarted")
        meta = json.loads(self.supervisor.meta_path.read_text())
        self.assertIn("last_restart_at", meta)
        self.assertEqual(meta["restart_count"], 1)

    def test_restart_failure_exits_nonzero_and_records_incident(self):
        write_heartbeat(self.state_dir, alive_ago=300, tick_ago=300)
        write_pid(self.state_dir, 999_999)
        with unittest.mock.patch.object(
                self.supervisor, "_restart",
                return_value={"running": False, "pid": None}):
            result = self.supervisor.supervise_once(restart=True, alert=False)
        self.assertFalse(result["healthy"])
        self.assertEqual(result["exit_code"], 1)
        self.assertEqual(self.incidents()[0]["action"], "restart_failed")

    def test_disabled_automation_stands_down_without_incident(self):
        write_heartbeat(self.state_dir, alive_ago=300, tick_ago=300)
        write_pid(self.state_dir, 999_999)
        (self.state_dir / "automation.json").write_text(
            json.dumps({"enabled": False}) + "\n", encoding="utf-8")
        with unittest.mock.patch.object(self.supervisor, "_restart") as restart:
            result = self.supervisor.supervise_once(restart=True, alert=False)
        self.assertTrue(result["healthy"])
        self.assertEqual(result["actions"], ["disabled"])
        self.assertEqual(result["exit_code"], 0)
        restart.assert_not_called()
        self.assertEqual(self.incidents(), [])

    def test_restart_cooldown_skips_second_restart(self):
        write_heartbeat(self.state_dir, alive_ago=300, tick_ago=300)
        write_pid(self.state_dir, 999_999)
        with unittest.mock.patch.object(
                self.supervisor, "_restart",
                return_value={"running": True, "pid": 1234}) as restart:
            first = self.supervisor.supervise_once(restart=True, alert=False)
            second = self.supervisor.supervise_once(restart=True, alert=False)
        self.assertEqual(first["exit_code"], 0)
        self.assertEqual(second["signal"], "runner_down")
        self.assertEqual(second["exit_code"], 1)
        self.assertEqual(restart.call_count, 1)
        self.assertEqual(self.incidents()[1]["action"], "cooldown_skipped")

    def test_incident_lines_are_jsonl_readable_by_the_runner_hud(self):
        # The runner's live HUD parses the tail of this file with json.loads
        # per line; the format must stay strict JSONL with the HUD keys.
        write_heartbeat(self.state_dir, alive_ago=300, tick_ago=300)
        write_pid(self.state_dir, 999_999)
        self.supervisor.supervise_once(restart=False)
        lines = self.supervisor.incidents_path.read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(lines), 1)
        parsed = json.loads(lines[0])  # strict: one JSON object per line
        for key in ("ts", "incident", "signal", "heartbeat_age_seconds",
                    "pid", "action", "detail"):
            self.assertIn(key, parsed)


class LiveHudSurfaceTests(unittest.TestCase):
    """T5: the daemon watch loop writes live_status.json every cycle."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.db = self.root / ".spielos/state/company.sqlite"
        self.runtime = Runtime(self.db, {})
        self.runner = Runner(self.runtime)

    def test_live_status_written_on_watch_cycles_with_hud_keys(self):
        with unittest.mock.patch("company.runtime.runner.time.sleep"):
            list(self.runner.watch(max_ticks=2))
        path = self.runner.live_status_path()
        self.assertTrue(path.is_file(),
                        "watch must write live_status.json each cycle")
        payload = json.loads(path.read_text(encoding="utf-8"))
        for key in ("ts", "heartbeat", "next_digest_at", "active_goals",
                    "pending_approvals", "recent_terminals", "retry_ledger",
                    "incidents_tail"):
            self.assertIn(key, payload, "live HUD missing key %s" % key)
        self.assertIsInstance(payload["active_goals"], list)
        self.assertIsInstance(payload["retry_ledger"], list)
        # The HUD heartbeat mirrors the heartbeat file: pid/last_tick/cycle
        # are written per watch cycle; the `alive_at` PROCESS signal is
        # stamped by the dedicated heartbeat thread on its own 10s cadence
        # (covered by the heartbeat-thread tests in test_runner_watchdog).
        self.assertIn("pid", payload["heartbeat"])
        self.assertIn("last_tick", payload["heartbeat"])
        self.assertIn("cycle", payload["heartbeat"])

    def test_tick_alone_does_not_write_live_status(self):
        # Standalone tick() must never refresh the HUD (same rule as the
        # heartbeat) or a fallback tick would mask a dead daemon's stale
        # surface.
        self.runner.tick()
        self.assertFalse(self.runner.live_status_path().exists())


class DispatchRetryLedgerTests(unittest.TestCase):
    """T6: retry ledger upsert + newest-first reads (Watchdog v2)."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db = Path(self.temp.name) / "company.sqlite"
        self.store = Store(self.db)

    def test_record_upserts_and_preserves_first_error(self):
        first = self.store.record_dispatch_retry(
            "goal-a", "run-1", 1, "failed",
            first_error="provider 503", next_retry_at="2026-08-15T20:00:00+00:00")
        self.assertEqual(first["status"], "failed")
        self.assertEqual(first["first_error"], "provider 503")
        second = self.store.record_dispatch_retry(
            "goal-a", "run-1", 2, "retrying",
            first_error="provider 503 (retry)", next_retry_at=None)
        self.assertEqual(second["first_error"], "provider 503",
                         "first_error must be preserved from the first attempt")
        self.assertEqual(second["status"], "retrying")
        rows = self.store.dispatch_retries(limit=10)
        self.assertEqual([row["attempt"] for row in rows], [2, 1])
        self.assertEqual(rows[0]["goal_id"], "goal-a")

    def test_list_scoped_to_goal(self):
        self.store.record_dispatch_retry("goal-a", "run-1", 1, "failed")
        self.store.record_dispatch_retry("goal-b", "run-2", 1, "succeeded")
        rows = self.store.dispatch_retries(goal_id="goal-b")
        self.assertEqual([row["goal_id"] for row in rows], ["goal-b"])

    def test_dispatch_cli_record_and_list_roundtrip(self):
        # Real CLI against a temp DB: `company dispatch record` then `list`.
        env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1", "PYTHONPATH": ".."}
        record = subprocess.run(
            [PYTHON, "-B", "-m", "company", "--db", str(self.db),
             "dispatch", "record", "goal-c", "--run", "run-3", "--attempt", "1",
             "--status", "failed", "--error", "quota exhausted",
             "--next-retry-at", "2026-08-15T21:00:00+00:00", "--json"],
            cwd=str(REPO_ROOT), env=env, capture_output=True, text=True, timeout=120)
        self.assertEqual(record.returncode, 0, record.stderr)
        listed = subprocess.run(
            [PYTHON, "-B", "-m", "company", "--db", str(self.db),
             "dispatch", "list", "--goal", "goal-c", "--json"],
            cwd=str(REPO_ROOT), env=env, capture_output=True, text=True, timeout=120)
        self.assertEqual(listed.returncode, 0, listed.stderr)
        rows = json.loads(listed.stdout)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["goal_id"], "goal-c")
        self.assertEqual(rows[0]["attempt"], 1)
        self.assertEqual(rows[0]["status"], "failed")
        self.assertEqual(rows[0]["first_error"], "quota exhausted")


class SupervisorCliTests(unittest.TestCase):
    """T1 CLI: `python3 -B supervisor.py --check` exits 0 healthy / 1 down."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.state_dir = Path(self.temp.name) / ".spielos" / "state"
        self.state_dir.mkdir(parents=True)

    def run_check(self, *extra):
        return subprocess.run(
            [PYTHON, "-B", str(SUPERVISOR_SCRIPT), "--check", "--no-restart",
             "--no-alert", "--json", "--project-root", str(REPO_ROOT),
             "--state-dir", str(self.state_dir), *extra],
            cwd=str(REPO_ROOT), capture_output=True, text=True, timeout=120)

    def test_check_exits_zero_when_runner_healthy(self):
        write_heartbeat(self.state_dir, alive_ago=2, tick_ago=1)
        write_pid(self.state_dir, os.getpid())
        completed = self.run_check()
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        result = json.loads(completed.stdout)
        self.assertTrue(result["healthy"])
        self.assertIsNone(result["signal"])

    def test_check_exits_one_and_reports_runner_down(self):
        write_heartbeat(self.state_dir, alive_ago=300, tick_ago=300)
        write_pid(self.state_dir, 999_999)
        completed = self.run_check()
        self.assertEqual(completed.returncode, 1)
        result = json.loads(completed.stdout)
        self.assertEqual(result["signal"], "runner_down")
        # The incident was recorded next to the heartbeat.
        incidents_path = self.state_dir / "watchdog_incidents.jsonl"
        self.assertTrue(incidents_path.is_file())
        incident = json.loads(incidents_path.read_text().splitlines()[0])
        self.assertEqual(incident["incident"], "runner_down")
        self.assertEqual(incident["action"], "none")


if __name__ == "__main__":
    unittest.main()
