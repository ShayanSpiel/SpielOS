"""P2.5E: one causal frontier with Batches inside Runs, not peer Goals."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from company.runtime.alignment import pursuit_kind
from company.runtime.director import Director
from company.runtime.loop import Runtime
from company.runtime.models import GoalHandler, GoalStatus, RunStatus, StageResult
from company.runtime.system_improvement import SystemImprovement


class FrontierHandler(GoalHandler):
    id = "frontier_test"
    version = "1.0.0"

    def observe(self, ctx):
        return StageResult("collect", {"sequence": ctx.cycle["sequence"]})

    def decide(self, ctx, observation):
        return StageResult("diagnose", {"action": "measure", **observation})

    def act(self, ctx, decision):
        return StageResult("execute", {"sequence": decision["sequence"]})

    def evaluate(self, ctx, action_result):
        sequence = action_result["sequence"]
        if sequence == 1:
            next_snapshot = {
                **ctx.goal.config,
                "batch": {"id": "reply-batch-02", "size": 10},
            }
            return StageResult(
                "goal_check", {"delivery_rate": 0.72}, RunStatus.COMPLETED,
                evaluation={
                    "verdict": "continue", "goal_met": False,
                    "metrics": {"delivery_rate": 0.72}, "validity": "business",
                    "next_experiment": {
                        "action": "test_next_batch",
                        "change_one_variable": "sender_mapping",
                    },
                },
                next_run={
                    "run_type": "business_experiment",
                    "config_snapshot": next_snapshot,
                    "controlled_variables": {"offer": "services", "batch_size": 10},
                    "changed_variables": {"sender_mapping": "repaired"},
                })
        return StageResult(
            "goal_check", {"delivery_rate": 0.96}, RunStatus.COMPLETED,
            goal_status=GoalStatus.ACHIEVED,
            evaluation={
                "verdict": "goal_met", "goal_met": True,
                "metrics": {"delivery_rate": 0.96}, "validity": "business",
                "next_experiment": {},
            })


class CausalFrontierTests(unittest.TestCase):
    def runtime(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        return Runtime(Path(self.temp.name) / "state.sqlite", {
            "director": Director(),
            "frontier_test": FrontierHandler(),
            "system-improvement": SystemImprovement(),
        })

    def test_batch_cannot_be_created_as_a_goal(self):
        runtime = self.runtime()
        with self.assertRaisesRegex(ValueError, "batch is not a Goal"):
            runtime.create_goal(
                name="Batch 1", owner_id="frontier_test",
                metric="delivery_rate", operator="ge", target=0.9,
                config={"pursuit_kind": "batch"})
        self.assertEqual(runtime.store.goals(), [])

    def test_one_reply_frontier_returns_through_repair_and_remeasures_parent(self):
        runtime = self.runtime()
        primary = runtime.create_goal(
            name="Reach 30 percent replies", owner_id="director",
            metric="reply_rate", operator="ge", target=0.3,
            config={"pursuit_kind": "primary_goal"})
        supporting = runtime.create_goal(
            name="Restore delivery as the selected bottleneck",
            owner_id="frontier_test", metric="delivery_rate",
            operator="ge", target=0.9, parent_id=primary["id"],
            run_type="business_experiment",
            controlled_variables={"offer": "services", "batch_size": 10},
            config={
                "pursuit_kind": "supporting_goal",
                "batch": {"id": "reply-batch-01", "size": 10},
            })
        primary_cycle = runtime.store.cycle(primary["id"])
        runtime.store.update_cycle(
            primary_cycle["id"], stage="OBSERVE", step="collect",
            run_status="waiting", data={})

        first = runtime.once(supporting["id"])
        first_run_id = first["run"]["id"]
        self.assertEqual(first["cycle"]["run_status"], "completed")
        self.assertIsNone(first["pending_notifications"][0]["payload"]
                          ["required_user_action"])

        repair = runtime.create_goal(
            name="Repair the sender mapping dependency",
            owner_id="system-improvement", metric="acceptance_tests_passed",
            operator="eq", target=True, parent_id=primary["id"],
            run_type="system_improvement", evidence_validity="technical_only",
            resume_run_id=first_run_id,
            config={
                "owner_id": "frontier_test", "from_version": "1.0.0",
                "target_version": "1.0.1", "problem": "sender mapping",
                "allowed_files": ["frontier.py"],
                "acceptance_tests": ["python -m unittest"],
                "originating_run_id": first_run_id,
            })
        runtime.once(repair["id"])
        runtime.approve(repair["id"])
        blocked = runtime.once(repair["id"])
        task = blocked["change_tasks"][0]
        runtime.complete_change(
            task["id"], passed=True,
            result={"passed": True, "commands": ["python -m unittest"]})
        runtime.once(repair["id"])

        resumed = runtime.status(supporting["id"])
        self.assertEqual(resumed["cycle"]["sequence"], 2)
        achieved = runtime.once(supporting["id"])
        self.assertEqual(achieved["goal"]["goal_status"], "achieved")

        measured = runtime.once(primary["id"])
        self.assertNotEqual(measured["goal"]["goal_status"], "achieved")
        self.assertFalse(measured["evaluation"]["goal_met"])
        children = runtime.store.goals(parent_id=primary["id"])
        business_children = [child for child in children
                             if pursuit_kind(child) == "supporting_goal"]
        self.assertEqual([child["id"] for child in business_children], [supporting["id"]])
        self.assertEqual(pursuit_kind(primary), "primary_goal")
        self.assertEqual(pursuit_kind(repair), "system_improvement_goal")
        self.assertNotIn("batch", {pursuit_kind(child) for child in children})


if __name__ == "__main__":
    unittest.main()
