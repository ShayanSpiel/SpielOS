from __future__ import annotations

import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from company.__main__ import build_parser, main
from company.cli import _vendored_home, main as console_main
from company.runtime.artifacts import (
    finalize_workspace, prepare_workspace, present_artifact)
from company.runtime.friction import friction_summary, record_friction
from company.runtime.migration import inspect_source, migration_plan
from company.runtime.bootstrap import scaffold
from company.runtime.export import (
    RETIRED_HARNESS_FILES, RETIRED_HOST_AGENTS, refresh_home)
from company.runtime.config import VERSION


class OrientationTests(unittest.TestCase):
    def test_release_metadata_and_trusted_publish_workflow_are_aligned(self):
        root = Path(__file__).parents[2]
        package = json.loads((root / "package.json").read_text())
        workflow = (root / ".github/workflows/publish.yml").read_text()

        self.assertEqual("8.0.1", VERSION)
        self.assertEqual(VERSION, package["version"])
        self.assertIn("npm@^11.5.1", workflow)
        self.assertNotIn("NPM_TOKEN", workflow)
        self.assertFalse((root / ".github/workflows/npm-only.yml").exists())

    def test_update_prunes_only_known_legacy_host_agents(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory) / "home"
            scaffold(home, minimal=True)
            self.assertTrue(
                (home / ".agents/company/departments/core.py").is_file())
            for host, filenames in RETIRED_HOST_AGENTS.items():
                agents = home / f".{host}" / "agents"
                agents.mkdir(parents=True, exist_ok=True)
                for filename in filenames:
                    (agents / filename).write_text("legacy\n")
                (agents / "custom-owner-agent.md").write_text("keep\n")
            company = home / ".agents/company"
            for relative in RETIRED_HARNESS_FILES:
                retired = company / relative
                retired.parent.mkdir(parents=True, exist_ok=True)
                retired.write_text("retired\n")
            custom_connection = company / "connections/custom-owner.py"
            custom_connection.write_text("keep = True\n")

            receipt = refresh_home(target=home)

            self.assertEqual(2, len(receipt["removed_retired_host_agents"]))
            self.assertEqual(
                len(RETIRED_HARNESS_FILES),
                len(receipt["removed_retired_harness_files"]))
            for host, filenames in RETIRED_HOST_AGENTS.items():
                agents = home / f".{host}" / "agents"
                self.assertTrue((agents / "custom-owner-agent.md").is_file())
                for filename in filenames:
                    self.assertFalse((agents / filename).exists())
            for relative in RETIRED_HARNESS_FILES:
                self.assertFalse((company / relative).exists())
            self.assertTrue(custom_connection.is_file())

    def test_director_does_not_auto_open_code_or_internal_artifacts(self):
        instructions = (Path(__file__).parents[1] / "skills/director/SKILL.md").read_text()
        self.assertIn("Never automatically open code, packages, archives, tests", instructions)
        self.assertIn("video, image,\n   audio, copy, document, deck", instructions)

    def test_console_finds_nearest_initialized_home(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory) / "home"
            runtime = home / ".agents" / "company" / "__main__.py"
            runtime.parent.mkdir(parents=True)
            runtime.write_text("# vendored runtime\n")
            nested = home / "projects" / "website"
            nested.mkdir(parents=True)
            self.assertEqual(home.resolve(), _vendored_home(nested))

    def test_console_explains_how_to_recover_from_deleted_cwd(self):
        original = os.getcwd()
        with tempfile.TemporaryDirectory() as directory:
            deleted = Path(directory) / "deleted-home"
            deleted.mkdir()
            os.chdir(deleted)
            deleted.rmdir()
            output = io.StringIO()
            try:
                with redirect_stderr(output):
                    code = console_main()
            finally:
                os.chdir(original)

        self.assertEqual(code, 2)
        self.assertIn("current folder was deleted", output.getvalue())
        self.assertIn("cd ~/Desktop/Projects", output.getvalue())

    def test_release_readiness_commands_are_discoverable(self):
        parser = build_parser()
        commands = next(action for action in parser._actions
                        if action.dest == "command").choices
        self.assertTrue({"overview", "artifact", "friction", "migration", "agent", "update"}
                        <= set(commands))
        self.assertIn("json", {action.dest for action in commands["update"]._actions})
        runner = commands["runner"]
        runner_commands = next(action for action in runner._actions
                               if action.dest == "runner_command").choices
        tick = runner_commands["tick"]
        self.assertIn("json", {action.dest for action in tick._actions})
        agents = commands["agent"]
        agent_commands = next(action for action in agents._actions
                              if action.dest == "agent_command").choices
        self.assertIn("list", agent_commands)

    def test_goal_topology_has_human_output_without_json(self):
        with tempfile.TemporaryDirectory() as directory:
            output = io.StringIO()
            with redirect_stdout(output):
                code = main(["--db", str(Path(directory) / "state.sqlite"),
                             "goal", "topology"])
            self.assertEqual(code, 0)
            self.assertIn("# Goal topology", output.getvalue())
            self.assertIn("Canonical primary root", output.getvalue())

    def test_overview_is_one_readable_command(self):
        with tempfile.TemporaryDirectory() as directory:
            output = io.StringIO()
            with redirect_stdout(output):
                code = main(["--db", str(Path(directory) / "state.sqlite"),
                             "overview"])
            self.assertEqual(code, 0)
            self.assertIn("# Company overview", output.getvalue())
            self.assertIn("Departments:", output.getvalue())
            self.assertIn("Agents:", output.getvalue())


class ArtifactLifecycleTests(unittest.TestCase):
    def test_macos_presentation_opens_final_folder_with_finder(self):
        with tempfile.TemporaryDirectory() as directory:
            prepared = prepare_workspace(
                goal_id="goal-1", run_id="run-1", project_root=directory)
            final = Path(prepared["final"])
            with patch("company.runtime.artifacts.sys.platform", "darwin"), \
                    patch("company.runtime.artifacts.subprocess.run") as run:
                run.return_value.returncode = 0
                receipt = present_artifact(
                    final, open_folder=True, project_root=directory)
            run.assert_called_once_with(
                ["open", "-a", "Finder", str(final)],
                check=False, capture_output=True, text=True)
            self.assertTrue(receipt["opened"])

    def test_finalize_moves_finals_hashes_them_and_cleans_work(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            prepared = prepare_workspace(
                goal_id="goal-1", run_id="run-1", workflow_id="video",
                project_root=root)
            work = Path(prepared["work"])
            final_video = work / "launch.mp4"
            final_video.write_bytes(b"verified-video")
            (work / "discarded-frame.png").write_bytes(b"temporary")

            receipt = finalize_workspace(
                goal_id="goal-1", run_id="run-1", workflow_id="video",
                files=[final_video], project_root=root)

            self.assertFalse(work.exists())
            self.assertTrue((Path(receipt["final"]) / "launch.mp4").is_file())
            manifest = json.loads(Path(receipt["manifest"]).read_text())
            self.assertEqual(manifest["status"], "final")
            self.assertEqual(64, len(manifest["final_files"][0]["sha256"]))

    def test_present_rejects_paths_outside_artifact_authority(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            outside = root / "outside.txt"
            outside.write_text("no")
            with self.assertRaisesRegex(ValueError, "inside"):
                present_artifact(outside, project_root=root)


class FrictionTests(unittest.TestCase):
    def test_repeated_mismatch_is_durable_and_grouped(self):
        with tempfile.TemporaryDirectory() as directory:
            for _ in range(2):
                record_friction(
                    kind="command_mismatch", source="company runner tick",
                    expected="readable result", actual="renderer error",
                    fallback="targeted status", project_root=directory)
            summary = friction_summary(project_root=directory)
            self.assertEqual(2, summary["event_count"])
            self.assertEqual(1, summary["unique_count"])
            self.assertEqual(2, summary["recent"][0]["occurrences"])


class MigrationPolicyTests(unittest.TestCase):
    def test_website_and_harness_are_separate_migration_units(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "package.json").write_text('{"scripts":{"build":"vite build"}}\n')
            source = root / "src/main.ts"
            source.parent.mkdir()
            source.write_text("export const ready = true\n")
            generated = root / "node_modules/library/index.js"
            generated.parent.mkdir(parents=True)
            generated.write_text("ignore generated dependency\n")
            department = root / ".agents/company/departments/design"
            department.mkdir(parents=True)
            (department / "department.py").write_text("legacy = True\n")

            inspection = inspect_source(root)
            plan = migration_plan(root)

            application = inspection["inventory"]["application"]
            self.assertTrue(application["detected"])
            self.assertEqual(2, application["files"])
            self.assertEqual("website_application", plan["site_unit"]["target_type"])
            self.assertEqual("design", plan["units"][0]["target_id"])
            self.assertIn(
                "website build, tests, and critical user flows pass in the destination",
                plan["required_gates"])

    def test_legacy_harness_is_planned_without_importing_its_runtime(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = root / ".agents/company/runtime/config.py"
            config.parent.mkdir(parents=True)
            config.write_text('VERSION = "6.2.6"\n')
            department = root / ".agents/company/departments/outbound"
            department.mkdir(parents=True)
            (department / "department.py").write_text("legacy = True\n")
            state = root / ".spielos/state/company.sqlite"
            state.parent.mkdir(parents=True)
            state.write_bytes(b"archive-me")

            inspection = inspect_source(root)
            plan = migration_plan(root)

            self.assertEqual("6.2.6", inspection["detected_version"])
            self.assertEqual(["outbound"], inspection["inventory"]["departments"])
            self.assertTrue(inspection["inventory"]["has_operational_state"])
            self.assertEqual("archive_then_selectively_promote", plan["state_action"])
            self.assertEqual("needs_validation_and_acceptance", plan["units"][0]["status"])
            self.assertIn("never import", inspection["policies"]["foreign_runtime"])

    def test_classification_uses_path_context_not_misleading_filenames(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            agents = root / "AGENTS.md"
            agents.write_text("# Company instructions\n")
            local_config = (root / ".agents/company/departments/outbound/"
                            "workflows/email/config.py")
            local_config.parent.mkdir(parents=True)
            local_config.write_text("TIMEOUT = 10\n")
            template = (root / ".agents/company/departments/design/"
                        "templates/social/agent-brief.html")
            template.parent.mkdir(parents=True)
            template.write_text("<p>brief</p>\n")

            assessments = {
                Path(item["path"]).name: item["target_type"]
                for item in inspect_source(root)["inventory"]["file_assessments"]
            }
            self.assertEqual("host_instruction", assessments["AGENTS.md"])
            self.assertEqual("workflow_component", assessments["config.py"])
            self.assertEqual("template_asset", assessments["agent-brief.html"])

    def test_arbitrary_file_is_classified_or_quarantined(self):
        with tempfile.TemporaryDirectory() as directory:
            workflow = Path(directory) / "customer-playbook.json"
            workflow.write_text(json.dumps({"worksteps": [{"id": "review"}]}))
            inspection = inspect_source(workflow)
            assessment = inspection["inventory"]["file_assessments"][0]
            self.assertEqual("workflow", assessment["target_type"])
            self.assertEqual("convert_and_validate", assessment["action"])


if __name__ == "__main__":
    unittest.main()
