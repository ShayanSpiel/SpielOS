"""P3C: Memory is evidence-backed, reusable, and used by a later decision."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from company.runtime.interpreter import InterpretedDepartment
from company.runtime.loop import Runtime
from company.runtime.models import (
    Department, RunStatus, StageResult, WorkflowSpec, WorkflowStep,
)


class _MemoryDepartment(InterpretedDepartment, Department):
    id = department_id = "memory_test"
    version = "1.0.0"
    description = "Memory semantics fixture"
    agent_ids = ("researcher",)
    goal_schema = {"metrics": ["outputs"], "config": {}}
    evidence_metrics = {"outputs": ("output",)}
    workflows = (WorkflowSpec(
        "primary", "Use a remembered research choice", ("produce",),
        ("researcher",), (), (), ("output",), (), graph=(
            WorkflowStep("produce", "employee", employee_id="researcher",
                         produces=("output",)),
        )),)

    def observe(self, ctx):
        if ctx.goal.config.get("memory_fixture"):
            return StageResult("collect", {
                "evidence": list(ctx.cycle.get("evidence") or ()),
            })
        return super().observe(ctx)

    def decide(self, ctx, observation):
        if ctx.goal.config.get("memory_fixture"):
            return StageResult("choose", {"action": "evaluate_fixture"})
        return super().decide(ctx, observation)

    def act(self, ctx, decision):
        if ctx.goal.config.get("memory_fixture"):
            return StageResult("execute", {"tested": True})
        return super().act(ctx, decision)

    def evaluate(self, ctx, action_result):
        fixture = ctx.goal.config.get("memory_fixture")
        if not fixture:
            return super().evaluate(ctx, action_result)
        evidence = list(ctx.cycle.get("evidence") or ())
        learning = {
            "claim": "Use the square research frame for this workflow",
            "evidence": {"observed_variant": "square"},
            "confidence": 0.9,
        }
        if fixture != "routine":
            learning.update({
                "reusable": True,
                "decision_relevance": "Choose the research frame in a later output decision",
                "evidence_ids": [evidence[-1]["id"]],
                "applies_to": {"metrics": ["outputs"], "workflows": ["primary"]},
            })
        validity = "invalid" if fixture == "invalid" else "business"
        return StageResult(
            "goal_check", {"outputs": 0}, RunStatus.COMPLETED,
            evaluation={"verdict": "continue", "goal_met": False,
                        "metrics": {"outputs": 0}, "validity": validity,
                        "next_experiment": {}},
            learnings=[learning])


class MemorySemanticsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.runtime = Runtime(Path(self.temp.name) / "state.sqlite", {
            "memory_test": _MemoryDepartment(),
        })

    def learning_goal(self, fixture="reusable"):
        goal = self.runtime.create_goal(
            name="Learn one reusable research choice", owner_id="memory_test",
            metric="outputs", operator="ge", target=1,
            run_type="business_experiment",
            config={"memory_fixture": fixture})
        self.runtime.add_evidence(
            goal["id"], kind="output", source="researcher",
            payload={"variant": "square"},
            validity="invalid" if fixture == "invalid" else "business")
        self.runtime.once(goal["id"])
        return goal

    def test_evidence_backed_reusable_claim_persists(self):
        goal = self.learning_goal()
        memories = self.runtime.store.memories("memory_test", goal["id"])
        self.assertEqual(1, len(memories))
        self.assertEqual("Use the square research frame for this workflow",
                         memories[0]["claim"])
        self.assertEqual(1, len(memories[0]["evidence"]["evidence_ids"]))

    def test_routine_completion_summary_stays_out_of_memory(self):
        goal = self.learning_goal("routine")
        self.assertEqual((), self.runtime.store.memories("memory_test", goal["id"]))

    def test_invalid_support_cannot_create_memory(self):
        goal = self.learning_goal("invalid")
        self.assertEqual((), self.runtime.store.memories("memory_test", goal["id"]))

    def test_malformed_learning_is_ignored_without_failing_run(self):
        goal = self.runtime.create_goal(
            name="Ignore malformed learning", owner_id="memory_test",
            metric="outputs", operator="ge", target=1,
            config={"memory_fixture": "routine"})
        handler = self.runtime.registry["memory_test"]
        original = handler.evaluate

        def malformed(ctx, action_result):
            result = original(ctx, action_result)
            result.learnings = [{"claim": "bad", "reusable": True,
                                 "decision_relevance": "future",
                                 "evidence_ids": {"not": "a list"},
                                 "applies_to": {"metrics": "outputs"}}]
            return result

        handler.evaluate = malformed
        self.addCleanup(setattr, handler, "evaluate", original)
        result = self.runtime.once(goal["id"])
        self.assertEqual("completed", result["cycle"]["run_status"])
        self.assertEqual((), self.runtime.store.memories("memory_test", goal["id"]))

    def test_learning_can_cite_evidence_emitted_by_the_same_result(self):
        goal = self.runtime.create_goal(
            name="Learn from the current result", owner_id="memory_test",
            metric="outputs", operator="ge", target=1,
            config={"memory_fixture": "same_result"})
        handler = self.runtime.registry["memory_test"]

        def evaluate(ctx, action_result):
            return StageResult(
                "goal_check", {"outputs": 0}, RunStatus.COMPLETED,
                evaluation={"verdict": "continue", "goal_met": False,
                            "metrics": {"outputs": 0}, "validity": "business",
                            "next_experiment": {}},
                evidence=[{"ref": "current-output", "kind": "output",
                           "source": "researcher", "payload": {"variant": "square"}}],
                learnings=[{
                    "claim": "Square framing is reusable for this workflow",
                    "reusable": True,
                    "decision_relevance": "Choose the next research frame",
                    "evidence_refs": ["current-output"],
                    "applies_to": {"metrics": ["outputs"], "workflows": ["primary"]},
                }])

        original = handler.evaluate
        handler.evaluate = evaluate
        self.addCleanup(setattr, handler, "evaluate", original)
        self.runtime.once(goal["id"])
        memories = self.runtime.store.memories("memory_test", goal["id"])
        self.assertEqual(1, len(memories))
        self.assertEqual(1, len(memories[0]["evidence"]["evidence_ids"]))

    def test_later_related_decision_retrieves_and_uses_ancestor_memory(self):
        parent = self.learning_goal()
        memory = self.runtime.store.memories("memory_test", parent["id"])[0]
        child = self.runtime.create_goal(
            name="Use the learned research choice", owner_id="memory_test",
            metric="outputs", operator="ge", target=1, parent_id=parent["id"],
            config={"workflow": "primary"})
        result = self.runtime.once(child["id"])
        decision = next(item for item in result["decisions"]
                        if item["decision_type"] == "request_agent")
        self.assertEqual([memory["id"]], decision["payload"]["memory_ids"])
        self.assertIn(memory["claim"], decision["rationale"])

    def test_unrelated_goal_does_not_receive_owner_memory(self):
        self.learning_goal()
        unrelated = self.runtime.create_goal(
            name="Unrelated output", owner_id="memory_test",
            metric="outputs", operator="ge", target=1,
            config={"workflow": "primary"})
        result = self.runtime.once(unrelated["id"])
        decision = next(item for item in result["decisions"]
                        if item["decision_type"] == "request_agent")
        self.assertNotIn("memory_ids", decision["payload"])


if __name__ == "__main__":
    unittest.main()
