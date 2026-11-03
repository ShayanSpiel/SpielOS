"""Synthetic regressions for the 29 October architecture review."""
from contextlib import closing
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace
import sqlite3
import tempfile
import threading
import unittest

from company.agents.core import AgentResult, AgentEvidence
from company.commands.goal_runtime import CleanCommandRuntime
from company.evals.engine import compute_report
from company.evals.models import EvalCriterion, EvalSuite
from company.runtime.engine import Decision
from company.workflows import Workflow, WorkflowStep


class ArchitectureStabilizationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "state.sqlite"
        self.runtime = CleanCommandRuntime(self.path)
        row = self.runtime.create_goal(name="Synthetic cost", owner_id="director",
            metric="cost", operator="le", target=100,
            config={"aggregation": "latest"})
        self.goal = self.runtime.goals.get(row["id"])
        self.run = self.runtime.runs.current(self.goal.id)
        self.controller = self.runtime.runtime.controller
        self.repo = self.runtime.work_orders_repository

    def context(self, evidence=()):
        return SimpleNamespace(goal=self.goal, run_id=self.run.id,
                               evidence=evidence, memory=())

    def order(self):
        intervention = self.runtime.interventions.create(goal_id=self.goal.id,
            run_id=self.run.id, kind="request_agent", description="Synthetic work",
            context={"agent_id": "director", "evidence_kind": "cost"})
        return self.repo.open(goal_id=self.goal.id, run_id=self.run.id,
            intervention_id=intervention.id, agent_id="director", step_id="direct",
            brief={"instruction": "Synthetic work", "evidence_kind": "cost"})

    def evidence(self, payload, **kwargs):
        return self.runtime.evidence.record(goal_id=self.goal.id,
            run_id=self.run.id, kind="cost", payload=payload, **kwargs)

    def test_missing_measurement_does_not_complete_cost_goal(self):
        context = self.context()
        self.assertIsNone(self.controller.observe(context)["cost"])
        self.assertFalse(self.controller.evaluate(context, Decision("evaluate", "check"), ()).goal_complete)

    def test_missing_populations_are_unknown_for_every_aggregation(self):
        for aggregation in ("count", "sum", "latest", "max", "min", "boolean_all", "boolean_any"):
            with self.subTest(aggregation=aggregation):
                row = self.runtime.create_goal(name="No measurements", owner_id="director",
                    metric="absent", operator="eq", target=False if aggregation.startswith("boolean") else 0,
                    config={"aggregation": aggregation})
                context = SimpleNamespace(goal=self.runtime.goals.get(row["id"]),
                    run_id=self.runtime.runs.current(row["id"]).id, evidence=(), memory=())
                self.assertIsNone(self.controller.observe(context)["absent"])
                self.assertFalse(self.controller.evaluate(context, Decision("evaluate", "check"), ()).goal_complete)

    def test_technical_measurement_cannot_complete_business_goal(self):
        evidence = self.evidence({"cost": 1, "validity": "technical_only"})
        result = self.controller.evaluate(self.context((evidence,)), Decision("evaluate", "check"), (evidence,))
        self.assertFalse(result.goal_complete)

    def test_actual_zero_is_a_valid_measurement(self):
        evidence = self.evidence({"cost": 0})
        result = self.controller.evaluate(self.context((evidence,)), Decision("evaluate", "check"), (evidence,))
        self.assertTrue(result.goal_complete)

    def suite(self, ids):
        return EvalSuite("synthetic", "Synthetic", "workflow", "synthetic", "report",
            (EvalCriterion("correct", "Correct", "Matches reference", "reference"),),
            item_selector=lambda payload: [(item, {}) for item in ids])

    def test_empty_population_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "empty"):
            compute_report(self.suite([]), {}, {"items": {}})

    def test_duplicate_population_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "duplicate"):
            compute_report(self.suite(["a", "a"]), {}, {"items": {"a": {
                "correct": {"pass": True, "score": 1, "reason": "reference matched"}}}})

    def test_only_one_concurrent_claim_succeeds(self):
        order = self.order()
        barrier = threading.Barrier(2)
        def claim():
            barrier.wait()
            try:
                self.repo.claim(order.id, "director")
                return True
            except RuntimeError:
                return False
        with ThreadPoolExecutor(2) as pool:
            self.assertEqual(sum(pool.map(lambda _: claim(), range(2))), 1)

    def test_stale_generation_cannot_complete_reclaimed_order(self):
        first = self.repo.claim(self.order().id, "director")
        with self.runtime.database.connect() as connection:
            connection.execute("UPDATE core_work_orders SET lease_expires_at='2000' WHERE id=?", (first.id,))
        second = self.repo.claim(first.id, "director")
        self.assertGreater(second.attempt, first.attempt)
        with self.assertRaisesRegex(RuntimeError, "token"):
            self.repo.complete(first.id, {}, executor_id="director", claim_token=first.claim_token)
        result = self.repo.complete(second.id, {}, executor_id="director", claim_token=second.claim_token)
        self.assertEqual(result.status, "completed")

    def test_basic_completion_returns_committed_state(self):
        order = self.repo.claim(self.order().id, "director")
        self.assertEqual(self.repo.complete(order.id, {}, executor_id="director",
            claim_token=order.claim_token).status, "completed")

    def test_wal_commits_are_visible_to_next_snapshot(self):
        writer = sqlite3.connect(self.path)
        self.addCleanup(writer.close)
        writer.execute("PRAGMA wal_autocheckpoint=0")
        writer.execute("BEGIN")
        writer.execute("SELECT COUNT(*) FROM core_evidence").fetchone()
        before = CleanCommandRuntime._cached_snapshot(self.path)
        before_stat = self.path.stat()
        self.evidence({"cost": 7})
        self.assertEqual(before_stat.st_mtime_ns, self.path.stat().st_mtime_ns)
        after = CleanCommandRuntime._cached_snapshot(self.path)
        def count(path):
            with closing(sqlite3.connect(path / "empty.sqlite")) as connection, connection:
                return connection.execute("SELECT COUNT(*) FROM core_evidence").fetchone()[0]
        self.assertEqual(count(after), count(before) + 1)

    def test_owner_preferences_cannot_starve_direct_lessons(self):
        evidence = self.evidence({"cost": 9})
        self.runtime.memory.remember("workflow", "Reuse the verified reference", evidence_ids=(evidence.id,),
            goal_id=self.goal.id, run_id=self.run.id)
        for index in range(25):
            self.runtime.memory.remember("owner", f"Preference {index}")
        self.assertIn("Reuse the verified reference",
            self.runtime.runtime.resolution._brief_memory(goal_id=self.goal.id))

    def test_one_completion_with_three_evidence_rows_is_one_example(self):
        order = self.repo.claim(self.order().id, "director")
        self.repo.complete_with_evidence(order.id, {}, executor_id="director",
            claim_token=order.claim_token, kind="cost", payload={"cost": 1},
            evidence_items=[("cost", {"cost": index}) for index in range(3)])
        shapes = self.controller._repetition_shapes(self.goal.id)
        self.assertEqual([len(entries) for entries in shapes.values()], [1])
        self.assertIsNone(self.controller._crystallized_workflow(self.context(), {}))


    def test_runtime_does_not_infer_strategy(self):
        evidence = self.evidence({"cost": 10})
        result = self.controller.evaluate(self.context((evidence,)),
            Decision("execute_workflow", "Check", "synthetic"), (evidence,))
        self.assertIsNone(result.strategy_learning)

    def test_concurrent_resolution_invokes_executor_once(self):
        order = self.order()
        entered = threading.Event()
        release = threading.Event()
        calls = []
        class Executor:
            def execute(self, agent, work):
                calls.append(work.id)
                entered.set()
                if not release.wait(10):
                    raise RuntimeError("test executor timed out")
                return AgentResult("completed", {"cost": 1}, evidence=(AgentEvidence("cost", {"cost": 1}),))
        resolution = self.runtime.runtime.resolution
        resolution.executor = Executor()
        with ThreadPoolExecutor(2) as pool:
            first = pool.submit(resolution.resolve, order.intervention_id)
            self.assertTrue(entered.wait(10))
            second = pool.submit(resolution.resolve, order.intervention_id)
            try:
                second.result(timeout=10)
            finally:
                release.set()
            first.result(timeout=10)
        self.assertEqual(calls, [order.id])
