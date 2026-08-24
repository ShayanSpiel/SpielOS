import importlib.util
import io
import json
import os
import sqlite3
import subprocess
import tempfile
import time
import unittest
from contextlib import ExitStack, redirect_stdout, contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from company.runtime.director import Director
from company.departments.outbound.email_workflow import EmailWorkflow, outbound_context
from company.runtime.system_improvement import SystemImprovement
from company.runtime.models import GoalHandler, GoalContext, Goal, GoalStatus, RunStatus, Stage, StageResult
from company.runtime.runner import Runner
from company.runtime.service import RunnerService
from company.runtime.store import Store
from company.runtime.hooks import run_transition_hook
from company.runtime import hooks as runtime_hooks
from company.runtime import loop as runtime_loop
from company.runtime.loop import Runtime
from company.__main__ import main, render_report


class ApprovalHandler(GoalHandler):
    id = "approval_test"

    def observe(self, ctx):
        return StageResult("collect", {"real": True})

    def decide(self, ctx, observation):
        return StageResult("diagnose", {"action": "test", "observation": observation})

    def act(self, ctx, decision):
        if ctx.approval_status("execute") != "approved":
            return StageResult("review", {"prepared": True}, RunStatus.AWAITING_APPROVAL, Stage.ACT)
        return StageResult("execute", {"executed": True})

    def evaluate(self, ctx, action_result):
        validity = (ctx.cycle.get("run") or {}).get("evidence_validity") or "business"
        return StageResult("goal_check", {"goal_met": action_result.get("executed")},
                           RunStatus.IDLE, goal_status=GoalStatus.ACHIEVED,
                           evaluation={"verdict": "goal_met", "goal_met": True,
                                       "metrics": {ctx.goal.metric: True},
                                       "validity": validity})


class ImmediateHandler(GoalHandler):
    id = "immediate_test"

    def observe(self, ctx):
        return StageResult("collect", {"ok": True})

    def decide(self, ctx, observation):
        return StageResult("diagnose", {"action": "finish"})

    def act(self, ctx, decision):
        return StageResult("execute", {"done": True})

    def evaluate(self, ctx, action_result):
        validity = (ctx.cycle.get("run") or {}).get("evidence_validity") or "business"
        return StageResult("goal_check", {"done": True}, RunStatus.IDLE,
                           goal_status=GoalStatus.ACHIEVED,
                           evaluation={"verdict": "goal_met", "goal_met": True,
                                       "metrics": {ctx.goal.metric: True},
                                       "validity": validity},
                           learnings=[{"claim": "Immediate action worked", "evidence": {"done": True},
                                       "confidence": 1.0}])


class IterativeHandler(GoalHandler):
    id = "iterative_test"

    def observe(self, ctx):
        return StageResult("collect", {"sequence": ctx.cycle["sequence"]})

    def decide(self, ctx, observation):
        return StageResult("diagnose", {"action": "sample", **observation})

    def act(self, ctx, decision):
        return StageResult("execute", {"sample": decision["sequence"]})

    def evaluate(self, ctx, action_result):
        experiment = {"action": "sample_again", "change_one_variable": "sample"}
        return StageResult("goal_check", {"score": 0.2}, RunStatus.COMPLETED,
                           evaluation={"verdict": "continue", "goal_met": False,
                                       "metrics": {"score": 0.2}, "validity": "business",
                                       "next_experiment": experiment},
                           next_run={"run_type": "business_experiment",
                                     "changed_variables": {"sample": "next"}})


class RuntimeTests(unittest.TestCase):
    def runtime(self, registry):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        return Runtime(Path(self.temp.name) / "state.sqlite", registry)

    def test_stage_step_and_status_are_independent(self):
        runtime = self.runtime({"approval_test": ApprovalHandler()})
        goal = runtime.create_goal(name="Approval", owner_id="approval_test", metric="done",
                                   operator="eq", target=True, config={})
        parked = runtime.once(goal["id"])
        self.assertEqual(parked["cycle"]["stage"], "ACT")
        self.assertEqual(parked["cycle"]["step"], "review")
        self.assertEqual(parked["cycle"]["run_status"], "awaiting_approval")
        interaction = parked["pending_notifications"][0]["payload"]["approval_interaction"]
        self.assertEqual("Approval required", interaction["header"])
        self.assertEqual(["Approve", "Reject"],
                         [item["label"] for item in interaction["options"]])
        self.assertIn(goal["id"], interaction["fallback_command"])
        self.assertEqual("internal runtime", interaction["destination"])
        runtime.approve(goal["id"])
        complete = runtime.once(goal["id"])
        self.assertEqual(complete["goal"]["goal_status"], "achieved")
        self.assertEqual(complete["cycle"]["stage"], "OBSERVE")

    def test_unapproved_action_never_executes(self):
        runtime = self.runtime({"approval_test": ApprovalHandler()})
        goal = runtime.create_goal(name="Safe", owner_id="approval_test", metric="done",
                                   operator="eq", target=True, config={})
        first = runtime.once(goal["id"])
        second = runtime.once(goal["id"])
        self.assertEqual(first["cycle"]["data"], second["cycle"]["data"])
        self.assertEqual(len(runtime.store.events(goal["id"])), 4)

    def test_expired_goal_never_runs(self):
        runtime = self.runtime({"immediate_test": ImmediateHandler()})
        goal = runtime.create_goal(name="Expired", owner_id="immediate_test", metric="done",
                                   operator="eq", target=True, deadline="2000-01-01T00:00:00Z", config={})
        result = runtime.once(goal["id"])
        self.assertEqual(result["goal"]["goal_status"], "expired")
        self.assertEqual(result["cycle"]["stage"], "OBSERVE")

    def test_lease_prevents_two_clients_running_same_goal(self):
        runtime = self.runtime({"immediate_test": ImmediateHandler()})
        goal = runtime.create_goal(name="Exclusive", owner_id="immediate_test", metric="done",
                                   operator="eq", target=True, config={})
        self.assertTrue(runtime.store.acquire(goal["id"], "opencode"))
        with self.assertRaisesRegex(RuntimeError, "already running"):
            runtime.once(goal["id"], holder="codex")
        runtime.store.release(goal["id"], "opencode")

    def test_completed_unmet_run_continues_without_company_next(self):
        runtime = self.runtime({"iterative_test": IterativeHandler()})
        goal = runtime.create_goal(name="Improve score", owner_id="iterative_test",
                                   metric="score", operator="ge", target=0.8,
                                   run_type="business_experiment", config={})
        completed = runtime.once(goal["id"])
        self.assertEqual(completed["cycle"]["run_status"], "completed")
        self.assertEqual(completed["cycle"]["sequence"], 1)
        notes = runtime.store.notifications("pending")
        self.assertEqual([note["kind"] for note in notes], ["run_completed"])
        self.assertIsNone(notes[0]["payload"]["required_user_action"])
        self.assertIn("starts automatically", notes[0]["why_next"])

        continued = runtime.once(goal["id"])
        self.assertEqual(continued["cycle"]["sequence"], 2)
        self.assertEqual(continued["run"]["changed_variables"], {"sample": "next"})
        events = runtime.store.events(goal["id"])
        started = [item for item in events if item["kind"] == "run.started"
                   and item["payload"].get("automatic")]
        self.assertTrue(started)

    def test_email_shortfall_emits_typed_director_action(self):
        runtime = self.runtime({"email": EmailWorkflow()})
        goal = runtime.create_goal(name="Email batch", owner_id="email", metric="reply_rate",
                                   operator="ge", target=0.3, run_type="business_experiment",
                                   config={"execution_mode": "dry_run", "batch_size": 10})
        fake = SimpleNamespace(
            stop_file=Path(self.temp.name) / "STOP",
            workflow=SimpleNamespace(observe=lambda _ctx: {"queue": {"size": 3}}),
            control=SimpleNamespace(knobs=lambda: {"block_size": 10,
                                                   "cohort_filters": {"min_tier": "Verified"}}),
        )
        with patch("company.departments.outbound.email_workflow.outbound_context", return_value=fake):
            blocked = runtime.once(goal["id"])
        self.assertEqual(blocked["cycle"]["run_status"], "blocked")
        self.assertEqual(blocked["cycle"]["data"]["decision"]["needed_leads"], 7)
        note = runtime.store.notifications("pending")[0]
        self.assertEqual(note["kind"], "action_required")
        self.assertEqual(note["payload"]["attention"]["capability"], "lead_research")
        self.assertIn("company retry", note["payload"]["next_trigger"])
        orders = runtime.store.work_orders(status="open", goal_id=goal["id"])
        self.assertEqual(1, len(orders))
        self.assertEqual("lead-researcher", orders[0]["employee_id"])
        self.assertEqual(7, orders[0]["needed"])
        self.assertEqual(note["payload"]["work_order_id"], orders[0]["id"])

    def test_director_dispatches_child_and_completes(self):
        runtime = self.runtime({"director": Director(), "immediate_test": ImmediateHandler()})
        parent = runtime.create_goal(name="Company outcome", owner_id="director",
                                     metric="all_children_achieved", operator="eq", target=True, config={})
        child = runtime.create_goal(name="Child outcome", owner_id="immediate_test", metric="done",
                                    operator="eq", target=True, parent_id=parent["id"], config={})
        result = runtime.once(parent["id"])
        self.assertEqual(runtime.status(child["id"])["goal"]["goal_status"], "achieved")
        self.assertEqual(result["goal"]["goal_status"], "achieved")
        self.assertEqual((), runtime.store.memories("immediate_test", child["id"]))

    def test_director_technical_children_cannot_satisfy_business_outcome(self):
        runtime = self.runtime({"director": Director(), "immediate_test": ImmediateHandler()})
        parent = runtime.create_goal(
            name="Generate 10 daily services leads", owner_id="director",
            metric="all_children_achieved", operator="eq", target=True, config={})
        children = [runtime.create_goal(
            name=name, owner_id="immediate_test", metric="done", operator="eq", target=True,
            parent_id=parent["id"], run_type="system_improvement",
            evidence_validity="technical_only", config={}) for name in (
                "Build attribution infrastructure", "Build content pipeline infrastructure")]

        for child in children:
            self.assertEqual(runtime.once(child["id"])["goal"]["goal_status"], "achieved")

        result = runtime.once(parent["id"])

        self.assertNotEqual(result["goal"]["goal_status"], "achieved")
        self.assertFalse(result["evaluation"]["goal_met"])
        self.assertEqual(result["cycle"]["data"]["evaluation"]["achieved_children"], 2)
        self.assertEqual(result["cycle"]["data"]["evaluation"]["accepted_achieved_children"], 0)

    def test_director_system_improvement_decision_preserves_strategic_lineage(self):
        goal = Goal("parent", "Increase qualified services leads", "director", "sales",
                    "ge", 10, None, None, "active", {})
        proposal = {
            "owner_id": "outbound", "from_version": "2.0.0", "target_version": "2.0.1",
            "problem": "Transport failures invalidated the acquisition experiment",
            "allowed_files": ["outbound.py"], "acceptance_tests": ["python -m unittest"],
            "observed_reality": "Transport failed for the controlled batch",
            "causal_hypothesis": "Provider result mapping drops successful sends",
            "smallest_intervention": "Repair outbound transport mapping only",
            "expected_measurable_effect": "Child run produces valid send evidence",
            "stop_condition": "Acceptance tests pass and the child can resume",
        }
        child = {
            "id": "child-outbound", "goal_status": "active",
            "cycle": {"run_status": "completed"},
            "evaluation": {"run_id": "run-child", "validity": "contaminated",
                           "contamination_reason": "Transport failed for the controlled batch",
                           "next_experiment": {"system_improvement": proposal}},
        }
        created = []
        ctx = GoalContext(goal, {"children": (child,)}, (), lambda _key: None,
                          create_child_goal=lambda spec: created.append(spec) or {"id": "repair"})

        decision = Director().decide(ctx, {"children": [child]})
        lineage = decision.decision["payload"]["strategic_lineage"]

        self.assertEqual(lineage["business_goal"]["id"], "parent")
        self.assertEqual(lineage["observed_reality"], "Transport failed for the controlled batch")
        self.assertEqual(lineage["diagnosis_level"], "system")
        self.assertTrue(lineage["causal_hypothesis"])
        self.assertTrue(lineage["smallest_intervention"])
        self.assertTrue(lineage["expected_measurable_effect"])
        self.assertTrue(lineage["stop_condition"])
        self.assertTrue(lineage["non_goals"])

        Director().act(ctx, decision.payload)
        self.assertEqual(created[0]["config"]["strategic_lineage"], lineage)

    def test_director_system_improvement_decision_links_child_evidence(self):
        runtime = self.runtime({
            "director": Director(),
            "immediate_test": ImmediateHandler(),
            "system-improvement": SystemImprovement(),
        })
        parent = runtime.create_goal(
            name="Increase qualified services leads", owner_id="director",
            metric="sales", operator="ge", target=10, config={})
        child = runtime.create_goal(
            name="Run acquisition transport", owner_id="immediate_test",
            metric="done", operator="eq", target=True,
            parent_id=parent["id"], config={})
        relevant = runtime.store.add_evidence(
            child["id"], runtime.store.cycle(child["id"])["id"],
            "transport_failure", "outbound", {"failed": True}, "contaminated")
        runtime.store.add_evidence(
            child["id"], runtime.store.cycle(child["id"])["id"],
            "market_observation", "outbound", {"visible": True}, "business")
        proposal = {
            "owner_id": "outbound", "from_version": "2.0.0",
            "target_version": "2.0.1", "problem": "Transport mapping failed",
            "allowed_files": ["outbound.py"],
            "acceptance_tests": ["python -m unittest"],
            "observed_reality": "Transport failed for the controlled batch",
            "causal_hypothesis": "Provider mapping drops successful sends",
            "smallest_intervention": "Repair outbound transport mapping only",
            "expected_measurable_effect": "The child produces valid send evidence",
            "stop_condition": "Acceptance passes and the child can resume",
        }
        child_run = runtime.store.cycle(child["id"])["id"]
        runtime.store.add_evaluation(child["id"], child_run, {
            "verdict": "contaminated", "goal_met": False,
            "metrics": {"done": False}, "validity": "contaminated",
            "contamination_reason": "Transport failed for the controlled batch",
            "next_experiment": {"system_improvement": proposal},
        })
        runtime.store.update_cycle(
            child_run, stage="OBSERVE", step="goal_check",
            run_status="completed", data={})
        runtime.store.update_run(
            child_run, status="completed", validity="contaminated",
            contamination_reason="Transport failed for the controlled batch")

        runtime.once(parent["id"])

        decisions = runtime.store.decisions(runtime.store.cycle(parent["id"])["id"])
        intervention = next(item for item in decisions
                            if item["decision_type"] == "system_improvement")
        self.assertEqual(intervention["evidence_ids"], [relevant["id"]])

    def test_director_blocks_untraceable_system_improvement(self):
        goal = Goal("parent", "Increase qualified services leads", "director", "sales",
                    "ge", 10, None, None, "active", {})
        child = {
            "id": "child-outbound", "goal_status": "active",
            "cycle": {"run_status": "completed"},
            "evaluation": {"run_id": "run-child", "validity": "contaminated",
                           "contamination_reason": "",
                           "next_experiment": {"system_improvement": {
                               "owner_id": "outbound", "from_version": "2.0.0",
                               "target_version": "2.0.1", "allowed_files": ["outbound.py"],
                               "acceptance_tests": ["python -m unittest"]}}},
        }
        ctx = GoalContext(goal, {"children": (child,)}, (), lambda _key: None)

        result = Director().decide(ctx, {"children": [child]})

        self.assertEqual(result.run_status, RunStatus.BLOCKED)
        self.assertEqual(result.decision["type"], "block_untraceable_system_improvement")
        self.assertIn("observed_reality", result.payload["defects"])
        self.assertNotEqual(result.payload["action"], "create_system_improvement")

    def test_director_surfaces_child_approval_without_approving_it(self):
        runtime = self.runtime({"director": Director(), "approval_test": ApprovalHandler()})
        parent = runtime.create_goal(name="Company outcome", owner_id="director",
                                     metric="all_children_achieved", operator="eq", target=True, config={})
        child = runtime.create_goal(name="Guarded child", owner_id="approval_test", metric="done",
                                    operator="eq", target=True, parent_id=parent["id"], config={})
        runtime.once(parent["id"])
        blocked = runtime.once(parent["id"])
        self.assertEqual(blocked["cycle"]["run_status"], "waiting")
        self.assertEqual(runtime.status(child["id"])["cycle"]["run_status"], "awaiting_approval")
        runtime.approve(child["id"])
        runtime.once(child["id"])
        complete = runtime.once(parent["id"])
        self.assertEqual(complete["goal"]["goal_status"], "achieved")

    def test_email_bridge_loads_existing_engine_without_running_it(self):
        context = outbound_context(dry=True)
        self.assertEqual(EmailWorkflow.id, "email")
        self.assertEqual(context.workflow.name, "email")

    def test_email_bridge_honors_existing_stop_switch(self):
        with tempfile.TemporaryDirectory() as directory:
            stop = Path(directory) / "STOP"
            stop.touch()
            goal = Goal("g", "Email", "email", "reply_rate", "ge", 0.3, None, None,
                        "active", {"execution_mode": "dry_run"})
            context = GoalContext(goal, {"data": {}}, (), lambda key: None)
            with patch("company.departments.outbound.email_workflow.outbound_context", return_value=SimpleNamespace(stop_file=stop)):
                result = EmailWorkflow().observe(context)
            self.assertEqual(result.run_status, RunStatus.BLOCKED)
            self.assertEqual(result.next_stage, Stage.OBSERVE)

    def test_email_bridge_dry_run_still_requires_approval(self):
        with tempfile.TemporaryDirectory() as directory:
            stop = Path(directory) / "STOP"
            row = {"id": "batch-1", "batch": {"emails": [{"lead_id": "lead-1"}]},
                   "preview_path": "/tmp/preview.md"}
            outbound = SimpleNamespace(stop_file=stop, store=SimpleNamespace(get_batch=lambda batch_id: row))
            goal = Goal("g", "Email", "email", "reply_rate", "ge", 0.3, None, None,
                        "active", {"execution_mode": "dry_run"})
            first_ctx = GoalContext(goal, {"data": {}}, (), lambda key: None)
            with patch("company.departments.outbound.email_workflow.outbound_context", return_value=outbound), \
                 patch("company.departments.outbound.execution.prepare", return_value=row), \
                 patch("company.departments.outbound.execution.validate", return_value=[]), \
                 patch("company.departments.outbound.execution.gate", return_value={"ok": True}):
                parked = EmailWorkflow().act(first_ctx, {"action": "prepare_batch"})
            self.assertEqual(parked.run_status, RunStatus.AWAITING_APPROVAL)

            second_ctx = GoalContext(goal, {"data": {"action_result": parked.payload}}, (),
                                       lambda key: "approved")
            with patch("company.departments.outbound.email_workflow.outbound_context", return_value=outbound), \
                 patch("company.departments.outbound.execution.execute", return_value={"sent": 0, "note": "dry"}) as execute:
                result = EmailWorkflow().act(second_ctx, {"action": "prepare_batch"})
            execute.assert_called_once_with(outbound, row, dry=True)
            self.assertEqual(result.run_status, RunStatus.WAITING)
            self.assertEqual(result.next_stage, Stage.EVALUATE)

    def test_live_business_reply_goal_requires_observable_capture(self):
        goal = Goal("g", "Replies", "email", "reply_rate", "ge", 0.3, None, None,
                    "active", {"execution_mode": "live", "evidence_window_hours": 48})
        context = GoalContext(goal, {"data": {}}, (), lambda key: None)
        result = EmailWorkflow().act(context, {"action": "prepare_batch"})
        self.assertEqual(result.run_status, RunStatus.BLOCKED)
        self.assertEqual(result.attention["capability"], "inbound_email_setup")
        self.assertIn("reply evidence source", result.payload["reason"])

    def test_typed_run_preserves_hypothesis_variables_and_version(self):
        runtime = self.runtime({"immediate_test": ImmediateHandler()})
        goal = runtime.create_goal(
            name="Typed", owner_id="immediate_test", metric="done", operator="eq", target=True,
            run_type="business_experiment", evidence_validity="business",
            hypothesis={"statement": "Changing X improves Y", "variable": "x", "prediction": "Y rises"},
            controlled_variables={"offer": "fixed"}, changed_variables={"x": "variant-b"}, config={})
        state = runtime.status(goal["id"])
        self.assertEqual(state["run"]["run_type"], "business_experiment")
        self.assertEqual(state["run"]["owner_version"], "1.0.0")
        self.assertEqual(state["run"]["controlled_variables"], {"offer": "fixed"})
        self.assertTrue(state["run"]["hypothesis_id"].startswith("hyp-"))

    def test_system_improvement_requires_approval_then_versions_result(self):
        runtime = self.runtime({"system-improvement": SystemImprovement()})
        goal = runtime.create_goal(
            name="Repair sender", owner_id="system-improvement",
            metric="acceptance_tests_passed", operator="eq", target=True,
            run_type="system_improvement", evidence_validity="technical_only", config={
                "owner_id": "email", "from_version": "2.0.0", "target_version": "2.0.1",
                "problem": "provider result mapping is wrong", "allowed_files": ["email.py"],
                "acceptance_tests": ["python -m unittest"], "originating_run_id": "run-origin",
                "owner_override": True})
        parked = runtime.once(goal["id"])
        self.assertEqual(parked["cycle"]["run_status"], "awaiting_approval")
        runtime.approve(goal["id"])
        blocked = runtime.once(goal["id"])
        self.assertEqual(blocked["cycle"]["step"], "execute_change")
        task = blocked["change_tasks"][0]
        runtime.complete_change(task["id"], passed=True,
                                result={"passed": True, "commands": ["python -m unittest"]})
        complete = runtime.once(goal["id"])
        self.assertEqual(complete["goal"]["goal_status"], "achieved")
        versions = runtime.store.owner_versions("email")
        self.assertEqual(versions[-1]["version"], "2.0.1")

    def test_test_inbox_batch_prepares_without_sending(self):
        runtime = self.runtime({"email": EmailWorkflow()})
        goal = runtime.create_goal(name="Test replies", owner_id="email", metric="reply_rate",
                                   operator="ge", target=0.3, run_type="system_test",
                                   evidence_validity="technical_only", config={
                                       "audience_type": "test_inbox", "execution_mode": "live",
                                       "test_recipients": ["one@example.com", "two@example.com"],
                                       "throttle_seconds": 0, "evidence_window_hours": 24,
                                       "reply_capture": "manual_inbox"})
        with patch("company.departments.outbound.email_workflow._write_test_preview", return_value=Path("/tmp/preview.md")):
            parked = runtime.once(goal["id"])
        self.assertEqual(parked["cycle"]["run_status"], "awaiting_approval")
        self.assertEqual(parked["cycle"]["step"], "review")
        self.assertEqual(parked["cycle"]["data"]["action_result"]["recipients"],
                         ["one@example.com", "two@example.com"])

    def test_four_inbox_flow_wakes_at_two_replies_and_achieves_goal(self):
        runtime = self.runtime({"email": EmailWorkflow()})
        recipients = [f"test-{index}@example.com" for index in range(4)]
        goal = runtime.create_goal(name="Four inboxes", owner_id="email", metric="reply_rate",
                                   operator="ge", target=0.3, run_type="system_test",
                                   evidence_validity="technical_only", config={
                                       "audience_type": "test_inbox", "execution_mode": "live",
                                       "test_recipients": recipients, "throttle_seconds": 0,
                                       "evidence_window_hours": 24,
                                       "reply_capture": "manual_inbox"})
        with patch("company.departments.outbound.email_workflow._write_test_preview", return_value=Path("/tmp/preview.md")):
            runtime.once(goal["id"])
        runtime.approve(goal["id"])
        with patch("company.departments.outbound.workflows.email.providers.send_email",
                   side_effect=[{"id": f"provider-{index}"} for index in range(4)]):
            waiting = runtime.once(goal["id"])
        self.assertEqual(waiting["cycle"]["run_status"], "waiting")
        self.assertEqual(len([item for item in waiting["evidence"] if item["kind"] == "email_sent"]), 4)
        runtime.add_evidence(goal["id"], kind="reply", source="test",
                             payload={"recipient": recipients[0]}, validity="technical_only")
        one_reply = runtime.status(goal["id"])
        self.assertGreater(one_reply["cycle"]["resume_at"], datetime.now(timezone.utc).isoformat())
        runtime.add_evidence(goal["id"], kind="reply", source="test",
                             payload={"recipient": recipients[1]}, validity="technical_only")
        with patch("company.departments.outbound.email_workflow._observe_test_provider", return_value=[]):
            complete = runtime.once(goal["id"])
        self.assertEqual(complete["goal"]["goal_status"], "achieved")
        self.assertEqual(complete["evaluation"]["metrics"]["reply_rate"], 0.5)

    def test_email_run_completes_reports_and_waits_for_next_run_approval(self):
        runtime = self.runtime({"email": EmailWorkflow()})
        recipients = [f"loop-{index}@example.com" for index in range(4)]
        goal = runtime.create_goal(name="Improve replies", owner_id="email", metric="reply_rate",
                                   operator="ge", target=0.3, run_type="system_test",
                                   evidence_validity="technical_only", config={
                                       "audience_type": "test_inbox", "execution_mode": "live",
                                       "test_recipients": recipients, "throttle_seconds": 0,
                                       "evidence_window_hours": 0,
                                       "reply_capture": "manual_inbox"})
        with patch("company.departments.outbound.email_workflow._write_test_preview",
                   return_value=Path("/tmp/preview.md")), \
             patch("company.departments.outbound.workflows.email.providers.send_email",
                   side_effect=[{"id": f"provider-{index}"} for index in range(4)]), \
             patch("company.departments.outbound.email_workflow._observe_test_provider", return_value=[]):
            runtime.once(goal["id"])
            runtime.approve(goal["id"])
            Runner(runtime).tick(goal["id"])

        next_state = runtime.status(goal["id"])
        self.assertEqual(next_state["goal"]["goal_status"], "active")
        self.assertEqual(next_state["cycle"]["sequence"], 2)
        self.assertEqual(next_state["cycle"]["run_status"], "awaiting_approval")
        self.assertEqual(next_state["run"]["changed_variables"], {"test_token": "new_run_token"})
        self.assertIsNone(runtime.store.approval(
            goal["id"], next_state["cycle"]["id"], "execute"))
        evaluation = runtime.store.latest_evaluation_for_goal(goal["id"])
        self.assertEqual(evaluation["verdict"], "not_yet")
        self.assertEqual(evaluation["next_experiment"]["change_one_variable"], "test_token")
        self.assertIn("run_completed",
                      {item["kind"] for item in runtime.store.notifications("pending")})

    def test_resend_observer_imports_opens_and_replies_then_achieves_goal(self):
        runtime = self.runtime({"email": EmailWorkflow()})
        recipients = [f"auto-{index}@example.com" for index in range(4)]
        goal = runtime.create_goal(name="Automatic replies", owner_id="email", metric="reply_rate",
                                   operator="ge", target=0.3, run_type="system_test",
                                   evidence_validity="technical_only", config={
                                       "audience_type": "test_inbox", "execution_mode": "live",
                                       "provider": "resend", "test_recipients": recipients,
                                       "throttle_seconds": 0, "evidence_window_hours": 24,
                                       "observer_interval_seconds": 300,
                                       "reply_capture": "resend_inbound"})
        with patch("company.departments.outbound.email_workflow._write_test_preview", return_value=Path("/tmp/preview.md")):
            runtime.once(goal["id"])
        runtime.approve(goal["id"])
        with patch("company.departments.outbound.workflows.email.config.REPLY_TO", "runs@reply.example.com"), \
             patch("company.departments.outbound.workflows.email.providers.receiving_domain_status",
                   return_value={"ready": True, "domain": "reply.example.com"}), \
             patch("company.departments.outbound.workflows.email.providers.send_email_via",
                   side_effect=[{"id": f"resend-{index}"} for index in range(4)]):
            waiting = runtime.once(goal["id"])
        action = waiting["cycle"]["data"]["action_result"]
        runtime.store.update_cycle(waiting["cycle"]["id"], stage="EVALUATE", step="measure",
                                   run_status="waiting", resume_at=datetime.now(timezone.utc).isoformat(),
                                   data=waiting["cycle"]["data"])
        received = [{"id": f"received-{index}", "from": recipients[index],
                     "subject": f"Re: {action['subject']}",
                     "created_at": datetime.now(timezone.utc).isoformat()}
                    for index in range(2)]
        with patch("company.departments.outbound.workflows.email.providers.fetch_email_status",
                   return_value={"last_event": "opened"}), \
             patch("company.departments.outbound.workflows.email.providers.list_received_emails",
                   return_value={"data": received}):
            complete = runtime.once(goal["id"])
        self.assertEqual(complete["goal"]["goal_status"], "achieved")
        self.assertEqual(complete["evaluation"]["metrics"]["reply_rate"], 0.5)
        self.assertEqual(complete["evaluation"]["metrics"]["automatic_replies"], 2)
        kinds = [item["kind"] for item in complete["evidence"]]
        self.assertEqual(kinds.count("email_opened"), 4)
        self.assertEqual(kinds.count("reply"), 2)

    def test_resend_inbound_mode_blocks_without_reply_to(self):
        runtime = self.runtime({"email": EmailWorkflow()})
        goal = runtime.create_goal(name="Missing inbound", owner_id="email", metric="reply_rate",
                                   operator="ge", target=0.3, run_type="system_test",
                                   evidence_validity="technical_only", config={
                                       "audience_type": "test_inbox", "execution_mode": "live",
                                       "provider": "resend", "test_recipients": ["one@example.com"],
                                       "throttle_seconds": 0, "evidence_window_hours": 24,
                                       "reply_capture": "resend_inbound"})
        with patch("company.departments.outbound.email_workflow._write_test_preview", return_value=Path("/tmp/preview.md")):
            runtime.once(goal["id"])
        runtime.approve(goal["id"])
        with patch("company.departments.outbound.workflows.email.config.REPLY_TO", ""):
            blocked = runtime.once(goal["id"])
        self.assertEqual(blocked["cycle"]["run_status"], "blocked")
        self.assertIn("REPLY_TO", blocked["cycle"]["data"]["action_result"]["error"])

    def test_event_only_waiting_does_not_advance_without_wake(self):
        runtime = self.runtime({"director": Director(), "approval_test": ApprovalHandler()})
        parent = runtime.create_goal(name="Company outcome", owner_id="director",
                                     metric="all_children_achieved", operator="eq", target=True, config={})
        runtime.create_goal(name="Guarded child", owner_id="approval_test", metric="done",
                            operator="eq", target=True, parent_id=parent["id"], config={})
        runtime.once(parent["id"])
        waiting = runtime.once(parent["id"])
        self.assertEqual(waiting["cycle"]["run_status"], "waiting")
        self.assertIsNone(waiting["cycle"]["resume_at"])
        unchanged = runtime.once(parent["id"])
        self.assertEqual(unchanged["cycle"], waiting["cycle"])

    def test_runner_continues_child_evaluation_and_parent_goal(self):
        runtime = self.runtime({"director": Director(), "email": EmailWorkflow()})
        parent = runtime.create_goal(name="Reply outcome", owner_id="director",
                                     metric="reply_rate", operator="ge", target=0.3,
                                     evidence_validity="technical_only",
                                     config={"accepted_evidence_validity": ["technical_only"]})
        recipients = [f"runner-{index}@example.com" for index in range(4)]
        child = runtime.create_goal(name="Email child", owner_id="email", metric="reply_rate",
                                    operator="ge", target=0.3, parent_id=parent["id"],
                                    run_type="system_test", evidence_validity="technical_only", config={
                                        "audience_type": "test_inbox", "execution_mode": "live",
                                        "test_recipients": recipients, "throttle_seconds": 0,
                                        "evidence_window_hours": 24,
                                        "reply_capture": "manual_inbox"})
        runner = Runner(runtime)
        with patch("company.departments.outbound.email_workflow._write_test_preview", return_value=Path("/tmp/preview.md")):
            runner.tick(parent["id"])
        self.assertEqual(runtime.status(child["id"])["cycle"]["run_status"], "awaiting_approval")
        self.assertEqual(runtime.status(parent["id"])["cycle"]["run_status"], "waiting")

        runtime.approve(child["id"])
        with patch("company.departments.outbound.workflows.email.providers.send_email",
                   side_effect=[{"id": f"runner-provider-{index}"} for index in range(4)]):
            runner.tick(parent["id"])
        self.assertEqual(runtime.status(child["id"])["cycle"]["run_status"], "waiting")

        for recipient in recipients[:2]:
            runtime.add_evidence(child["id"], kind="reply", source="test",
                                 payload={"recipient": recipient}, validity="technical_only")
        with patch("company.departments.outbound.email_workflow._observe_test_provider", return_value=[]):
            outcome = runner.tick(child["id"])
        self.assertTrue(outcome["advanced"])
        self.assertEqual(runtime.status(child["id"])["goal"]["goal_status"], "achieved")
        # Parent is a business reply-rate outcome; a technical system_test child
        # cannot convert it into a technical readiness Goal.
        self.assertNotEqual(runtime.status(parent["id"])["goal"]["goal_status"], "achieved")
        kinds = {item["kind"] for item in runtime.store.notifications("pending")}
        self.assertIn("goal_achieved", kinds)

    def test_new_department_task_requires_and_persists_department_spec(self):
        runtime = self.runtime({"system-improvement": SystemImprovement()})
        invalid = runtime.create_goal(
            name="Build Content Department", owner_id="system-improvement",
            metric="acceptance_tests_passed", operator="eq", target=True,
            run_type="system_improvement", evidence_validity="technical_only", config={
                "change_kind": "create_department", "owner_id": "content",
                "from_version": "new", "target_version": "1.0.0",
                "problem": "Create content distribution capability",
                "allowed_files": [".agents/company/departments/content/department.py"],
                "acceptance_tests": ["python -m unittest"],
                "owner_override": True})
        blocked = runtime.once(invalid["id"])
        self.assertIn("department_spec", blocked["cycle"]["data"]["decision"]["missing"])

        valid = runtime.create_goal(
            name="Build Content Department", owner_id="system-improvement",
            metric="acceptance_tests_passed", operator="eq", target=True,
            run_type="system_improvement", evidence_validity="technical_only", config={
                "change_kind": "create_department", "owner_id": "content",
                "from_version": "new", "target_version": "1.0.0",
                "problem": "Create content distribution capability",
                "allowed_files": [".agents/company/departments/content/department.py"],
                "acceptance_tests": ["python -m unittest"],
                "department_spec": {"purpose": "distribute content", "metrics": ["qualified_views"],
                                "external_actions": ["publish"], "approval_points": ["publish"],
                                "evidence_sources": ["analytics"]},
                "owner_override": True})
        parked = runtime.once(valid["id"])
        task = parked["change_tasks"][0]
        self.assertEqual(task["change_kind"], "create_department")
        self.assertEqual(task["specification"]["purpose"], "distribute content")


class DirectorIdentityContractTests(unittest.TestCase):
    def test_opencode_director_is_not_generic_build_agent(self):
        root = Path(__file__).resolve().parents[2]
        prompt = (root / "company/init_templates/hosts/opencode/agents/director.md").read_text()
        self.assertIn("You are the operating Director of SpielOS", prompt)
        self.assertIn("must never introduce yourself as a coding or website assistant", prompt)
        self.assertIn("reports do not require a new goal", prompt)
        self.assertIn("permissions:", prompt)
        self.assertIn("- action: edit", prompt)
        self.assertIn("effect: deny", prompt)
        self.assertIn("- action: shell", prompt)
        self.assertIn("effect: allow", prompt)

    def test_codex_director_has_same_identity_boundary(self):
        root = Path(__file__).resolve().parents[2]
        prompt = (root / "company/init_templates/hosts/codex/agents/director.toml").read_text()
        self.assertIn("You are the operating Director of SpielOS", prompt)
        self.assertIn("Route unrelated repository implementation", prompt)
        self.assertIn("request_user_input", prompt)

    def test_opencode_notification_hook_uses_native_question_and_chat_surface(self):
        root = Path(__file__).resolve().parents[2]
        config = (root / "opencode.json").read_text()
        plugin = (root / "company/init_templates/hosts/opencode/plugins/spielos-notifications.ts").read_text()
        self.assertIn("spielos-notifications.ts", config)
        self.assertIn('event.type === "session.idle"', plugin)
        # V2 contract (opencode2, 0.0.0-next-17444): the approval wake-up uses
        # ctx.session.prompt (no agent field, no V1 promptAsync) and the
        # stop/start interception hook does not exist in the V2 CommandDomain
        # — daemon lifecycle belongs to the OS supervisor.
        self.assertIn("ctx.session.prompt", plugin)
        self.assertNotIn("promptAsync", plugin)
        self.assertNotIn("command.execute.before", plugin)
        self.assertIn("supervisor.py", plugin)
        self.assertIn("native question tool", plugin)

    def test_system_improvement_groups_safe_permissions(self):
        root = Path(__file__).resolve().parents[2]
        prompt = (root / "company/init_templates/hosts/opencode/agents/system-improvement.md").read_text()
        self.assertIn("permissions:", prompt)
        self.assertIn("- action: edit", prompt)
        self.assertIn("effect: allow", prompt)
        self.assertIn("- action: external_directory", prompt)
        self.assertIn("effect: ask", prompt)


class RuntimeControlTests(unittest.TestCase):
    def test_stop_is_persistent_and_runner_honors_it(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            db = root / ".spielos/state/company.sqlite"
            runtime = Runtime(db, {"immediate_test": ImmediateHandler()})
            runtime.create_goal(name="test", owner_id="immediate_test", metric="done",
                                operator="eq", target=True)
            service = RunnerService(root, db)
            self.assertTrue(service.status()["enabled"])
            self.assertFalse(service.stop()["enabled"])
            self.assertTrue(Runner(runtime).tick()["stopped"])
            self.assertTrue(service.enable()["enabled"])

    def test_v4_storage_columns_migrate_without_losing_rows(self):
        with tempfile.TemporaryDirectory() as directory:
            db = Path(directory) / "company.sqlite"
            with sqlite3.connect(db) as con:
                con.execute("""CREATE TABLE goals (
                    id TEXT PRIMARY KEY, name TEXT NOT NULL, engine_id TEXT NOT NULL,
                    metric TEXT NOT NULL, operator TEXT NOT NULL, target_json TEXT NOT NULL,
                    deadline TEXT, parent_id TEXT, goal_status TEXT NOT NULL,
                    config_json TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL)""")
                con.execute("INSERT INTO goals VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                            ("legacy", "Legacy", "outbound", "reply_rate", "ge", "0.3",
                             None, None, "active", "{}", "now", "now"))
            store = Store(db)
            goal = store.goal("legacy")
            self.assertEqual("outbound", goal["owner_id"])
            self.assertNotIn("engine_id", goal)


class TransitionHookTests(unittest.TestCase):
    """The generic post-transition hook (website decoupling): disabled by
    default, fires once per persisted transition when configured via
    SPIELOS_TRANSITION_HOOK, and never breaks a goal transition."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)

    def runtime(self):
        return Runtime(Path(self.temp.name) / "state.sqlite",
                       {"immediate_test": ImmediateHandler()})

    def test_hook_disabled_by_default(self):
        runtime = self.runtime()
        goal = runtime.create_goal(name="No hook", owner_id="immediate_test",
                                   metric="done", operator="eq", target=True, config={})
        with patch.dict(os.environ, {}, clear=True):
            result = runtime.once(goal["id"])
        self.assertEqual(result["goal"]["goal_status"], "achieved")

    def test_hook_fires_on_every_persisted_transition_with_payload(self):
        runtime = self.runtime()
        goal = runtime.create_goal(name="Hooked", owner_id="immediate_test",
                                   metric="done", operator="eq", target=True, config={})
        calls = []

        def record(event, payload, **kwargs):
            calls.append((event, payload))
            return {"returncode": 0}

        with patch.dict(os.environ,
                        {"SPIELOS_TRANSITION_HOOK": "true"}, clear=False), \
             patch("company.runtime.loop.run_transition_hook", side_effect=record):
            result = runtime.once(goal["id"])
        # ImmediateHandler advances OBSERVE -> DECIDE -> ACT -> EVALUATE:
        # exactly four persisted transitions, one hook invocation each.
        self.assertEqual(result["goal"]["goal_status"], "achieved")
        self.assertEqual(len(calls), 4)
        for event, payload in calls:
            self.assertEqual(event, "goal_transition")
            self.assertEqual(payload["goal_id"], goal["id"])
            self.assertIn("run_id", payload)
            self.assertIn("run_status", payload)
            self.assertIn("goal_status", payload)
        self.assertEqual(calls[-1][1]["goal_status"], "achieved")

    def test_hook_failure_never_breaks_the_goal_transition(self):
        runtime = self.runtime()
        goal = runtime.create_goal(name="Hook fails", owner_id="immediate_test",
                                   metric="done", operator="eq", target=True, config={})
        with patch.dict(os.environ,
                        {"SPIELOS_TRANSITION_HOOK": "false"}, clear=False):
            with patch("company.runtime.hooks.subprocess.run",
                       side_effect=subprocess.TimeoutExpired(cmd=["x"], timeout=1)):
                started = time.monotonic()
                result = runtime.once(goal["id"])
                self.assertLess(time.monotonic() - started, 5)
        self.assertEqual(result["goal"]["goal_status"], "achieved")

    def test_run_transition_hook_substitutes_and_quotes(self):
        calls = []
        with patch.dict(os.environ, {"SPIELOS_TRANSITION_HOOK":
                                     "python3 hook.py {event} {payload_json}"}, clear=False), \
             patch("company.runtime.hooks.subprocess.run",
                   side_effect=lambda cmd, **kw: calls.append(cmd)
                   or SimpleNamespace(returncode=0)):
            result = run_transition_hook("goal_transition", {"goal_id": "g x"})
        self.assertEqual({"returncode": 0}, result)
        command = calls[0]
        self.assertEqual(command, "python3 hook.py goal_transition '{\"goal_id\": \"g x\"}'")

    def test_run_transition_hook_env_file_fallback_and_env_var_priority(self):
        env_file = Path(self.temp.name) / ".env"
        env_file.write_text("# comment\nSPIELOS_TRANSITION_HOOK=file-cmd\n", encoding="utf-8")
        # File fallback when the variable is unset.
        with patch.dict(os.environ, {}, clear=True), \
             patch.object(runtime_hooks, "HOOK_ENV_FILE", env_file):
            self.assertEqual(runtime_hooks._hook_template(), "file-cmd")
        # Env var wins over the file.
        with patch.dict(os.environ, {"SPIELOS_TRANSITION_HOOK": "env-cmd"}, clear=False), \
             patch.object(runtime_hooks, "HOOK_ENV_FILE", env_file):
            self.assertEqual(runtime_hooks._hook_template(), "env-cmd")
        # Empty everywhere -> disabled.
        with patch.dict(os.environ, {}, clear=True), \
             patch.object(runtime_hooks, "HOOK_ENV_FILE",
                          Path(self.temp.name) / "missing.env"):
            self.assertIsNone(run_transition_hook("goal_transition", {}))


class PlainLanguageProjectionTests(unittest.TestCase):
    """The compact status projection speaks plain language; --raw keeps its
    machine shape, and notifications keep result.message while gaining a
    plain why/next read."""

    def runtime(self, registry=None):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        return Runtime(Path(self.temp.name) / "state.sqlite",
                       registry or {"approval_test": ApprovalHandler()})

    def capture(self, runtime, *arguments):
        output = io.StringIO()
        with redirect_stdout(output):
            code = main(["--db", str(runtime.store.path), *arguments])
        self.assertEqual(0, code)
        return output.getvalue()

    def waiting_fixture(self, runtime):
        goal = runtime.create_goal(name="Evidence wait", owner_id="approval_test",
                                   metric="done", operator="eq", target=True, config={})
        cycle = runtime.store.cycle(goal["id"])
        runtime.store.update_cycle(
            cycle["id"], stage="EVALUATE", step="measure", run_status="waiting",
            resume_at="2026-08-11T11:59:00+00:00",
            data={"action_result": {"evidence_deadline": "2026-08-13T03:24:43.927977+00:00"}})
        return goal

    def test_compact_projection_has_plain_language_why_next_for_waiting_run(self):
        runtime = self.runtime()
        goal = self.waiting_fixture(runtime)
        row = runtime.store.goal_summaries(statuses=("active",), limit=10)[0]
        self.assertEqual(row["id"], goal["id"])
        # machine fields stay unchanged in shape
        self.assertEqual(row["run_status"], "waiting")
        self.assertEqual(row["resume_at"], "2026-08-11T11:59:00+00:00")
        self.assertIn("waiting —", row["why_next"])
        self.assertIn("evidence window open until 2026-08-13 03:24 UTC", row["why_next"])
        self.assertIn("next automatic check 2026-08-11 11:59 UTC", row["why_next"])

    def test_compact_status_render_shows_why_next_and_local_runner_header(self):
        runtime = self.runtime()
        self.waiting_fixture(runtime)
        output = self.capture(runtime, "status")
        self.assertIn("Local runner:", output)
        self.assertIn("goals only advance while this machine is on", output)
        self.assertIn("evidence window open until 2026-08-13 03:24 UTC", output)
        self.assertIn("next automatic check 2026-08-11 11:59 UTC", output)

    def test_paused_runner_header_prints_exact_start_hint(self):
        runtime = self.runtime()
        self.waiting_fixture(runtime)
        paused = {"enabled": True, "running": False, "pid": None, "started_at": None}
        with patch("company.__main__.RunnerService.status", return_value=paused):
            output = self.capture(runtime, "status")
        self.assertIn("Local runner: **paused** - start with `company runner start`", output)
        self.assertIn("goals only advance while this machine is on", output)

    def test_raw_status_keeps_token_identical_shape(self):
        runtime = self.runtime()
        goal = self.waiting_fixture(runtime)
        raw = json.loads(self.capture(runtime, "status", "--raw", goal["id"]))
        self.assertEqual(
            {"goal", "cycle", "run", "evidence", "decisions", "evaluation",
             "latest_result", "change_tasks", "work_orders", "children",
             "pending_notifications"},
            set(raw))
        self.assertEqual({"id", "goal_id", "sequence", "stage", "step", "run_status",
                          "resume_at", "data", "created_at", "updated_at"}, set(raw["cycle"]))
        self.assertEqual("waiting", raw["cycle"]["run_status"])
        self.assertNotIn("why_next", raw["cycle"])
        self.assertNotIn("why_next", raw["goal"])

        company = json.loads(self.capture(runtime, "status", "--raw"))
        self.assertNotIn("why_next", company[0]["goal"])
        self.assertNotIn("why_next", company[0]["cycle"])

    def test_notifications_keep_result_message_and_add_plain_wording(self):
        runtime = self.runtime()
        goal = runtime.create_goal(name="Guarded", owner_id="approval_test",
                                   metric="done", operator="eq", target=True, config={})
        cycle = runtime.store.cycle(goal["id"])
        runtime.store.update_cycle(cycle["id"], stage="ACT", step="review",
                                   run_status="awaiting_approval", data={})
        runtime.store.notify(goal["id"], cycle["id"], "approval_required", {
            "result": {"message": "Review the prepared batch"},
            "required_user_action": "Approve the prepared action",
            "approval_interaction": {"question": "Approve this batch?"},
        })
        runtime.store.notify(goal["id"], cycle["id"], "blocked", {
            "result": {"message": "Coding executor must modify only allowed files",
                       "metrics": {"task": {"status": "approved"}}},
        })
        rows = {row["kind"]: row for row in runtime.store.notifications("pending")}
        self.assertEqual(rows["approval_required"]["payload"]["result"]["message"],
                         "Review the prepared batch")
        self.assertEqual(rows["approval_required"]["why_next"],
                         "approval needed — prepared action needs your approval")
        self.assertEqual(rows["approval_required"]["payload"]["approval_interaction"]["question"],
                         "Approve this batch?")
        self.assertEqual(rows["blocked"]["payload"]["result"]["message"],
                         "Coding executor must modify only allowed files")
        self.assertEqual(rows["blocked"]["why_next"], "blocked — needs coding executor")

    def test_runner_service_exposes_started_at_for_live_process(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            db = root / ".spielos/state/company.sqlite"
            Runtime(db, {"approval_test": ApprovalHandler()})
            service = RunnerService(root, db)
            self.assertIsNone(service.status()["started_at"])  # no pid file yet
            state_dir = root / ".spielos/state"
            state_dir.mkdir(parents=True, exist_ok=True)
            pid_file = state_dir / "runner.pid"
            pid_file.write_text(json.dumps({"pid": 424242, "command": ["-m", "company"],
                                            "db_path": str(db)}) + "\n")
            stamp = datetime(2026, 8, 11, 12, 17, 0, tzinfo=timezone.utc).timestamp()
            os.utime(pid_file, (stamp, stamp))
            with patch("company.runtime.service._alive", return_value=True):
                status = service.status()
            self.assertTrue(status["running"])
            self.assertEqual(status["pid"], 424242)
            self.assertTrue(status["started_at"].startswith("2026-08-11T12:17:00"))


class TransitionHookBoundTests(unittest.TestCase):
    """company-runtime 6.1: the transition hook never blocks a goal
    transition and is strictly bounded; the retired live sync/push machinery
    no longer exists in loop.py."""

    def runtime(self, registry):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        return Runtime(Path(self.temp.name) / "state.sqlite", registry)

    def test_website_deploy_symbols_are_gone_from_loop(self):
        for symbol in ("LIVE_SYNC_SCRIPT", "LIVE_SYNC_DB", "LIVE_SYNC_OUT",
                       "LIVE_PUSH_STATE_OUT", "_git_push_sequence",
                       "_push_live_main_ref", "_sync_live_snapshot",
                       "_maybe_push_live_snapshot", "_load_live_sync"):
            self.assertFalse(hasattr(runtime_loop, symbol),
                             f"website coupling must stay out of the runtime: {symbol}")

    def test_hook_subprocess_is_bounded(self):
        with patch("company.runtime.hooks.subprocess.run") as run:
            run.return_value = SimpleNamespace(returncode=0, stdout="", stderr="")
            with patch.dict(os.environ,
                            {"SPIELOS_TRANSITION_HOOK": "true"}, clear=False):
                run_transition_hook("goal_transition", {})
        self.assertIn("timeout", run.call_args.kwargs)
        self.assertLessEqual(run.call_args.kwargs["timeout"], 30)

    def test_hanging_hook_never_blocks_transition(self):
        runtime = self.runtime({"immediate_test": ImmediateHandler()})
        goal = runtime.create_goal(name="Hung hook", owner_id="immediate_test",
                                   metric="done", operator="eq", target=True, config={})
        started = time.monotonic()
        with patch.dict(os.environ,
                        {"SPIELOS_TRANSITION_HOOK": "true"}, clear=False), \
             patch("company.runtime.hooks.subprocess.run",
                   side_effect=subprocess.TimeoutExpired(cmd=["git", "push"], timeout=1)):
            result = runtime.once(goal["id"])  # must not raise and must return fast
        self.assertLess(time.monotonic() - started, 5)
        self.assertEqual(result["goal"]["goal_status"], "achieved")

    def test_stale_running_cycle_resumes_but_live_lease_blocks(self):
        runtime = self.runtime({"immediate_test": ImmediateHandler()})
        runner = Runner(runtime)

        stale = runtime.create_goal(name="Stale", owner_id="immediate_test",
                                    metric="done", operator="eq", target=True, config={})
        cycle = runtime.store.cycle(stale["id"])
        runtime.store.update_cycle(cycle["id"], stage="ACT", step="execute",
                                   run_status="running", resume_at=None,
                                   data=cycle.get("data") or {})
        row = {"goal": runtime.status(stale["id"])["goal"],
               "cycle": runtime.store.cycle(stale["id"])}
        self.assertTrue(runner._runnable(row), "stale running cycle must be runnable")
        resumed = runtime.once(stale["id"], holder="company-runner")
        self.assertEqual(resumed["goal"]["goal_status"], "achieved")

        live = runtime.create_goal(name="Live", owner_id="immediate_test",
                                   metric="done", operator="eq", target=True, config={})
        cycle = runtime.store.cycle(live["id"])
        runtime.store.update_cycle(cycle["id"], stage="ACT", step="execute",
                                   run_status="running", resume_at=None,
                                   data=cycle.get("data") or {})
        runtime.store.acquire(live["id"], "ghost-client", seconds=60)
        row = {"goal": runtime.status(live["id"])["goal"],
               "cycle": runtime.store.cycle(live["id"])}
        self.assertFalse(runner._runnable(row), "live lease must block a second client")
        runtime.store.release(live["id"], "ghost-client")
