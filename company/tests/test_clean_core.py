from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

from company.agents.core import Agent, AgentResult, AgentSpec, FunctionExecutor
from company.connections.core import Connection, ConnectionSpec
from company.capabilities import Capability
from company.commands import CleanCommandRuntime
from company.goals import GoalRepository
from company import GoalRuntime as PublicGoalRuntime, Runtime as PublicRuntime
from company.observability import Observer
from company.runtime.engine import Decision, Evaluation, GoalRuntime, GoalStage
from company.runtime.loop import CompatibilityRuntime
from company.state import Database, migrate_legacy_goals
from company.state.migration import backup_database, plan_legacy_goal_migration
from company.work_orders import WorkOrderRepository
from company.workflows import Workflow, WorkflowStep
from company.__main__ import main as cli_main


class ScenarioController:
    def __init__(self, complete_after=2):
        self.observations = 0
        self.complete_after = complete_after

    def observe(self, context):
        self.observations += 1
        return {"reply_rate": 2 * self.observations}

    def decide(self, context, observation):
        return Decision(
            "change_workflow", "build better research workflow", "research",
            {"bottleneck": "targeting"})

    def evaluate(self, context, decision, evidence):
        ids = tuple(item.id for item in evidence if item.kind == "research_validated")
        return Evaluation(
            self.observations >= self.complete_after,
            {"reply_rate": 2 * self.observations},
            "targeting moved replies", "Better research improves qualified replies", ids)


def research_workflow(approval_key=None):
    return Workflow("research", "Research", (
        WorkflowStep("research", "researcher", "Improve lead research",
                     "research_validated", approval_key),
    ), "outbound")


class CleanCoreAcceptanceTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.db = Path(self.temporary.name) / "company.sqlite"

    def tearDown(self):
        self.temporary.cleanup()

    def _direct_external_completion_state(self, database_path=None):
        class DirectExternalController(ScenarioController):
            def decide(self, context, observation):
                return Decision(
                    "repair_agent", "repair the research Agent", context={
                        "agent_id": "repairer",
                        "evidence_kind": "repair_validated",
                    })

            def evaluate(self, context, decision, evidence):
                return Evaluation(True, {"reply_rate": 2}, "repair ready")

        runtime = GoalRuntime(
            database_path or self.db, DirectExternalController(complete_after=1),
            FunctionExecutor({"repairer": lambda order: AgentResult(
                "ask_user", message="owner must finish the repair")}))
        goal = runtime.create_goal("Increase replies", "reply_rate", ">=", 2)
        runtime.tick(max_advances=10)
        waiting = runtime.status(goal.id)
        intervention = waiting["intervention"]
        with runtime.database.connect() as connection:
            order = connection.execute(
                """SELECT * FROM core_work_orders
                   WHERE intervention_id=? AND step_id='direct'""",
                (intervention.id,),
            ).fetchone()
        return runtime, goal, waiting["run"], intervention, order

    def test_full_goal_run_repairs_locally_then_starts_next_run(self):
        attempts = {"count": 0}

        def execute(order):
            attempts["count"] += 1
            if attempts["count"] <= 2:
                return AgentResult("fixable", message=f"bad output {attempts['count']}")
            return AgentResult(
                "completed", "research_validated", {"reply_rate": 4},
                workflow_learning="Validate researcher output before campaign launch")

        runtime = GoalRuntime(
            self.db, ScenarioController(), FunctionExecutor({"researcher": execute}))
        runtime.resolution.workflows.save(research_workflow())
        goal = runtime.create_goal(
            "Increase outbound replies", "reply_rate", ">=", 4, goal_id="replies")

        result = runtime.tick(max_advances=20)

        self.assertTrue(result["quiescent"])
        self.assertEqual(runtime.goals.get(goal.id).status, "complete")
        self.assertEqual(runtime.runs.current(goal.id).sequence, 2)
        self.assertEqual(attempts["count"], 4)
        with runtime.database.connect() as connection:
            self.assertEqual(connection.execute(
                "SELECT COUNT(*) FROM core_goals").fetchone()[0], 1)
            self.assertEqual(connection.execute("""SELECT COUNT(*) FROM core_evidence
                WHERE kind='resolution_iteration'""").fetchone()[0], 2)
            broken_lineage = connection.execute("""SELECT COUNT(*) FROM core_work_orders
                WHERE goal_id IS NULL OR run_id IS NULL OR intervention_id IS NULL""").fetchone()[0]
            self.assertEqual(broken_lineage, 0)
            scopes = {row[0] for row in connection.execute(
                "SELECT scope FROM core_memory")}
            self.assertEqual(scopes, {"workflow", "strategy"})

        trace = Observer(runtime.database).trace(goal.id)
        self.assertEqual(len(trace["runs"]), 2)
        self.assertEqual(trace["runs"][0]["interventions"][0]["outcome"],
                         "RETURN_TO_GOAL")

    def test_restart_resumes_same_intervention_and_claimed_work_order(self):
        controller = ScenarioController(complete_after=1)
        runtime = GoalRuntime(
            self.db, controller,
            FunctionExecutor({"researcher": lambda order: AgentResult(
                "ask_user", message="credentials required")}))
        runtime.resolution.workflows.save(research_workflow())
        goal = runtime.create_goal("Replies", "reply_rate", ">=", 2)
        runtime.tick(max_advances=10)
        before = runtime.status(goal.id)
        self.assertEqual(before["run"].stage, GoalStage.ACT)
        self.assertEqual(before["run"].status, "waiting")
        intervention_id = before["intervention"].id

        restarted = GoalRuntime(
            self.db, controller,
            FunctionExecutor({"researcher": lambda order: AgentResult(
                "completed", "research_validated", {"reply_rate": 2})}))
        restarted.resume(goal.id)
        restarted.advance(goal.id)

        self.assertEqual(restarted.goals.get(goal.id).status, "complete")
        trace = Observer(restarted.database).trace(goal.id)
        self.assertEqual(trace["runs"][0]["interventions"][0]["id"], intervention_id)
        with restarted.database.connect() as connection:
            self.assertEqual(connection.execute(
                "SELECT COUNT(*) FROM core_work_orders").fetchone()[0], 1)

    def test_approval_parks_resolution_not_the_goal_decision_loop(self):
        runtime = GoalRuntime(
            self.db, ScenarioController(complete_after=1),
            FunctionExecutor({"researcher": lambda order: AgentResult(
                "completed", "research_validated", {"reply_rate": 2})}))
        runtime.resolution.workflows.save(research_workflow("publish"))
        goal = runtime.create_goal("Replies", "reply_rate", ">=", 2)
        runtime.tick(max_advances=10)
        state = runtime.status(goal.id)
        self.assertEqual(state["run"].status, "waiting")
        runtime.resolution.approvals.grant(
            goal_id=goal.id, run_id=state["run"].id, key="publish",
            intervention_id=state["intervention"].id)
        runtime.resume(goal.id)
        runtime.advance(goal.id)
        self.assertEqual(runtime.goals.get(goal.id).status, "complete")

    def test_parent_support_and_block_graphs_are_independent_and_acyclic(self):
        runtime = GoalRuntime(
            self.db, ScenarioController(), FunctionExecutor({}))
        north = runtime.create_goal("Revenue", "revenue", ">=", 10)
        outbound = runtime.create_goal(
            "Outbound", "replies", ">=", 4, parent_id=north.id)
        quality = runtime.create_goal("Lead quality", "quality", ">=", 8)
        capacity = runtime.create_goal("Delivery capacity", "capacity", ">=", 4)
        runtime.goals.add_support(quality.id, outbound.id)
        runtime.goals.add_block(capacity.id, outbound.id)
        self.assertEqual(runtime.goals.get(outbound.id).parent_id, north.id)
        self.assertEqual(runtime.goals.supports(quality.id)[0].id, outbound.id)
        self.assertEqual(runtime.goals.blocks(capacity.id)[0].id, outbound.id)
        with self.assertRaisesRegex(ValueError, "DAG cycle"):
            runtime.goals.add_support(outbound.id, quality.id)
        with self.assertRaisesRegex(ValueError, "DAG cycle"):
            runtime.goals.add_block(outbound.id, capacity.id)
        with self.assertRaisesRegex(ValueError, "tree cycle"):
            runtime.goals.set_parent(north.id, outbound.id)

    def test_scheduler_uses_blocks_but_not_supports_for_eligibility(self):
        runtime = GoalRuntime(self.db, ScenarioController(), FunctionExecutor({}))
        supporter = runtime.create_goal("Supporter", "ready", "eq", True)
        supported = runtime.create_goal("Supported", "ready", "eq", True)
        blocker = runtime.create_goal("Blocker", "ready", "eq", True)
        blocked = runtime.create_goal("Blocked", "ready", "eq", True)
        runtime.goals.add_support(supporter.id, supported.id)
        runtime.goals.add_block(blocker.id, blocked.id)

        ready = runtime.runs.ready()

        ready_goal_ids = [item.goal_id for item in ready]
        self.assertIn(supported.id, ready_goal_ids)
        self.assertNotIn(blocked.id, ready_goal_ids)
        runtime.goals.set_status(blocker.id, "complete")
        self.assertIn(blocked.id, [item.goal_id for item in runtime.runs.ready()])

    def test_goal_metric_aggregation_is_explicit_and_deterministic(self):
        cases = {
            "count": ((2, 5, 9), 3),
            "sum": ((2, 5, 9), 16),
            "latest": ((2, 5, 9), 9),
            "max": ((2, 5, 9), 9),
            "min": ((2, 5, 9), 2),
            "boolean_all": ((True, False, True), False),
            "boolean_any": ((True, False, False), True),
        }
        for aggregation, (values, expected) in cases.items():
            with self.subTest(aggregation=aggregation), tempfile.TemporaryDirectory() as tmp:
                runtime = CleanCommandRuntime(Path(tmp) / "company.sqlite")
                created = runtime.create_goal(
                    name=f"Aggregate {aggregation}", owner_id="analytics",
                    metric="result", operator="ge", target=1,
                    config={"aggregation": aggregation})
                first_run = runtime.runs.current(created["id"])
                runtime.evidence.record(
                    goal_id=created["id"], run_id=first_run.id,
                    kind="measurement", payload={"result": values[0]})
                runtime.runs.update(first_run.id, status="complete")
                second_run = runtime.runs.create(created["id"])
                for value in values[1:]:
                    runtime.evidence.record(
                        goal_id=created["id"], run_id=second_run.id,
                        kind="measurement", payload={"result": value})

                runtime.runtime.advance(created["id"])

                observation = runtime.runs.get(second_run.id).observation
                self.assertEqual(observation["result"], expected)

    def test_goal_metric_aggregation_defaults_to_latest_not_evidence_count(self):
        runtime = CleanCommandRuntime(self.db)
        created = runtime.create_goal(
            name="Latest result", owner_id="analytics", metric="result",
            operator="ge", target=1, config={})
        run = runtime.runs.current(created["id"])
        for value in (2, 5, 9):
            runtime.evidence.record(
                goal_id=created["id"], run_id=run.id, kind="measurement",
                payload={"result": value})

        runtime.runtime.advance(created["id"])

        self.assertEqual(runtime.runs.get(run.id).observation["result"], 9)

    def test_strategy_memory_requires_same_run_evidence_owner_memory_does_not(self):
        runtime = GoalRuntime(
            self.db, ScenarioController(), FunctionExecutor({}))
        goal = runtime.create_goal("Replies", "reply_rate", ">=", 4)
        run = runtime.runs.current(goal.id)
        owner = runtime.memory.remember("owner", "Never publish without approval")
        self.assertEqual(owner.scope, "owner")
        with self.assertRaisesRegex(ValueError, "requires evidence"):
            runtime.memory.remember(
                "strategy", "Targeting helps", goal_id=goal.id, run_id=run.id)
        other = runtime.create_goal("Other", "ready", "eq", True)
        other_run = runtime.runs.current(other.id)
        other_evidence = runtime.evidence.record(
            goal_id=other.id, run_id=other_run.id, kind="fact", payload={})
        with self.assertRaisesRegex(ValueError, "causal Goal"):
            runtime.memory.remember(
                "strategy", "Wrong lineage", evidence_ids=(other_evidence.id,),
                goal_id=goal.id, run_id=other_run.id)

    def test_clean_cli_memory_profile_context_and_overview_share_one_authority(self):
        runtime = CleanCommandRuntime(self.db)
        goal = runtime.create_goal(
            name="Respect the owner voice", owner_id="content", metric="drafts",
            operator="ge", target=1, config={"aggregation": "count"})

        profile_output = StringIO()
        with redirect_stdout(profile_output):
            self.assertEqual(cli_main([
                "--db", str(self.db), "profile", "set",
                "--namespace", "voice", "--key", "tone", "--value", "direct",
                "--json",
            ]), 0)
        profile_record = json.loads(profile_output.getvalue())
        self.assertEqual(profile_record["scope"], "owner")

        commands = (
            ("profile", "list", "--json"),
            ("memory", "summary", "--json"),
            ("context", "--prompt", "draft in my voice", "--json"),
            ("overview", "--json"),
        )
        outputs = []
        for command in commands:
            output = StringIO()
            with redirect_stdout(output):
                self.assertEqual(
                    cli_main(["--db", str(self.db), *command]), 0,
                    command)
            outputs.append(json.loads(output.getvalue()))

        profile_list, memory_summary, context, overview = outputs
        self.assertEqual(profile_list[0]["id"], profile_record["id"])
        self.assertEqual(memory_summary["counts"]["owner"], 1)
        self.assertIn("voice.tone", context["context"])
        self.assertIn("Respect the owner voice", context["context"])
        self.assertEqual(overview["goals"]["focus"]["id"], goal["id"])
        with runtime.database.connect() as connection:
            self.assertEqual(connection.execute(
                "SELECT COUNT(*) FROM core_memory WHERE scope='owner'"
            ).fetchone()[0], 1)
            tables = {row[0] for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'")}
        self.assertTrue({
            "profile_claims", "directives", "experiment_memories",
            "workflow_memories", "recent_memories",
        }.isdisjoint(tables))

    def test_clean_memory_retrieval_is_bounded_scoped_and_supersession_aware(self):
        runtime = GoalRuntime(self.db, ScenarioController(), FunctionExecutor({}))
        goal = runtime.create_goal("Replies", "reply_rate", ">=", 4)
        run = runtime.runs.current(goal.id)
        evidence = runtime.evidence.record(
            goal_id=goal.id, run_id=run.id, kind="fact", payload={"ok": True})
        other_goal = runtime.create_goal("Other", "ready", "eq", True)
        other_run = runtime.runs.current(other_goal.id)
        other_evidence = runtime.evidence.record(
            goal_id=other_goal.id, run_id=other_run.id,
            kind="fact", payload={"ok": True})

        obsolete = runtime.memory.remember("owner", "Use formal language")
        replacement = runtime.memory.remember(
            "owner", "Use direct language", confidence=0.95,
            supersedes_id=obsolete.id)
        strategy = runtime.memory.remember(
            "strategy", "Target technical founders", goal_id=goal.id,
            run_id=run.id, evidence_ids=(evidence.id,))
        runtime.memory.remember(
            "strategy", "Unrelated strategy", goal_id=other_goal.id,
            run_id=other_run.id, evidence_ids=(other_evidence.id,))
        selected_workflow = runtime.memory.remember(
            "workflow", "Verify account fit", goal_id=goal.id, run_id=run.id,
            workflow_id="research", evidence_ids=(evidence.id,))
        runtime.memory.remember(
            "workflow", "Use a different process", goal_id=goal.id, run_id=run.id,
            workflow_id="other-workflow", evidence_ids=(evidence.id,))

        before_decide = runtime._context(goal, run).memory
        before_claims = {item.claim for item in before_decide}
        self.assertIn(replacement.claim, before_claims)
        self.assertIn(strategy.claim, before_claims)
        self.assertNotIn(obsolete.claim, before_claims)
        self.assertNotIn(selected_workflow.claim, before_claims)
        self.assertNotIn("Use a different process", before_claims)
        self.assertNotIn("Unrelated strategy", before_claims)

        runtime.runs.update(
            run.id, decision=Decision(
                "change_workflow", "use research", workflow_id="research"))
        after_decide = runtime._context(goal, runtime.runs.get(run.id)).memory
        after_claims = {item.claim for item in after_decide}
        self.assertIn(selected_workflow.claim, after_claims)
        self.assertNotIn("Use a different process", after_claims)
        self.assertLessEqual(len(runtime.memory.relevant(
            goal_id=goal.id, workflow_id="research", limit=2)), 2)
        self.assertEqual(runtime.memory.get(obsolete.id).status, "superseded")
        self.assertEqual(replacement.confidence, 0.95)

    def test_direct_intervention_can_fix_retry_and_return_without_child_goal(self):
        attempts = {"count": 0}

        class DirectController(ScenarioController):
            def decide(self, context, observation):
                return Decision("repair_agent", "repair the research Agent", context={
                    "agent_id": "repairer", "evidence_kind": "repair_validated"})

            def evaluate(self, context, decision, evidence):
                return Evaluation(True, {"reply_rate": 2}, "repair ready")

        def repair(order):
            attempts["count"] += 1
            if attempts["count"] == 1:
                return AgentResult("fixable", message="test still failing")
            return AgentResult("completed", "repair_validated", {"tests": "passed"})

        runtime = GoalRuntime(
            self.db, DirectController(complete_after=1),
            FunctionExecutor({"repairer": repair}))
        goal = runtime.create_goal("Increase replies", "reply_rate", ">=", 2)
        runtime.tick(max_advances=10)
        self.assertEqual(runtime.goals.get(goal.id).status, "complete")
        self.assertEqual(attempts["count"], 2)
        self.assertEqual(len(runtime.goals.list()), 1)

    def test_completed_direct_work_order_resumes_once_without_reexecution(self):
        attempts = {"count": 0}

        class DirectExternalController(ScenarioController):
            def decide(self, context, observation):
                return Decision(
                    "repair_agent", "repair the research Agent", context={
                        "agent_id": "repairer",
                        "evidence_kind": "repair_validated",
                    })

            def evaluate(self, context, decision, evidence):
                return Evaluation(True, {"reply_rate": 2}, "repair ready")

        def request_external_completion(order):
            attempts["count"] += 1
            return AgentResult("ask_user", message="owner must finish the repair")

        runtime = GoalRuntime(
            self.db, DirectExternalController(complete_after=1),
            FunctionExecutor({"repairer": request_external_completion}))
        goal = runtime.create_goal("Increase replies", "reply_rate", ">=", 2)
        runtime.tick(max_advances=10)
        waiting = runtime.status(goal.id)
        intervention = waiting["intervention"]
        with runtime.database.connect() as connection:
            order = connection.execute(
                """SELECT * FROM core_work_orders
                   WHERE intervention_id=? AND step_id='direct'""",
                (intervention.id,),
            ).fetchone()
        self.assertIsNotNone(order)
        self.assertEqual(attempts["count"], 1)

        runtime.resolution.work_orders.complete_with_evidence(
            order["id"], {"tests": "passed"},
            executor_id=order["claimed_by"], kind="repair_validated",
            payload={"tests": "passed"})
        resumed = runtime.resume(goal.id)
        self.assertEqual(resumed["run"].stage, GoalStage.EVALUATE)
        completed_intervention = runtime.interventions.get(intervention.id)
        self.assertEqual(completed_intervention.status, "complete")
        self.assertEqual(
            completed_intervention.resolution_outcome, "RETURN_TO_GOAL")
        self.assertEqual(attempts["count"], 1)
        with runtime.database.connect() as connection:
            self.assertEqual(connection.execute(
                """SELECT COUNT(*) FROM core_work_orders
                   WHERE intervention_id=? AND step_id='direct'""",
                (intervention.id,),
            ).fetchone()[0], 1)
            self.assertEqual(connection.execute(
                """SELECT COUNT(*) FROM core_evidence
                   WHERE work_order_id=? AND kind='repair_validated'""",
                (order["id"],),
            ).fetchone()[0], 1)

    def test_external_direct_completion_atomically_returns_to_evaluate(self):
        runtime, goal, run, intervention, order = (
            self._direct_external_completion_state())

        completed, evidence_ids = runtime.resolution.work_orders.complete_with_evidence(
            order["id"], {"tests": "passed"},
            executor_id=order["claimed_by"], kind="repair_validated",
            payload={"tests": "passed"})

        self.assertEqual(completed.status, "completed")
        self.assertEqual(len(evidence_ids), 1)
        self.assertEqual(runtime.interventions.get(intervention.id).status, "complete")
        self.assertEqual(
            runtime.interventions.get(intervention.id).resolution_outcome,
            "RETURN_TO_GOAL")
        transitioned = runtime.runs.get(run.id)
        self.assertEqual(transitioned.stage, GoalStage.EVALUATE)
        self.assertEqual(transitioned.status, "running")
        with runtime.database.connect() as connection:
            notification = connection.execute(
                """SELECT status FROM core_notifications
                   WHERE intervention_id=? AND kind='owner_input_required'""",
                (intervention.id,),
            ).fetchone()
        self.assertEqual(notification["status"], "acknowledged")
        self.assertEqual(runtime.goals.get(goal.id).status, "active")

    def test_external_direct_completion_rolls_back_at_every_write_boundary(self):
        failure_triggers = {
            "evidence insert": """CREATE TRIGGER reject_external_evidence
                BEFORE INSERT ON core_evidence BEGIN
                SELECT RAISE(ABORT, 'simulated external completion crash'); END""",
            "notification acknowledgement": """CREATE TRIGGER reject_external_ack
                BEFORE UPDATE ON core_notifications WHEN NEW.status='acknowledged' BEGIN
                SELECT RAISE(ABORT, 'simulated external completion crash'); END""",
            "intervention transition": """CREATE TRIGGER reject_external_intervention
                BEFORE UPDATE ON core_interventions WHEN NEW.status='complete' BEGIN
                SELECT RAISE(ABORT, 'simulated external completion crash'); END""",
            "run transition": """CREATE TRIGGER reject_external_run
                BEFORE UPDATE ON core_runs WHEN NEW.stage='EVALUATE' BEGIN
                SELECT RAISE(ABORT, 'simulated external completion crash'); END""",
        }
        for boundary, trigger in failure_triggers.items():
            with self.subTest(boundary=boundary), tempfile.TemporaryDirectory() as tmp:
                runtime, goal, run, intervention, order = (
                    self._direct_external_completion_state(
                        Path(tmp) / "company.sqlite"))
                with runtime.database.connect() as connection:
                    connection.execute(trigger)

                with self.assertRaisesRegex(
                        sqlite3.IntegrityError,
                        "simulated external completion crash"):
                    runtime.resolution.work_orders.complete_with_evidence(
                        order["id"], {"tests": "passed"},
                        executor_id=order["claimed_by"], kind="repair_validated",
                        payload={"tests": "passed"})

                self.assertEqual(
                    runtime.resolution.work_orders.get(order["id"]).status,
                    "claimed")
                self.assertEqual(
                    runtime.interventions.get(intervention.id).status, "waiting")
                unchanged_run = runtime.runs.get(run.id)
                self.assertEqual(unchanged_run.stage, GoalStage.ACT)
                self.assertEqual(unchanged_run.status, "waiting")
                with runtime.database.connect() as connection:
                    self.assertEqual(connection.execute(
                        "SELECT COUNT(*) FROM core_evidence WHERE work_order_id=?",
                        (order["id"],),
                    ).fetchone()[0], 0)
                    notification = connection.execute(
                        """SELECT status FROM core_notifications
                           WHERE intervention_id=?
                             AND kind='owner_input_required'""",
                        (intervention.id,),
                    ).fetchone()
                self.assertEqual(notification["status"], "pending")
                self.assertEqual(runtime.goals.get(goal.id).status, "active")

    def test_intervention_cannot_exist_without_goal_and_run_lineage(self):
        database = Database(self.db)
        with self.assertRaises(sqlite3.IntegrityError):
            with database.connect() as connection:
                connection.execute("""INSERT INTO core_interventions
                    VALUES ('orphan','missing','missing','repair','bad','running',NULL,
                            '{}','now','now')""")

    def test_subsystems_do_not_depend_on_goal_runtime(self):
        self.assertIs(PublicRuntime, PublicGoalRuntime)
        roots = ["goals/core.py", "workflows/core.py", "work_orders/core.py",
                 "evidence/records.py", "memory/records.py", "state/database.py",
                 "agents/core.py", "connections/core.py", "skills/core.py",
                 "capabilities/core.py",
                 "departments/core.py", "hosts/core.py", "context/core.py",
                 "observability/read_model.py"]
        company = Path(__file__).parents[1]
        for relative in roots:
            source = (company / relative).read_text()
            self.assertNotIn("from ..runtime", source, relative)
            self.assertNotIn("from company.runtime", source, relative)
        cli = (company / "__main__.py").read_text()
        self.assertIn("from .runtime import CompatibilityRuntime", cli)
        self.assertNotIn("LegacyRuntime as Runtime", cli)

    def test_capability_is_a_host_resolved_contract_not_runtime_state(self):
        capability = Capability(
            "browser", "Navigate web pages", ("codex",), ("network",))
        agent = Agent("researcher", capability_ids=(capability.id,))
        self.assertEqual(agent.capability_ids, ("browser",))
        self.assertTrue(capability.requires_approval)

    def test_domain_import_boundaries_are_enforced(self):
        company = Path(__file__).parents[1]
        boundaries = {
            "goals/core.py": ("agents", "workflows", "resolution"),
            "capabilities/core.py": ("runtime", "goals", "workflows"),
            "skills/core.py": ("runtime", "goals", "workflows"),
            "evidence/records.py": ("agents", "workflows", "resolution"),
            "memory/records.py": ("agents", "hosts", "resolution"),
        }
        for relative, forbidden in boundaries.items():
            source = (company / relative).read_text()
            for package in forbidden:
                self.assertNotIn(f"from ..{package}", source, relative)
                self.assertNotIn(f"from company.{package}", source, relative)

    def test_legacy_goal_migration_is_explicit_and_bounded(self):
        connection = sqlite3.connect(self.db)
        connection.executescript("""CREATE TABLE goals (
            id TEXT PRIMARY KEY,name TEXT,owner_id TEXT,metric TEXT,operator TEXT,
            target_json TEXT,deadline TEXT,parent_id TEXT,goal_status TEXT,
            config_json TEXT,created_at TEXT,updated_at TEXT);
        """)
        values = [
            ("chosen", "Chosen", "outbound", "replies", ">=", "4", None, None,
             "active", '{"supports_goal_ids":["ignored"]}', "then", "then"),
            ("ignored", "Ignored", "outbound", "quality", ">=", "8", None, None,
             "active", "{}", "then", "then"),
        ]
        connection.executemany("INSERT INTO goals VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", values)
        connection.commit()
        connection.close()
        database = Database(self.db)
        result = migrate_legacy_goals(database, ["chosen"])
        self.assertEqual(result, {"migrated": ["chosen"], "skipped": []})
        with database.connect() as current:
            self.assertEqual(current.execute(
                "SELECT COUNT(*) FROM core_goals").fetchone()[0], 1)
            self.assertEqual(current.execute(
                "SELECT COUNT(*) FROM core_goal_edges").fetchone()[0], 0)
        migrated = GoalRuntime(
            self.db, ScenarioController(), FunctionExecutor({}))
        self.assertEqual(migrated.runs.current("chosen").stage, GoalStage.OBSERVE)

    def test_compatibility_runtime_cannot_write_after_clean_core_activation(self):
        runtime = GoalRuntime(
            self.db, ScenarioController(), FunctionExecutor({}))
        runtime.create_goal("Canonical", "ready", "eq", True)
        compatibility = CompatibilityRuntime(self.db)
        with self.assertRaisesRegex(RuntimeError, "clean-core authority is active"):
            compatibility.create_goal(
                name="Historical", owner_id="director", metric="ready",
                operator="eq", target=True, config={})
        readonly = CompatibilityRuntime(self.db, readonly=True)
        self.assertTrue(readonly.readonly)

    def test_lineage_is_coherent_and_evidence_is_immutable_in_sqlite(self):
        runtime = GoalRuntime(
            self.db, ScenarioController(), FunctionExecutor({}))
        first = runtime.create_goal("First", "ready", "eq", True)
        second = runtime.create_goal("Second", "ready", "eq", True)
        first_run = runtime.runs.current(first.id)
        second_run = runtime.runs.current(second.id)
        with self.assertRaisesRegex(sqlite3.IntegrityError, "lineage mismatch"):
            with runtime.database.connect() as connection:
                connection.execute("""INSERT INTO core_interventions
                    VALUES ('mixed',?,?,?,?,?,NULL,'{}','now','now')""",
                    (first.id, second_run.id, "repair", "mixed lineage", "running"))
        intervention = runtime.interventions.create(
            goal_id=first.id, run_id=first_run.id, kind="observe", description="record")
        with self.assertRaisesRegex(sqlite3.IntegrityError, "lineage mismatch"):
            with runtime.database.connect() as connection:
                connection.execute(
                    "UPDATE core_interventions SET run_id=? WHERE id=?",
                    (second_run.id, intervention.id))
        evidence = runtime.evidence.record(
            goal_id=first.id, run_id=first_run.id, intervention_id=intervention.id,
            kind="fact", payload={"value": 1})
        with self.assertRaisesRegex(sqlite3.IntegrityError, "immutable"):
            with runtime.database.connect() as connection:
                connection.execute(
                    "UPDATE core_evidence SET kind='changed' WHERE id=?", (evidence.id,))

        second_intervention = runtime.interventions.create(
            goal_id=first.id, run_id=first_run.id, kind="observe", description="other")
        order = runtime.resolution.work_orders.open(
            goal_id=first.id, run_id=first_run.id,
            intervention_id=intervention.id, agent_id="agent", brief={})
        with self.assertRaisesRegex(sqlite3.IntegrityError, "lineage mismatch"):
            runtime.evidence.record(
                goal_id=first.id, run_id=first_run.id,
                intervention_id=second_intervention.id, work_order_id=order.id,
                kind="mixed", payload={})
        with self.assertRaisesRegex(sqlite3.IntegrityError, "lineage mismatch"):
            runtime.resolution.approvals.grant(
                goal_id=first.id, run_id=second_run.id, key="mixed",
                intervention_id=intervention.id)

    def test_agent_and_connection_compatibility_names_are_aliases_not_models(self):
        self.assertIs(AgentSpec, Agent)
        self.assertIs(ConnectionSpec, Connection)

    def test_public_goal_commands_use_clean_core_in_a_fresh_home(self):
        output = StringIO()
        with redirect_stdout(output):
            code = cli_main([
                "--db", str(self.db), "goal", "create", "--name", "Research",
                "--owner", "outbound", "--metric", "qualified_leads",
                "--target", "1", "--config", '{"workflow":"lead-research"}',
                "--json",
            ])
        self.assertEqual(code, 0)
        database = Database(self.db)
        with database.connect() as connection:
            self.assertEqual(connection.execute(
                "SELECT COUNT(*) FROM core_goals").fetchone()[0], 1)
            self.assertIsNone(connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='goals'"
            ).fetchone())
        with redirect_stdout(StringIO()):
            self.assertEqual(cli_main([
                "--db", str(self.db), "runner", "tick", "--json"]), 0)
        with database.connect() as connection:
            order = connection.execute(
                "SELECT id,goal_id,claimed_by FROM core_work_orders").fetchone()
        with redirect_stdout(StringIO()):
            self.assertEqual(cli_main([
                "--db", str(self.db), "tasks", order["id"],
                "--complete", order["claimed_by"], "--evidence",
                '[{"kind":"lead_dossier","payload":{"qualified_leads":1}}]',
                "--json"]), 0)
            self.assertEqual(cli_main([
                "--db", str(self.db), "retry", order["goal_id"], "--json"]), 0)
            self.assertEqual(cli_main([
                "--db", str(self.db), "runner", "tick", "--json"]), 0)
        self.assertEqual(GoalRepository(database).get(order["goal_id"]).status, "complete")

    def test_clean_command_approval_grants_the_exact_workflow_gate(self):
        runtime = CleanCommandRuntime(self.db)
        goal = runtime.create_goal(
            name="Approve SEO change", owner_id="seo", metric="seo_reports",
            operator="ge", target=1, config={"workflow": "seo-improvement"})
        runtime.tick()
        run = runtime.runs.current(goal["id"])
        self.assertEqual(run.status, "waiting")
        runtime.approve(goal["id"], "approved")
        self.assertEqual(runtime.approvals.status(run.id, "step:approve"), "approved")
        self.assertEqual(len(runtime.work_orders(goal_id=goal["id"])), 1)
        self.assertEqual(len(list(runtime.watch(0, goal["id"], 1))), 1)

    def test_legacy_goal_migration_preview_is_read_only_and_reports_omissions(self):
        connection = sqlite3.connect(self.db)
        connection.executescript("""CREATE TABLE goals (
            id TEXT PRIMARY KEY,name TEXT,owner_id TEXT,metric TEXT,operator TEXT,
            target_json TEXT,deadline TEXT,parent_id TEXT,goal_status TEXT,
            config_json TEXT,created_at TEXT,updated_at TEXT);
        """)
        connection.execute("INSERT INTO goals VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", (
            "release", "Release", "director", "ready", "eq", "true", None,
            "historical", "active", '{"supports_goal_ids":["historical"]}',
            "then", "then"))
        connection.commit()
        connection.close()
        database = Database(self.db)

        plan = plan_legacy_goal_migration(database, ["release", "missing"])

        self.assertEqual(plan["selected"], ["release"])
        self.assertEqual(plan["missing"], ["missing"])
        self.assertEqual(plan["parents_omitted"], [
            {"goal_id": "release", "parent_id": "historical"}])
        self.assertEqual(plan["supports_omitted"], [
            {"goal_id": "release", "target_goal_id": "historical"}])
        with database.connect() as current:
            self.assertEqual(current.execute(
                "SELECT COUNT(*) FROM core_goals").fetchone()[0], 0)

    def test_database_backup_is_consistent_before_cutover(self):
        database = Database(self.db)
        with database.connect() as connection:
            connection.execute("""INSERT INTO core_goals VALUES
                ('release','Release','ready','eq','true',NULL,'active','then','then')""")
        destination = Path(self.temporary.name) / "company.before-cutover.sqlite"

        backup_database(database, destination)

        copied = sqlite3.connect(destination)
        try:
            self.assertEqual(copied.execute(
                "SELECT name FROM core_goals WHERE id='release'").fetchone()[0],
                "Release")
        finally:
            copied.close()

    def test_continue_local_stays_runnable_instead_of_stranding_act(self):
        runtime = GoalRuntime(
            self.db, ScenarioController(),
            FunctionExecutor({"researcher": lambda order: AgentResult(
                "fixable", message="retry locally")}),
            max_local_iterations=1)
        runtime.resolution.workflows.save(research_workflow())
        goal = runtime.create_goal("Replies", "reply_rate", ">=", 2)

        runtime.advance(goal.id)
        runtime.advance(goal.id)
        runtime.advance(goal.id)

        state = runtime.status(goal.id)
        self.assertEqual(state["run"].stage, GoalStage.ACT)
        self.assertEqual(state["run"].status, "ready")
        self.assertEqual(state["intervention"].status, "running")
        self.assertEqual(state["intervention"].resolution_outcome, "CONTINUE_LOCAL")

    def test_ask_user_is_durable_and_claimant_cannot_be_substituted(self):
        runtime = GoalRuntime(
            self.db, ScenarioController(complete_after=1),
            FunctionExecutor({"researcher": lambda order: AgentResult(
                "ask_user", message="credentials required")}))
        runtime.resolution.workflows.save(research_workflow())
        goal = runtime.create_goal("Replies", "reply_rate", ">=", 2)
        runtime.tick(max_advances=10)
        order = runtime.resolution.work_orders.for_workflow_run(
            runtime.resolution.workflows.active_for_intervention(
                runtime.status(goal.id)["intervention"].id).id)[0]

        with runtime.database.connect() as connection:
            notification = connection.execute("""SELECT kind,payload_json,status
                FROM core_notifications WHERE intervention_id=?""",
                (order.intervention_id,)).fetchone()
        self.assertEqual(notification["kind"], "owner_input_required")
        self.assertEqual(notification["status"], "pending")
        with self.assertRaisesRegex(RuntimeError, "claiming Agent"):
            runtime.resolution.work_orders.complete_with_evidence(
                order.id, {}, executor_id="intruder", kind="fact", payload={})

    def test_expired_work_order_lease_can_be_reclaimed(self):
        runtime = GoalRuntime(self.db, ScenarioController(), FunctionExecutor({}))
        goal = runtime.create_goal("Replies", "reply_rate", ">=", 2)
        run = runtime.runs.current(goal.id)
        intervention = runtime.interventions.create(
            goal_id=goal.id, run_id=run.id, kind="repair", description="repair")
        orders = WorkOrderRepository(runtime.database)
        order = orders.open(goal_id=goal.id, run_id=run.id,
                            intervention_id=intervention.id, agent_id="agent",
                            step_id="direct", brief={})
        orders.claim(order.id, "first", lease_seconds=-1)

        reclaimed = orders.claim(order.id, "second")

        self.assertEqual(reclaimed.claimed_by, "second")
        self.assertEqual(reclaimed.attempt, 1)

    def test_legacy_claimed_work_order_with_null_lease_can_be_reclaimed(self):
        runtime = GoalRuntime(self.db, ScenarioController(), FunctionExecutor({}))
        goal = runtime.create_goal("Replies", "reply_rate", ">=", 2)
        run = runtime.runs.current(goal.id)
        intervention = runtime.interventions.create(
            goal_id=goal.id, run_id=run.id, kind="repair", description="repair")
        orders = WorkOrderRepository(runtime.database)
        order = orders.open(
            goal_id=goal.id, run_id=run.id, intervention_id=intervention.id,
            agent_id="agent", step_id="direct", brief={})
        with runtime.database.connect() as connection:
            connection.execute("""UPDATE core_work_orders
                SET status='claimed',claimed_by='legacy-executor',
                    claimed_at='2020-01-01T00:00:00+00:00',lease_expires_at=NULL
                WHERE id=?""", (order.id,))

        reclaimed = orders.claim(order.id, "current-executor")

        self.assertEqual(reclaimed.claimed_by, "current-executor")
        self.assertIsNotNone(reclaimed.lease_expires_at)
        self.assertEqual(reclaimed.attempt, 1)

    def test_order_evidence_and_workflow_advance_roll_back_together(self):
        runtime = GoalRuntime(self.db, ScenarioController(), FunctionExecutor({}))
        runtime.resolution.workflows.save(research_workflow())
        goal = runtime.create_goal("Replies", "reply_rate", ">=", 2)
        run = runtime.runs.current(goal.id)
        intervention = runtime.interventions.create(
            goal_id=goal.id, run_id=run.id, kind="repair", description="repair")
        workflow_run = runtime.resolution.workflows.start(
            "research", goal_id=goal.id, run_id=run.id,
            intervention_id=intervention.id)
        order = runtime.resolution.work_orders.open(
            goal_id=goal.id, run_id=run.id, intervention_id=intervention.id,
            workflow_run_id=workflow_run.id, step_id="research",
            agent_id="researcher", brief={})
        order = runtime.resolution.work_orders.claim(order.id, "executor")
        with runtime.database.connect() as connection:
            connection.execute("""CREATE TRIGGER reject_workflow_advance
                BEFORE UPDATE ON core_workflow_runs BEGIN
                SELECT RAISE(ABORT, 'simulated crash'); END""")

        with self.assertRaisesRegex(sqlite3.IntegrityError, "simulated crash"):
            runtime.resolution.work_orders.complete_with_evidence(
                order.id, {"ok": True}, executor_id="executor", kind="fact",
                payload={"ok": True}, advance_workflow=True)

        self.assertEqual(runtime.resolution.work_orders.get(order.id).status, "claimed")
        with runtime.database.connect() as connection:
            self.assertEqual(connection.execute(
                "SELECT COUNT(*) FROM core_evidence").fetchone()[0], 0)

    def test_intervention_and_run_transition_roll_back_together(self):
        runtime = GoalRuntime(
            self.db, ScenarioController(complete_after=1),
            FunctionExecutor({"researcher": lambda order: AgentResult(
                "completed", "research_validated", {"reply_rate": 2})}))
        runtime.resolution.workflows.save(research_workflow())
        goal = runtime.create_goal("Replies", "reply_rate", ">=", 2)
        runtime.advance(goal.id)
        runtime.advance(goal.id)
        run = runtime.runs.current(goal.id)
        with runtime.database.connect() as connection:
            connection.execute("""CREATE TRIGGER reject_evaluate_transition
                BEFORE UPDATE ON core_runs WHEN NEW.stage='EVALUATE' BEGIN
                SELECT RAISE(ABORT, 'simulated transition crash'); END""")

        with self.assertRaisesRegex(sqlite3.IntegrityError, "simulated transition crash"):
            runtime.advance(goal.id)

        intervention = runtime.interventions.active_for_run(run.id)
        self.assertEqual(intervention.status, "running")
        self.assertIsNone(intervention.resolution_outcome)
        self.assertEqual(runtime.runs.get(run.id).stage, GoalStage.ACT)

    def test_evaluation_memory_goal_and_next_run_roll_back_together(self):
        runtime = GoalRuntime(self.db, ScenarioController(), FunctionExecutor({}))
        goal = runtime.create_goal("Replies", "reply_rate", ">=", 4)
        run = runtime.runs.current(goal.id)
        evidence = runtime.evidence.record(
            goal_id=goal.id, run_id=run.id, kind="fact", payload={})
        evaluation = Evaluation(
            False, {"reply_rate": 2}, "continue", "learned",
            (evidence.id,))
        with runtime.database.connect() as connection:
            connection.execute("""CREATE TRIGGER reject_next_run
                BEFORE INSERT ON core_runs WHEN NEW.sequence=2 BEGIN
                SELECT RAISE(ABORT, 'simulated next-run crash'); END""")

        with self.assertRaisesRegex(sqlite3.IntegrityError, "simulated next-run crash"):
            runtime._commit_evaluation(goal, run, evaluation)

        self.assertNotEqual(runtime.runs.get(run.id).status, "complete")
        with runtime.database.connect() as connection:
            self.assertEqual(connection.execute(
                "SELECT COUNT(*) FROM core_memory").fetchone()[0], 0)

    def test_workflow_run_freezes_revision_and_unchanged_save_is_idempotent(self):
        runtime = GoalRuntime(self.db, ScenarioController(), FunctionExecutor({}))
        original = runtime.resolution.workflows.save(research_workflow())
        same = runtime.resolution.workflows.save(research_workflow())
        self.assertEqual((original.version, same.version), (1, 1))
        goal = runtime.create_goal("Replies", "reply_rate", ">=", 2)
        run = runtime.runs.current(goal.id)
        intervention = runtime.interventions.create(
            goal_id=goal.id, run_id=run.id, kind="repair", description="repair")
        frozen = runtime.resolution.workflows.start(
            "research", goal_id=goal.id, run_id=run.id,
            intervention_id=intervention.id)
        runtime.resolution.workflows.save(Workflow(
            "research", "Changed", (WorkflowStep(
                "changed", "writer", "Changed", "changed"),), "outbound"))

        self.assertEqual(frozen.workflow_version, 1)
        self.assertEqual(frozen.steps[0].id, "research")
        self.assertEqual(runtime.resolution.workflows.get("research").version, 2)

    def test_escalation_finishes_old_run_and_creates_fresh_run(self):
        runtime = GoalRuntime(
            self.db, ScenarioController(),
            FunctionExecutor({"researcher": lambda order: AgentResult(
                "escalate", message="strategy invalid")}))
        runtime.resolution.workflows.save(research_workflow())
        goal = runtime.create_goal("Replies", "reply_rate", ">=", 2)
        first = runtime.runs.current(goal.id)
        runtime.advance(goal.id)
        runtime.advance(goal.id)
        runtime.advance(goal.id)

        current = runtime.runs.current(goal.id)
        self.assertEqual(runtime.runs.get(first.id).status, "complete")
        self.assertEqual(current.sequence, 2)
        self.assertEqual(current.stage, GoalStage.OBSERVE)
        self.assertEqual(runtime.runs.get(first.id).decision.kind, "change_workflow")

    def test_readonly_clean_runtime_uses_sqlite_readonly_mode(self):
        writable = CleanCommandRuntime(self.db)
        writable.create_goal(name="Read", owner_id="outbound", metric="leads",
                             operator="ge", target=1, config={})
        before = self.db.read_bytes()
        readonly = CleanCommandRuntime(self.db, readonly=True)
        self.assertEqual(len(readonly.goal_summaries()), 1)
        with self.assertRaises(PermissionError):
            readonly.create_goal(name="Write", owner_id="outbound", metric="leads",
                                 operator="ge", target=1, config={})
        self.assertEqual(self.db.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
