"""Department portability as a GitHub-repo import (``company export`` /
``company import``): export closure + manifest + README, import validation
(manifest, spine pin, closure, declaration), install surface (the six
owner layers only), idempotence, preservation, and live-goal proof.

Every pin drives the real command surface (``company.__main__.main``)
against fresh temp homes; the committed fixture bundle at
``tests/fixtures/bundle-repo`` is a generated-shape bundle produced by
``company export`` itself.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from company.__main__ import main

REPO = Path(__file__).resolve().parents[2]
FIXTURES = Path(__file__).resolve().parent / "fixtures"
BUNDLE_FIXTURE = FIXTURES / "bundle-repo"

DEPARTMENT_SOURCE = '''"""Portable research Department."""

from __future__ import annotations

from ...workflows import Workflow, WorkflowStep


class ResearchDepartment:
    department_id = "research"
    id = "research"
    version = "1.0.0"
    description = "Researches and briefs."
    agent_ids = ("research-analyst",)
    production_ready = True

    workflows = (
        Workflow(
            "weekly-brief",
            "Produce one weekly research brief.",
            (
                WorkflowStep(
                    id="collect", agent_id="research-analyst",
                    instruction="Collect signals through the research-store "
                                "Connection using skills/research_method; "
                                "missing stays missing. Record "
                                "{'research_signals': {...}} as evidence.",
                    evidence_kind="research_signals",
                    skill_ids=("research_method",),
                    connection_ids=("research_store",)),
                WorkflowStep(
                    id="write", agent_id="research-analyst",
                    instruction="Write the brief following "
                                "strategy/brief-voice.md; record "
                                "{'briefs': 1} as evidence.",
                    evidence_kind="brief_delivered",
                    skill_ids=("research_method",)),
            ),
            department_id="research"),
    )

    evidence_metrics = {"briefs": ("brief_delivered",)}
    goal_schema = {"metrics": ["briefs"],
                   "config": {"workflow": {"enum": ["weekly-brief"]}}}
    workflow_agents = {"weekly-brief": "research-analyst"}
'''


def _company(home: Path, *command: str) -> dict:
    """Run one real CLI command in a home; assert exit 0 and return JSON."""
    result = subprocess.run(
        [sys.executable, "-B", "-m", "company", *command], cwd=home,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1",
             "PYTHONPATH": str(home / ".agents")},
        capture_output=True, text=True, timeout=120)
    assert result.returncode == 0, result.stderr or result.stdout
    return json.loads(result.stdout)


def _company_fails(home: Path, *command: str) -> tuple[int, str]:
    """Run one real CLI command expecting failure; return code + stderr."""
    result = subprocess.run(
        [sys.executable, "-B", "-m", "company", *command], cwd=home,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1",
             "PYTHONPATH": str(home / ".agents")},
        capture_output=True, text=True, timeout=120)
    return result.returncode, (result.stderr or result.stdout)


def _init_home(directory: Path, name: str = "home") -> Path:
    home = directory / name
    assert 0 == main(["init", "--dir", str(home), "-y", "--json"])
    return home


def _layers(home: Path) -> Path:
    return home / ".agents" / "company"


def _write_research_department(home: Path, *, with_closure: bool = True,
                               agent_json: str | None = None) -> None:
    """A realistic department + its closure, as an owner would author it."""
    agents = _layers(home)
    (agents / "departments" / "research").mkdir(parents=True, exist_ok=True)
    (agents / "departments" / "research" / "__init__.py").write_text("")
    (agents / "departments" / "research" / "department.py").write_text(
        DEPARTMENT_SOURCE)
    (agents / "skills" / "research_method").mkdir(parents=True, exist_ok=True)
    (agents / "skills" / "research_method" / "SKILL.md").write_text(
        "# Research method\n")
    (agents / "agents" / "installed").mkdir(parents=True, exist_ok=True)
    (agents / "agents" / "installed" / "research-analyst.json").write_text(
        agent_json or json.dumps({
            "id": "research-analyst",
            "description": "Collects research signals",
            "skill_ids": ["research_method"],
            "connection_ids": ["research_store"],
            "produces": ["research_signals", "brief_delivered"]}))
    if with_closure:
        (agents / "connections").mkdir(exist_ok=True)
        (agents / "connections" / "research_store.py").write_text(
            "class ResearchStore: pass\n")
        (agents / "strategy").mkdir(exist_ok=True)
        (agents / "strategy" / "brief-voice.md").write_text("# voice\n")


class ExportTests(unittest.TestCase):
    """A: export writes the complete bundle repo folder; missing closure
    pieces are named and the export refuses."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.base = Path(self._tmp.name)
        self.home = _init_home(self.base)

    def tearDown(self):
        self._tmp.cleanup()

    def test_export_writes_complete_bundle_repository(self):
        _write_research_department(self.home)
        out = self.base / "bundle"
        self.assertEqual(0, main(["export", "research",
                                  "--dir", str(self.home),
                                  "--out", str(out), "--json"]))
        manifest = json.loads((out / "bundle.json").read_text())
        self.assertEqual("research", manifest["id"])
        self.assertEqual("1.0.0", manifest["version"])
        # The spine pin matches the running spine.
        from company.runtime.config import VERSION
        self.assertEqual(VERSION, manifest["spine_pin"])
        # The closure file list names every layer path, relative.
        files = set(manifest["files"])
        for rel in (
            "departments/research/department.py",
            "departments/research/__init__.py",
            "skills/research_method/SKILL.md",
            "connections/research_store.py",
            "strategy/brief-voice.md",
            "agents/installed/research-analyst.json",
        ):
            self.assertIn(rel, files, rel)
        # The closure summary names every referenced piece.
        closure = manifest["closure"]
        self.assertEqual(["research-analyst"], closure["agents"])
        self.assertEqual(["research_store"], closure["connections"])
        self.assertEqual(["research_method"], closure["skills"])
        self.assertEqual(["brief-voice.md"], closure["strategy"])
        # The README carries the onboarding steps: download/clone, the one
        # import command, and one paste-prompt block per adopter.
        readme = (out / "README.md").read_text()
        self.assertIn("git clone", readme)
        self.assertIn("company import", readme)
        for adopter in ("OpenCode", "Codex", "Claude Code"):
            self.assertIn(f"### {adopter}", readme)
            self.assertIn("```text", readme)
        self.assertIn("goal loop", readme)
        # The department bytes ship verbatim.
        self.assertEqual(
            DEPARTMENT_SOURCE,
            (out / "departments" / "research" / "department.py").read_text())

    def test_export_refuses_incomplete_closure_naming_every_missing_piece(self):
        _write_research_department(self.home, with_closure=False)
        out = self.base / "bundle"
        code, stderr = _company_fails(
            self.home, "export", "research",
            "--dir", str(self.home), "--out", str(out))
        self.assertEqual(1, code)
        self.assertFalse(out.exists(),
                         "a refused export writes no bundle folder")
        # The refusal names the missing connection and strategy document.
        self.assertIn("research_store", stderr)
        self.assertIn("brief-voice.md", stderr)

    def test_export_names_missing_skill_and_agent(self):
        # Department references a skill and an agent nothing provides.
        agents = _layers(self.home)
        (agents / "departments" / "research").mkdir(parents=True)
        (agents / "departments" / "research" / "department.py").write_text(
            DEPARTMENT_SOURCE)
        (agents / "departments" / "research" / "__init__.py").write_text("")
        code, stderr = _company_fails(
            self.home, "export", "research",
            "--out", str(self.base / "b2"))
        self.assertEqual(1, code)
        self.assertIn("research_method", stderr)   # missing skill
        self.assertIn("research-analyst", stderr)   # missing agent


class ImportValidationTests(unittest.TestCase):
    """B: import validates manifest, spine pin, closure, and declaration;
    a broken bundle leaves the home untouched."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.base = Path(self._tmp.name)
        self.home = _init_home(self.base)
        self.bundle = self.base / "bundle"
        shutil.copytree(BUNDLE_FIXTURE, self.bundle)

    def tearDown(self):
        self._tmp.cleanup()

    def _layer_files(self) -> set[str]:
        return {path.relative_to(_layers(self.home)).as_posix()
                for path in _layers(self.home).rglob("*")
                if path.is_file() and "__pycache__" not in path.parts}

    def test_import_installs_fixture_bundle_into_owner_layers(self):
        receipt = _company(self.home, "import", str(self.bundle), "--json")
        self.assertEqual("research_briefs", receipt["imported"])
        self.assertEqual("1.0.0", receipt["version"])
        installed = set(receipt["installed"])
        self.assertEqual(set(json.loads(
            (self.bundle / "bundle.json").read_text())["files"]), installed)
        manifest = json.loads((self.bundle / "bundle.json").read_text())
        for rel in manifest["files"]:
            target = _layers(self.home) / rel
            self.assertTrue(target.is_file(), rel)
            self.assertEqual((self.bundle / rel).read_bytes(),
                             target.read_bytes(), rel)
        # The department is live.
        departments = _company(self.home, "departments", "--json")
        self.assertEqual(["research_briefs"], [item["id"] for item in departments])

    def test_bad_manifest_leaves_home_untouched(self):
        before = self._layer_files()
        (self.bundle / "bundle.json").write_text("{ not json")
        code, _ = _company_fails(self.home, "import", str(self.bundle))
        self.assertEqual(1, code)
        self.assertEqual(before, self._layer_files())

    def test_incompatible_spine_pin_fails_with_repair_and_installs_nothing(self):
        before = self._layer_files()
        manifest = json.loads((self.bundle / "bundle.json").read_text())
        manifest["spine_pin"] = "9.0.0"
        (self.bundle / "bundle.json").write_text(json.dumps(manifest, indent=2))
        code, stderr = _company_fails(self.home, "import", str(self.bundle))
        self.assertEqual(1, code)
        self.assertIn("spine", stderr.lower())
        self.assertIn("update", stderr.lower())  # names the repair
        self.assertEqual(before, self._layer_files(),
                         "an incompatible pin must install nothing")

    def test_patch_compatible_pin_imports(self):
        from company.runtime.config import VERSION
        manifest = json.loads((self.bundle / "bundle.json").read_text())
        major, minor, _ = VERSION.split(".")
        manifest["spine_pin"] = f"{major}.{minor}.0"
        (self.bundle / "bundle.json").write_text(json.dumps(manifest, indent=2))
        receipt = _company(self.home, "import", str(self.bundle), "--json")
        self.assertEqual("research_briefs", receipt["imported"])

    def test_incomplete_closure_fails_naming_the_missing_piece(self):
        before = self._layer_files()
        # Remove the skill folder from the bundle; the manifest still lists it.
        shutil.rmtree(self.bundle / "skills" / "research_method")
        code, stderr = _company_fails(self.home, "import", str(self.bundle))
        self.assertEqual(1, code)
        self.assertEqual(before, self._layer_files(),
                         "a broken bundle must leave the home untouched")

    def test_closure_satisfied_by_home_imports_without_bundle_copy(self):
        # The home already owns the strategy doc with different content:
        # import succeeds, and the bundle-owned path refreshes to bundle
        # bytes while a NON-bundle owner file stays untouched.
        agents = _layers(self.home)
        (agents / "strategy").mkdir(parents=True, exist_ok=True)
        (agents / "strategy" / "owner-notes.md").write_text("# owner\n")
        receipt = _company(self.home, "import", str(self.bundle), "--json")
        self.assertEqual("research_briefs", receipt["imported"])
        self.assertEqual(
            "# owner\n",
            (agents / "strategy" / "owner-notes.md").read_text(),
            "owner files outside the bundle list are never touched")

    def test_manifest_file_missing_from_bundle_refuses_whole_import(self):
        before = self._layer_files()
        (self.bundle / "skills" / "research_method" / "SKILL.md").unlink()
        code, _ = _company_fails(self.home, "import", str(self.bundle))
        self.assertEqual(1, code)
        self.assertEqual(before, self._layer_files())

    def test_bundle_claiming_spine_path_is_refused_whole(self):
        before = self._layer_files()
        manifest = json.loads((self.bundle / "bundle.json").read_text())
        manifest["files"].append("runtime/engine.py")
        (self.bundle / "runtime").mkdir()
        (self.bundle / "runtime" / "engine.py").write_text("# hijack\n")
        (self.bundle / "bundle.json").write_text(json.dumps(manifest, indent=2))
        code, stderr = _company_fails(self.home, "import", str(self.bundle))
        self.assertEqual(1, code)
        self.assertIn("owner layers", stderr)
        self.assertEqual(before, self._layer_files(),
                         "a bundle claiming spine paths installs nothing")
        # The vendored spine file still carries the home's own bytes.
        self.assertNotEqual(
            "# hijack\n",
            (_layers(self.home) / "runtime" / "engine.py").read_text(),
            "the vendored spine is never overwritten by an import")

    def test_bundle_claiming_layer_root_spine_files_is_refused(self):
        # The vendored spine keeps __init__.py/core.py at layer roots;
        # a bundle may never own those, but departments/<id>/__init__.py
        # (inside a department package) is legitimate bundle content.
        original = (self.bundle / "bundle.json").read_text()
        for claimed in ("departments/__init__.py", "skills/core.py",
                        "connections/__init__.py"):
            before = self._layer_files()
            manifest = json.loads(original)
            manifest["files"].append(claimed)
            target = self.bundle / claimed
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("# hijack\n")
            (self.bundle / "bundle.json").write_text(
                json.dumps(manifest, indent=2))
            code, _ = _company_fails(self.home, "import", str(self.bundle))
            self.assertEqual(1, code, claimed)
            self.assertEqual(before, self._layer_files(), claimed)
            target.unlink()
        # Sanity: the pristine bundle still imports, and the fixture's
        # department package __init__.py is legal bundle content.
        (self.bundle / "bundle.json").write_text(original)
        receipt = _company(self.home, "import", str(self.bundle), "--json")
        self.assertIn("departments/research_briefs/__init__.py",
                      receipt["installed"])

    def test_broken_declaration_refuses_import(self):
        before = self._layer_files()
        declaration = (self.bundle / "departments" / "research_briefs"
                        / "department.py")
        declaration.write_text("import does_not_exist_anywhere\n")
        code, stderr = _company_fails(self.home, "import", str(self.bundle))
        self.assertEqual(1, code)
        self.assertIn("import", stderr.lower())
        self.assertEqual(before, self._layer_files(),
                         "a declaration that fails the live contracts "
                         "installs nothing")


class InstallSurfaceTests(unittest.TestCase):
    """C: import lands only in the six owner layers; idempotent; owner
    files outside the list survive; conflicting non-bundle content is
    never overwritten."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.base = Path(self._tmp.name)
        self.home = _init_home(self.base)
        self.bundle = self.base / "bundle"
        shutil.copytree(BUNDLE_FIXTURE, self.bundle)

    def tearDown(self):
        self._tmp.cleanup()

    def _all_home_files(self) -> dict[str, bytes]:
        snapshot = {}
        for path in sorted(self.home.rglob("*")):
            if not path.is_file() or "__pycache__" in path.parts:
                continue
            snapshot[path.relative_to(self.home).as_posix()] = path.read_bytes()
        return snapshot

    def test_import_never_touches_spine_hosts_or_settings(self):
        _company(self.home, "import", str(self.bundle), "--json")
        manifest = json.loads((self.bundle / "bundle.json").read_text())
        bundle_paths = set(manifest["files"])
        agents = self.home / ".agents"
        # The vendored spine under .agents/company outside the owner
        # layers is byte-identical to the pristine fresh home.
        pristine = _init_home(self.base, "pristine")
        for spine in ("runtime/engine.py", "commands/goal_runtime.py",
                      "layout.py", "state/database.py", "__main__.py"):
            self.assertEqual(
                (pristine / ".agents" / "company" / spine).read_bytes(),
                (agents / "company" / spine).read_bytes(), spine)
        # Host trees and settings are untouched.
        for host in (".opencode", ".codex", ".claude"):
            for path in (self.home / host).rglob("*"):
                if path.is_file():
                    self.assertEqual(
                        (pristine / host /
                         path.relative_to(self.home / host)).read_bytes(),
                        path.read_bytes(), str(path))
        for rel in ("opencode.json", "AGENTS.md", "CLAUDE.md"):
            self.assertEqual((pristine / rel).read_bytes(),
                             (self.home / rel).read_bytes(), rel)
        # Exactly the manifest paths landed under .agents/company.
        landed = {path.relative_to(agents / "company").as_posix()
                  for path in (agents / "company").rglob("*")
                  if path.is_file() and "__pycache__" not in path.parts}
        bundle_owned_under_company = {
            rel for rel in bundle_paths}
        self.assertTrue(bundle_owned_under_company <= landed)

    def test_idempotent_reimport_refreshes_bundle_owned_paths(self):
        _company(self.home, "import", str(self.bundle), "--json")
        # Diverge a bundle-owned file, then re-import: bundle bytes win.
        target = _layers(self.home) / "skills" / "research_method" / "SKILL.md"
        target.write_text("# tampered\n")
        _company(self.home, "import", str(self.bundle), "--json")
        self.assertEqual(
            (self.bundle / "skills" / "research_method" / "SKILL.md")
            .read_text(), target.read_text(),
            "re-import refreshes bundle-owned paths to bundle bytes")

    def test_owner_files_outside_bundle_list_survive_reimport(self):
        agents = _layers(self.home)
        _company(self.home, "import", str(self.bundle), "--json")
        (agents / "departments" / "owner-custom").mkdir()
        (agents / "departments" / "owner-custom" / "department.py").write_text(
            "# owner department\n")
        (agents / "strategy" / "owner-plan.md").write_text("# owner plan\n")
        _company(self.home, "import", str(self.bundle), "--json")
        self.assertEqual(
            "# owner department\n",
            (agents / "departments" / "owner-custom" / "department.py")
            .read_text())
        self.assertEqual(
            "# owner plan\n",
            (agents / "strategy" / "owner-plan.md").read_text())

    def test_conflicting_non_bundle_content_is_never_overwritten(self):
        # An owner file at a path the bundle does NOT list: import never
        # touches it even when a same-named folder exists in the bundle.
        agents = _layers(self.home)
        (agents / "skills" / "owner-skill").mkdir(parents=True)
        (agents / "skills" / "owner-skill" / "SKILL.md").write_text("# mine\n")
        _company(self.home, "import", str(self.bundle), "--json")
        self.assertEqual(
            "# mine\n",
            (agents / "skills" / "owner-skill" / "SKILL.md").read_text(),
            "conflicting non-bundle content is never overwritten")


class LiveGoalTests(unittest.TestCase):
    """D: after import, the Department is listed, catalog-visible, and a
    goal on one of its workflows runs end-to-end through the real loop."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.base = Path(self._tmp.name)
        self.home = _init_home(self.base)
        self.bundle = self.base / "bundle"
        shutil.copytree(BUNDLE_FIXTURE, self.bundle)

    def tearDown(self):
        self._tmp.cleanup()

    def test_imported_department_runs_a_goal_end_to_end(self):
        receipt = _company(self.home, "import", str(self.bundle), "--json")
        self.assertEqual("research_briefs", receipt["imported"])
        departments = _company(self.home, "departments", "--json")
        self.assertEqual(["research_briefs"], [item["id"] for item in departments])
        catalog = _company(self.home, "catalog", "--json")
        self.assertEqual(["research_briefs"], [item["id"] for item in catalog])
        self.assertIn("weekly-brief", catalog[0]["workflows"])
        # A goal on the department's declared metric runs through the loop.
        goal = _company(
            self.home, "goal", "create",
            "--name", "Ship one weekly research brief",
            "--owner", "research_briefs", "--metric", "briefs",
            "--target", "1", "--operator", "ge",
            "--config", '{"aggregation":"latest"}')
        goal_id = goal["id"]
        _company(self.home, "runner", "tick")
        orders = _company(self.home, "tasks", "--json")
        self.assertTrue(orders, "the loop dispatched a work order")
        order = orders[0]
        self.assertEqual("research-analyst", order["agent_id"])
        self.assertEqual("collect", order["step_id"])
        # Complete each dispatched step through the real CLI, like the host.
        while True:
            orders = _company(self.home, "tasks", "--json")
            if not orders:
                break
            order = orders[0]
            _company(self.home, "tasks", order["id"],
                     "--complete", order["agent_id"],
                     "--evidence", json.dumps([{
                         "kind": order["brief"].get("evidence_kind")
                         or "brief_delivered",
                         "payload": {"briefs": 1, "source": "test"}}]))
            _company(self.home, "runner", "tick")
        status = _company(self.home, "goal", "show", goal_id)
        self.assertEqual("achieved", status["goal"]["goal_status"],
                         "the imported department's workflow completed the "
                         "goal end to end: "
                         + str(status["goal"]))


class UpdatePreservationTests(unittest.TestCase):
    """E: ``spielos update`` on a home with an imported Department
    preserves every imported file exactly, and the department still
    imports cleanly after the update."""

    def test_update_preserves_imported_bundle_files(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            home = _init_home(base)
            bundle = base / "bundle"
            shutil.copytree(BUNDLE_FIXTURE, bundle)
            receipt = _company(home, "import", str(bundle), "--json")
            imported = {rel: (_layers(home) / rel).read_bytes()
                        for rel in receipt["installed"]}
            self.assertTrue(imported)

            self.assertEqual(0, main(["update", "--dir", str(home),
                                      "--json"]))

            # Every imported file survives byte-identical.
            for rel, content in imported.items():
                self.assertTrue((_layers(home) / rel).is_file(), rel)
                self.assertEqual(content, (_layers(home) / rel).read_bytes(), rel)
            # The department still imports cleanly after the update:
            # re-import validates the declaration against the refreshed
            # spine's live contracts and succeeds.
            again = _company(home, "import", str(bundle), "--json")
            self.assertEqual("research_briefs", again["imported"])
            departments = _company(home, "departments", "--json")
            self.assertEqual(["research_briefs"],
                             [item["id"] for item in departments])


if __name__ == "__main__":
    unittest.main()
