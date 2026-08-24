"""P3B: hypotheses resolve only from same-Run prediction tests."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from company.runtime.loop import Runtime
from company.runtime.models import GoalHandler, GoalStatus, RunStatus, StageResult


class _HypothesisHandler(GoalHandler):
    id = "hypothesis_test"
    version = "1.0.0"

    def observe(self, ctx):
        return StageResult("collect", {"ready": True})

    def decide(self, ctx, observation):
        return StageResult("choose", {"action": "test_prediction"})

    def act(self, ctx, decision):
        return StageResult("execute", {"tested": True})

    def evaluate(self, ctx, action_result):
        config = ctx.goal.config
        evaluation = {
            "verdict": config.get("verdict", "keep"),
            "goal_met": config.get("goal_met", True),
            "metrics": {ctx.goal.metric: config.get("goal_met", True)},
            "validity": config.get("validity", "business"),
        }
        result = config.get("hypothesis_result")
        if result:
            hypothesis_id = (ctx.cycle.get("run") or {}).get("hypothesis_id")
            evaluation["hypothesis_result"] = {
                "hypothesis_id": ("wrong-hypothesis" if result.get("mismatched")
                                  else hypothesis_id),
                "prediction_tested": result.get("prediction_tested", True),
                "status": result["status"],
            }
        goal_status = GoalStatus.ACHIEVED if evaluation["goal_met"] else None
        return StageResult("goal_check", evaluation["metrics"], RunStatus.IDLE,
                           goal_status=goal_status, evaluation=evaluation)


class HypothesisLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.runtime = Runtime(Path(self.temp.name) / "state.sqlite", {
            "hypothesis_test": _HypothesisHandler(),
        })

    def create(self, *, config=None, run_type="business_experiment",
               validity="business", parent_id=None):
        return self.runtime.create_goal(
            name="Test one prediction", owner_id="hypothesis_test",
            metric="result", operator="eq", target=True,
            parent_id=parent_id, config=config or {}, run_type=run_type,
            evidence_validity=validity,
            hypothesis={"statement": "The intervention changes the result",
                        "variable": "intervention", "prediction": "result improves"})

    def hypothesis(self, goal):
        run = self.runtime.store.run(self.runtime.store.cycle(goal["id"])["id"])
        return self.runtime.store.hypothesis(run["hypothesis_id"])

    def test_business_experiment_resolves_its_tested_hypothesis(self):
        goal = self.create(config={"hypothesis_result": {"status": "supported"}})
        self.runtime.once(goal["id"])
        self.assertEqual(self.hypothesis(goal)["status"], "supported")
        evaluation = self.runtime.store.latest_evaluation_for_goal(goal["id"])
        self.assertTrue(evaluation["metrics"]["hypothesis_result"]["prediction_tested"])
        events = self.runtime.store.events(goal["id"], 20)
        self.assertTrue(any(item["kind"] == "hypothesis.resolved" for item in events))

    def test_goal_achievement_alone_leaves_hypothesis_active(self):
        goal = self.create()
        self.runtime.once(goal["id"])
        self.assertEqual(self.hypothesis(goal)["status"], "active")

    def test_mismatched_branch_cannot_resolve_hypothesis(self):
        goal = self.create(config={
            "hypothesis_result": {"status": "rejected", "mismatched": True}})
        self.runtime.once(goal["id"])
        self.assertEqual(self.hypothesis(goal)["status"], "active")

    def test_invalid_prediction_test_resolves_only_inconclusive(self):
        goal = self.create(config={
            "validity": "invalid",
            "hypothesis_result": {"status": "supported"},
        })
        self.runtime.once(goal["id"])
        self.assertEqual(self.hypothesis(goal)["status"], "inconclusive")

    def test_technical_only_evidence_cannot_settle_business_hypothesis(self):
        goal = self.create(config={
            "validity": "technical_only",
            "hypothesis_result": {"status": "supported"},
        }, validity="technical_only")
        self.runtime.once(goal["id"])
        self.assertEqual(self.hypothesis(goal)["status"], "active")

    def test_adjacent_system_improvement_resolves_only_its_own_hypothesis(self):
        business = self.create()
        repair = self.create(
            parent_id=business["id"], run_type="system_improvement",
            validity="technical_only", config={
                "validity": "technical_only",
                "hypothesis_result": {"status": "supported"},
            })
        self.runtime.once(repair["id"])
        self.assertEqual(self.hypothesis(repair)["status"], "supported")
        self.assertEqual(self.hypothesis(business)["status"], "active")

    def test_terminal_hypothesis_result_is_append_only(self):
        goal = self.create(config={"hypothesis_result": {"status": "supported"}})
        self.runtime.once(goal["id"])
        hypothesis = self.hypothesis(goal)
        self.runtime.store.resolve_hypothesis(hypothesis["id"], "rejected")
        self.assertEqual(self.hypothesis(goal)["status"], "supported")


if __name__ == "__main__":
    unittest.main()
