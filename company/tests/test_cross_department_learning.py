"""P4: explicit, relevant, bounded Memory may cross Departments."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from company.runtime.interpreter import InterpretedDepartment
from company.runtime.loop import Runtime
from company.runtime.models import (
    Department, GoalHandler, RunStatus, StageResult, WorkflowSpec, WorkflowStep,
)


class _OutboundLearning(GoalHandler):
    id = "outbound"
    version = "1.0.0"

    def observe(self, ctx):
        return StageResult("collect", {
            "evidence": list(ctx.cycle.get("evidence") or ()),
        })

    def decide(self, ctx, observation):
        return StageResult("choose", {"action": "evaluate_signal"})

    def act(self, ctx, decision):
        return StageResult("execute", {"evaluated": True})

    def evaluate(self, ctx, action_result):
        evidence = list(ctx.cycle.get("evidence") or ())
        config = ctx.goal.config
        learning = {
            "claim": "ICP buyers respond to evidence-first positioning",
            "evidence": {"segment": "founder-led B2B"},
            "confidence": 0.9,
            "reusable": True,
            "decision_relevance": "Choose the framing for a later Content draft",
            "evidence_ids": [evidence[-1]["id"]],
            "applies_to": {"metrics": ["published_items"],
                           "workflows": ["publish"]},
            "share_scope": config.get("share_scope", "company"),
            "audience_departments": config.get("audience_departments", ["content"]),
            "topics": config.get("topics", ["positioning"]),
        }
        validity = config.get("validity", "business")
        return StageResult(
            "goal_check", {"signals": 1}, RunStatus.COMPLETED,
            evaluation={"verdict": "continue", "goal_met": False,
                        "metrics": {"signals": 1}, "validity": validity,
                        "next_experiment": {}},
            learnings=[learning])


class _ContentDepartment(InterpretedDepartment, Department):
    id = department_id = "content"
    version = "1.0.0"
    description = "Cross-Department Memory consumer"
    agent_ids = ("content-writer",)
    goal_schema = {"metrics": ["published_items"], "config": {}}
    evidence_metrics = {"published_items": ("publication_receipt",)}
    workflows = (WorkflowSpec(
        "publish", "Prepare content using relevant company learning", ("draft",),
        ("content-writer",), (), (), ("draft_item",), (), graph=(
            WorkflowStep("draft", "employee", employee_id="content-writer",
                         produces=("draft_item",)),
        )),)


class CrossDepartmentLearningTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.runtime = Runtime(Path(self.temp.name) / "state.sqlite", {
            "outbound": _OutboundLearning(),
            "content": _ContentDepartment(),
        })

    def learn(self, **config):
        goal = self.runtime.create_goal(
            name="Learn a validated positioning fact", owner_id="outbound",
            metric="signals", operator="ge", target=2,
            run_type="business_experiment", config=config)
        validity = config.get("validity", "business")
        self.runtime.add_evidence(
            goal["id"], kind="customer_signal", source="outbound-research",
            payload={"framing": "evidence-first"}, validity=validity)
        self.runtime.once(goal["id"])
        return goal

    def content_decision(self, topics=("positioning",)):
        goal = self.runtime.create_goal(
            name="Create a related Content draft", owner_id="content",
            metric="published_items", operator="ge", target=1,
            config={"workflow": "publish", "memory_topics": list(topics)})
        result = self.runtime.once(goal["id"])
        decision = next(item for item in result["decisions"]
                        if item["decision_type"] == "request_agent")
        return result, decision

    def test_outbound_claim_changes_later_content_decision(self):
        source = self.learn()
        memory = self.runtime.store.memories("outbound", source["id"])[0]
        result, decision = self.content_decision()
        self.assertEqual([memory["id"]], decision["payload"]["memory_ids"])
        self.assertIn(memory["claim"], decision["rationale"])
        observed = result["cycle"]["data"]["observation"]["memory"]
        self.assertEqual([memory["id"]], [item["id"] for item in observed])
        order = self.runtime.store.work_orders(status="open", goal_id=result["goal"]["id"])[0]
        self.assertEqual([memory["id"]], [item["id"] for item in order["brief"]["memory"]])

    def test_wrong_topic_is_not_retrieved(self):
        self.learn(topics=["positioning"])
        result, decision = self.content_decision(("analytics",))
        self.assertEqual([], result["cycle"]["data"]["observation"]["memory"])
        self.assertNotIn("memory_ids", decision["payload"])

    def test_wrong_audience_and_unshared_claims_are_not_retrieved(self):
        self.learn(audience_departments=["analytics"])
        self.learn(share_scope="department")
        result, decision = self.content_decision()
        self.assertEqual([], result["cycle"]["data"]["observation"]["memory"])
        self.assertNotIn("memory_ids", decision["payload"])

    def test_invalid_cross_department_claim_is_not_persisted(self):
        source = self.learn(validity="invalid")
        self.assertEqual((), self.runtime.store.memories("outbound", source["id"]))
        result, _ = self.content_decision()
        self.assertEqual([], result["cycle"]["data"]["observation"]["memory"])

    def test_cross_department_context_is_capped_at_ten(self):
        source = self.learn()
        template = self.runtime.store.memories("outbound", source["id"])[0]
        for index in range(14):
            self.runtime.store.learn(
                "outbound", source["id"], f"Relevant positioning claim {index}",
                template["evidence"], 0.8)
        result, _ = self.content_decision()
        observed = result["cycle"]["data"]["observation"]["memory"]
        self.assertEqual(10, len(observed))
        self.assertTrue(all(
            "positioning" in item["evidence"]["topics"] for item in observed))


if __name__ == "__main__":
    unittest.main()
