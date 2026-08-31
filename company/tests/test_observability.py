"""Acceptance coverage for the live SpielOS architecture observatory."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from company.__main__ import build_parser
from company.runtime.loop import Runtime
from company.runtime.observability import LAYERS, collect_snapshot


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

        self.assertEqual("1.0", snapshot["schema_version"])
        self.assertIn("goal:goal-primary", nodes)
        self.assertTrue(nodes["goal:goal-repair"]["live"])
        self.assertIn(("goal:goal-primary", "goal:goal-repair", "parent_of"), edges)
        self.assertIn(("goal:goal-repair", "goal:goal-primary", "supports"), edges)
        run_id = self.runtime.store.cycle(child["id"])["id"]
        self.assertIn((f"goal:{child['id']}", f"run:{run_id}", "current_run"), edges)
        self.assertIn((f"run:{run_id}", "loop:observe", "currently_at"), edges)

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
        self.assertEqual([".spielos/", ".env"], nodes["policy:gitignore"]["meta"]["patterns"])
        self.assertGreater(snapshot["metrics"]["architecture_nodes"], 20)
        self.assertGreater(snapshot["metrics"]["relations"], 10)

    def test_cli_and_ui_contract(self):
        args = build_parser().parse_args(["observatory", "--snapshot", "--json"])
        self.assertEqual("observatory", args.command)
        self.assertTrue(args.snapshot)
        ui = (Path(__file__).parents[1] / "runtime/observability_ui.html").read_text(
            encoding="utf-8")
        for required in ("/api/snapshot", "Goal tree + DAG", "Architecture",
                         "Coherence", "Everything", "setInterval(refresh,2000)"):
            self.assertIn(required, ui)
        self.assertNotIn("https://", ui)


if __name__ == "__main__":
    unittest.main()
