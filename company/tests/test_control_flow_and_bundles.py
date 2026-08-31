import unittest
import tempfile
from pathlib import Path

from company.__main__ import build_parser
from company.runtime.catalog import catalog
from company.runtime.export import export_department
from company.runtime.package import validate_package
from company.runtime.registry import departments


EXPECTED = {
    "analytics", "client_delivery", "content", "design", "outbound", "seo",
    "videography",
}


class DepartmentBundleTests(unittest.TestCase):
    def test_bundled_departments_validate_and_discover(self):
        installed = departments()
        self.assertEqual(EXPECTED, set(installed))
        for department_id, department in installed.items():
            self.assertEqual([], validate_package(department), department_id)

    def test_catalog_relations_resolve(self):
        value = catalog()
        agent_ids = {item["id"] for item in value["agents"]}
        skill_ids = {item["id"] for item in value["skills"]}
        connection_ids = {item["id"] for item in value["connections"]}
        for department in value["departments"]:
            self.assertTrue(department["lego"], department["package_defects"])
            self.assertLessEqual(set(department["agent_ids"]), agent_ids)
            for workflow in department["workflows"]:
                self.assertLessEqual(set(workflow["skills"]), skill_ids)
                self.assertLessEqual(set(workflow["connections"]), connection_ids)

    def test_export_uses_declared_workflow_agent_and_connection_dependencies(self):
        with tempfile.TemporaryDirectory() as temp:
            receipt = export_department("outbound", Path(temp))
        self.assertEqual(
            {"copywriting", "outbound", "outbound-email"},
            set(receipt["skills"]),
        )
        self.assertEqual(
            {"email-delivery", "web-research"},
            set(receipt["connections"]),
        )


class ControlSurfaceTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(__file__).resolve().parents[2]
        self.company = self.root / "company"
        self.shipped = self.company / "init_templates/agents/company"

    def test_hosts_ship_only_architecture_level_agents(self):
        expected = {"director", "system-improvement", "department-runner"}
        locations = (
            (self.root / ".codex/agents", ".toml"),
            (self.root / ".opencode/agents", ".md"),
            (self.company / "init_templates/hosts/codex/agents", ".toml"),
            (self.company / "init_templates/hosts/opencode/agents", ".md"),
        )
        for folder, suffix in locations:
            self.assertEqual(expected, {path.stem for path in folder.glob(f"*{suffix}")})

    def test_executable_spine_matches_shipped_template(self):
        paths = [self.company / "__main__.py"]
        paths += sorted((self.company / "runtime").glob("*.py"))
        paths += sorted((self.company / "connections").glob("*.py"))
        paths += sorted((self.company / "agents").glob("*.py"))
        for source in paths:
            relative = source.relative_to(self.company)
            shipped = self.shipped / relative
            self.assertTrue(shipped.is_file(), str(relative))
            self.assertEqual(source.read_bytes(), shipped.read_bytes(), str(relative))

    def test_lean_layout_has_departments_and_no_retired_workgroups(self):
        for root in (self.company, self.shipped):
            self.assertTrue((root / "departments").is_dir())
            self.assertFalse((root / "workgroups").exists())
            self.assertFalse((root / "runtime/workgroup_install.py").exists())

    def test_public_cli_exposes_department_portability(self):
        parser = build_parser()
        action = next(item for item in parser._actions if item.dest == "command")
        self.assertTrue({"department", "departments", "add", "agent"}
                        <= set(action.choices))

    def test_runtime_uses_department_and_agent_contracts(self):
        models = (self.company / "runtime/models.py").read_text()
        interpreter = (self.company / "runtime/interpreter.py").read_text()
        self.assertIn("class Department", models)
        self.assertIn("class AgentSpec", models)
        self.assertIn("class InterpretedDepartment", interpreter)
        self.assertNotIn("class Workgroup", models)

    def test_skill_discovery_has_exactly_two_scopes(self):
        source = (self.company / "agents/__init__.py").read_text()
        self.assertIn("_OPERATOR_SKILLS_ROOT", source)
        self.assertIn("_DEPARTMENTS_ROOT", source)
        self.assertNotIn("_WORKGROUPS_ROOT", source)
        self.assertNotIn(".agents/skills", source)

    def test_department_runner_is_shipped_byte_identically(self):
        source = self.company / "skills/department-runner/SKILL.md"
        shipped = self.shipped / "skills/department-runner/SKILL.md"
        self.assertTrue(source.is_file())
        self.assertEqual(source.read_bytes(), shipped.read_bytes())


if __name__ == "__main__":
    unittest.main()
