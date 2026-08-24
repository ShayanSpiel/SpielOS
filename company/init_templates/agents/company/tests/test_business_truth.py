"""Integrity 6.2: a business Goal is achieved only by valid proof of its outcome."""

from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from company.runtime.director import Director
from company.runtime.interpreter import InterpretedDepartment
from company.runtime.loop import Runtime
from company.runtime.models import (
    Department, Goal, GoalContext, GoalStatus, RunStatus, StageResult,
    WorkflowSpec, WorkflowStep,
)
from company.runtime.system_improvement import SystemImprovement
from company.runtime.truth import (
    accepted_validities, is_business_outcome, is_explicitly_technical,
)
from company.tests.test_runtime import ImmediateHandler


class _LeadDepartment(InterpretedDepartment, Department):
    id = department_id = "truth_leads"
    version = "1.0.0"
    description = "Business-outcome fixture"
    agent_ids = ("content-strategist",)
    goal_schema = {"metrics": ["leads"], "config": {"workflow": {"enum": ["primary"]}}}
    evidence_metrics = {"leads": ("lead_record",)}
    workflows = (WorkflowSpec(
        "primary", "fixture", ("collect",), ("content-strategist",), (), (),
        ("lead_record",), (), graph=(
            WorkflowStep("collect", "employee", produces=("lead_record",)),
        )),)


class BusinessTruthDiscriminatorTests(unittest.TestCase):
    def test_config_cannot_widen_a_business_outcome(self):
        goal = {"owner_id": "director", "metric": "reply_rate",
                "config": {"accepted_evidence_validity": ["technical_only"]}}
        self.assertTrue(is_business_outcome(goal, {"run_type": "execution"}))
        self.assertEqual(accepted_validities(goal, {"run_type": "execution"}),
                         frozenset({"business"}))

    def test_system_improvement_stays_technical(self):
        goal = {"owner_id": "system-improvement", "metric": "acceptance_tests_passed"}
        run = {"run_type": "system_improvement"}
        self.assertTrue(is_explicitly_technical(goal, run))
        self.assertFalse(is_business_outcome(goal, run))
        self.assertIn("technical_only", accepted_validities(goal, run))


class BusinessTruthRuntimeTests(unittest.TestCase):
    def runtime(self, registry):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        return Runtime(Path(self.temp.name) / "state.sqlite", registry)

    def test_technical_children_do_not_achieve_business_parent(self):
        runtime = self.runtime({"director": Director(), "immediate_test": ImmediateHandler()})
        parent = runtime.create_goal(
            name="Generate 10 daily services leads", owner_id="director",
            metric="all_children_achieved", operator="eq", target=True, config={})
        for name in ("Build attribution", "Build pipeline"):
            child = runtime.create_goal(
                name=name, owner_id="immediate_test", metric="done",
                operator="eq", target=True, parent_id=parent["id"],
                run_type="system_improvement", evidence_validity="technical_only")
            self.assertEqual(runtime.once(child["id"])["goal"]["goal_status"], "achieved")
        result = runtime.once(parent["id"])
        self.assertNotEqual(result["goal"]["goal_status"], "achieved")
        self.assertFalse(result["evaluation"]["goal_met"])
        self.assertEqual(result["evaluation"]["metrics"]["achieved_children"], 0)

    def test_unrelated_business_children_do_not_satisfy_target_metric(self):
        runtime = self.runtime({"director": Director(), "immediate_test": ImmediateHandler()})
        parent = runtime.create_goal(
            name="Reach 30 percent reply rate", owner_id="director",
            metric="reply_rate", operator="ge", target=0.3, config={})
        child = runtime.create_goal(
            name="Ship a rendition", owner_id="immediate_test", metric="done",
            operator="eq", target=True, parent_id=parent["id"],
            evidence_validity="business")
        self.assertEqual(runtime.once(child["id"])["goal"]["goal_status"], "achieved")
        result = runtime.once(parent["id"])
        self.assertNotEqual(result["goal"]["goal_status"], "achieved")
        self.assertFalse(result["evaluation"]["goal_met"])
        self.assertIsNone(result["evaluation"]["metrics"]["reply_rate"])

    def test_invalid_evidence_of_the_right_kind_does_not_achieve(self):
        department = _LeadDepartment()
        runtime = self.runtime({"truth_leads": department})
        created = runtime.create_goal(
            name="One attributed lead", owner_id="truth_leads", metric="leads",
            operator="ge", target=1, config={"workflow": "primary"})
        runtime.add_evidence(created["id"], kind="lead_record", source="test",
                             payload={"lead": "x"}, validity="invalid")
        result = runtime.once(created["id"])
        self.assertNotEqual(result["goal"]["goal_status"], "achieved")
        row = runtime.store.goal(created["id"])
        cycle = runtime.store.cycle(created["id"])
        ctx = GoalContext(
            Goal(row["id"], row["name"], row["owner_id"], row["metric"],
                 row["operator"], row["target"], row["deadline"], row["parent_id"],
                 row["goal_status"], row["config"]),
            {**cycle, "run": runtime.store.run(cycle["id"]),
             "evidence": runtime.store.evidence(cycle["id"])},
            (), lambda _key: None)
        judged = department.evaluate(ctx, {"metric": "leads"})
        self.assertFalse(judged.evaluation["goal_met"])
        self.assertEqual(judged.evaluation["metrics"]["leads"], 0)

    def test_technical_goal_achieves_on_valid_technical_proof(self):
        runtime = self.runtime({"system-improvement": SystemImprovement()})
        goal = runtime.create_goal(
            name="Repair sender", owner_id="system-improvement",
            metric="acceptance_tests_passed", operator="eq", target=True,
            run_type="system_improvement", evidence_validity="technical_only",
            config={
                "owner_id": "email", "from_version": "2.0.0", "target_version": "2.0.1",
                "problem": "mapping", "allowed_files": ["email.py"],
                "acceptance_tests": ["python -m unittest"],
                "owner_override": True,
            })
        runtime.once(goal["id"])
        runtime.approve(goal["id"])
        blocked = runtime.once(goal["id"])
        runtime.complete_change(
            blocked["change_tasks"][0]["id"], passed=True,
            result={"passed": True, "commands": ["python -m unittest"]})
        complete = runtime.once(goal["id"])
        self.assertEqual(complete["goal"]["goal_status"], "achieved")
        self.assertEqual(complete["evaluation"]["validity"], "technical_only")
        self.assertTrue(complete["evaluation"]["goal_met"])

    def test_config_cannot_convert_business_parent_to_technical(self):
        runtime = self.runtime({"director": Director(), "immediate_test": ImmediateHandler()})
        parent = runtime.create_goal(
            name="Reply rate", owner_id="director", metric="reply_rate",
            operator="ge", target=0.3,
            config={"accepted_evidence_validity": ["technical_only"]})
        child = runtime.create_goal(
            name="Repair", owner_id="immediate_test", metric="done",
            operator="eq", target=True, parent_id=parent["id"],
            run_type="system_improvement", evidence_validity="technical_only")
        runtime.once(child["id"])
        result = runtime.once(parent["id"])
        self.assertNotEqual(result["goal"]["goal_status"], "achieved")
        self.assertEqual(
            result["cycle"]["data"]["evaluation"]["accepted_evidence_validity"],
            ["business"])

    def test_deadline_does_not_overwrite_an_achieved_goal(self):
        runtime = self.runtime({"immediate_test": ImmediateHandler()})
        goal = runtime.create_goal(
            name="Already done", owner_id="immediate_test", metric="done",
            operator="eq", target=True)
        achieved = runtime.once(goal["id"])
        self.assertEqual(achieved["goal"]["goal_status"], "achieved")
        past = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
        with runtime.store.connect() as con:
            con.execute("UPDATE goals SET deadline=? WHERE id=?", (past, goal["id"]))
        later = runtime.once(goal["id"])
        self.assertEqual(later["goal"]["goal_status"], "achieved")
        self.assertNotEqual(later["goal"]["goal_status"], GoalStatus.EXPIRED.value)

    def test_central_runtime_rejects_achieved_without_metric_proof(self):
        class BareAchieve(ImmediateHandler):
            id = "bare_achieve"

            def evaluate(self, ctx, action_result):
                return StageResult("goal_check", {"done": True}, RunStatus.IDLE,
                                   goal_status=GoalStatus.ACHIEVED)

        runtime = self.runtime({"bare_achieve": BareAchieve()})
        goal = runtime.create_goal(
            name="No proof", owner_id="bare_achieve", metric="reply_rate",
            operator="ge", target=0.3)
        result = runtime.once(goal["id"])
        self.assertNotEqual(result["goal"]["goal_status"], "achieved")


if __name__ == "__main__":
    unittest.main()
