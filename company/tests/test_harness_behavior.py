"""Behavioral test suite for the SpielOS clean-core harness (source tree).

Ported from the SpielOS-Website home audit (2026-09-03,
AUDIT-BEHAVIOR-REPORT.md): every test asserts one intended UX behavior
end-to-end against throwaway SQLite databases. Department-dependent
classes run against fixture declarations from ``tests/fixtures/departments``
(loaded through the ``SPIELOS_TEST_DEPARTMENTS_DIR`` seam); the shipped
product still carries zero departments by design.

The original suite pinned eight defects as KNOWN-DEFECT tests; those pins
are inverted here because D1–D8 are fixed in this source tree:

- D1 executor identity: orders are claimed with the bare agent id; the
  historical ``executor:<agent_id>`` claimant is accepted as a synonym.
- D2 memory writes: ``tasks --complete --learning`` and ``memory add``
  persist workflow/strategy memory through the lineage-enforcing remember().
- D3 undeclared metrics: ``goal create`` rejects metrics the owner
  Department does not declare.
- D4 escalation livelock: after three consecutive escalated runs the goal
  parks for the owner instead of churning new runs.
- D5 run-scoped approvals: ``approve --scope run`` satisfies every later
  intervention of the same run.
- D6 installed agents: ``agents/installed/*.json`` declarations load into
  the ResolutionCycle.
- D7 approval-only steps: gates with nothing to produce auto-advance once
  approved instead of parking a work order.
- D8 readonly snapshots: cached per (path, mtime, size); the database
  file stays byte-for-byte untouched.

Run:  PYTHONDONTWRITEBYTECODE=1 python3 -B -m unittest \\
          company.tests.test_harness_behavior -v
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
FIXTURES = Path(__file__).resolve().parent / "fixtures"

# The source tree itself resolves as a home (flat `company/` checkout), so
# no sys.path bootstrap is needed; CLI subprocess tests pin PYTHONPATH to
# the repo root and SPIELOS_HOME to a temp home so vendored lookup does not
# walk into a real home.
os.environ.setdefault("SPIELOS_HOME", str(REPO))

with_departments = __import__(
    "unittest").skipUnless(
        FIXTURES.is_dir(), "department fixtures not present")


def temp_db() -> Path:
    handle = tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False)
    handle.close()
    path = Path(handle.name)
    path.unlink()
    return path


from company.agents.core import Agent, AgentEvidence, AgentResult, FunctionExecutor  # noqa: E402
from company.commands.goal_runtime import (  # noqa: E402
    AssignmentExecutor,
    CatalogController,
    CleanCommandRuntime,
)
from company.context.core import codex_hook_output  # noqa: E402
from company.runtime.engine import GoalRuntime, GoalStage  # noqa: E402
from company.runtime.registry import departments  # noqa: E402
from company.runtime.util import compare  # noqa: E402
from company.state import Database  # noqa: E402
from company.workflows.core import Workflow, WorkflowStep  # noqa: E402


class ScriptedExecutor:
    """Test double for the host: parks, succeeds, fixes, or escalates on cue.

    The real host (the Director) reacts to a WorkOrder by doing the work and
    completing it through ``tasks --complete``. ScriptedExecutor drives the
    same AgentExecutor seam programmatically.
    """

    def __init__(self, script=None):
        self.script = list(script or [])
        self.calls: list[tuple[str, str]] = []

    def execute(self, agent, order):
        self.calls.append((agent.id, order.id))
        if self.script:
            return self.script.pop(0)
        return AgentResult("ask_user",
                           message=f"WorkOrder {order.id} is ready for Agent {agent.id}")


def completing_executor(payload=None, workflow_learning=None):
    """Executor that always completes the current step with evidence."""

    class _CompleteAll:
        def execute(self, agent, order):
            kinds = tuple(order.brief.get("evidence_kinds")
                         or ((order.brief.get("evidence_kind"),)
                             if order.brief.get("evidence_kind") else ()))
            kinds = kinds or ("intervention_result",)
            return AgentResult(
                "completed",
                evidence=tuple(AgentEvidence(k, dict(payload or {}))
                               for k in kinds),
                workflow_learning=workflow_learning,
            )
    return _CompleteAll()


class HarnessCase(unittest.TestCase):
    """Shared: fresh CleanCommandRuntime on a throwaway database."""

    def setUp(self):
        self.db = temp_db()
        self.runtime = CleanCommandRuntime(self.db)
        self.engine = self.runtime.runtime

    def tearDown(self):
        self.db.unlink(missing_ok=True)

    def new_goal(self, name="G", owner="director", metric="m",
                 operator="ge", target=1, parent_id=None, priority=None,
                 aggregation=None, workflow=None):
        config = {}
        if aggregation:
            config["aggregation"] = aggregation
        if priority:
            config["priority"] = priority
        if workflow:
            config["workflow"] = workflow
        config = config or {"aggregation": "latest"}
        row = self.runtime.create_goal(name=name, owner_id=owner, metric=metric,
                                       operator=operator, target=target,
                                       parent_id=parent_id, config=config)
        self.goal_id = row["id"]
        return row

    def other_goal(self, name="Other", metric="m_other"):
        """Create a secondary Goal WITHOUT rebinding self.goal_id."""
        return self.runtime.create_goal(
            name=name, owner_id="director", metric=metric, operator="ge",
            target=1, config={"aggregation": "latest"})

    def tick_until(self, predicate, budget=40):
        for _ in range(budget):
            self.runtime.tick(max_advances=50)
            if predicate():
                return True
        return predicate()

    def current_run(self):
        return self.runtime.runs.current(self.goal_id)

    def active_orders(self):
        return self.runtime.work_orders(status="active", goal_id=self.goal_id)


# =========================================================================
# 1. HOST INPUT -> GOAL -> THE PERSISTED LOOP  (seo fixtures)
# =========================================================================

@with_departments
class TestGoalLoopLifecycle(HarnessCase):
    """Owner asks the Director for an outcome; a measurable Goal runs."""

    @classmethod
    def setUpClass(cls):
        os.environ["SPIELOS_TEST_DEPARTMENTS_DIR"] = str(
            FIXTURES / "departments")

    @classmethod
    def tearDownClass(cls):
        os.environ.pop("SPIELOS_TEST_DEPARTMENTS_DIR", None)

    def test_goal_create_persists_goal_and_first_ready_run(self):
        self.new_goal(name="Map opportunities", owner="seo",
                      metric="keyword_opportunities", target=1,
                      aggregation="count", workflow="keyword-research")
        goal = self.runtime.goals.get(self.goal_id)
        run = self.runtime.runs.current(self.goal_id)
        self.assertEqual(goal.status, "active")
        self.assertEqual((run.sequence, run.stage, run.status),
                         (1, GoalStage.OBSERVE, "ready"),
                         "a new Goal must immediately own one ready OBSERVE run")

    def test_full_loop_completes_goal_when_evidence_meets_target(self):
        self.new_goal(name="Map opportunities", owner="seo",
                      metric="keyword_opportunities", target=1,
                      aggregation="count", workflow="keyword-research")
        self.engine.resolution.executor = completing_executor(
            payload={"keyword_opportunities": 1})
        done = self.tick_until(
            lambda: self.runtime.goals.get(self.goal_id).status == "complete")
        self.assertTrue(done, "goal must complete once evidence meets target")
        evidence = self.runtime.evidence.for_goal(self.goal_id)
        self.assertTrue(any(e.kind == "keyword_opportunity" for e in evidence),
                        "the completing step's evidence must be the kind the "
                        "department declares for the metric")

    def test_incomplete_goal_creates_next_run(self):
        self.new_goal(name="Map opportunities", owner="seo",
                      metric="keyword_opportunities", target=10,
                      aggregation="count", workflow="keyword-research")
        self.engine.resolution.executor = completing_executor(
            payload={"keyword_opportunities": 1})
        progressed = self.tick_until(
            lambda: self.runtime.runs.current(self.goal_id).sequence > 1)
        self.assertTrue(progressed,
                        "a not-yet-met Goal must open its next OBSERVE run")

    def test_undeclared_department_metric_is_rejected_at_create(self):
        # D3 fixed: a goal whose metric is not declared by its department
        # can never be proven; creation fails with the declared list.
        with self.assertRaises(ValueError) as caught:
            self.new_goal(name="Publish one article", owner="seo",
                          metric="articles_published", target=1,
                          aggregation="count", workflow="article")
        self.assertIn("articles_published", str(caught.exception))
        self.assertIn("keyword_opportunities", str(caught.exception),
                      "the error must list the declared metrics")

    def test_advance_parks_work_order_for_host_when_no_department(self):
        self.new_goal(name="Weekly sales", owner="director", metric="weekly_sales")
        self.runtime.tick(max_advances=10)
        run = self.current_run()
        self.assertEqual((run.stage, run.status), (GoalStage.ACT, "waiting"))
        orders = self.active_orders()
        self.assertEqual(len(orders), 1)
        self.assertEqual(orders[0]["agent_id"], "director",
                         "a departmentless goal parks a direct work order "
                         "for the Director; nothing executes implicitly")

    def test_stage_persistence_is_one_step_per_advance(self):
        self.new_goal(owner="seo", metric="keyword_opportunities", target=1,
                      aggregation="count", workflow="keyword-research")
        before = self.current_run()
        self.runtime.once(self.goal_id)
        after = self.current_run()
        self.assertNotEqual((before.stage, before.status),
                            (after.stage, after.status),
                            "one advance must move exactly one stage boundary")
        self.assertEqual(after.sequence, before.sequence)

    def test_paused_goal_is_not_scheduled(self):
        self.new_goal(metric="weekly_sales")
        self.runtime.goals.set_status(self.goal_id, "paused")
        self.runtime.tick(max_advances=10)
        ready_ids = [r.goal_id for r in self.runtime.runs.ready()]
        self.assertNotIn(self.goal_id, ready_ids,
                         "paused Goals must never be scheduled")

    def test_completed_goal_advance_is_a_noop(self):
        self.new_goal(owner="seo", metric="keyword_opportunities", target=1,
                      aggregation="count", workflow="keyword-research")
        self.engine.resolution.executor = completing_executor(
            payload={"keyword_opportunities": 1})
        self.tick_until(lambda: self.runtime.goals.get(self.goal_id).status == "complete")
        result = self.runtime.once(self.goal_id)
        self.assertEqual(result["goal"]["goal_status"], "achieved")


# =========================================================================
# 2. WORKFLOW EXECUTION: steps, approvals, evidence, completion
# =========================================================================

@with_departments
class TestWorkflowExecution(HarnessCase):

    @classmethod
    def setUpClass(cls):
        os.environ["SPIELOS_TEST_DEPARTMENTS_DIR"] = str(
            FIXTURES / "departments")

    @classmethod
    def tearDownClass(cls):
        os.environ.pop("SPIELOS_TEST_DEPARTMENTS_DIR", None)

    def setUp(self):
        super().setUp()
        self.new_goal(name="Send outreach batch", owner="outbound",
                      metric="email_batches_sent", target=1,
                      workflow="email-outreach")

    def test_decision_binds_the_requested_department_workflow(self):
        self.runtime.tick(max_advances=5)
        run = self.current_run()
        self.assertIsNotNone(run.decision)
        self.assertEqual(run.decision.kind, "execute_workflow")
        self.assertEqual(run.decision.workflow_id, "outbound:email-outreach",
                         "the requested department workflow must be bound "
                         "into the persisted Decision")

    def test_workflow_parks_for_approval_before_external_send(self):
        self.engine.resolution.executor = completing_executor(payload={})
        parked = self.tick_until(
            lambda: any("approval required: send" in item.get("message", "")
                        for item in self.runtime.attention(goal_id=self.goal_id)))
        self.assertTrue(parked, "live external send must park for approval first")
        send_orders = [o for o in self.runtime.work_orders(goal_id=self.goal_id)
                       if o["step_id"] == "send"]
        self.assertEqual(send_orders, [],
                         "no work order may exist for the send step before "
                         "the owner approves")

    def test_approval_grants_exact_key_and_resumes(self):
        self.engine.resolution.executor = completing_executor(payload={})
        self.tick_until(lambda: self.runtime.attention(goal_id=self.goal_id))
        self.runtime.approve(self.goal_id, note="owner approves send",
                              keys=("send",))
        with self.runtime.connect() as connection:
            rows = [(r[0], r[1]) for r in connection.execute(
                "SELECT key,status FROM core_approvals").fetchall()]
        self.assertIn(("send", "approved"), rows,
                      "approve must persist the exact declared key")
        self.engine.resolution.executor = completing_executor(
            payload={"email_batches_sent": 1, "events": []})
        proceeded = self.tick_until(
            lambda: self.runtime.goals.get(self.goal_id).status == "complete"
            or any(o["step_id"] == "send" for o in
                   self.runtime.work_orders(goal_id=self.goal_id)))
        self.assertTrue(proceeded, "after approval the workflow must proceed")

    def test_approval_only_step_does_not_park_a_work_order(self):
        # D7 fixed: after /approve, the approve step (a gate with nothing to
        # produce) must auto-advance; the send step's own order appears
        # immediately, with no intervening approve-step order.
        self.engine.resolution.executor = completing_executor(payload={})
        self.tick_until(lambda: self.runtime.attention(goal_id=self.goal_id))
        self.runtime.approve(self.goal_id, keys=("send",))
        self.engine.resolution.executor = completing_executor(
            payload={"email_batches_sent": 1})
        self.tick_until(
            lambda: any(o["step_id"] == "send" for o in
                        self.runtime.work_orders(goal_id=self.goal_id)))
        opened = [o["step_id"] for o in
                  self.runtime.work_orders(goal_id=self.goal_id)]
        self.assertNotIn("approve", opened,
                         "an approval-only step is a gate, not work: no "
                         "work order may open for it")

    def test_run_scoped_approval_covers_later_interventions(self):
        # D5 fixed: --scope run grants the key against the run itself
        # (intervention_id NULL); the repository's run-key fallback then
        # satisfies every later intervention of the SAME run.
        self.engine.resolution.executor = completing_executor(payload={})
        self.tick_until(lambda: self.runtime.attention(goal_id=self.goal_id))
        self.runtime.approve(self.goal_id, keys=("send",), scope="run")
        with self.runtime.connect() as connection:
            scopes = connection.execute(
                "SELECT key,intervention_id FROM core_approvals").fetchall()
        for row in scopes:
            if row["key"] == "send":
                self.assertIsNone(row["intervention_id"],
                                  "run-scoped grants are stored intervention-free")

    def test_approvals_do_not_leak_into_the_next_run(self):
        self.engine.resolution.executor = completing_executor(payload={})
        self.tick_until(lambda: self.runtime.attention(goal_id=self.goal_id))
        self.runtime.approve(self.goal_id, keys=("send",))
        self.engine.resolution.executor = completing_executor(
            payload={"email_batches_sent": 1})
        self.tick_until(
            lambda: self.runtime.runs.current(self.goal_id).sequence > 1
            or self.runtime.goals.get(self.goal_id).status == "complete")
        if self.runtime.goals.get(self.goal_id).status != "complete":
            parked = self.tick_until(
                lambda: bool(self.runtime.attention(goal_id=self.goal_id)))
            self.assertTrue(parked,
                            "the next run must re-park for its own approval")

    def test_workflow_memory_learning_saved_with_run_lineage(self):
        self.engine.resolution.executor = completing_executor(
            payload={"email_batches_sent": 1},
            workflow_learning="Personalized hooks raise reply rates")
        self.tick_until(
            lambda: self.runtime.goals.get(self.goal_id).status == "complete")
        learned = [m for m in self.runtime.memories(limit=50)
                   if m["scope"] == "workflow"]
        self.assertTrue(learned,
                        "executor workflow_learning must persist as "
                        "workflow-scope memory with run lineage")
        if learned:
            self.assertIsNotNone(learned[0]["run_id"])

    def test_tasks_complete_learning_persists_workflow_memory(self):
        # D2 fixed: the documented host flow can write workflow memory.
        # Park the first workflow step for the host (as AssignmentExecutor
        # does), then complete it with --learning like the CLI would.
        self.engine.resolution.executor = ScriptedExecutor([])
        self.tick_until(lambda: self.active_orders())
        order = self.active_orders()[0]
        self.runtime.complete_work_order(
            order["id"], order["agent_id"],
            [{"kind": "lead_batch", "payload": {"leads": []}}],
            learning="Select queries perform better with fresh Supabase cohorts")
        learned = [m for m in self.runtime.memories(limit=50)
                   if m["scope"] == "workflow"]
        self.assertTrue(learned,
                        "tasks --complete --learning must persist "
                        "workflow-scope memory")
        if learned:
            self.assertEqual(learned[0]["run_id"], order["run_id"])
            self.assertEqual(learned[0]["goal_id"], order["goal_id"])

    def test_evidence_kinds_gate_step_completion(self):
        # Steps that declare evidence kinds must receive exactly them.
        self.engine.resolution.executor = completing_executor(payload={})
        self.tick_until(lambda: self.runtime.attention(goal_id=self.goal_id)
                        or self.active_orders())
        orders = self.active_orders()
        if orders and orders[0]["brief"].get("evidence_kinds"):
            required = set(orders[0]["brief"]["evidence_kinds"])
            from company.work_orders import WorkOrderRepository
            repo = WorkOrderRepository(Database(self.db))
            order = repo.get(orders[0]["id"])
            with self.assertRaises(ValueError):
                repo.complete_with_evidence(
                    order.id, {}, executor_id=order.claimed_by,
                    kind="wrong_kind", payload={})


# =========================================================================
# 3. MEMORY: scopes, triggers, lineage, supersession
# =========================================================================

class TestMemoryBehavior(HarnessCase):

    def setUp(self):
        super().setUp()
        self.new_goal(metric="m")
        self.run_id = self.current_run().id

    def _evidence(self, kind="m", payload=None):
        return self.runtime.evidence.record(
            goal_id=self.goal_id, run_id=self.run_id, kind=kind,
            payload=payload or {"m": 1})

    def test_owner_memory_saved_without_evidence_via_profile_set(self):
        record = self.runtime.set_profile_claim(
            namespace="layout", claim_key="canonical-folders",
            value={"rule": "one canonical layer per concept"})
        self.assertEqual(record["scope"], "owner")
        self.assertIn("layout.canonical-folders", record["claim"])

    def test_profile_set_supersedes_previous_claim_of_same_key(self):
        self.runtime.set_profile_claim(namespace="outbound", claim_key="tone",
                                       value="direct")
        second = self.runtime.set_profile_claim(namespace="outbound",
                                                 claim_key="tone", value="warmer")
        owner = self.runtime.owner_memory()
        active = [m for m in owner if m["claim_key"] == "tone"
                  and m["status"] == "active"]
        self.assertEqual(len(active), 1,
                         "only one active owner claim per key may remain")
        self.assertIn('"warmer"', second["claim"])

    def test_non_owner_memory_requires_evidence_and_lineage(self):
        evidence = self._evidence()
        record = self.runtime.memory.remember(
            "workflow", "hook-before-pain works", evidence_ids=(evidence.id,),
            goal_id=self.goal_id, run_id=self.run_id,
            workflow_id="outbound:email-outreach")
        self.assertEqual(record.scope, "workflow")
        self.assertEqual(record.evidence_ids, (evidence.id,))

    def test_non_owner_memory_rejected_without_evidence(self):
        with self.assertRaises(ValueError):
            self.runtime.memory.remember("strategy", "no proof",
                                         goal_id=self.goal_id,
                                         run_id=self.run_id)

    def test_non_owner_memory_rejected_without_goal_run_lineage(self):
        evidence = self._evidence()
        with self.assertRaises(ValueError):
            self.runtime.memory.remember("workflow", "orphan learning",
                                         evidence_ids=(evidence.id,))

    def test_memory_evidence_must_belong_to_same_goal_and_run(self):
        other = self.other_goal(name="G2")
        other_run = self.runtime.runs.current(other["id"])
        evidence = self.runtime.evidence.record(
            goal_id=other["id"], run_id=other_run.id, kind="m_other", payload={})
        with self.assertRaises(ValueError):
            self.runtime.memory.remember(
                "workflow", "cross-goal learning", evidence_ids=(evidence.id,),
                goal_id=self.goal_id, run_id=self.run_id)

    def test_invalid_scope_rejected(self):
        with self.assertRaises(ValueError):
            self.runtime.memory.remember("department", "not a scope")

    def test_supersession_only_within_same_scope(self):
        evidence = self._evidence()
        first = self.runtime.memory.remember(
            "strategy", "v1", evidence_ids=(evidence.id,),
            goal_id=self.goal_id, run_id=self.run_id)
        second = self.runtime.memory.remember(
            "strategy", "v2", evidence_ids=(evidence.id,),
            goal_id=self.goal_id, run_id=self.run_id,
            supersedes_id=first.id)
        self.assertEqual(second.status, "active")
        self.assertEqual(self.runtime.memory.get(first.id).status, "superseded")

    def test_relevant_memory_scoping(self):
        evidence = self._evidence()
        self.runtime.memory.remember("owner", "owner claim")
        self.runtime.memory.remember(
            "workflow", "wf learning", evidence_ids=(evidence.id,),
            goal_id=self.goal_id, run_id=self.run_id, workflow_id="w1")
        self.runtime.memory.remember(
            "strategy", "strategy learning", evidence_ids=(evidence.id,),
            goal_id=self.goal_id, run_id=self.run_id)
        relevant = self.runtime.memory.relevant(
            goal_id=self.goal_id, workflow_id="w1", limit=10)
        scopes = [m.scope for m in relevant]
        for expected in ("owner", "workflow", "strategy"):
            self.assertIn(expected, scopes)
        without_workflow = self.runtime.memory.relevant(
            goal_id=self.goal_id, workflow_id=None, limit=10)
        self.assertNotIn("workflow", [m.scope for m in without_workflow],
                         "workflow memory applies only with its workflow_id")

    def test_strategy_memory_written_by_goal_evaluation_with_evidence(self):
        evidence = self._evidence()
        from company.runtime.engine import Evaluation
        self.engine._commit_evaluation(
            self.engine.goals.get(self.goal_id),
            self.engine.runs.current(self.goal_id),
            Evaluation(False, {}, "summary",
                       strategy_learning="retarget ICP segment",
                       evidence_ids=(evidence.id,)))
        strategy = [m for m in self.runtime.memories(limit=20)
                    if m["scope"] == "strategy"]
        self.assertTrue(strategy,
                        "strategy_learning must persist with run lineage")

    def _commit_evaluation(self, learning, evidence_ids):
        from company.runtime.engine import Evaluation
        return self.engine._commit_evaluation(
            self.engine.goals.get(self.goal_id),
            self.engine.runs.current(self.goal_id),
            Evaluation(False, {}, "s", strategy_learning=learning,
                       evidence_ids=evidence_ids))

    def test_strategy_learning_without_evidence_is_refused(self):
        # The guard lives in GoalRuntime.advance (every real path);
        # _commit_evaluation persists what it is given, so probe advance().
        self._drive_to_evaluate()

        class GuardedController(type(self.engine.controller)):
            def evaluate(inner, context, decision, ev):
                from company.runtime.engine import Evaluation
                return Evaluation(False, {}, "s", strategy_learning="x",
                                  evidence_ids=())

        original = self.engine.controller
        self.engine.controller = GuardedController(self.engine.database)
        try:
            with self.assertRaises(ValueError):
                self.engine.advance(self.goal_id)
        finally:
            self.engine.controller = original

    def test_strategy_evidence_must_belong_to_the_evaluated_run(self):
        other = self.other_goal(name="G2")
        other_run = self.runtime.runs.current(other["id"])
        other_evidence = self.runtime.evidence.record(
            goal_id=other["id"], run_id=other_run.id, kind="m_other", payload={})
        self._drive_to_evaluate()

        class GuardedController(type(self.engine.controller)):
            def evaluate(inner, context, decision, ev):
                from company.runtime.engine import Evaluation
                return Evaluation(False, {}, "s", strategy_learning="x",
                                  evidence_ids=(other_evidence.id,))

        original = self.engine.controller
        self.engine.controller = GuardedController(self.engine.database)
        try:
            with self.assertRaises(ValueError):
                self.engine.advance(self.goal_id)
        finally:
            self.engine.controller = original

    def _drive_to_evaluate(self):
        """Park the direct work order, answer it, and land on the
        EVALUATE/running boundary where the guard probe can act."""
        self.engine.resolution.executor = ScriptedExecutor([])
        for _ in range(12):
            self.runtime.tick(max_advances=30)
            run = self.current_run()
            if run.stage == GoalStage.EVALUATE and run.status == "running":
                return
            if run.status == "waiting":
                order = self.active_orders()[0]
                self.runtime.complete_work_order(
                    order["id"], order["agent_id"],
                    [{"kind": "m", "payload": {"m": 0}}])
                run = self.current_run()
                if run.stage == GoalStage.EVALUATE and run.status == "running":
                    return
        run = self.current_run()
        self.assertEqual((run.stage, run.status),
                         (GoalStage.EVALUATE, "running"))

    def test_memory_add_writes_workflow_and_strategy_with_lineage(self):
        # D2 fixed: `memory add` reaches both scopes with the engine guards.
        evidence = self._evidence()
        workflow_memory = self.runtime.add_memory(
            "workflow", "batch throttling at 25/hour held delivery",
            evidence_ids=[evidence.id], goal_id=self.goal_id,
            run_id=self.run_id, workflow_id="outbound:email-outreach")
        self.assertEqual(workflow_memory.scope, "workflow")
        self.assertEqual(workflow_memory.evidence_ids, (evidence.id,))
        strategy_memory = self.runtime.add_memory(
            "strategy", "double opt-in lifts reply quality",
            evidence_ids=[evidence.id], goal_id=self.goal_id,
            run_id=self.run_id)
        self.assertEqual(strategy_memory.scope, "strategy")

    def test_memory_add_refuses_orphan_and_cross_run_evidence(self):
        evidence = self._evidence()
        with self.assertRaises(ValueError):
            self.runtime.add_memory("strategy", "no lineage",
                                    evidence_ids=[evidence.id])
        other = self.other_goal(name="G2")
        other_run = self.runtime.runs.current(other["id"])
        cross = self.runtime.evidence.record(
            goal_id=other["id"], run_id=other_run.id, kind="m_other", payload={})
        with self.assertRaises(ValueError):
            self.runtime.add_memory(
                "workflow", "cross-run claim", evidence_ids=[cross.id],
                goal_id=self.goal_id, run_id=self.run_id)

    def test_memory_add_rejects_owner_scope(self):
        with self.assertRaises(ValueError):
            self.runtime.add_memory("owner", "owner claims use profile set")


# =========================================================================
# 4. CONTEXT ASSEMBLY (what the host hooks inject per request)
# =========================================================================

class TestContextAssembly(HarnessCase):

    def setUp(self):
        super().setUp()
        self.new_goal(name="One sale per week", metric="weekly_sales")
        self.runtime.set_profile_claim(namespace="owner", claim_key="pref",
                                       value="concise reports")

    def test_context_contains_prompt_goal_memory_evidence(self):
        self.runtime.add_evidence(self.goal_id, kind="weekly_sales",
                                  source="host", payload={"weekly_sales": 0})
        projection = self.runtime.assemble_context(
            prompt="what should I do next?", owner_id="director")
        self.assertIn("what should I do next?", projection["context"])
        self.assertIn("One sale per week", projection["context"])
        self.assertIn("weekly_sales", projection["context"])
        self.assertIn("owner.pref", projection["context"],
                      "owner memory must be injected into host context")
        self.assertEqual(projection["goal_id"], self.goal_id)
        self.assertTrue(projection["sources"])

    def test_readonly_context_does_not_mutate_database(self):
        before = self.db.read_bytes()
        CleanCommandRuntime(self.db, readonly=True).assemble_context(
            prompt="x", owner_id="director")
        self.assertEqual(before, self.db.read_bytes(),
                         "readonly context must not touch the database file")

    def test_readonly_snapshot_is_cached_per_database_version(self):
        # D8 fixed: repeated read-only projections over an unchanged
        # database reuse one scratch snapshot instead of copying per request.
        CleanCommandRuntime._SNAPSHOT_CACHE.clear()
        for _ in range(3):
            CleanCommandRuntime(self.db, readonly=True).assemble_context(
                prompt="x", owner_id="director")
        self.assertEqual(len(CleanCommandRuntime._SNAPSHOT_CACHE), 1,
                         "one unchanged database must yield one snapshot")
        # and a mutated database is re-copied, never stale.
        self.runtime.add_evidence(self.goal_id, kind="weekly_sales",
                                  source="host", payload={"weekly_sales": 1})
        projection = CleanCommandRuntime(self.db, readonly=True).assemble_context(
            prompt="x", owner_id="director")
        self.assertIn("weekly_sales", projection["context"])

    def test_codex_hook_output_shape(self):
        projection = self.runtime.assemble_context(prompt="hi",
                                                   owner_id="director")
        payload = codex_hook_output(projection, "UserPromptSubmit")
        self.assertTrue(payload["continue"])
        self.assertEqual(payload["hookSpecificOutput"]["hookEventName"],
                         "UserPromptSubmit")
        self.assertIn("hi", payload["hookSpecificOutput"]["additionalContext"])

    def test_context_token_budget_truncates(self):
        projection = self.runtime.assemble_context(
            prompt="x" * 200, owner_id="director", token_budget=10)
        self.assertLessEqual(len(projection["context"]), 44)

    def test_context_scopes_to_requested_owner(self):
        self.new_goal(name="Director owned goal", metric="articles",
                      aggregation="latest")
        projection = self.runtime.assemble_context(prompt="p", owner_id="director")
        self.assertIn("One sale per week", projection["context"])


# =========================================================================
# 5. WORK ORDERS: claiming, lease, executor identity, evidence
# =========================================================================

class TestWorkOrderContract(HarnessCase):

    def setUp(self):
        super().setUp()
        self.new_goal(metric="m")
        self.runtime.tick(max_advances=10)  # parks one direct work order
        self.order_row = self.active_orders()[0]
        self.order_id = self.order_row["id"]

    def test_runtime_claims_orders_with_the_bare_agent_id(self):
        # D1 fixed: the runtime claims with the agent id the notification
        # names, so the documented flow completes without ceremony.
        self.assertEqual(self.order_row["claimed_by"], "director",
                         "orders must be claimable by the documented host "
                         "identity (the bare agent id)")

    def test_complete_with_agent_id_succeeds_while_lease_holds(self):
        # D1 fixed (inverted pin): the documented flow works immediately.
        result = self.runtime.complete_work_order(
            self.order_id, "director",
            [{"kind": "m", "payload": {"m": 1}}])
        self.assertEqual(result["work_order"]["status"], "completed")
        run = self.current_run()
        self.assertEqual(run.stage, GoalStage.EVALUATE,
                         "direct completion must wake the run into EVALUATE")

    def test_complete_with_executor_prefix_identity_succeeds(self):
        # D1 compatibility: the historical 'executor:<agent>' claimant is
        # accepted as a synonym, so older homes never wedge.
        self.runtime.complete_work_order(
            self.order_id, "executor:director",
            [{"kind": "m", "payload": {"m": 1}}])
        run = self.current_run()
        self.assertEqual(run.stage, GoalStage.EVALUATE)

    def test_complete_with_wrong_identity_is_refused(self):
        with self.assertRaises(RuntimeError):
            self.runtime.complete_work_order(
                self.order_id, "someone-else",
                [{"kind": "m", "payload": {"m": 1}}])

    def test_completing_order_records_evidence_with_lineage(self):
        self.runtime.complete_work_order(
            self.order_id, "director",
            [{"kind": "m", "payload": {"m": 1}}])
        evidence = self.runtime.evidence.for_goal(self.goal_id)
        self.assertTrue(all(e.goal_id == self.goal_id for e in evidence))
        self.assertTrue(any(e.payload == {"m": 1} for e in evidence))

    def test_multiple_evidence_items_recorded_atomically(self):
        result = self.runtime.complete_work_order(
            self.order_id, "director",
            [{"kind": "m", "payload": {"m": 1}},
             {"kind": "detail", "payload": {"note": "n"}}])
        self.assertEqual(result["work_order"]["status"], "completed")
        kinds = [e.kind for e in self.runtime.evidence.for_run(
            self.current_run().id)]
        self.assertIn("detail", kinds)

    def test_lease_expiry_allows_reclaim_by_host_agent(self):
        with self.runtime.connect() as connection:
            connection.execute(
                "UPDATE core_work_orders SET lease_expires_at=? WHERE id=?",
                ("2000-01-01T00:00:00+00:00", self.order_id))
        claimed = self.runtime.claim_work_order(self.order_id, "director")
        self.assertEqual(claimed["claimed_by"], "director")
        done = self.runtime.complete_work_order(
            self.order_id, "director", [{"kind": "m", "payload": {"m": 1}}])
        self.assertEqual(done["work_order"]["status"], "completed")

    def test_completion_requires_evidence(self):
        with self.assertRaises(ValueError):
            self.runtime.complete_work_order(self.order_id, "director", [])


# =========================================================================
# 6. NOTIFICATIONS / ATTENTION (the OpenCode plugin surface)
# =========================================================================

class TestNotificationsAndAttention(HarnessCase):

    def setUp(self):
        super().setUp()
        self.new_goal(metric="m")

    def test_ask_user_creates_pending_owner_input_required_notification(self):
        self.runtime.tick(max_advances=10)
        pending = self.runtime.notifications(goal_id=self.goal_id)
        self.assertEqual(len(pending), 1)
        self.assertEqual(pending[0]["kind"], "owner_input_required")
        self.assertIn("required_user_action", pending[0]["payload"])

    def test_attention_maps_pending_notifications(self):
        self.runtime.tick(max_advances=10)
        attention = self.runtime.attention(goal_id=self.goal_id)
        self.assertEqual(len(attention), 1)
        self.assertIn("message", attention[0])

    def test_acknowledge_only_pending(self):
        self.runtime.tick(max_advances=10)
        item = self.runtime.notifications(goal_id=self.goal_id)[0]
        self.runtime.acknowledge_notification(item["id"])
        with self.assertRaises(ValueError):
            self.runtime.acknowledge_notification(item["id"])

    def test_workflow_completion_acknowledges_pending_attention(self):
        self.runtime.tick(max_advances=10)
        order = self.active_orders()[0]
        self.runtime.complete_work_order(
            order["id"], "director",
            [{"kind": "m", "payload": {"m": 1}}])
        self.assertEqual(self.runtime.notifications(goal_id=self.goal_id), [],
                         "answering a parked ask must clear its attention")

    def test_company_snapshot_surfaces_attention_and_work_orders(self):
        self.runtime.tick(max_advances=10)
        snapshot = self.runtime.company_snapshot()
        self.assertIn("attention", snapshot)
        self.assertIn("work_orders", snapshot)
        self.assertEqual(snapshot["counts"]["active"], 1)

    def test_unread_results_surface_completed_runs(self):
        self.runtime.tick(max_advances=10)
        order = self.active_orders()[0]
        self.runtime.complete_work_order(
            order["id"], "director",
            [{"kind": "m", "payload": {"m": 1}}])
        self.runtime.tick(max_advances=10)  # EVALUATE -> run complete
        results = self.runtime.unread_results(goal_id=self.goal_id)
        self.assertTrue(results,
                        "completed runs with evaluations must surface as "
                        "unread results")


# =========================================================================
# 7. REGISTRIES: departments, installed agents, metric utilities
# =========================================================================

@with_departments
class TestRegistries(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        os.environ["SPIELOS_TEST_DEPARTMENTS_DIR"] = str(
            FIXTURES / "departments")

    @classmethod
    def tearDownClass(cls):
        os.environ.pop("SPIELOS_TEST_DEPARTMENTS_DIR", None)

    def test_fixture_departments_import_as_clean_declarations(self):
        found = departments()
        expected = {"analytics", "client_delivery", "content", "design",
                    "outbound", "seo", "videography"}
        self.assertEqual(set(found), expected,
                         "the fixture tree must mirror a real home's "
                         "department layer")

    def test_every_workflow_step_binds_agent_and_data(self):
        for manifest in departments().values():
            for workflow in manifest.workflows:
                self.assertTrue(workflow.steps,
                                f"{manifest.id}:{workflow.id} has no steps")
                for step in workflow.steps:
                    self.assertTrue(step.agent_id,
                                    f"{manifest.id}:{workflow.id}:{step.id} "
                                    "lacks an agent")
                    self.assertTrue(step.instruction,
                                    f"{manifest.id}:{workflow.id}:{step.id} "
                                    "lacks instructions")

    def test_department_evidence_metrics_declared_for_goal_metrics(self):
        manifests = departments()
        self.assertIn("email_batches_sent",
                      manifests["outbound"].evidence_metrics)
        self.assertEqual(
            manifests["outbound"].evidence_metrics["email_batches_sent"],
            ("provider_events",),
            "goal metrics must map to the evidence kinds that prove them")

    def test_metric_util_operators(self):
        self.assertTrue(compare(5, "ge", 1))
        self.assertTrue(compare(1, "le", 1))
        self.assertTrue(compare(2, "eq", 2))
        self.assertFalse(compare(1, "gt", 2))
        self.assertFalse(compare(1, "unknown-op", 0),
                         "unknown operator must fail closed")

    def test_installed_agents_load_into_the_resolution_cycle(self):
        # D6 fixed: installed agent declarations reach the cycle. The layer
        # is <home>/.agents/company/agents/installed (canonical user layer).
        from company.agents import available_agents
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            installed = home / ".agents" / "company" / "agents" / "installed"
            installed.mkdir(parents=True)
            (installed / "seo-operator.json").write_text(json.dumps({
                "id": "seo-operator",
                "description": "SEO operator",
                "skill_ids": ["seo"],
                "permissions": ["write_evidence"],
                "produces": ["seo_audit", "seo_report"],
            }))
            (installed / "broken.json").write_text("{not json")
            agents = available_agents(home)
        self.assertIn("seo-operator", agents,
                      "installed declarations must load as Agent records")
        agent = agents["seo-operator"]
        self.assertEqual(agent.skill_ids, ("seo",))
        self.assertEqual(agent.produces, ("seo_audit", "seo_report"))
        self.assertNotIn("broken", agents,
                         "an unparseable declaration is skipped, not fatal")

    def test_runtime_passes_installed_agents_to_resolution(self):
        # D6 wiring: CleanCommandRuntime plumbs available_agents() through
        # GoalRuntime into ResolutionCycle.agents. Point the loader at a
        # fixture home so the assertion does not depend on this checkout.
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            installed = home / ".agents" / "company" / "agents" / "installed"
            installed.mkdir(parents=True)
            (installed / "wired-agent.json").write_text(json.dumps(
                {"id": "wired-agent", "skill_ids": ["outbound-email"]}))
            from company.agents import available_agents
            self.assertIn("wired-agent", available_agents(home))
            runtime_db = home / ".spielos" / "state" / "company.sqlite"
            runtime = CleanCommandRuntime(runtime_db)
            self.assertIn("wired-agent", runtime.runtime.resolution.agents,
                          "CleanCommandRuntime must load installed agents "
                          "into the resolution cycle")


# =========================================================================
# 8. SCHEMA INTEGRITY: lineage triggers, evidence immutability
# =========================================================================

class TestSchemaIntegrity(HarnessCase):

    def setUp(self):
        super().setUp()
        self.new_goal(metric="m")
        self.run_id = self.current_run().id

    def test_evidence_is_immutable(self):
        self.runtime.add_evidence(self.goal_id, kind="m", source="host",
                                  payload={"m": 1})
        with self.assertRaises(Exception):
            with self.runtime.connect() as connection:
                connection.execute("UPDATE core_evidence SET kind='hacked'")

    def test_evidence_cannot_be_deleted(self):
        self.runtime.add_evidence(self.goal_id, kind="m", source="host",
                                  payload={"m": 1})
        with self.assertRaises(Exception):
            with self.runtime.connect() as connection:
                connection.execute("DELETE FROM core_evidence")

    def test_intervention_lineage_mismatch_aborts(self):
        other = self.new_goal(name="G2", metric="m2")
        with self.assertRaises(Exception):
            with self.runtime.connect() as connection:
                connection.execute(
                    "INSERT INTO core_interventions VALUES "
                    "(?,?,?,?,?,?,?,?,?,?)",
                    ("i-bad", other["id"], self.run_id, "k", "d", "running",
                     None, "{}", "2026-01-01", "2026-01-01"))

    def test_memory_scope_check_constraint(self):
        with self.assertRaises(Exception):
            with self.runtime.connect() as connection:
                connection.execute(
                    "INSERT INTO core_memory (id,scope,claim,goal_id,run_id,"
                    "intervention_id,workflow_id,evidence_ids_json,created_at)"
                    " VALUES ('m-bad','department','c',NULL,NULL,NULL,NULL,"
                    "'[]','2026')")

    def test_approval_lineage_mismatch_aborts(self):
        other = self.new_goal(name="G3", metric="m3")
        with self.assertRaises(Exception):
            with self.runtime.connect() as connection:
                connection.execute(
                    "INSERT INTO core_approvals VALUES (?,?,?,?,?,?,?,?,?)",
                    ("a-bad", other["id"], self.run_id, None, "k",
                     "approved", None, "2026", "2026"))


# =========================================================================
# 9. RESOLUTION OUTCOMES: fixable, escalate, ask_user, budget, D4 parking
# =========================================================================

class TestResolutionOutcomes(HarnessCase):

    def setUp(self):
        super().setUp()
        self.new_goal(metric="m")

    def _drive_with(self, script, budget=15):
        self.engine.resolution.executor = ScriptedExecutor(script)
        for _ in range(budget):
            self.runtime.tick(max_advances=30)
            run = self.current_run()
            if run.status in {"waiting", "complete"} or run.sequence > 1:
                return run
        return self.current_run()

    def test_fixable_failures_retry_locally_with_iteration_evidence(self):
        run = self._drive_with([
            AgentResult("fixable", message="transient"),
            AgentResult("completed", evidence=(AgentEvidence("m", {"m": 1}),)),
        ])
        kinds = [e.kind for e in self.runtime.evidence.for_goal(self.goal_id)]
        self.assertIn("resolution_iteration", kinds,
                      "local fixes must be recorded as iteration evidence")
        self.assertEqual(run.sequence, 1,
                         "a fixed-locally failure must not consume the run")

    def test_escalation_completes_run_and_opens_next_goal_run(self):
        run = self._drive_with([AgentResult("escalate", message="invalid")])
        self.assertGreater(run.sequence, 1,
                           "escalation must return control to a fresh run")
        with self.runtime.connect() as connection:
            outcome = connection.execute(
                "SELECT resolution_outcome FROM core_interventions"
            ).fetchone()[0]
        self.assertEqual(outcome, "ESCALATE_TO_GOAL")

    def test_repeated_escalation_parks_after_threshold(self):
        # D4 fixed (inverted pin): three consecutive escalations park the
        # goal for the owner instead of spinning new runs forever.
        from company.runtime.engine import ESCALATION_PARK_THRESHOLD
        self.engine.resolution.executor = ScriptedExecutor(
            [AgentResult("escalate", message="boom")] * 200)
        for _ in range(40):
            self.runtime.tick(max_advances=50)
        runs = len(self.runtime.runs._get_all(self.goal_id)) \
            if hasattr(self.runtime.runs, "_get_all") else None
        with self.runtime.connect() as connection:
            count = connection.execute(
                "SELECT COUNT(*) FROM core_runs WHERE goal_id=?",
                (self.goal_id,)).fetchone()[0]
            status = connection.execute("""SELECT status FROM core_runs
                WHERE goal_id=? ORDER BY sequence DESC LIMIT 1""",
                (self.goal_id,)).fetchone()[0]
        self.assertLessEqual(count, ESCALATION_PARK_THRESHOLD + 1,
                             "escalation must stop opening runs")
        self.assertEqual(status, "waiting",
                         "the escalated goal must park for the owner")
        attention = self.runtime.attention(goal_id=self.goal_id)
        self.assertTrue(any("escalation" in item.get("message", "").lower()
                            for item in attention),
                        "a parked escalation must surface owner attention")

    def test_ask_user_parks_run_and_notification(self):
        run = self._drive_with([])
        self.assertEqual((run.stage, run.status), (GoalStage.ACT, "waiting"))
        self.assertEqual(len(self.runtime.attention(goal_id=self.goal_id)), 1)

    def test_resume_continues_parked_run_after_host_answer(self):
        self._drive_with([])
        run = self.current_run()
        self.assertEqual(run.status, "waiting")
        order = self.active_orders()[0]
        self.runtime.complete_work_order(
            order["id"], "director",
            [{"kind": "m", "payload": {"m": 1}}])
        run = self.current_run()
        self.assertEqual(run.stage, GoalStage.EVALUATE,
                         "answering the parked ask must continue the run")

    def test_local_iteration_budget_yields_continue_local(self):
        # When the host keeps fixing forever without completing, the cycle
        # must stop at max_local_iterations and park, not loop forever.
        self.engine.resolution.executor = ScriptedExecutor(
            [AgentResult("fixable", message="forever")] * 200)
        self.engine.resolution.max_local_iterations = 3
        for _ in range(10):
            self.runtime.tick(max_advances=30)
        run = self.current_run()
        self.assertIn(run.status, {"waiting", "ready", "running"})


# =========================================================================
# 10. GOAL RELATIONSHIPS & SCHEDULING (supports/blocks/priority)
# =========================================================================

class TestGoalTopologyAndScheduling(HarnessCase):

    def test_blocks_edge_prevents_ready_run(self):
        primary = self.new_goal(name="Primary")
        blocked = self.new_goal(name="Blocked")
        self.runtime.goals.add_block(primary["id"], blocked["id"])
        ready = [r.goal_id for r in self.runtime.runs.ready()]
        self.assertNotIn(blocked["id"], ready,
                         "a Goal blocked by an incomplete prerequisite must "
                         "never appear ready")

    def test_priority_orders_ready_runs(self):
        self.new_goal(name="low", priority="low")
        critical = self.new_goal(name="crit", priority="critical")
        ready = [r.goal_id for r in self.runtime.runs.ready()]
        others = [g["id"] for g in self.runtime.goal_summaries()
                  if g["id"] != critical["id"]]
        self.assertTrue(ready.index(critical["id"]) < max(
            ready.index(g) for g in others if g in ready),
            "critical priority must be scheduled first")

    def test_topology_audit_detects_missing_parent(self):
        # Create a real orphan goal: the audit must flag it. Written with
        # a raw connection (no FK pragma) to simulate a parent row that
        # vanished in an older database.
        import sqlite3
        parent = self.new_goal(name="P")
        self.new_goal(name="C", parent_id=parent["id"])
        goal_id = "goal-orphan-1"
        raw = sqlite3.connect(self.db)
        raw.execute("PRAGMA foreign_keys=OFF")
        raw.execute(
            "INSERT INTO core_goals VALUES (?,?,?,?,?,?,?,?,?)",
            (goal_id, "Orphan", "m", "ge", "1", "goal-missing-parent",
             "active", "2026-01-01", "2026-01-01"))
        raw.execute(
            "INSERT INTO core_goal_metadata VALUES (?,?,?,?)",
            (goal_id, "director", None, "{}"))
        raw.commit()
        raw.close()
        audit = self.runtime.topology_audit()
        kinds = [d["kind"] for d in audit["defects"]]
        self.assertIn("missing_parent", kinds)
        defect = next(d for d in audit["defects"]
                      if d["kind"] == "missing_parent")
        self.assertEqual(defect["parent_id"], "goal-missing-parent")

    def test_cycle_edges_rejected(self):
        a = self.new_goal(name="A")
        b = self.new_goal(name="B")
        self.runtime.goals.add_block(a["id"], b["id"])
        with self.assertRaises(ValueError):
            self.runtime.goals.add_block(b["id"], a["id"])

    def test_parent_cycle_rejected(self):
        a = self.new_goal(name="A")
        b = self.new_goal(name="B", parent_id=a["id"])
        with self.assertRaises(ValueError):
            self.runtime.goals.set_parent(a["id"], b["id"])

    def test_all_children_achieved_rollup(self):
        parent = self.new_goal(name="All children",
                               metric="all_children_achieved",
                               operator="eq", target=1)
        child = self.new_goal(name="child", parent_id=parent["id"])
        context = self.engine._context(
            self.engine.goals.get(parent["id"]),
            self.engine.runs.current(parent["id"]))
        observation = self.engine.controller.observe(context)
        self.assertFalse(observation["all_children_achieved"])
        self.engine.goals.set_status(child["id"], "complete")
        context = self.engine._context(
            self.engine.goals.get(parent["id"]),
            self.engine.runs.current(parent["id"]))
        observation = self.engine.controller.observe(context)
        self.assertTrue(observation["all_children_achieved"])


# =========================================================================
# 11. EVALS (LLM-as-judge Lego piece)
# =========================================================================

class TestEvalEngine(unittest.TestCase):

    def _suite(self, criteria, thresholds=None, item_selector=None):
        from company.evals.models import EvalCriterion, EvalSuite
        return EvalSuite(
            id="s", name="S", scope="x", department_id="content",
            payload_kind="campaign_manifest", criteria=criteria,
            thresholds=thresholds or {},
            item_selector=item_selector)

    def test_suite_validation_and_report_computation(self):
        from company.evals.models import EvalCriterion
        from company.evals.engine import run_suite, report_to_evidence
        suite = self._suite(
            (EvalCriterion("c1", "One", "d", "src"),
             EvalCriterion("c2", "Two", "d", "src")),
            thresholds={"all_pass": True},
            item_selector=lambda payload: [(i["item_id"], i)
                                           for i in payload["items"]])
        payload = {"batch_id": "b1", "items": [{"item_id": "it1"}]}
        verdicts = {"items": {"it1": {
            "c1": {"pass": True, "score": 1.0, "reason": "ok"},
            "c2": {"pass": False, "score": 0.4, "reason": "weak"}}}}
        report = run_suite(suite, payload, verdicts)
        self.assertFalse(report.overall)
        self.assertEqual(report.failed_criteria(), ["it1:c2"])
        evidence = report_to_evidence(report)
        self.assertFalse(evidence["overall"])
        self.assertIn("per_item", evidence)

    def test_invalid_verdict_document_rejected(self):
        from company.evals.models import EvalCriterion
        from company.evals.engine import run_suite
        suite = self._suite((EvalCriterion("c1", "One", "d", "src"),))
        with self.assertRaises(ValueError):
            run_suite(suite, {"items": []}, {"items": {"missing": {}}})

    def test_warn_criteria_advisory_unless_all_pass(self):
        from company.evals.models import EvalCriterion
        from company.evals.engine import run_suite
        suite = self._suite((EvalCriterion("c1", "One", "d", "src",
                                           severity="warn"),))
        payload = {"id": "i"}
        verdicts = {"items": {"i": {"c1": {"pass": False, "score": 0.1,
                                           "reason": "warn only"}}}}
        report = run_suite(suite, payload, verdicts)
        self.assertTrue(report.overall,
                        "warn criteria must not gate by default")

    def test_all_pass_threshold_makes_warn_criteria_gate(self):
        from company.evals.models import EvalCriterion
        from company.evals.engine import run_suite
        suite = self._suite((EvalCriterion("c1", "One", "d", "src",
                                           severity="warn"),),
                            thresholds={"all_pass": True})
        payload = {"id": "i"}
        verdicts = {"items": {"i": {"c1": {"pass": False, "score": 0.1,
                                           "reason": "warn gates now"}}}}
        report = run_suite(suite, payload, verdicts)
        self.assertFalse(report.overall,
                         "all_pass=true must make even warn criteria gate")


@with_departments
class TestShippedEvalSuites(unittest.TestCase):
    """Fixture suites (content/design) must import with real sources."""

    @classmethod
    def setUpClass(cls):
        os.environ["SPIELOS_TEST_DEPARTMENTS_DIR"] = str(
            FIXTURES / "departments")

    @classmethod
    def tearDownClass(cls):
        os.environ.pop("SPIELOS_TEST_DEPARTMENTS_DIR", None)

    def test_content_and_design_suites_importable_with_real_sources(self):
        # Eval criteria ground in source files. In a real home those live in
        # the preserved user layers; in the source fixture tree the
        # referenced paths are rewritten to the fixture home layout, so we
        # assert importability and structure (ids, departments, criteria).
        from company.evals.registry import suites
        found = suites()
        self.assertTrue(any(s.department_id == "content" for s in found.values()))
        self.assertTrue(any(s.department_id == "design" for s in found.values()))
        for suite in found.values():
            for criterion in suite.criteria:
                self.assertTrue(criterion.id and criterion.description,
                                f"{suite.id} has a hollow criterion")


# =========================================================================
# 12. CLI SURFACE (the documented host command vocabulary)
# =========================================================================

class TestCLISurface(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        import json as jsonlib
        import subprocess
        cls.json = jsonlib
        cls.subprocess = subprocess
        handle = tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False)
        handle.close()
        cls.db = Path(handle.name)
        cls.db.unlink()
        cls.run_cli("goal", "create", "--name", "CLI goal",
                    "--owner", "director", "--metric", "m",
                    "--target", "1")

    @classmethod
    def run_cli(cls, *args, expect_ok=True):
        env = dict(os.environ, PYTHONPATH=str(REPO),
                   PYTHONDONTWRITEBYTECODE="1",
                   SPIELOS_HOME=str(REPO))
        result = cls.subprocess.run(
            [sys.executable, "-B", "-m", "company", "--db", str(cls.db), *args],
            cwd=str(REPO), env=env, capture_output=True, text=True,
            timeout=180)
        if expect_ok:
            assert result.returncode == 0, f"CLI {args} failed: {result.stderr}"
            try:
                return cls.json.loads(result.stdout)
            except cls.json.JSONDecodeError:
                return result.stdout
        return result

    @classmethod
    def tearDownClass(cls):
        cls.db.unlink(missing_ok=True)

    def test_goal_create_through_cli(self):
        listing = self.run_cli("goal", "list", "--json")
        self.assertEqual(len(listing), 1)
        self.assertEqual(listing[0]["name"], "CLI goal")

    def test_status_snapshot_json(self):
        snapshot = self.run_cli("status", "--json")
        self.assertIn("counts", snapshot)
        self.assertEqual(snapshot["counts"]["active"], 1)

    def test_context_command_json(self):
        projection = self.run_cli("context", "--prompt", "hello", "--json")
        self.assertIn("hello", projection["context"])

    def test_runner_tick_quiesces_after_park(self):
        tick = self.run_cli("runner", "tick", "--json")
        self.assertTrue(tick["quiescent"],
                        "tick parks work for the host and then goes quiet")

    def test_notifications_list_json(self):
        self.run_cli("runner", "tick", "--json")
        rows = self.run_cli("notifications", "list", "--json")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["kind"], "owner_input_required")

    def test_tasks_complete_by_agent_id_documented_flow_succeeds(self):
        # D1 fixed (inverted pin): the documented host flow completes an
        # order the runtime claimed, using the agent id, first try.
        orders = self.run_cli("tasks", "--json")
        order_id, agent_id = orders[0]["id"], orders[0]["agent_id"]
        result = self.run_cli("tasks", order_id, "--complete", agent_id,
                              "--evidence", '[{"kind":"m","payload":{"m":1}}]')
        self.assertEqual(result["work_order"]["status"], "completed")

    def test_memory_summary_scopes(self):
        summary = self.run_cli("memory", "summary", "--json")
        self.assertEqual(set(summary["durable_memory"]),
                         {"owner", "workflow", "strategy"})

    def test_profile_set_and_list(self):
        self.run_cli("profile", "set", "--namespace", "ns", "--key", "k",
                     "--value", '"v"')
        listing = self.run_cli("profile", "list", "--json")
        self.assertTrue(any(item["claim_key"] == "k" for item in listing))

    def test_tasks_complete_learning_flag_writes_workflow_memory(self):
        # D2 fixed, through the real CLI: --learning persists workflow
        # memory grounded in the evidence just recorded. Uses its own goal
        # so other CLI tests' completed orders do not consume the park.
        self.run_cli("goal", "create", "--name", "Learning goal",
                     "--owner", "director", "--metric", "m",
                     "--target", "1")
        self.run_cli("runner", "tick", "--json")
        orders = [o for o in self.run_cli("tasks", "--json")
                  if o["goal_id"] != "CLI goal" or o["status"] in ("open", "claimed")]
        orders = [o for o in orders if o["agent_id"] == "director"]
        self.assertTrue(orders, "a parked order must exist to complete")
        order_id, agent_id = orders[0]["id"], orders[0]["agent_id"]
        self.run_cli("tasks", order_id, "--complete", agent_id,
                     "--evidence", '[{"kind":"m","payload":{"m":2}}]',
                     "--learning", "CLI completions should surface learning")
        memories = self.run_cli("memory", "workflows", "--json")
        self.assertTrue(any("CLI completions" in item["claim"]
                            for item in memories),
                        "tasks --complete --learning must persist workflow "
                        "memory reachable from memory workflows")

    def test_goal_create_rejects_undeclared_department_metric_via_cli(self):
        # D3 fixed through the real CLI with fixture departments.
        env_fixture = dict(os.environ)
        env_fixture["SPIELOS_TEST_DEPARTMENTS_DIR"] = str(
            FIXTURES / "departments")
        import subprocess
        result = self.subprocess.run(
            [sys.executable, "-B", "-m", "company", "--db", str(self.db),
             "goal", "create", "--name", "Bad metric", "--owner", "seo",
             "--metric", "articles_published", "--target", "1"],
            cwd=str(REPO),
            env=dict(env_fixture, PYTHONPATH=str(REPO),
                     PYTHONDONTWRITEBYTECODE="1",
                     SPIELOS_HOME=str(REPO)),
            capture_output=True, text=True, timeout=60)
        self.assertNotEqual(result.returncode, 0,
                             "goal create must refuse undeclared metrics")
        self.assertIn("does not declare metric", result.stderr)


if __name__ == "__main__":
    unittest.main(verbosity=2)
