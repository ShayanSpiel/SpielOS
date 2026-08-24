"""Fix-wave regression tests (audit docs/HARNESS_AUDIT_2026-08-23.md §3).

Focused coverage for the bounded fix wave of 2026-08-23:

* bug 2  — supervisor restart bookkeeping records the truthful action
* bug 3  — continuation creation is atomic/idempotent on UNIQUE(goal_id, sequence)
* bug 8  — terminal goal status is written AFTER its justifying evidence
* bug 12 — foreground once/next/retry/approve honor the stop switch
* bug 13 — notification upsert preserves delivered_at unless explicitly reopened

Item 17 (website decoupling / transition hook) lives in
``test_runtime.TransitionHookTests`` and ``TransitionHookBoundTests``.
"""

from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from company.runtime.loop import Runtime
from company.runtime.models import GoalStatus, RunStatus, StageResult
from company.runtime.service import RunnerService
from company.runtime.store import Store
from company.runtime.supervisor import Supervisor
from company.tests.test_runtime import ImmediateHandler


class AchievingWithEvidenceHandler(ImmediateHandler):
    """Like ImmediateHandler but attaches explicit evidence at EVALUATE."""

    def evaluate(self, ctx, action_result):
        result = super().evaluate(ctx, action_result)
        result.evidence = [{"kind": "final_proof", "source": "fix_wave_test",
                            "payload": {"proof": True}}]
        return result


def write_pid(state_dir: Path, pid: int) -> None:
    state_dir.mkdir(parents=True, exist_ok=True)
    (state_dir / "runner.pid").write_text(
        json.dumps({"pid": pid, "command": []}) + "\n", encoding="utf-8")


def heartbeat_stale(state_dir: Path) -> None:
    stamp = datetime.now(timezone.utc).isoformat()
    state_dir.mkdir(parents=True, exist_ok=True)
    (state_dir / "runner.heartbeat").write_text(
        json.dumps({"pid": 999_999, "alive_at": stamp, "last_tick": stamp}) + "\n",
        encoding="utf-8")


class SupervisorTruthfulRestartTests(unittest.TestCase):
    """Bug 2: supervisor.json must record what ACTUALLY happened."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.state_dir = self.root / ".spielos" / "state"
        self.supervisor = Supervisor(self.root)

    def incidents(self):
        if not self.supervisor.incidents_path.exists():
            return []
        return [json.loads(line) for line in
                self.supervisor.incidents_path.read_text(encoding="utf-8").splitlines()]

    def test_failed_restart_is_recorded_as_restart_failed_not_restarted(self):
        heartbeat_stale(self.state_dir)
        write_pid(self.state_dir, 999_999)
        with patch.object(self.supervisor, "_restart",
                          return_value={"running": False, "pid": None}):
            result = self.supervisor.supervise_once(restart=True, alert=False)
        self.assertEqual("restart_failed", result["incident"]["action"])
        meta = json.loads(self.supervisor.meta_path.read_text())
        self.assertEqual("restart_failed", meta["last_action"])
        # The cooldown still advances on a failed attempt (crash-loop guard).
        self.assertIn("last_restart_at", meta)
        self.assertEqual(meta["restart_count"], 1)
        self.assertFalse(result["healthy"])

    def test_successful_restart_records_restarted_after_checking_status(self):
        heartbeat_stale(self.state_dir)
        write_pid(self.state_dir, 999_999)
        with patch.object(self.supervisor, "_restart",
                          return_value={"running": True, "pid": 1234}):
            result = self.supervisor.supervise_once(restart=True, alert=False)
        self.assertEqual("restarted", result["incident"]["action"])
        meta = json.loads(self.supervisor.meta_path.read_text())
        self.assertEqual("restarted", meta["last_action"])
        self.assertTrue(result["healthy"])

    def test_raising_restart_also_records_restart_failed(self):
        heartbeat_stale(self.state_dir)
        write_pid(self.state_dir, 999_999)
        with patch.object(self.supervisor, "_restart",
                          side_effect=RuntimeError("spawn failed")):
            result = self.supervisor.supervise_once(restart=True, alert=False)
        self.assertEqual("restart_failed", result["incident"]["action"])
        meta = json.loads(self.supervisor.meta_path.read_text())
        self.assertEqual("restart_failed", meta["last_action"])


class AtomicContinuationTests(unittest.TestCase):
    """Bug 3: losing a concurrent continuation race is an idempotent no-op."""

    @staticmethod
    def _insert_concurrent_winner(db_path, goal_id: str, sequence: int) -> str:
        """Simulate a concurrent continuation winner: one cycle + one run."""
        import uuid
        winner_id = f"run-{uuid.uuid4().hex[:10]}"
        stamp = datetime.now(timezone.utc).isoformat()
        with sqlite3.connect(str(db_path)) as con:
            con.execute(
                "INSERT INTO cycles VALUES (?,?,?,?,?,?,?,?,?,?)",
                (winner_id, goal_id, sequence, "OBSERVE", "collect", "idle", None,
                 "{}", stamp, stamp))
            con.execute(
                "INSERT INTO runs VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (winner_id, goal_id, "execution", None, None, "immediate_test",
                 "unversioned", None, "{}", "{}", "{}", "business", None, None,
                 "idle", stamp, stamp))
        return winner_id

    def test_new_cycle_conflicting_sequence_returns_existing_cycle_cleanly(self):
        with tempfile.TemporaryDirectory() as directory:
            runtime = Runtime(Path(directory) / "state.sqlite",
                              {"immediate_test": ImmediateHandler()})
            goal = runtime.create_goal(name="Race", owner_id="immediate_test",
                                       metric="done", operator="eq", target=True,
                                       config={})
            stale = runtime.store.cycle(goal["id"])
            winner_id = self._insert_concurrent_winner(
                runtime.store.path, goal["id"], stale["sequence"] + 1)
            # The loser already read `stale` before the winner committed; its
            # INSERT therefore collides on UNIQUE(goal_id, sequence).
            real_cycle = Store.cycle
            state = {"reads": 0}

            def stale_then_real(store_self, goal_id):
                state["reads"] += 1
                if state["reads"] == 1:
                    return stale  # snapshot taken before the winner's commit
                return real_cycle(store_self, goal_id)

            with patch.object(Store, "cycle", stale_then_real):
                created = runtime.store.new_cycle(goal["id"], {})
            # Loser gets the winner's run back instead of a raw IntegrityError.
            self.assertEqual(winner_id, created["id"])
            self.assertEqual(stale["sequence"] + 1, created["sequence"])

    def test_next_race_loser_does_not_raise_integrity_error(self):
        with tempfile.TemporaryDirectory() as directory:
            runtime = Runtime(Path(directory) / "state.sqlite",
                              {"immediate_test": ImmediateHandler()})
            goal = runtime.create_goal(name="Race next", owner_id="immediate_test",
                                       metric="done", operator="eq", target=True,
                                       config={})
            stale = runtime.store.cycle(goal["id"])
            winner_id = self._insert_concurrent_winner(
                runtime.store.path, goal["id"], stale["sequence"] + 1)
            real_cycle = Store.cycle
            state = {"reads": 0}

            def stale_then_real(store_self, goal_id):
                state["reads"] += 1
                if state["reads"] == 1:
                    return stale
                return real_cycle(store_self, goal_id)

            with patch.object(Store, "cycle", stale_then_real):
                try:
                    created = runtime.store.new_cycle(goal["id"], {})
                except sqlite3.IntegrityError:
                    self.fail("new_cycle must swallow the UNIQUE(goal_id, sequence) "
                              "race as an idempotent no-op")
            self.assertEqual(winner_id, created["id"])


class ProofBeforeTerminalStatusTests(unittest.TestCase):
    """Bug 8: evidence/decisions/evaluations persist BEFORE goal status."""

    def test_terminal_status_write_follows_evidence_writes(self):
        with tempfile.TemporaryDirectory() as directory:
            runtime = Runtime(Path(directory) / "state.sqlite",
                              {"proof_test": AchievingWithEvidenceHandler()})
            goal = runtime.create_goal(name="Proof order", owner_id="proof_test",
                                       metric="done", operator="eq", target=True,
                                       config={})
            order = []
            real_add_evidence = runtime.store.add_evidence
            real_set_status = runtime.store.set_goal_status

            def traced_add_evidence(*args, **kwargs):
                order.append("evidence")
                return real_add_evidence(*args, **kwargs)

            def traced_set_status(goal_id, status):
                order.append(f"status:{status}")
                return real_set_status(goal_id, status)

            with patch.object(runtime.store, "add_evidence", traced_add_evidence), \
                 patch.object(runtime.store, "set_goal_status", traced_set_status):
                result = runtime.once(goal["id"])
            self.assertEqual("achieved", result["goal"]["goal_status"])
            self.assertIn("evidence", order)
            self.assertIn("status:achieved", order)
            self.assertLess(order.index("evidence"), order.index("status:achieved"))


class ForegroundAutomationGateTests(unittest.TestCase):
    """Bug 12: `company runner stop` stops manual commands too."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.db = self.root / ".spielos" / "state" / "company.sqlite"
        self.runtime = Runtime(self.db, {"immediate_test": ImmediateHandler()})
        self.goal = self.runtime.create_goal(name="Stopped", owner_id="immediate_test",
                                             metric="done", operator="eq",
                                             target=True, config={})

    def stop(self) -> None:
        RunnerService(self.root, self.db).stop()

    def test_stop_refuses_foreground_once_next_retry_approve(self):
        self.stop()
        for call in (
                lambda: self.runtime.once(self.goal["id"]),
                lambda: self.runtime.next(self.goal["id"]),
                lambda: self.runtime.retry(self.goal["id"]),
                lambda: self.runtime.approve(self.goal["id"])):
            with self.assertRaises(RuntimeError) as caught:
                call()
            self.assertIn("automation is disabled", str(caught.exception))

    def test_enable_restores_foreground_commands(self):
        service = RunnerService(self.root, self.db)
        service.stop()
        service.enable()
        result = self.runtime.once(self.goal["id"])
        self.assertEqual("achieved", result["goal"]["goal_status"])

    def test_default_state_allows_foreground_commands(self):
        # No automation.json anywhere -> enabled -> nothing refused.
        result = self.runtime.once(self.goal["id"])
        self.assertEqual("achieved", result["goal"]["goal_status"])


class NotificationDeliveryPreservationTests(unittest.TestCase):
    """Bug 13: upsert keeps delivered state unless reopen=True."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.runtime = Runtime(Path(self.temp.name) / "state.sqlite",
                               {"immediate_test": ImmediateHandler()})

    def notify(self, payload_version):
        goal = "goal-x"
        run = self.runtime.store.cycle(self._seed_goal())["id"]
        return self.runtime.store.notify(goal, run, "action_required",
                                         {"version": payload_version})

    def _seed_goal(self) -> str:
        return self.runtime.create_goal(name="Notify", owner_id="immediate_test",
                                        metric="done", operator="eq", target=True,
                                        config={})["id"]

    def test_upsert_preserves_delivered_state_by_default(self):
        goal_id = self._seed_goal()
        run_id = self.runtime.store.cycle(goal_id)["id"]
        first = self.runtime.store.notify(goal_id, run_id, "action_required",
                                          {"version": 1})
        delivered = self.runtime.store.acknowledge_notification(first["id"])
        self.assertEqual("delivered", delivered["status"])
        # Accidental-looking upsert must NOT resurrect the row as pending.
        again = self.runtime.store.notify(goal_id, run_id, "action_required",
                                          {"version": 2})
        self.assertEqual(first["id"], again["id"])
        self.assertEqual("delivered", again["status"])
        self.assertIsNotNone(again["delivered_at"])
        self.assertEqual({"version": 2}, again["payload"])
        self.assertEqual([], [row for row in self.runtime.store.notifications("pending")
                              if row["goal_id"] == goal_id])

    def test_explicit_reopen_makes_the_notification_pending_again(self):
        goal_id = self._seed_goal()
        run_id = self.runtime.store.cycle(goal_id)["id"]
        first = self.runtime.store.notify(goal_id, run_id, "action_required",
                                          {"version": 1})
        self.runtime.store.acknowledge_notification(first["id"])
        reopened = self.runtime.store.notify(goal_id, run_id, "action_required",
                                             {"version": 2}, reopen=True)
        self.assertEqual("pending", reopened["status"])
        self.assertIsNone(reopened["delivered_at"])

    def test_upsert_still_refreshes_created_for_rate_limiting(self):
        goal_id = self._seed_goal()
        run_id = self.runtime.store.cycle(goal_id)["id"]
        first = self.runtime.store.notify(goal_id, run_id, "action_required", {"v": 1})
        second = self.runtime.store.notify(goal_id, run_id, "action_required", {"v": 2})
        self.assertEqual(first["id"], second["id"])
        self.assertGreaterEqual(second["created_at"], first["created_at"])


if __name__ == "__main__":
    unittest.main()
