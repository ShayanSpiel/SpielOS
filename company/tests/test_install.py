"""Department install path: spec → package files → discovery → goals."""

import json
import os
import sys
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

from company.agents import agents as installed_agents
from company.runtime.install import (
    allowed_install_files,
    agent_file_stem,
    install_department,
    normalize_department_spec,
    validate_department_spec,
)
from company.runtime.loop import Runtime
from company.runtime.registry import departments, handlers
from company.runtime.system_improvement import SystemImprovement
from company.runtime.templates import build_graph_from_brief, infer_template


@contextmanager
def isolated_install_roots():
    """Redirect live install destinations into a temporary company tree."""

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        departments_root = root / "departments"
        agents_root = root / "agents" / "installed"
        departments_root.mkdir(parents=True)
        agents_root.mkdir(parents=True)
        import company.departments as department_package
        import company.runtime.install as install_mod

        original_path = list(department_package.__path__)
        previous_agents = os.environ.get("SPIELOS_AGENTS_INSTALLED_ROOT")
        department_package.__path__.insert(0, str(departments_root))
        os.environ["SPIELOS_AGENTS_INSTALLED_ROOT"] = str(agents_root)
        try:
            with patch.object(install_mod, "DEPARTMENTS_ROOT", departments_root), \
                 patch.object(install_mod, "AGENTS_INSTALLED_ROOT", agents_root):
                yield {
                    "root": root,
                    "departments": departments_root,
                    "agents": agents_root,
                }
        finally:
            department_package.__path__[:] = original_path
            if previous_agents is None:
                os.environ.pop("SPIELOS_AGENTS_INSTALLED_ROOT", None)
            else:
                os.environ["SPIELOS_AGENTS_INSTALLED_ROOT"] = previous_agents
            for prefix in ("company.departments.demo_ops",
                           "company.departments.auto_install_dept",
                           "company.departments.cli_install_dept",
                           "company.departments.iso_ops",
                           "company.departments.content"):
                for key in list(sys.modules):
                    if key == prefix or key.startswith(prefix + "."):
                        del sys.modules[key]


class SpecNormalizationTests(unittest.TestCase):
    def test_short_brief_becomes_multi_step_package_with_agents(self):
        package = normalize_department_spec({
            "id": "partnerships",
            "purpose": "Win partner intros",
            "metrics": ["meetings"],
            "evidence_sources": ["partner_meeting"],
            "approval_points": ["outreach"],
            "steps": ["research", "draft", "approve", "record"],
        })
        self.assertEqual("partnerships", package["id"])
        self.assertEqual(["meetings"], package["metrics"])
        self.assertEqual(["partner_meeting"], package["evidence_metrics"]["meetings"])
        self.assertEqual(1, len(package["workflows"]))
        graph = package["workflows"][0]["graph"]
        self.assertGreaterEqual(len(graph), 3)
        self.assertTrue(any(node["kind"] == "approval" for node in graph))
        self.assertTrue(any(node["kind"] == "employee" for node in graph))
        self.assertTrue(package["agents"])
        self.assertEqual(package["agent_ids"][0], package["agents"][0]["id"])
        self.assertIn("partner_meeting", package["agents"][0]["produces"]
                      + package["workflows"][0]["graph"][-1]["produces"])
        self.assertEqual([], validate_department_spec(package))

    def test_publish_template_builds_connection_graph(self):
        self.assertEqual("publish", infer_template({
            "connection_ids": ["buffer"], "external_actions": ["publish"],
            "approval_points": ["approve"],
        }))
        labels, graph = build_graph_from_brief(
            template="publish", employee="pub-ops", agents=["pub-ops"],
            produces=["content_package", "publication_receipt"],
            skill_ids=["outbound-email"], connection_ids=["buffer"],
            approval_points=["approve"],
        )
        kinds = [node["kind"] for node in graph]
        self.assertEqual(["employee", "approval", "connection"], kinds)
        self.assertEqual(["buffer"], graph[-1]["connection_ids"])
        self.assertIn("select", labels)

    def test_validation_rejects_unresolved_package_references(self):
        defects = validate_department_spec({
            "id": "broken_refs",
            "metrics": ["items"],
            "skill_ids": ["missing-skill"],
            "connection_ids": ["missing-connection"],
        })
        self.assertTrue(any("unknown skill missing-skill" in item for item in defects))
        self.assertTrue(any("unknown connection missing-connection" in item
                            for item in defects))

    def test_validation_rejects_duplicate_workflow_and_step_ids(self):
        defects = validate_department_spec({
            "id": "duplicate_graph",
            "metrics": ["items"],
            "evidence_metrics": {"items": ["item_record"]},
            "workflows": [{
                "id": "primary",
                "graph": [
                    {"id": "same", "kind": "employee", "produces": ["item_record"]},
                    {"id": "same", "kind": "employee", "produces": ["item_record"]},
                ],
            }],
        })
        self.assertTrue(any("duplicate step id same" in item for item in defects))

    def test_validation_rejects_agent_filename_collisions(self):
        defects = validate_department_spec({
            "id": "agent_collision",
            "metrics": ["items"],
            "agent_ids": ["same-agent", "same_agent"],
        })
        self.assertTrue(any("share installed filename same_agent.json" in item
                            for item in defects))


class InstallPathTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.dept_id = "demo_ops"
        stack = isolated_install_roots()
        self.tree = stack.__enter__()
        self.addCleanup(stack.__exit__, None, None, None)

    def test_install_writes_package_agents_and_registers(self):
        receipt = install_department({
            "id": self.dept_id,
            "description": "Demo operations department",
            "version": "1.0.0",
            "metrics": ["playbooks"],
            "agent_ids": ["demo-ops-operator"],
            "evidence_metrics": {"playbooks": ["playbook_record"]},
            "skill_ids": ["outbound-email"],
            "steps": ["research", "draft", "record"],
            "template": "pipeline",
        }, force=True)
        self.assertTrue(receipt["ok"])
        self.assertEqual(self.dept_id, receipt["id"])
        self.assertIn("demo-ops-operator", receipt["agents"])
        self.assertTrue(any("agents/installed" in path or str(self.tree["agents"]) in path
                            for path in receipt["agents_written"]))
        self.assertIn(self.dept_id, departments())
        self.assertIn("demo-ops-operator", installed_agents())
        agent = installed_agents()["demo-ops-operator"]
        self.assertIn("playbook_record", agent.produces)
        installed = departments()[self.dept_id]
        self.assertEqual("1.0.0", installed.version)
        self.assertEqual("playbooks", installed.goal_schema["metrics"][0])
        graph = installed.workflows[0].graph
        self.assertGreaterEqual(len(graph), 2)
        self.assertTrue((self.tree["departments"] / self.dept_id / "department.py").is_file())

        with tempfile.TemporaryDirectory() as tmp:
            runtime = Runtime(Path(tmp) / "company.sqlite")
            goal = runtime.create_goal(
                name="One playbook", owner_id=self.dept_id, metric="playbooks",
                operator="ge", target=1, config={})
            blocked = runtime.once(goal["id"])
            self.assertEqual("blocked", blocked["cycle"]["run_status"])
            order = runtime.store.work_orders(status="open", goal_id=goal["id"])[0]
            self.assertEqual("demo-ops-operator", order["employee_id"])

    def test_install_respects_allowed_files(self):
        with self.assertRaises(PermissionError):
            install_department({
                "id": self.dept_id,
                "purpose": "x",
                "metrics": ["a"],
            }, force=True, allowed_files=["company/departments/other/department.py"])

    def test_force_cannot_overwrite_built_in_department(self):
        built_in = self.tree["departments"] / "content"
        built_in.mkdir()
        with self.assertRaisesRegex(ValueError, "built-in"):
            install_department({
                "id": "content", "purpose": "collision", "metrics": ["items"],
            }, force=True)

    def test_live_install_rolls_back_when_discovery_fails(self):
        spec = {
            "id": self.dept_id,
            "purpose": "Original package",
            "metrics": ["items"],
            "evidence_sources": ["item_record"],
        }
        install_department(spec, force=True)
        department_file = self.tree["departments"] / self.dept_id / "department.py"
        original = department_file.read_text()

        with patch("company.runtime.install.load_installed_department",
                   side_effect=ValueError("discovery failed")):
            with self.assertRaisesRegex(ValueError, "discovery failed"):
                install_department({**spec, "purpose": "Broken replacement"}, force=True)

        self.assertEqual(original, department_file.read_text())
        self.assertIn(self.dept_id, departments())


class SystemImprovementInstallTests(unittest.TestCase):
    def setUp(self):
        self.dept_id = "auto_install_dept"
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        stack = isolated_install_roots()
        self.tree = stack.__enter__()
        self.addCleanup(stack.__exit__, None, None, None)

    def test_create_department_installs_after_approval(self):
        runtime = Runtime(Path(self.temp.name) / "company.sqlite",
                          {"system-improvement": SystemImprovement()})
        preview = normalize_department_spec({
            "id": self.dept_id,
            "purpose": "Auto installed demo",
            "metrics": ["ships"],
            "evidence_sources": ["ship_receipt"],
            "template": "research",
        })
        goal = runtime.create_goal(
            name="Install auto dept", owner_id="system-improvement",
            metric="acceptance_tests_passed", operator="eq", target=True,
            run_type="system_improvement", evidence_validity="technical_only", config={
                "change_kind": "create_department",
                "owner_id": self.dept_id,
                "from_version": "new",
                "target_version": "1.0.0",
                "problem": "Need an auto-installed Lego department",
                "allowed_files": allowed_install_files(
                    self.dept_id, preview["agent_ids"]),
                "acceptance_tests": ["company department list"],
                "force_install": True,
                "owner_override": True,
                "department_spec": {
                    "id": self.dept_id,
                    "purpose": "Auto installed demo",
                    "metrics": ["ships"],
                    "evidence_sources": ["ship_receipt"],
                    "template": "research",
                },
            })
        parked = runtime.once(goal["id"])
        self.assertEqual("awaiting_approval", parked["cycle"]["run_status"])
        runtime.approve(goal["id"])
        done = runtime.once(goal["id"])
        self.assertEqual("achieved", done["goal"]["goal_status"])
        task = done["change_tasks"][0]
        self.assertEqual("completed", task["status"])
        self.assertTrue(task["result"]["passed"])
        self.assertEqual(self.dept_id, task["result"]["install"]["id"])
        self.assertIn(self.dept_id, handlers())
        # Research template installs multi-step graph + roster employees.
        dept = departments()[self.dept_id]
        self.assertGreaterEqual(len(dept.workflows[0].graph), 3)
        for agent_id in dept.agent_ids:
            self.assertIn(agent_id, installed_agents())


class CliInstallTests(unittest.TestCase):
    def setUp(self):
        self.dept_id = "cli_install_dept"
        stack = isolated_install_roots()
        self.tree = stack.__enter__()
        self.addCleanup(stack.__exit__, None, None, None)

    def test_cli_validate_and_install(self):
        from company.__main__ import main
        import io
        from contextlib import redirect_stdout

        spec = {
            "id": self.dept_id,
            "purpose": "CLI installed",
            "metrics": ["notes"],
            "evidence_sources": ["note_record"],
            "template": "artifact",
            "agents": [{
                "id": "cli-install-writer",
                "description": "Writes notes",
                "skill_ids": ["outbound-email"],
                "permissions": ["read_strategy", "write_evidence"],
                "produces": ["note_record"],
            }],
            "agent_ids": ["cli-install-writer"],
        }
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = main(["department", "validate", "--spec", json.dumps(spec)])
        self.assertEqual(0, code)
        payload = json.loads(buf.getvalue())
        self.assertTrue(payload["ok"])
        self.assertGreaterEqual(len(payload["package"]["workflows"][0]["graph"]), 2)

        buf = io.StringIO()
        with redirect_stdout(buf):
            code = main(["department", "install", "--spec", json.dumps(spec), "--force"])
        self.assertEqual(0, code)
        receipt = json.loads(buf.getvalue())
        self.assertTrue(receipt["ok"])
        self.assertEqual(self.dept_id, receipt["id"])
        self.assertIn(self.dept_id, departments())
        self.assertIn("cli-install-writer", installed_agents())
        stem = agent_file_stem("cli-install-writer")
        self.assertTrue((self.tree["agents"] / f"{stem}.json").is_file())


if __name__ == "__main__":
    unittest.main()
