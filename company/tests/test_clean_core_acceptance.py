"""Fresh-home acceptance for the clean runtime boundary."""

from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from company.__main__ import main
from company.agents import Agent, AgentEvidence, AgentResult
from company.commands import CleanCommandRuntime
from company.runtime.engine import Decision, Evaluation, GoalRuntime
from company.workflows import Workflow, WorkflowStep


CORE_TABLES = {
    "core_goals", "core_goal_metadata", "core_goal_edges", "core_runs",
    "core_interventions", "core_workflows", "core_workflow_runs",
    "core_work_orders", "core_evidence", "core_memory", "core_approvals",
    "core_notifications",
}


class FreshHomeAcceptanceTests(unittest.TestCase):
    def test_fresh_home_has_only_clean_core_tables(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory) / "home"
            self.assertEqual(0, main(["init", "--dir", str(home), "-y", "--json"]))
            environment = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1",
                           "PYTHONPATH": str(home / ".agents")}
            commands = [(), ("status",), ("overview",), ("context",),
                        ("memory", "summary"), ("profile", "list"),
                        ("runner", "tick")]
            for command in commands:
                result = subprocess.run(
                    [sys.executable, "-B", "-m", "company", *command], cwd=home,
                    env=environment, capture_output=True, text=True, timeout=30)
                self.assertEqual(0, result.returncode, result.stderr or result.stdout)
            database = home / ".spielos" / "state" / "company.sqlite"
            with sqlite3.connect(database) as connection:
                tables = {row[0] for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'")}
            self.assertEqual(CORE_TABLES, tables)


class _WorkflowController:
    def observe(self, _context):
        return {"outcome": 0}

    def decide(self, _context, _observation):
        return Decision("execute_workflow", "produce two evidence items", "two-evidence")

    def evaluate(self, _context, _decision, evidence):
        return Evaluation(True, {"outcome": len(evidence)}, "evidence accepted")


class _TwoEvidenceExecutor:
    def execute(self, _agent, _order):
        return AgentResult("completed", payload={"completed": True}, evidence=(
            AgentEvidence("draft", {"outcome": 1}),
            AgentEvidence("receipt", {"outcome": 2}),
        ))


class RuntimeStabilityTests(unittest.TestCase):
    def test_goal_and_first_run_are_atomic(self):
        with tempfile.TemporaryDirectory() as directory:
            runtime = GoalRuntime(Path(directory) / "state.sqlite",
                                  _WorkflowController(), _TwoEvidenceExecutor())
            with runtime.database.connect() as connection:
                connection.execute("""CREATE TRIGGER reject_initial_run
                    BEFORE INSERT ON core_runs
                    BEGIN SELECT RAISE(ABORT, 'run rejected'); END""")
            with self.assertRaises(sqlite3.IntegrityError):
                runtime.create_goal("Atomic", "outcome", "ge", 1)
            with runtime.database.connect() as connection:
                self.assertEqual(0, connection.execute(
                    "SELECT COUNT(*) FROM core_goals").fetchone()[0])
                connection.execute("DROP TRIGGER reject_initial_run")
            goal = runtime.create_goal("Atomic", "outcome", "ge", 1)
            self.assertEqual(1, runtime.runs.current(goal.id).sequence)

    def test_one_approval_can_release_all_step_keys_and_record_multi_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            command = CleanCommandRuntime(Path(directory) / "state.sqlite")
            command.runtime.controller = _WorkflowController()
            command.runtime.resolution.executor = _TwoEvidenceExecutor()
            command.runtime.resolution.agents = {"worker": Agent("worker")}
            command.runtime.resolution.workflows.save(Workflow(
                "two-evidence", "Two approvals and two evidence records", (
                    WorkflowStep("publish", "worker", "produce evidence",
                                 evidence_kinds=("draft", "receipt"),
                                 approval_keys=("legal", "owner")),
                )))
            goal = command.runtime.create_goal("Release", "outcome", "ge", 1)
            command.runtime.advance(goal.id)
            command.runtime.advance(goal.id)
            waiting = command.runtime.advance(goal.id)
            self.assertEqual("waiting", waiting["run"].status)
            command.approve(goal.id, "approved as one action")
            run = command.runtime.runs.current(goal.id)
            self.assertEqual("EVALUATE", run.stage.value)
            self.assertEqual({"draft", "receipt"}, {
                item.kind for item in command.runtime.evidence.for_run(run.id)})
            intervention = command.runtime.interventions.active_for_run(run.id)
            self.assertIsNone(intervention)
            with command.database.connect() as connection:
                keys = {row[0] for row in connection.execute(
                    "SELECT key FROM core_approvals WHERE run_id=?", (run.id,))}
            self.assertEqual({"legal", "owner"}, keys)
            command.runtime.advance(goal.id)
            self.assertEqual("complete", command.runtime.goals.get(goal.id).status)
