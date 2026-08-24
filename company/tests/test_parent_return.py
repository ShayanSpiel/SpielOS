"""P2.5D: child state returns to the parent without false parent achievement."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from company.runtime.director import Director
from company.runtime.loop import Runtime
from company.runtime.models import GoalHandler, GoalStatus, RunStatus, StageResult
from company.runtime.system_improvement import SystemImprovement
from company.tests.test_runtime import ImmediateHandler, IterativeHandler


class FailedHandler(GoalHandler):
    id = "failed_test"

    def observe(self, ctx):
        return StageResult("collect", {"ok": False})

    def decide(self, ctx, observation):
        return StageResult("diagnose", {"action": "fail"})

    def act(self, ctx, decision):
        return StageResult("execute", {"failed": True})

    def evaluate(self, ctx, action_result):
        return StageResult(
            "goal_check", {"failed": True}, RunStatus.FAILED,
            evaluation={
                "verdict": "failed", "goal_met": False,
                "metrics": {ctx.goal.metric: False}, "validity": "invalid",
            })


class ParentReturnTests(unittest.TestCase):
    def runtime(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        return Runtime(Path(self.temp.name) / "state.sqlite", {
            "director": Director(),
            "failed_test": FailedHandler(),
            "immediate_test": ImmediateHandler(),
            "iterative_test": IterativeHandler(),
            "system-improvement": SystemImprovement(),
        })

    def test_supporting_success_wakes_parent_without_achieving_it(self):
        runtime = self.runtime()
        parent = runtime.create_goal(
            name="Reach 30 percent replies", owner_id="director",
            metric="reply_rate", operator="ge", target=0.3, config={})
        child = runtime.create_goal(
            name="Ship a supporting artifact", owner_id="immediate_test",
            metric="done", operator="eq", target=True, parent_id=parent["id"], config={})
        cycle = runtime.store.cycle(parent["id"])
        runtime.store.update_cycle(
            cycle["id"], stage="OBSERVE", step="collect",
            run_status="waiting", data={})
        runtime.once(child["id"])
        parent_state = runtime.status(parent["id"])
        self.assertEqual(parent_state["cycle"]["run_status"], "idle")
        self.assertEqual(parent_state["cycle"]["stage"], "OBSERVE")
        measured = runtime.once(parent["id"])
        self.assertNotEqual(measured["goal"]["goal_status"], "achieved")
        self.assertFalse((measured.get("evaluation") or {}).get("goal_met", False))

    def test_system_improvement_success_resumes_originating_run(self):
        runtime = self.runtime()
        parent = runtime.create_goal(
            name="Reach 30 percent replies", owner_id="director",
            metric="reply_rate", operator="ge", target=0.3, config={})
        origin = runtime.create_goal(
            name="Outbound attempt", owner_id="iterative_test",
            metric="score", operator="ge", target=0.8, parent_id=parent["id"],
            run_type="business_experiment", config={})
        finished = runtime.once(origin["id"])
        self.assertEqual(finished["cycle"]["run_status"], "completed")
        first_run = finished["run"]["id"]
        repair = runtime.create_goal(
            name="Repair sender", owner_id="system-improvement",
            metric="acceptance_tests_passed", operator="eq", target=True,
            parent_id=parent["id"], run_type="system_improvement",
            evidence_validity="technical_only", resume_run_id=first_run,
            config={
                "owner_id": "email", "from_version": "2.0.0", "target_version": "2.0.1",
                "problem": "mapping", "allowed_files": ["email.py"],
                "acceptance_tests": ["python -m unittest"],
                "originating_run_id": first_run,
            })
        runtime.once(repair["id"])
        runtime.approve(repair["id"])
        blocked = runtime.once(repair["id"])
        runtime.complete_change(blocked["change_tasks"][0]["id"], passed=True,
                                result={"passed": True, "commands": ["python -m unittest"]})
        runtime.once(repair["id"])
        origin_state = runtime.status(origin["id"])
        self.assertEqual(origin_state["cycle"]["sequence"], 2)
        self.assertNotEqual(origin_state["run"]["id"], first_run)
        self.assertNotEqual(runtime.status(parent["id"])["goal"]["goal_status"], "achieved")

    def test_failed_child_surfaces_attention_without_satisfying_parent(self):
        runtime = self.runtime()
        parent = runtime.create_goal(
            name="Reach 30 percent replies", owner_id="director",
            metric="reply_rate", operator="ge", target=0.3, config={})
        child = runtime.create_goal(
            name="Failed supporting work", owner_id="failed_test",
            metric="done", operator="eq", target=True, parent_id=parent["id"], config={})
        runtime.once(parent["id"])
        failed = runtime.once(child["id"])
        self.assertEqual(failed["cycle"]["run_status"], "failed")
        parent_state = runtime.status(parent["id"])
        self.assertNotEqual(parent_state["goal"]["goal_status"], "achieved")
        kinds = {item["kind"] for item in parent_state["pending_notifications"]}
        self.assertIn("action_required", kinds)

    def test_paused_child_surfaces_attention_without_satisfying_parent(self):
        runtime = self.runtime()
        parent = runtime.create_goal(
            name="Reach 30 percent replies", owner_id="director",
            metric="reply_rate", operator="ge", target=0.3, config={})
        child = runtime.create_goal(
            name="Stuck supporting work", owner_id="immediate_test",
            metric="done", operator="eq", target=True, parent_id=parent["id"], config={})
        runtime.once(parent["id"])
        runtime.set_goal_status(child["id"], GoalStatus.PAUSED)
        parent_state = runtime.status(parent["id"])
        self.assertNotEqual(parent_state["goal"]["goal_status"], "achieved")
        kinds = {item["kind"] for item in parent_state["pending_notifications"]}
        self.assertIn("action_required", kinds)

    def test_duplicate_child_transition_does_not_duplicate_parent_runs(self):
        runtime = self.runtime()
        parent = runtime.create_goal(
            name="Reach 30 percent replies", owner_id="director",
            metric="reply_rate", operator="ge", target=0.3, config={})
        child = runtime.create_goal(
            name="One shot", owner_id="immediate_test",
            metric="done", operator="eq", target=True, parent_id=parent["id"], config={})
        cycle = runtime.store.cycle(parent["id"])
        runtime.store.update_cycle(
            cycle["id"], stage="OBSERVE", step="collect",
            run_status="waiting", data={})
        runtime.once(child["id"])
        sequence = runtime.status(parent["id"])["cycle"]["sequence"]
        runtime.once(child["id"])
        self.assertEqual(runtime.status(parent["id"])["cycle"]["sequence"], sequence)

    def test_pausing_ancestor_halts_descendants_and_claimed_work_orders(self):
        runtime = self.runtime()
        parent = runtime.create_goal(
            name="Reach 30 percent replies", owner_id="director",
            metric="reply_rate", operator="ge", target=0.3, config={})
        child = runtime.create_goal(
            name="Open assignment", owner_id="immediate_test",
            metric="done", operator="eq", target=True, parent_id=parent["id"], config={})
        cycle = runtime.store.cycle(child["id"])
        order = runtime.store.open_work_order(
            goal_id=child["id"], run_id=cycle["id"], employee_id="lead-researcher",
            needed=1, accepts_evidence=["lead_dossier"])
        runtime.store.claim_work_order(order["id"], "worker-1")
        runtime.set_goal_status(parent["id"], GoalStatus.PAUSED)
        self.assertEqual(runtime.store.goal(child["id"])["goal_status"], "paused")
        self.assertEqual(runtime.store.work_order(order["id"])["status"], "cancelled")
        self.assertFalse(runtime.continuation_decision(child["id"])["eligible"])

    def test_terminal_ancestor_halts_descendants_and_claimed_work_orders(self):
        for terminal_status in (
                GoalStatus.ABANDONED, GoalStatus.EXPIRED, GoalStatus.ACHIEVED):
            with self.subTest(status=terminal_status.value):
                runtime = self.runtime()
                parent = runtime.create_goal(
                    name="Reach 30 percent replies", owner_id="director",
                    metric="reply_rate", operator="ge", target=0.3, config={})
                child = runtime.create_goal(
                    name="Open assignment", owner_id="immediate_test",
                    metric="done", operator="eq", target=True,
                    parent_id=parent["id"], config={})
                cycle = runtime.store.cycle(child["id"])
                order = runtime.store.open_work_order(
                    goal_id=child["id"], run_id=cycle["id"],
                    employee_id="lead-researcher", needed=1,
                    accepts_evidence=["lead_dossier"])
                runtime.store.claim_work_order(order["id"], "worker-1")
                runtime.set_goal_status(parent["id"], terminal_status)
                self.assertEqual(runtime.store.goal(child["id"])["goal_status"], "paused")
                self.assertEqual(runtime.store.work_order(order["id"])["status"], "cancelled")
                self.assertFalse(runtime.continuation_decision(child["id"])["eligible"])
