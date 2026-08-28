"""Destination and user-layer invariants for install/add/update commands."""

from __future__ import annotations

import contextlib
import io
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from company.__main__ import main
from company.runtime.bootstrap import scaffold
from company.runtime.export import add_department, refresh_home
from company.runtime.onboard import run_init


class InstallDestinationTests(unittest.TestCase):
    def test_fresh_init_seeds_generic_strategy_but_no_state_or_departments(self):
        with tempfile.TemporaryDirectory() as raw:
            home = Path(raw) / "selected-home"
            scaffold(home, force=True, minimal=True)

            self.assertTrue((home / ".agents/company/strategy/README.md").is_file())
            self.assertFalse((home / ".spielos/state/company.sqlite").exists())
            departments = home / ".agents/company/departments"
            installed = [path.name for path in departments.iterdir()
                         if path.is_dir() and not path.name.startswith(("_", "."))]
            self.assertEqual([], installed)

    def test_verified_cli_init_still_leaves_no_database(self):
        with tempfile.TemporaryDirectory() as raw:
            home = Path(raw) / "selected-home"
            with contextlib.redirect_stdout(io.StringIO()):
                result = run_init(dir=str(home), force=True, minimal=True,
                                  assume_yes=True, as_json=True)

            self.assertEqual(0, result)
            self.assertFalse((home / ".spielos/state/company.sqlite").exists())

    def test_forced_init_preserves_existing_user_layer(self):
        with tempfile.TemporaryDirectory() as raw:
            home = (Path(raw) / "home").resolve()
            scaffold(home, force=True, minimal=True)
            strategy = home / ".agents/company/strategy/voice.md"
            strategy.write_text("owner strategy\n")
            asset = home / ".agents/company/assets/proof.md"
            asset.write_text("owner proof\n")
            department = home / ".agents/company/departments/custom/department.py"
            department.parent.mkdir(parents=True)
            department.write_text("owner department\n")
            employee = home / ".agents/company/agents/installed/custom.json"
            employee.parent.mkdir(parents=True, exist_ok=True)
            employee.write_text('{"id":"custom"}\n')

            scaffold(home, force=True, minimal=True)

            self.assertEqual("owner strategy\n", strategy.read_text())
            self.assertEqual("owner proof\n", asset.read_text())
            self.assertEqual("owner department\n", department.read_text())
            self.assertEqual('{"id":"custom"}\n', employee.read_text())

    def test_init_refuses_a_destination_inside_a_virtualenv(self):
        with tempfile.TemporaryDirectory() as raw:
            venv = Path(raw) / "unrelated-python-env"
            venv.mkdir()
            (venv / "pyvenv.cfg").write_text("home = /usr/bin\n")
            selected = venv / "project"

            with self.assertRaisesRegex(ValueError, "virtualenv"):
                scaffold(selected, force=True, minimal=True)

            self.assertFalse((selected / ".agents").exists())

    def test_refresh_uses_exact_selected_home_and_preserves_strategy(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            selected = root / "selected"
            decoy = root / "decoy"
            scaffold(selected, force=True, minimal=True)
            scaffold(decoy, force=True, minimal=True)
            selected_strategy = selected / ".agents/company/strategy/voice.md"
            decoy_strategy = decoy / ".agents/company/strategy/voice.md"
            selected_strategy.write_text("selected strategy\n")
            decoy_strategy.write_text("decoy strategy\n")
            previous = Path.cwd()
            try:
                os.chdir(decoy)
                receipt = refresh_home(target=selected)
            finally:
                os.chdir(previous)

            self.assertGreater(receipt["refreshed_files"], 0)
            self.assertEqual("selected strategy\n", selected_strategy.read_text())
            self.assertEqual("decoy strategy\n", decoy_strategy.read_text())

    def test_refresh_does_not_walk_from_selected_child_to_parent_home(self):
        with tempfile.TemporaryDirectory() as raw:
            parent = Path(raw) / "home"
            scaffold(parent, force=True, minimal=True)
            selected_child = parent / "not-a-home"
            selected_child.mkdir()

            with self.assertRaisesRegex(ValueError, "no harness home"):
                refresh_home(target=selected_child)

    def test_add_installs_only_in_explicit_selected_home(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            selected = root / "selected"
            decoy = root / "decoy"
            scaffold(selected, force=True, minimal=True)
            scaffold(decoy, force=True, minimal=True)
            previous = Path.cwd()
            try:
                os.chdir(decoy)
                add_department("content", home=selected)
            finally:
                os.chdir(previous)

            self.assertTrue(
                (selected / ".agents/company/departments/content/department.py").is_file())
            self.assertFalse(
                (decoy / ".agents/company/departments/content").exists())

    def test_department_install_cli_passes_selected_home_roots(self):
        with tempfile.TemporaryDirectory() as raw:
            home = (Path(raw) / "home").resolve()
            scaffold(home, force=True, minimal=True)
            receipt = {"id": "demo", "version": "1.0.0", "ok": True}
            with mock.patch("company.runtime.install.install_department",
                            return_value=receipt) as install:
                with contextlib.redirect_stdout(io.StringIO()):
                    result = main([
                        "department", "install", "--dir", str(home),
                        "--spec", '{"id":"demo","purpose":"demo","metrics":["items"]}',
                    ])

            self.assertEqual(0, result)
            self.assertEqual(
                home / ".agents/company/departments",
                install.call_args.kwargs["root"])
            self.assertEqual(
                home / ".agents/company/agents/installed",
                install.call_args.kwargs["agents_root"])

    def test_refresh_cli_passes_exact_dir(self):
        with tempfile.TemporaryDirectory() as raw:
            selected = Path(raw) / "selected"
            with mock.patch("company.runtime.export.refresh_home",
                            return_value={"refreshed_files": 0, "preserved": []}) as refresh:
                with contextlib.redirect_stdout(io.StringIO()):
                    result = main(["refresh", "--dir", str(selected)])
            self.assertEqual(0, result)
            refresh.assert_called_once_with(force=True, target=str(selected))

    def test_installer_script_is_valid_posix_shell(self):
        root = Path(__file__).resolve().parents[2]
        result = subprocess.run(
            ["sh", "-n", str(root / "install.sh")],
            text=True, capture_output=True, check=False)
        self.assertEqual(0, result.returncode, result.stderr)


if __name__ == "__main__":
    unittest.main()
