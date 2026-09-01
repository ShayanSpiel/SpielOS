"""P5: persistent valid business failure moves Director reasoning upward."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from company.runtime.director import Director
from company.runtime.loop import Runtime
from company.runtime.models import GoalHandler, RunStatus, StageResult


class _PersistentFailure(GoalHandler):
    id = "market_test"
    version = "1.0.0"

    def observe(self, ctx):
        return StageResult("collect", {"sequence": ctx.cycle["sequence"]})

    def decide(self, ctx, observation):
        return StageResult("choose", {"action": "test_tactical_hypothesis"})

    def act(self, ctx, decision):
        return StageResult("execute", {"tested": True})

    def evaluate(self, ctx, action_result):
        mode = ctx.goal.config.get("failure_mode", "qualified")
        run = ctx.cycle.get("run") or {}
        technical = mode == "technical"
        invalid = mode == "invalid"
        validity = "technical_only" if technical else ("invalid" if invalid else "business")
        metrics = {
            "reply_rate": 0.0,
            "execution_competent": mode != "missing_competence",
            "system_trustworthy": mode != "missing_system_trust",
        }
        if mode != "unresolved":
            metrics["hypothesis_result"] = {
                "hypothesis_id": run.get("hypothesis_id"),
                "prediction_tested": True,
                "status": "rejected",
            }
        next_experiment = {
            "action": "test_next_tactical_variable",
            "change_one_variable": "message_variant",
        }
        next_run_type = "system_test" if technical else "business_experiment"
        evaluation = {"verdict": "rejected", "goal_met": False,
                      "metrics": metrics, "validity": validity,
                      "next_experiment": next_experiment}
        if mode != "unresolved":
            evaluation["hypothesis_result"] = metrics["hypothesis_result"]
        return StageResult(
            "goal_check", metrics, RunStatus.COMPLETED,
            evaluation=evaluation,
            evidence=[{"kind": "market_result", "source": "market-test",
                       "validity": validity, "payload": {"reply_rate": 0.0}}],
            next_run={
                "run_type": next_run_type,
                "evidence_validity": validity,
                "hypothesis": {
                    "statement": "The next tactical message improves replies",
                    "variable": "message_variant",
                    "prediction": "reply rate improves",
                },
                "controlled_variables": {"ICP": "fixed", "offer": "fixed"},
                "changed_variables": {"message_variant": "next"},
            })


class StrategicFrontierTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.runtime = Runtime(Path(self.temp.name) / "state.sqlite", {
            "director": Director(), "market_test": _PersistentFailure(),
        })

    def goals(self, mode="qualified"):
        parent = self.runtime.create_goal(
            name="Reach 30 percent reply rate", owner_id="director",
            metric="reply_rate", operator="ge", target=0.3, config={})
        child = self.runtime.create_goal(
            name="Find an effective outbound message", owner_id="market_test",
            metric="reply_rate", operator="ge", target=0.3,
            parent_id=parent["id"], run_type=(
                "system_test" if mode == "technical" else "business_experiment"),
            evidence_validity=("technical_only" if mode == "technical" else
                               "invalid" if mode == "invalid" else "business"),
            hypothesis={
                "statement": "This tactical message improves replies",
                "variable": "message_variant",
                "prediction": "reply rate improves",
            },
            config={
                "failure_mode": mode,
                "strategic_candidate": {
                    "kind": "model",
                    "proposal": "Test whether the ICP problem framing is wrong",
                    "scope": "outbound positioning for the canonical ICP",
                    "experiment": {
                        "hypothesis": "Problem framing, not copy execution, limits replies",
                        "changed_variable": "problem_frame",
                        "stop_condition": "Compare two qualified 50-recipient samples",
                    },
                    "contradictions_assessment": (
                        "No valid contradictory success exists in the evaluated branch"),
                    "confidence": 0.8,
                },
            })
        return parent, child

    def run_failures(self, child, count=3):
        for _ in range(count):
            self.runtime.once(child["id"])

    def strategic_decision(self, parent):
        result = self.runtime.once(parent["id"])
        decisions = [item for item in result["decisions"]
                     if item["decision_type"] == "strategic_experiment"]
        return result, decisions

    def test_three_qualified_failures_park_strategic_experiment_proposal(self):
        parent, child = self.goals()
        self.run_failures(child)
        result, decisions = self.strategic_decision(parent)
        self.assertEqual("awaiting_approval", result["cycle"]["run_status"])
        self.assertEqual(1, len(decisions))
        decision = decisions[0]
        proposal = decision["payload"]
        self.assertEqual("model", proposal["strategic_level"])
        self.assertEqual(3, len(proposal["failed_run_ids"]))
        self.assertEqual(3, len(proposal["rejected_hypothesis_ids"]))
        self.assertEqual(3, len(decision["evidence_ids"]))
        self.assertTrue(proposal["required_owner_authority"])
        self.assertFalse(proposal["strategy_mutated"])
        self.assertEqual(
            [child["id"]], [item["goal"]["id"] for item in result["children"]])

    def test_owner_approval_authorizes_test_without_mutating_strategy(self):
        parent, child = self.goals()
        self.run_failures(child)
        self.strategic_decision(parent)
        self.runtime.approve(parent["id"])
        result = self.runtime.once(parent["id"])
        action = result["cycle"]["data"]["action_result"]
        self.assertTrue(action["owner_authorized"])
        self.assertFalse(action["strategy_mutated"])

    def test_one_business_failure_does_not_escalate(self):
        parent, child = self.goals()
        self.run_failures(child, 1)
        _, decisions = self.strategic_decision(parent)
        self.assertEqual([], decisions)

    def test_technical_or_invalid_runs_do_not_escalate(self):
        for mode in ("technical", "invalid"):
            with self.subTest(mode=mode):
                temp = tempfile.TemporaryDirectory()
                self.addCleanup(temp.cleanup)
                runtime = Runtime(Path(temp.name) / "state.sqlite", {
                    "director": Director(), "market_test": _PersistentFailure(),
                })
                original = self.runtime
                self.runtime = runtime
                try:
                    parent, child = self.goals(mode)
                    self.run_failures(child)
                    _, decisions = self.strategic_decision(parent)
                    self.assertEqual([], decisions)
                finally:
                    self.runtime = original

    def test_unresolved_or_untrusted_failures_do_not_escalate(self):
        for mode in ("unresolved", "missing_competence", "missing_system_trust"):
            with self.subTest(mode=mode):
                temp = tempfile.TemporaryDirectory()
                self.addCleanup(temp.cleanup)
                runtime = Runtime(Path(temp.name) / "state.sqlite", {
                    "director": Director(), "market_test": _PersistentFailure(),
                })
                original = self.runtime
                self.runtime = runtime
                try:
                    parent, child = self.goals(mode)
                    self.run_failures(child)
                    _, decisions = self.strategic_decision(parent)
                    self.assertEqual([], decisions)
                finally:
                    self.runtime = original


if __name__ == "__main__":
    unittest.main()
