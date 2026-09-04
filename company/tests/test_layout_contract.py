"""Canonical layout contract: audit rules for every owner-named drift case."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from company.layout import audit, layout_summary


def _company(root: Path) -> Path:
    path = root / ".agents" / "company"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _kinds(result: dict) -> set[str]:
    return {item["kind"] for item in result["violations"]}


def _paths(result: dict) -> set[str]:
    return {item["path"] for item in result["violations"]}


class LayoutAuditTests(unittest.TestCase):
    def test_clean_home_has_no_violations(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            company = _company(root)
            for name in ("departments", "skills", "capabilities",
                         "connections", "strategy", "agents"):
                (company / name).mkdir()
            (company / "departments" / "seo").mkdir(parents=True)
            (company / "departments" / "seo" / "department.py").write_text("")
            (company / "skills" / "youtube").mkdir(parents=True)
            (company / "skills" / "youtube" / "SKILL.md").write_text("")
            (company / "skills" / "core.py").write_text("")  # vendored spine
            (company / "departments" / "__init__.py").write_text("")
            (company / "capabilities" / "browser").mkdir(parents=True)
            (company / "capabilities" / "browser" / "run.py").write_text("")
            (company / "connections" / "registry.py").write_text("")
            (company / "strategy" / "plan.md").write_text("g")
            (company / "agents" / "installed").mkdir(parents=True)
            (company / "agents" / "installed" / ".gitkeep").write_text("")
            (company / "cli.py").write_text("")  # vendored root file
            result = audit(root)
            self.assertEqual([], result["violations"])
            self.assertTrue(result["ok"])
            self.assertEqual(
                {"departments": 1, "skills": 1, "capabilities": 1,
                 "connections": 1, "strategy": 1, "agents_installed": 0},
                result["layers"])

    def test_invented_top_level_folder_is_flagged(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            company = _company(root)
            (company / "_lib").mkdir()
            result = audit(root)
            self.assertEqual({"invented_layer", "reserved_namespace"},
                             _kinds(result))
            self.assertIn(".agents/company/_lib", _paths(result))

    def test_invented_root_file_is_flagged(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            company = _company(root)
            (company / "declarations.py").write_text("")
            result = audit(root)
            self.assertEqual({"invented_root_file"}, _kinds(result))
            self.assertIn(".agents/company/declarations.py", _paths(result))

    def test_underscore_folders_inside_departments_are_flagged(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            company = _company(root)
            (company / "departments" / "seo").mkdir(parents=True)
            (company / "departments" / "seo" / "_strategy").mkdir()
            (company / "departments" / "seo" / "department.py").write_text("")
            result = audit(root)
            self.assertEqual({"reserved_namespace"}, _kinds(result))
            self.assertIn(
                ".agents/company/departments/seo/_strategy", _paths(result))

    def test_department_without_declaration_is_flagged(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            company = _company(root)
            (company / "departments" / "content").mkdir(parents=True)
            result = audit(root)
            self.assertEqual({"department_without_declaration"}, _kinds(result))
            self.assertIn(".agents/company/departments/content", _paths(result))
            self.assertIn("department.py",
                          result["violations"][0]["fix"])

    def test_stray_department_file_is_flagged(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            company = _company(root)
            (company / "departments").mkdir()
            (company / "departments" / "keywords.py").write_text("")
            result = audit(root)
            self.assertEqual({"stray_department_file"}, _kinds(result))
    def test_skill_drift_is_flagged(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            company = _company(root)
            skills = company / "skills"
            skills.mkdir()
            (skills / "director").mkdir()
            (skills / "director" / "SKILL.md").write_text("")  # reserved
            (skills / "noskill").mkdir()  # no SKILL.md
            (skills / "stray.py").write_text("")  # not a folder
            result = audit(root)
            self.assertEqual({"reserved_name", "skill_without_definition",
                             "skill_not_folder"}, _kinds(result))
            self.assertIn(".agents/company/skills/director", _paths(result))

    def test_department_reserved_name_is_flagged(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            company = _company(root)
            (company / "departments" / "director").mkdir(parents=True)
            (company / "departments" / "director" / "department.py").write_text("")
            result = audit(root)
            self.assertEqual({"reserved_name"}, _kinds(result))

    def test_missing_agents_tree_is_ok(self):
        with tempfile.TemporaryDirectory() as directory:
            result = audit(Path(directory))
            self.assertTrue(result["ok"])
            self.assertEqual([], result["violations"])

    def test_layout_summary_lines(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.assertEqual("ok", layout_summary(root))
            _company(root)
            (root / ".agents" / "company" / "declarations.py").write_text("")
            self.assertIn("1 violation", layout_summary(root))
            self.assertIn("company layout", layout_summary(root))


if __name__ == "__main__":
    unittest.main()
