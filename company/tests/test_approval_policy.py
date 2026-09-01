"""Acceptance tests for goal-approval-policy-20260815 (change_kind=repair).

Problem statement (the spec): "Every execute action parks at AWAITING_APPROVAL
with no policy to auto-approve; no CLI to set approval mode per goal."

Intended API contract (implementer must make every test pass by editing ONLY
`.agents/company/runtime/models.py`, `.agents/company/runtime/loop.py`,
`.agents/company/__main__.py`):

1. Approval policy modes, named exactly:
   - `per_action`           — today's behavior: every guarded execute action
                              parks at AWAITING_APPROVAL until approved.
   - `per_run`              — after the FIRST approval of a Run (cycle), every
                              remaining approval key of that Run reads as
                              "approved", so the Run proceeds without any
                              further prompts. A new Run starts unapproved.
   - `everything_approved`  — guarded execute actions never park; every key
                              reads as "approved" for the Goal.
   The policy is stored per Goal in `goal.config["approval_policy"]`.
   `per_action` is the default when the key is absent (existing behavior).
   Unknown policy values must be rejected at goal creation (ValueError).
   Optional but recommended: `company.runtime.models.ApprovalPolicy` as a
   str-Enum with members PER_ACTION="per_action", PER_RUN="per_run",
   EVERYTHING_APPROVED="everything_approved".

2. Runtime behavior (`Runtime.once` / `Runtime.approve`): the approval_status
   view handed to handlers reflects the policy:
   - everything_approved → every key approved, no parking.
   - per_run → once the run-level "execute" key is approved, every other key
     of the same cycle is approved too.
   - per_action → unchanged.

3. CLI (`company approve`): the approve command gains `--scope` with choices
   `per_action`, `per_run`, `everything_approved`. `approve GOAL --scope
   per_run` approves the current action AND records
   `config["approval_policy"] = "per_run"` on the goal; the same for
   `--scope everything_approved`; `--scope per_action` (or no flag) only
   approves the current action and never changes the policy.

Tests marked `# passes now` run green against the current runtime and pin the
existing contract. Tests marked `# expected after implementation` encode the
new behavior and fail until the implementation above lands.
"""

import io
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from company.__main__ import build_parser, main  # noqa: E402
from company.runtime.loop import Runtime  # noqa: E402
from company.runtime.models import (  # noqa: E402
    GoalHandler, GoalStatus, RunStatus, Stage, StageResult,
)

POLICY_MODES = ("per_action", "per_run", "everything_approved")


class ApprovalPolicyHandler(GoalHandler):
    """One guarded execute action in ACT (mirrors test_runtime.ApprovalHandler)."""

    id = "approval_policy_test"

    def observe(self, ctx):
        return StageResult("collect", {"real": True})

    def decide(self, ctx, observation):
        return StageResult("diagnose", {"action": "execute_gated"})

    def act(self, ctx, decision):
        if ctx.approval_status("execute") != "approved":
            return StageResult(
                "review", {"prepared": True, "step_id": "review"},
                RunStatus.AWAITING_APPROVAL, Stage.ACT)
        return StageResult("execute", {"executed": True})

    def evaluate(self, ctx, action_result):
        validity = (ctx.cycle.get("run") or {}).get("evidence_validity") or "business"
        return StageResult(
            "goal_check", {"done": True}, RunStatus.IDLE,
            goal_status=GoalStatus.ACHIEVED,
            evaluation={"verdict": "goal_met", "goal_met": True,
                        "metrics": {ctx.goal.metric: True}, "validity": validity})


class TwoGateHandler(GoalHandler):
    """Two sequential approval gates inside ONE run/cycle.

    Gate k parks at ACT step `gate{k}` unless `step:gate{k}` is approved.
    Gate 1 must execute before gate 2 is reached, so per_run semantics can be
    observed: after the first approval, the second gate must NOT park again.
    """

    id = "two_gate_test"

    def __init__(self):
        self.executed = []

    def observe(self, ctx):
        return StageResult("collect", {})

    def decide(self, ctx, observation):
        return StageResult("diagnose", {"action": "experiment"})

    def act(self, ctx, decision):
        data = ctx.cycle.get("data") or {}
        gate = (data.get("action_result") or {}).get("next_gate", 1)
        if ctx.approval_status("step:gate%d" % gate) != "approved":
            return StageResult(
                "gate%d" % gate,
                {"next_gate": gate, "step_id": "gate%d" % gate, "prepared": True},
                RunStatus.AWAITING_APPROVAL, Stage.ACT)
        self.executed.append(gate)
        if gate == 1:
            # Chain to gate 2 inside the same ACT stage: the default ACT
            # transition is EVALUATE, which would skip the second gate.
            return StageResult("gate1_done", {"next_gate": 2, "executed": [1]},
                               RunStatus.RUNNING, Stage.ACT)
        return StageResult("execute", {"next_gate": 2, "gates": 2,
                                       "executed": [1, 2]},
                           RunStatus.RUNNING, Stage.EVALUATE)

    def evaluate(self, ctx, action_result):
        validity = (ctx.cycle.get("run") or {}).get("evidence_validity") or "business"
        return StageResult(
            "goal_check", {"done": True}, RunStatus.IDLE,
            goal_status=GoalStatus.ACHIEVED,
            evaluation={"verdict": "goal_met", "goal_met": True,
                        "metrics": {ctx.goal.metric: True}, "validity": validity})


class ApprovalPolicyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.runtime = Runtime(Path(self.temp.name) / "state.sqlite",
                               {"approval_policy_test": ApprovalPolicyHandler(),
                                "two_gate_test": TwoGateHandler()})

    def create(self, owner="approval_policy_test", config=None, two_gate=False):
        if two_gate:
            owner = "two_gate_test"
        return self.runtime.create_goal(
            name="Policy", owner_id=owner, metric="done", operator="eq",
            target=True, config=config or {})

    def test_default_policy_per_action_parks_execute_action(self):  # passes now
        goal = self.create()
        parked = self.runtime.once(goal["id"])
        self.assertEqual(parked["cycle"]["stage"], "ACT")
        self.assertEqual(parked["cycle"]["step"], "review")
        self.assertEqual(parked["cycle"]["run_status"], "awaiting_approval")
        self.assertIsNone(
            self.runtime.store.approval(goal["id"], parked["cycle"]["id"], "execute"))

    def test_approve_grants_run_level_execute_key(self):  # passes now
        goal = self.create()
        parked = self.runtime.once(goal["id"])
        self.runtime.approve(goal["id"])
        self.assertEqual(
            "approved",
            self.runtime.store.approval(goal["id"], parked["cycle"]["id"], "execute"))
        complete = self.runtime.once(goal["id"])
        self.assertEqual(complete["goal"]["goal_status"], "achieved")

    def test_approve_rejects_goal_not_awaiting(self):  # passes now
        goal = self.create()
        self.runtime.once(goal["id"])  # parks
        self.runtime.approve(goal["id"])
        self.runtime.once(goal["id"])  # run completes past the approval
        with self.assertRaises(RuntimeError):
            self.runtime.approve(goal["id"])

    def test_cli_approve_without_scope_changes_no_policy(self):  # passes now
        goal = self.create()
        self.runtime.once(goal["id"])
        output = io.StringIO()
        with redirect_stdout(output):
            code = main(["--db", str(self.runtime.store.path), "approve", goal["id"]])
        self.assertEqual(0, code)
        config = self.runtime.store.goal(goal["id"])["config"]
        self.assertNotIn("approval_policy", config,
                         "plain approve must not change the goal policy")
        complete = self.runtime.once(goal["id"])
        self.assertEqual(complete["goal"]["goal_status"], "achieved")

    def test_per_action_requires_approval_per_gate(self):  # passes now
        goal = self.create(config={"approval_policy": "per_action"}, two_gate=True)
        first = self.runtime.once(goal["id"])
        self.assertEqual(first["cycle"]["run_status"], "awaiting_approval")
        self.assertEqual(first["cycle"]["step"], "gate1")
        self.runtime.approve(goal["id"])
        second = self.runtime.once(goal["id"])
        self.assertEqual(second["cycle"]["run_status"], "awaiting_approval")
        self.assertEqual(second["cycle"]["step"], "gate2",
                         "per_action must park again at the second gate")
        self.runtime.approve(goal["id"])
        done = self.runtime.once(goal["id"])
        self.assertEqual(done["goal"]["goal_status"], "achieved")

    def test_everything_approved_never_parks_execute(self):  # expected after implementation
        goal = self.create(config={"approval_policy": "everything_approved"})
        state = self.runtime.once(goal["id"])
        self.assertEqual(state["goal"]["goal_status"], "achieved")
        self.assertNotEqual(state["cycle"]["run_status"], "awaiting_approval",
                            "everything_approved must auto-approve the execute action")
        self.assertNotEqual(state["cycle"]["run_status"], "blocked")

    def test_everything_approved_skips_both_gates(self):  # expected after implementation
        goal = self.create(config={"approval_policy": "everything_approved"},
                           two_gate=True)
        state = self.runtime.once(goal["id"])
        self.assertEqual(state["goal"]["goal_status"], "achieved")
        self.assertEqual(
            [1, 2], self.runtime.registry["two_gate_test"].executed,
            "both gates must execute without any approval prompt")

    def test_per_run_approves_remaining_gates_after_first(self):  # expected after implementation
        goal = self.create(config={"approval_policy": "per_run"}, two_gate=True)
        first = self.runtime.once(goal["id"])
        self.assertEqual(first["cycle"]["run_status"], "awaiting_approval")
        handler = self.runtime.registry["two_gate_test"]
        self.assertEqual(handler.executed, [])
        self.runtime.approve(goal["id"])
        done = self.runtime.once(goal["id"])
        self.assertEqual(done["goal"]["goal_status"], "achieved",
                         "per_run: after the first approval the run must finish "
                         "without another approval prompt")
        self.assertEqual(handler.executed, [1, 2])

    def test_unknown_policy_value_is_rejected_at_creation(self):  # expected after implementation
        with self.assertRaises(ValueError):
            self.create(config={"approval_policy": "banana"})

    def test_approval_policy_enum_exists_with_policy_modes(self):  # expected after implementation
        try:
            from company.runtime.models import ApprovalPolicy
        except ImportError:
            self.fail("company.runtime.models.ApprovalPolicy is missing; "
                      "add the str-Enum with the three policy modes")
        values = {item.value for item in ApprovalPolicy}
        self.assertEqual(set(POLICY_MODES), values)
        self.assertEqual("per_action", ApprovalPolicy.PER_ACTION.value)


class ApproveScopeCliTests(unittest.TestCase):
    """`approve GOAL --scope {per_action,per_run,everything_approved}`."""

    def test_parser_accepts_the_three_scope_values(self):  # expected after implementation
        parser = build_parser()
        for scope in POLICY_MODES:
            args = parser.parse_args(["approve", "goal-x", "--scope", scope])
            self.assertEqual("approve", args.command)
            self.assertEqual(scope, args.scope)

    def test_parser_rejects_unknown_scope_value(self):  # passes now (unknown flag is also rejected)
        parser = build_parser()
        with self.assertRaises(SystemExit):
            parser.parse_args(["approve", "goal-x", "--scope", "forward_free"])

    def test_cli_approve_scope_per_run_records_policy(self):  # expected after implementation
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        runtime = Runtime(Path(self.temp.name) / "state.sqlite",
                          {"approval_policy_test": ApprovalPolicyHandler()})
        goal = runtime.create_goal(name="Policy", owner_id="approval_policy_test",
                                   metric="done", operator="eq", target=True, config={})
        runtime.once(goal["id"])
        output = io.StringIO()
        with redirect_stdout(output):
            code = main(["--db", str(runtime.store.path), "approve",
                         goal["id"], "--scope", "per_run"])
        self.assertEqual(0, code)
        config = runtime.store.goal(goal["id"])["config"]
        self.assertEqual("per_run", config.get("approval_policy"),
                         "--scope per_run must set the goal approval policy")
        done = runtime.once(goal["id"])
        self.assertEqual(done["goal"]["goal_status"], "achieved")


if __name__ == "__main__":
    unittest.main()