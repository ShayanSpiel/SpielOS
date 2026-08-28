"""Focused contracts for Content's Strategy -> copy boundary."""

import tempfile
import unittest
from pathlib import Path

from company.departments.content.department import ContentDepartment
from company.runtime.contracts import validate_goal_request
from company.runtime.loop import Runtime
from company.runtime.models import Goal, GoalContext
from company.runtime.package import validate_package


class ContentWorkflowWiringTests(unittest.TestCase):
    def _strategy(self):
        return {
            "state_hash": "strategy-test-hash",
            "sections": [
                {"id": "model.icp.buyer", "content": "A recruiting operator."},
                {"id": "policy.voice.one_idea", "content": "One idea."},
                {"id": "policy.voice.copy_shape", "content": "Short, concrete sentences."},
            ],
        }

    def _request(self):
        return {
            "icp": "Recruitment companies",
            "reader": "A founder or operator at a recruitment company",
            "intent": "educational",
            "topic": "candidate follow-up operations",
            "platforms": ["threads", "youtube-shorts"],
            "formats": ["thread", "short-video"],
            "cta_policy": "none",
            "link_policy": "none",
        }

    def _context(self, evidence=(), workflow="content-package", request=None):
        config = {"workflow": workflow, "content_request": request or self._request()}
        goal = Goal("content-test", "Content test", "content", "content_packages", "ge", 1,
                    None, None, "active", config)
        return GoalContext(goal, {"evidence": list(evidence)}, (), lambda _: None,
                           strategy=self._strategy())

    def test_content_package_is_an_explicit_strategy_to_copy_graph(self):
        workflow = next(item for item in ContentDepartment.workflows if item.id == "content-package")
        self.assertEqual(
            ["strategy_intake", "worldview", "brief", "copy", "editorial_review"],
            [step.id for step in workflow.graph],
        )
        self.assertEqual("content-strategist", workflow.graph[1].employee_id)
        self.assertEqual("content-strategist", workflow.graph[2].employee_id)
        self.assertEqual("content-writer", workflow.graph[3].employee_id)
        self.assertEqual([], validate_package(ContentDepartment()))

    def test_content_goal_gets_bounded_strategy_context_by_default(self):
        config = validate_goal_request(ContentDepartment(), metric="content_packages", config={})
        self.assertEqual("content-package", config["workflow"])
        self.assertIn("buyer", config["strategy_context"]["topics"])
        self.assertIn("policy", config["strategy_context"]["layers"])

    def test_missing_icp_request_blocks_before_a_generic_worker_order(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime = Runtime(Path(tmp) / "company.sqlite")
            goal = runtime.create_goal(
                name="Unscoped content", owner_id="content", metric="content_packages",
                operator="ge", target=1, config={"workflow": "content-package"})
            result = runtime.once(goal["id"])
            self.assertEqual("blocked", result["cycle"]["run_status"])
            self.assertTrue(any("content_request is required" in error
                                for error in result["cycle"]["data"]["action_result"]["attention"]["errors"]))
            self.assertEqual([], runtime.store.work_orders(status="open", goal_id=goal["id"]))

    def test_editorial_gate_rejects_copy_without_matching_icp(self):
        evidence = [{"kind": "content_copy", "payload": {
            "reader": self._request()["reader"], "renditions": {"threads": "copy"},
        }}]
        result = ContentDepartment().run_machine_step(
            self._context(evidence), {"step_id": "editorial_review", "workflow_id": "content-package"})
        self.assertEqual("blocked", result["run_status"])
        self.assertTrue(any("requested ICP exactly" in error for error in result["attention"]["errors"]))

    def test_editorial_gate_emits_final_text_artifact_when_copy_is_bound(self):
        request = self._request()
        evidence = [{"kind": "content_copy", "payload": {
            "icp": request["icp"], "reader": request["reader"],
            "renditions": {"threads": "copy", "youtube-shorts": {"narration": "copy"}},
        }}]
        result = ContentDepartment().run_machine_step(
            self._context(evidence), {"step_id": "editorial_review", "workflow_id": "content-package"})
        self.assertEqual("Content editorial review passed", result["message"])
        self.assertEqual({"editorial_report", "content_package", "content_ready"},
                         {item["kind"] for item in result["evidence"]})

    def test_durable_work_order_carries_the_full_content_request(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime = Runtime(Path(tmp) / "company.sqlite")
            goal = runtime.create_goal(
                name="One graphic", owner_id="design", metric="rendition_count",
                operator="ge", target=1,
                config={"workflow": "rendition-pack", "content_request": self._request()})
            runtime.once(goal["id"])
            order = runtime.store.work_orders(status="open", goal_id=goal["id"])[0]
            self.assertEqual(self._request(), order["brief"]["content_request"])
            self.assertEqual(goal["config"], order["brief"]["goal_config"])


if __name__ == "__main__":
    unittest.main()
