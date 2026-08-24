"""P2.5B: automatic next-Run continuation."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from company.runtime.continuation import (
    continuation_decision, next_experiment_valid, resource_key,
)
from company.runtime.director import Director
from company.runtime.loop import Runtime
from company.runtime.models import GoalHandler, GoalStatus, RunStatus, Stage, StageResult
from company.runtime.runner import Runner
from company.runtime.system_improvement import SystemImprovement


class _ScoreHandler(GoalHandler):
    id = "score_test"

    def observe(self, ctx):
        return StageResult("collect", {"ok": True})

    def decide(self, ctx, observation):
        return StageResult("diagnose", {"action": "sample"})

    def act(self, ctx, decision):
        return StageResult("execute", {"done": True})

    def evaluate(self, ctx, action_result):
        if "next_experiment" in ctx.goal.config:
            experiment = dict(ctx.goal.config.get("next_experiment") or {})
        else:
            experiment = {"action": "sample_again", "change_one_variable": "sample"}
        validity = ctx.goal.config.get("evaluation_validity") or "business"
        return StageResult(
            "goal_check", {"score": 0.2}, RunStatus.COMPLETED,
            evaluation={"verdict": "continue", "goal_met": False,
                        "metrics": {"score": 0.2}, "validity": validity,
                        "next_experiment": experiment},
            next_run={"run_type": "business_experiment",
                      "changed_variables": {"sample": "next"}})


class ContinuationPolicyTests(unittest.TestCase):
    def test_next_experiment_rejects_empty_and_system_improvement(self):
        self.assertFalse(next_experiment_valid({"next_experiment": {}}))
        self.assertFalse(next_experiment_valid({
            "next_experiment": {"system_improvement": {"problem": "x"}}}))
        self.assertTrue(next_experiment_valid({
            "next_experiment": {"action": "run_email_batch"}}))

    def test_email_and_outbound_share_a_channel_key(self):
        self.assertEqual(resource_key({"owner_id": "email", "config": {}}),
                         resource_key({"owner_id": "outbound", "config": {}}))

    def test_invalid_evaluation_and_run_limit_stop_continuation(self):
        goal = {"id": "g", "goal_status": "active", "owner_id": "email", "config": {"max_runs": 2}}
        cycle = {"run_status": "completed", "sequence": 2}
        invalid = continuation_decision(
            goal=goal, cycle=cycle,
            evaluation={"goal_met": False, "validity": "contaminated",
                        "next_experiment": {"action": "again"}},
            run_count=2)
        self.assertFalse(invalid["eligible"])
        self.assertEqual(invalid["reason"], "evaluation_contaminated")
        limited = continuation_decision(
            goal=goal, cycle=cycle,
            evaluation={"goal_met": False, "validity": "business",
                        "next_experiment": {"action": "again"}},
            run_count=2)
        self.assertFalse(limited["eligible"])
        self.assertEqual(limited["reason"], "run_limit_reached")


class ContinuationRuntimeTests(unittest.TestCase):
    def runtime(self, registry=None):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        return Runtime(Path(self.temp.name) / "state.sqlite",
                       registry or {"score_test": _ScoreHandler()})

    def test_invalid_evaluation_does_not_continue(self):
        runtime = self.runtime()
        goal = runtime.create_goal(
            name="Contaminated", owner_id="score_test", metric="score",
            operator="ge", target=0.8, config={"evaluation_validity": "contaminated",
                                               "next_experiment": {"action": "again"}})
        runtime.once(goal["id"])
        again = runtime.once(goal["id"])
        self.assertEqual(again["cycle"]["sequence"], 1)
        self.assertEqual(runtime.continuation_decision(goal["id"])["reason"],
                         "evaluation_contaminated")

    def test_missing_next_experiment_does_not_continue(self):
        runtime = self.runtime()
        goal = runtime.create_goal(
            name="No next", owner_id="score_test", metric="score",
            operator="ge", target=0.8, config={"next_experiment": {}})
        runtime.once(goal["id"])
        self.assertEqual(runtime.once(goal["id"])["cycle"]["sequence"], 1)
        self.assertEqual(runtime.continuation_decision(goal["id"])["reason"],
                         "invalid_next_experiment")

    def test_system_improvement_blocker_does_not_continue(self):
        runtime = self.runtime()
        goal = runtime.create_goal(
            name="Needs repair", owner_id="score_test", metric="score",
            operator="ge", target=0.8,
            config={"next_experiment": {"system_improvement": {"problem": "transport"}}})
        runtime.once(goal["id"])
        self.assertEqual(runtime.once(goal["id"])["cycle"]["sequence"], 1)
        self.assertEqual(runtime.continuation_decision(goal["id"])["reason"],
                         "system_improvement_blocker")

    def test_paused_parent_blocks_child_continuation(self):
        runtime = self.runtime({"score_test": _ScoreHandler(), "director": Director()})
        parent = runtime.create_goal(
            name="Reply rate", owner_id="director", metric="reply_rate",
            operator="ge", target=0.3, config={})
        child = runtime.create_goal(
            name="Child experiment", owner_id="score_test", metric="score",
            operator="ge", target=0.8, parent_id=parent["id"], config={})
        runtime.once(child["id"])
        runtime.set_goal_status(parent["id"], GoalStatus.PAUSED)
        child_state = runtime.status(child["id"])
        self.assertEqual(child_state["goal"]["goal_status"], "paused")
        self.assertEqual(child_state["cycle"]["sequence"], 1)
        with self.assertRaisesRegex(RuntimeError, "is paused"):
            runtime.once(child["id"])
        self.assertEqual(runtime.continuation_decision(child["id"])["reason"],
                         "goal_not_active")

    def test_resource_conflict_blocks_automatic_but_not_manual_next(self):
        runtime = self.runtime({"score_test": _ScoreHandler(), "email": _ScoreHandler()})
        busy = runtime.create_goal(
            name="Live send", owner_id="email", metric="score",
            operator="ge", target=0.8, config={})
        runtime.store.update_cycle(
            runtime.store.cycle(busy["id"])["id"],
            stage="ACT", step="review", run_status="awaiting_approval", data={})
        other = runtime.create_goal(
            name="Next batch", owner_id="email", metric="score",
            operator="ge", target=0.8, config={})
        runtime.once(other["id"])
        self.assertEqual(runtime.continuation_decision(other["id"])["reason"],
                         "resource_conflict")
        self.assertEqual(runtime.once(other["id"])["cycle"]["sequence"], 1)
        manual = runtime.next(other["id"])
        self.assertEqual(manual["cycle"]["sequence"], 2)

    def test_runner_continues_completed_unmet_run(self):
        runtime = self.runtime()
        goal = runtime.create_goal(
            name="Keep going", owner_id="score_test", metric="score",
            operator="ge", target=0.8, config={"max_runs": 3})
        runtime.once(goal["id"])
        Runner(runtime).tick(goal["id"], max_advances=2)
        self.assertGreaterEqual(runtime.status(goal["id"])["cycle"]["sequence"], 2)

    def test_system_improvement_owner_is_not_auto_iterated(self):
        runtime = self.runtime({"system-improvement": SystemImprovement()})
        goal = runtime.create_goal(
            name="Repair", owner_id="system-improvement",
            metric="acceptance_tests_passed", operator="eq", target=True,
            run_type="system_improvement", evidence_validity="technical_only",
            config={
                "owner_id": "email", "from_version": "2.0.0", "target_version": "2.0.1",
                "problem": "mapping", "allowed_files": ["email.py"],
                "acceptance_tests": ["python -m unittest"],
                "owner_override": True,
            })
        runtime.once(goal["id"])
        self.assertEqual(runtime.status(goal["id"])["cycle"]["run_status"], "awaiting_approval")
        self.assertFalse(runtime.continuation_decision(goal["id"])["eligible"])
