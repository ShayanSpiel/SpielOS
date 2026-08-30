import tempfile
import unittest
from pathlib import Path

from company.__main__ import build_parser
from company.runtime.workgroup_install import (
    bundled_workgroup_specs, install_workgroup, validate_workgroup_spec)
from company.workgroups.registry import workgroups


EXPECTED = {
    "growth-community", "product-reliability", "real-world-validation",
    "release-operations", "user-feedback", "ux-experience",
}


class WorkgroupBundleTests(unittest.TestCase):
    def test_six_real_bundles_validate_and_discover(self):
        specs = bundled_workgroup_specs()
        self.assertEqual(EXPECTED, {spec["id"] for spec in specs})
        self.assertEqual(EXPECTED, set(workgroups()))
        for spec in specs:
            self.assertEqual([], validate_workgroup_spec(spec), spec["id"])

    def test_install_all_materializes_every_bundle(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for spec in bundled_workgroup_specs():
                install_workgroup(spec, root=root)
            self.assertEqual(EXPECTED, {
                path.parent.name for path in root.glob("*/workgroup.json")})

    def test_ux_workgroup_has_three_worker_owned_handoffs(self):
        ux = workgroups()["ux-experience"].workgroup
        self.assertEqual(
            {"journey-researcher", "interaction-designer", "handoff-validator"},
            {worker.id for worker in ux.workers})
        flows = {flow.id: flow for worker in ux.workers for flow in worker.workflows}
        self.assertEqual({"journey_observation"}, set(flows[
            "command-and-delegation-review"].graph[0].requires))
        handoff = flows["worker-handoff-validation"].graph
        self.assertEqual(
            ["journey-researcher", "interaction-designer", "handoff-validator"],
            [step.employee_id for step in handoff])
        self.assertEqual({"ux_recommendation"}, set(handoff[2].requires))


class ControlSurfaceTests(unittest.TestCase):
    def test_hosts_ship_only_architecture_level_agents(self):
        root = Path(__file__).resolve().parents[2]
        expected = {"director", "system-improvement", "workgroup-runner"}
        locations = (
            (root / ".codex/agents", ".toml"),
            (root / ".opencode/agents", ".md"),
            (root / "company/init_templates/hosts/codex/agents", ".toml"),
            (root / "company/init_templates/hosts/opencode/agents", ".md"),
        )
        for folder, suffix in locations:
            self.assertEqual(expected, {path.stem for path in folder.glob(f"*{suffix}")})
            for path in folder.glob(f"*{suffix}"):
                prompt = path.read_text()
                self.assertNotIn("create_department", prompt)
                self.assertNotIn("skills/department-runner", prompt)
                self.assertNotIn("/departments/", prompt)

    def test_executable_spine_matches_shipped_template(self):
        company_root = Path(__file__).parents[1]
        template_root = company_root / "init_templates" / "agents" / "company"
        paths = [company_root / "__main__.py"]
        paths += sorted((company_root / "runtime").glob("*.py"))
        paths += sorted((company_root / "connections").glob("*.py"))
        paths += sorted((company_root / "workgroups").glob("*.py"))
        for source in paths:
            relative = source.relative_to(company_root)
            shipped = template_root / relative
            self.assertTrue(shipped.is_file(), str(relative))
            self.assertEqual(source.read_bytes(), shipped.read_bytes(), str(relative))

    def test_legacy_department_and_supervisor_trees_are_absent(self):
        company_root = Path(__file__).parents[1]
        template_root = company_root / "init_templates" / "agents" / "company"
        for root in (company_root, template_root):
            self.assertFalse((root / "departments").exists())
            self.assertFalse((root / "runtime" / "supervisor.py").exists())

    def test_public_cli_has_no_legacy_department_or_runner_wake_commands(self):
        parser = build_parser()
        command_action = next(action for action in parser._actions
                              if action.dest == "command")
        commands = set(command_action.choices)
        self.assertFalse({"department", "departments", "add"} & commands)
        runner = command_action.choices["runner"]
        runner_action = next(action for action in runner._actions
                             if action.dest == "runner_command")
        self.assertNotIn("wake", runner_action.choices)

    def test_runtime_has_no_retired_department_model_or_dead_renderers(self):
        company_root = Path(__file__).parents[1]
        models = (company_root / "runtime" / "models.py").read_text()
        interpreter = (company_root / "runtime" / "interpreter.py").read_text()
        command = (company_root / "__main__.py").read_text()
        registry = (company_root / "workgroups" / "registry.py").read_text()
        self.assertNotIn("class Department", models)
        self.assertNotIn("department_id", models + registry)
        self.assertNotIn("InterpretedDepartment", interpreter + registry)
        self.assertNotIn("render_departments", command)
        self.assertNotIn("render_department_packages", command)

    def test_skill_discovery_uses_workgroup_roots_only(self):
        source = (Path(__file__).parents[1] / "agents" / "__init__.py").read_text()
        self.assertIn("_WORKGROUPS_ROOT", source)
        self.assertNotIn("_DEPARTMENTS_ROOT", source)

    def test_runner_source_contains_advancement_not_watchdog_surfaces(self):
        source = (Path(__file__).parents[1] / "runtime" / "runner.py").read_text()
        self.assertIn("def tick", source)
        self.assertIn("def watch", source)
        for forbidden in ("digest_payload", "live_status", "heartbeat",
                          "runner_down", "watchdog_incidents", "def wake"):
            self.assertNotIn(forbidden, source)

    def test_director_skill_uses_owner_approved_attached_session_wake(self):
        source = (Path(__file__).parents[1] / "skills" / "director" / "SKILL.md").read_text()
        question = "Do you want me to supervise this run every\n5 minutes?"
        self.assertEqual(1, source.count(question))
        self.assertIn("sleep 300; echo SPIELOS_WAKE", source)
        self.assertIn("no active Goal", source)
        self.assertIn("memory apply-candidate", source)

    def test_workgroup_runner_starts_from_bounded_assignment_not_catalog(self):
        company_root = Path(__file__).parents[1]
        source = (company_root / "skills" / "workgroup-runner" / "SKILL.md").read_text()
        shipped = (company_root / "init_templates" / "agents" / "company" /
                   "skills" / "workgroup-runner" / "SKILL.md").read_text()
        for instructions in (source, shipped):
            self.assertNotIn("company catalog", instructions)
            self.assertIn("exact persisted Goal, Workgroup, Workflow, and work-order", instructions)
            self.assertIn("Never load the full company", instructions)
        self.assertEqual(source, shipped)


if __name__ == "__main__":
    unittest.main()
