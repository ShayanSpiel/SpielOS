"""Acceptance coverage for the live SpielOS architecture observatory."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from company.__main__ import build_parser
from company.evidence import EvidenceRepository
from company.goals import GoalRepository
from company.memory import MemoryRepository
from company.resolution.core import InterventionRepository
from company.runtime.engine import GoalStage, RunRepository
from company.runtime.loop import Runtime
from company.runtime.observability import LAYERS, collect_snapshot
from company.state import Database
from company.work_orders import WorkOrderRepository
from company.workflows import Workflow, WorkflowRepository, WorkflowStep


class ObservatoryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / ".spielos/state").mkdir(parents=True)
        (self.root / ".gitignore").write_text(".spielos/\n.env\n", encoding="utf-8")
        host = self.root / "company/init_templates/hosts/codex/hooks"
        host.mkdir(parents=True)
        (host / "context.py").write_text("# read-only adapter\n", encoding="utf-8")
        self.runtime = Runtime(self.root / ".spielos/state/company.sqlite")

    def test_snapshot_connects_goal_run_loop_and_support_dag(self):
        parent = self.runtime.store.create_goal(
            name="Primary outcome", owner_id="director", metric="outcome",
            operator="ge", target=1, goal_id="goal-primary",
            config={"pursuit_kind": "primary_goal"})
        child = self.runtime.store.create_goal(
            name="Supporting repair", owner_id="system-improvement",
            metric="acceptance_tests_passed", operator="eq", target=True,
            goal_id="goal-repair", parent_id=parent["id"],
            run_type="system_improvement", config={
                "pursuit_kind": "system_improvement_goal",
                "supports_goal_ids": [parent["id"]],
            })

        snapshot = collect_snapshot(self.runtime, project_root=self.root)
        nodes = {item["id"]: item for item in snapshot["nodes"]}
        edges = {(item["source"], item["target"], item["relation"])
                 for item in snapshot["edges"]}

        self.assertEqual("2.0", snapshot["schema_version"])
        self.assertIn("goal:goal-primary", nodes)
        self.assertTrue(nodes["goal:goal-repair"]["live"])
        self.assertIn(("goal:goal-primary", "goal:goal-repair", "parent_of"), edges)
        self.assertIn(("goal:goal-repair", "goal:goal-primary", "supports"), edges)
        run_id = self.runtime.store.cycle(child["id"])["id"]
        self.assertIn((f"goal:{child['id']}", f"run:{run_id}", "current_run"), edges)
        self.assertIn((f"run:{run_id}", "loop:observe", "currently_at"), edges)
        self.assertEqual(["OBSERVE", "DECIDE", "ACT", "EVALUATE"],
                         snapshot["loop"]["stages"])
        self.assertNotIn("loop:goal", nodes)

    def test_snapshot_exposes_real_layers_packages_state_and_ignored_paths(self):
        snapshot = collect_snapshot(self.runtime, project_root=self.root)
        nodes = {item["id"]: item for item in snapshot["nodes"]}
        self.assertEqual([item[0] for item in LAYERS],
                         [item["id"] for item in snapshot["layers"]])
        self.assertIn("department:outbound", nodes)
        self.assertIn("agent:lead-researcher", nodes)
        self.assertIn("workflow:outbound:lead-research", nodes)
        self.assertFalse(any(item["kind"] in {"retired_capability", "retired_executor"}
                             for item in nodes.values()))
        self.assertIn("table:goals", nodes)
        self.assertIn("system:intervention", nodes)
        self.assertIn("system:resolution", nodes)
        self.assertIn("system:workflow-run", nodes)
        self.assertIn("system:memory", nodes)
        self.assertEqual("compatibility", snapshot["source"]["runtime_model"])
        self.assertEqual([".spielos/", ".env"], nodes["policy:gitignore"]["meta"]["patterns"])
        self.assertGreater(snapshot["metrics"]["architecture_nodes"], 20)
        self.assertGreater(snapshot["metrics"]["relations"], 10)
        self.assertFalse(any(item["kind"] == "unused_connection"
                             for item in snapshot["findings"]))

    def test_clean_core_state_becomes_live_authority_without_mixing_legacy_goals(self):
        database = Database(self.root / ".spielos/state/company.sqlite")
        goals, runs = GoalRepository(database), RunRepository(database)
        goal = goals.create("Canonical outcome", "accepted", "eq", True,
                            goal_id="goal-canonical")
        run = runs.create(goal.id)
        runs.update(run.id, stage=GoalStage.ACT, status="running")
        intervention = InterventionRepository(database).create(
            goal_id=goal.id, run_id=run.id, kind="build",
            description="Connect the clean architecture")
        workflows = WorkflowRepository(database)
        workflows.save(Workflow("observe", "Observe", (
            WorkflowStep("render", "lead-researcher", "Render the living graph",
                         "observer_rendered"),
        ), "outbound"))
        workflow_run = workflows.start(
            "observe", goal_id=goal.id, run_id=run.id,
            intervention_id=intervention.id)
        order = WorkOrderRepository(database).open(
            goal_id=goal.id, run_id=run.id, intervention_id=intervention.id,
            workflow_run_id=workflow_run.id, step_id="render",
            agent_id="lead-researcher", brief={"view": "organism"})
        evidence = EvidenceRepository(database)
        item = evidence.record(
            goal_id=goal.id, run_id=run.id, intervention_id=intervention.id,
            workflow_run_id=workflow_run.id, work_order_id=order.id,
            kind="observer_rendered", payload={"healthy": True})
        MemoryRepository(database, evidence).remember(
            "workflow", "Keep graph state source-backed", evidence_ids=(item.id,),
            goal_id=goal.id, run_id=run.id, intervention_id=intervention.id,
            workflow_id="observe")

        snapshot = collect_snapshot(self.runtime, project_root=self.root)
        nodes = {entry["id"]: entry for entry in snapshot["nodes"]}
        edges = {(entry["source"], entry["target"], entry["relation"])
                 for entry in snapshot["edges"]}
        self.assertEqual("clean-core", snapshot["source"]["runtime_model"])
        self.assertIn("goal:goal-canonical", nodes)
        self.assertNotIn("goal:goal-primary", nodes)
        self.assertIn(f"intervention:{intervention.id}", nodes)
        self.assertIn(f"workflow-run:{workflow_run.id}", nodes)
        self.assertIn(f"work-order:{order.id}", nodes)
        self.assertIn(f"evidence:{item.id}", nodes)
        self.assertIn((f"work-order:{order.id}", f"evidence:{item.id}", "produced"), edges)

    def test_clean_core_multiple_roots_are_reported_instead_of_masked(self):
        database = Database(self.root / ".spielos/state/company.sqlite")
        goals = GoalRepository(database)
        goals.create("Release A", "ready", "eq", True, goal_id="release-a")
        goals.create("Release B", "ready", "eq", True, goal_id="release-b")

        snapshot = collect_snapshot(self.runtime, project_root=self.root)

        self.assertEqual("clean-core", snapshot["source"]["runtime_model"])
        self.assertTrue(any(item["kind"] == "missing_canonical_root"
                            for item in snapshot["findings"]))
        topology = [item for item in snapshot["findings"]
                    if item["kind"] == "goal_topology"]
        self.assertEqual({"goal:release-a", "goal:release-b"},
                         {item["node_ids"][0] for item in topology})

    def test_cli_and_ui_contract(self):
        args = build_parser().parse_args(["observatory", "--snapshot", "--json"])
        self.assertEqual("observatory", args.command)
        self.assertTrue(args.snapshot)
        ui = (Path(__file__).parents[1] / "runtime/observability_ui.html").read_text(
            encoding="utf-8")
        for required in ("/api/snapshot", "Goal tree + DAG", "Architecture",
                         "Coherence", "Everything", "setInterval(refresh,2000)",
                         "outfit-latin.woff2", "left-closed", "right-closed"):
            self.assertIn(required, ui)
        self.assertNotIn("https://", ui)


if __name__ == "__main__":
    unittest.main()
