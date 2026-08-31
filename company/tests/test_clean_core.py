from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from company.agents.core import AgentResult, FunctionExecutor
from company import GoalRuntime as PublicGoalRuntime, Runtime as PublicRuntime
from company.observability import Observer
from company.runtime.engine import Decision, Evaluation, GoalRuntime, GoalStage
from company.state import Database, migrate_legacy_goals
from company.state.migration import backup_database, plan_legacy_goal_migration
from company.workflows import Workflow, WorkflowStep


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

    def test_goal_tree_and_support_dag_are_independent_and_acyclic(self):
        runtime = GoalRuntime(
            self.db, ScenarioController(), FunctionExecutor({}))
        north = runtime.create_goal("Revenue", "revenue", ">=", 10)
        outbound = runtime.create_goal(
            "Outbound", "replies", ">=", 4, parent_id=north.id)
        quality = runtime.create_goal("Lead quality", "quality", ">=", 8)
        runtime.goals.add_support(quality.id, outbound.id)
        self.assertEqual(runtime.goals.get(outbound.id).parent_id, north.id)
        self.assertEqual(runtime.goals.supports(quality.id)[0].id, outbound.id)
        with self.assertRaisesRegex(ValueError, "DAG cycle"):
            runtime.goals.add_support(outbound.id, quality.id)
        with self.assertRaisesRegex(ValueError, "tree cycle"):
            runtime.goals.set_parent(north.id, outbound.id)

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
                 "evidence/records.py", "memory/records.py", "state/database.py"]
        company = Path(__file__).parents[1]
        for relative in roots:
            source = (company / relative).read_text()
            self.assertNotIn("runtime.engine", source, relative)
            self.assertNotIn("runtime.loop", source, relative)

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


if __name__ == "__main__":
    unittest.main()
