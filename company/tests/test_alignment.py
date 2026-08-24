"""P2.5A: pursuit semantics and Goal-alignment policy."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from company.runtime.alignment import (
    ALIGNMENT_CLASSES, ALIGNMENT_JUDGMENTS, PURSUIT_INVARIANTS, PURSUIT_KINDS,
    UNKNOWN, judge_alignment, needs_alignment,
)
from company.runtime.director import Director, _system_intervention_lineage
from company.runtime.loop import Runtime
from company.runtime.models import Goal, GoalContext, GoalStatus, RunStatus, Stage
from company.runtime.system_improvement import SystemImprovement


COMPLETE_LINEAGE = {
    "observed_reality": "Transport failed for the controlled batch",
    "causal_hypothesis": "Provider result mapping drops successful sends",
    "smallest_intervention": "Repair outbound transport mapping only",
    "expected_measurable_effect": "Child run produces valid send evidence",
    "stop_condition": "Acceptance tests pass and the child can resume",
}


def _si_config(**extra):
    config = {
        "owner_id": "email", "from_version": "2.0.0", "target_version": "2.0.1",
        "problem": "provider mapping", "allowed_files": ["email.py"],
        "acceptance_tests": ["python -m unittest"],
    }
    config.update(extra)
    return config


class PursuitSemanticsTests(unittest.TestCase):
    def test_locked_kinds_and_invariants(self):
        self.assertEqual(set(PURSUIT_KINDS), {
            "primary_goal", "supporting_goal", "system_improvement_goal",
            "run", "batch", "task", "guardrail",
        })
        self.assertIn("Owner override is not strategic justification", PURSUIT_INVARIANTS)
        self.assertIn("Batch is not a Goal", PURSUIT_INVARIANTS)
        self.assertEqual(ALIGNMENT_CLASSES, ("supports", "enables", "protects", "explores"))
        self.assertEqual(ALIGNMENT_JUDGMENTS, ("aligned", "defer_recommended"))

    def test_system_improvement_requests_need_alignment(self):
        self.assertTrue(needs_alignment({"owner_id": "system-improvement"}))
        self.assertFalse(needs_alignment({"owner_id": "outbound",
                                          "run_type": "system_improvement"}))


class AlignmentJudgmentTests(unittest.TestCase):
    def test_market_outcome_supports_itself(self):
        request = {"owner_id": "outbound", "metric": "reply_rate", "name": "Replies"}
        judged = judge_alignment(request, active_outcomes=[])
        self.assertEqual(judged["judgment"], "aligned")
        self.assertEqual(judged["class"], "supports")
        self.assertFalse(judged["owner_override"])

    def test_unrelated_repair_is_deferred(self):
        judged = judge_alignment(
            {"owner_id": "system-improvement", "metric": "acceptance_tests_passed",
             "config": _si_config()},
            active_outcomes=[{"id": "goal-replies", "name": "Reach 30% reply rate",
                              "owner_id": "outbound", "metric": "reply_rate",
                              "goal_status": "active"}])
        self.assertEqual(judged["judgment"], "defer_recommended")
        self.assertIsNone(judged["class"])
        self.assertIn("Reach 30% reply rate", judged["opportunity_cost"])
        self.assertFalse(judged["owner_override"])

    def test_parent_market_outcome_enables(self):
        parent = {"id": "goal-replies", "name": "Reach 30% reply rate",
                  "owner_id": "outbound", "metric": "reply_rate", "goal_status": "active"}
        judged = judge_alignment(
            {"owner_id": "system-improvement", "metric": "acceptance_tests_passed",
             "config": _si_config()},
            active_outcomes=[parent], parent=parent)
        self.assertEqual(judged["judgment"], "aligned")
        self.assertEqual(judged["class"], "enables")
        self.assertEqual(judged["outcome_id"], "goal-replies")

    def test_director_rollup_is_not_a_market_outcome(self):
        parent = {"id": "goal-dir", "name": "Coordinate children",
                  "owner_id": "director", "metric": "all_children_achieved",
                  "goal_status": "active"}
        judged = judge_alignment(
            {"owner_id": "system-improvement", "metric": "acceptance_tests_passed",
             "config": _si_config()},
            active_outcomes=[parent], parent=parent)
        self.assertEqual(judged["judgment"], "defer_recommended")

    def test_declared_inactive_outcome_is_not_alignment(self):
        judged = judge_alignment(
            {"owner_id": "system-improvement", "metric": "acceptance_tests_passed",
             "config": _si_config(alignment={"class": "enables",
                                             "outcome_id": "goal-missing"})},
            active_outcomes=[{"id": "goal-replies", "name": "Replies",
                              "owner_id": "outbound", "metric": "reply_rate",
                              "goal_status": "active"}])
        self.assertEqual(judged["judgment"], "defer_recommended")
        self.assertIn("outcome_not_active", judged["defects"])

    def test_explicit_protects_and_explores_require_evidence_fields(self):
        empty_protect = judge_alignment(
            {"owner_id": "system-improvement", "metric": "acceptance_tests_passed",
             "config": _si_config(alignment={"class": "protects"})},
            active_outcomes=[])
        self.assertEqual(empty_protect["judgment"], "defer_recommended")
        protected = judge_alignment(
            {"owner_id": "system-improvement", "metric": "acceptance_tests_passed",
             "config": _si_config(alignment={
                 "class": "protects",
                 "invariant": "Business truth cannot be achieved by repairs"})},
            active_outcomes=[])
        self.assertEqual(protected["judgment"], "aligned")
        self.assertEqual(protected["class"], "protects")
        explored = judge_alignment(
            {"owner_id": "system-improvement", "metric": "acceptance_tests_passed",
             "config": _si_config(alignment={
                 "class": "explores",
                 "rationale": "Bounded probe of inbound capture"})},
            active_outcomes=[])
        self.assertEqual(explored["judgment"], "aligned")
        self.assertEqual(explored["class"], "explores")


class AlignmentRuntimeTests(unittest.TestCase):
    def runtime(self, registry=None):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        return Runtime(Path(self.temp.name) / "state.sqlite",
                       registry or {"system-improvement": SystemImprovement(),
                                    "director": Director()})

    def test_unrelated_improvement_defers_until_owner_overrides(self):
        runtime = self.runtime()
        outcome = runtime.create_goal(
            name="Reach 30 percent reply rate", owner_id="director",
            metric="reply_rate", operator="ge", target=0.3, config={})
        goal = runtime.create_goal(
            name="Polish unused icon set", owner_id="system-improvement",
            metric="acceptance_tests_passed", operator="eq", target=True,
            run_type="system_improvement", evidence_validity="technical_only",
            config=_si_config())
        self.assertEqual(goal["goal_status"], "proposed")
        alignment = goal["config"]["alignment"]
        self.assertEqual(alignment["judgment"], "defer_recommended")
        self.assertFalse(alignment["owner_override"])
        self.assertIn(outcome["id"], alignment["opportunity_cost"])
        decisions = runtime.store.decisions(runtime.store.cycle(goal["id"])["id"])
        self.assertEqual(decisions[0]["decision_type"], "alignment")
        self.assertNotEqual(decisions[0]["decision_type"], "system_improvement")
        with self.assertRaisesRegex(RuntimeError, "recommended deferral"):
            runtime.once(goal["id"])

        overridden = runtime.approve(goal["id"], note="do it anyway")
        self.assertEqual(overridden["goal"]["goal_status"], "active")
        stored = runtime.store.goal(goal["id"])["config"]["alignment"]
        self.assertEqual(stored["judgment"], "defer_recommended")
        self.assertTrue(stored["owner_override"])
        self.assertNotEqual(stored["judgment"], "aligned")
        override_types = {item["decision_type"]
                          for item in runtime.store.decisions(runtime.store.cycle(goal["id"])["id"])}
        self.assertIn("owner_override", override_types)
        self.assertNotIn("system_improvement", override_types)

        parked = runtime.once(goal["id"])
        self.assertEqual(parked["cycle"]["run_status"], "awaiting_approval")
        self.assertEqual(parked["cycle"]["step"], "review")
        self.assertIsNone(runtime.store.approval(
            goal["id"], runtime.store.cycle(goal["id"])["id"], "execute"))

    def test_resume_is_an_override_and_keeps_deferral_judgment(self):
        runtime = self.runtime()
        goal = runtime.create_goal(
            name="Unrelated repair", owner_id="system-improvement",
            metric="acceptance_tests_passed", operator="eq", target=True,
            run_type="system_improvement", evidence_validity="technical_only",
            config=_si_config())
        runtime.set_goal_status(goal["id"], GoalStatus.ACTIVE)
        stored = runtime.store.goal(goal["id"])["config"]["alignment"]
        self.assertEqual(stored["judgment"], "defer_recommended")
        self.assertTrue(stored["owner_override"])

    def test_create_time_override_starts_without_claiming_alignment(self):
        runtime = self.runtime()
        goal = runtime.create_goal(
            name="Forced repair", owner_id="system-improvement",
            metric="acceptance_tests_passed", operator="eq", target=True,
            run_type="system_improvement", evidence_validity="technical_only",
            config=_si_config(owner_override=True))
        self.assertEqual(goal["goal_status"], "active")
        self.assertEqual(goal["config"]["alignment"]["judgment"], "defer_recommended")
        self.assertTrue(goal["config"]["alignment"]["owner_override"])

    def test_child_of_market_outcome_is_aligned_and_runs(self):
        runtime = self.runtime()
        parent = runtime.create_goal(
            name="Reach 30 percent reply rate", owner_id="director",
            metric="reply_rate", operator="ge", target=0.3, config={})
        child = runtime.create_goal(
            name="Repair sender", owner_id="system-improvement",
            metric="acceptance_tests_passed", operator="eq", target=True,
            parent_id=parent["id"], run_type="system_improvement",
            evidence_validity="technical_only", config=_si_config())
        self.assertEqual(child["goal_status"], "active")
        self.assertEqual(child["config"]["alignment"]["judgment"], "aligned")
        self.assertEqual(child["config"]["alignment"]["class"], "enables")
        parked = runtime.once(child["id"])
        self.assertEqual(parked["cycle"]["run_status"], "awaiting_approval")


class DirectorAlignmentTests(unittest.TestCase):
    def _child(self, proposal):
        return {
            "id": "child-outbound", "goal_status": "active",
            "cycle": {"run_status": "completed"},
            "evaluation": {"run_id": "run-child", "validity": "contaminated",
                           "contamination_reason": "Transport failed for the controlled batch",
                           "next_experiment": {"system_improvement": proposal}},
        }

    def test_does_not_synthesize_lineage_from_files_or_tests(self):
        proposal = {
            "owner_id": "outbound", "from_version": "2.0.0", "target_version": "2.0.1",
            "problem": "Transport failures invalidated the acquisition experiment",
            "allowed_files": ["outbound.py"], "acceptance_tests": ["python -m unittest"],
        }
        goal = Goal("parent", "Increase qualified services leads", "director", "sales",
                    "ge", 10, None, None, "active", {})
        lineage = _system_intervention_lineage(goal, self._child(proposal), proposal)
        self.assertEqual(lineage["observed_reality"], "Transport failed for the controlled batch")
        self.assertEqual(lineage["causal_hypothesis"], UNKNOWN)
        self.assertEqual(lineage["smallest_intervention"], UNKNOWN)
        self.assertEqual(lineage["expected_measurable_effect"], UNKNOWN)
        self.assertEqual(lineage["stop_condition"], UNKNOWN)
        self.assertNotIn(str(len(proposal["allowed_files"])), lineage["smallest_intervention"])
        self.assertNotIn(str(len(proposal["acceptance_tests"])), lineage["stop_condition"])

        ctx = GoalContext(goal, {"children": (self._child(proposal),)}, (), lambda _key: None)
        result = Director().decide(ctx, {"children": [self._child(proposal)]})
        self.assertEqual(result.run_status, RunStatus.BLOCKED)
        self.assertEqual(result.decision["type"], "block_untraceable_system_improvement")
        self.assertIn("causal_hypothesis", result.payload["defects"])

    def test_defers_complete_lineage_that_does_not_serve_a_market_outcome(self):
        proposal = {
            "owner_id": "outbound", "from_version": "2.0.0", "target_version": "2.0.1",
            "problem": "Transport failures invalidated the acquisition experiment",
            "allowed_files": ["outbound.py"], "acceptance_tests": ["python -m unittest"],
            **COMPLETE_LINEAGE,
        }
        goal = Goal("parent", "Coordinate children", "director", "all_children_achieved",
                    "eq", True, None, None, "active", {})
        ctx = GoalContext(goal, {"children": (self._child(proposal),)}, (), lambda _key: None)
        result = Director().decide(ctx, {"children": [self._child(proposal)]})
        self.assertEqual(result.decision["type"], "recommend_defer")
        self.assertEqual(result.payload["action"], "request_owner_override")
        self.assertEqual(result.payload["alignment"]["judgment"], "defer_recommended")

    def test_owner_override_creates_child_without_relabeling_alignment(self):
        proposal = {
            "owner_id": "outbound", "from_version": "2.0.0", "target_version": "2.0.1",
            "problem": "Transport failures invalidated the acquisition experiment",
            "allowed_files": ["outbound.py"], "acceptance_tests": ["python -m unittest"],
            **COMPLETE_LINEAGE,
        }
        goal = Goal("parent", "Coordinate children", "director", "all_children_achieved",
                    "eq", True, None, None, "active", {})
        child = self._child(proposal)
        created = []
        ctx = GoalContext(
            goal, {"children": (child,)}, (),
            lambda key: "approved" if key == "alignment_override" else None,
            create_child_goal=lambda spec: created.append(spec) or {"id": "repair"})
        decision = Director().decide(ctx, {"children": [child]})
        Director().act(ctx, decision.payload)
        self.assertEqual(created[0]["config"]["alignment"]["judgment"], "defer_recommended")
        self.assertTrue(created[0]["config"]["owner_override"])
        self.assertNotEqual(created[0]["config"]["alignment"]["judgment"], "aligned")
