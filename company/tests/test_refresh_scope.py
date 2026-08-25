"""Refresh scope guarantees: spine-only writes, user layer byte-preserved.

Answers three questions with executable proof rather than prose:
1. Does refresh ever touch departments / strategy / assets / config?
2. Does it write anything outside the home it was pointed at?
3. Do vendored departments survive byte-identical?
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from .test_template_parity import ROOT


def _tree(root: Path) -> dict[str, bytes]:
    return {
        str(p.relative_to(root)): p.read_bytes()
        for p in sorted(root.rglob("*"))
        if p.is_file() and "__pycache__" not in p.parts and p.suffix != ".pyc"
    }


class RefreshScopeTests(unittest.TestCase):
    def test_refresh_replaces_spine_only_and_preserves_user_layer(self):
        from company.runtime.bootstrap import scaffold
        from company.runtime.export import refresh_home

        allowed_prefixes = (".agents/", ".opencode/", ".codex/")
        with tempfile.TemporaryDirectory() as raw:
            home = Path(raw).resolve()
            scaffold(home, force=True, minimal=True, departments=["outbound"])

            # --- user layer: sentinels refresh must never touch ---------
            dept = home / ".agents/company/departments/mydept"
            dept.mkdir(parents=True)
                # noqa-spacing: keep bytes simple
            (dept / "department.py").write_text(
                '"""Custom department."""\nversion = "9.9.9"\n')
            outbound_py = home / ".agents/company/departments/outbound/department.py"
            strategy = home / ".agents/company/strategy"
            strategy_files = {p: p.read_bytes() for p in strategy.rglob("*")
                              if p.is_file()}
            assets_sentinel = home / ".agents/company/assets/keep-me.md"
            assets_sentinel.write_text("user asset\n")
            custom_config = '{\n  "custom": true\n}\n'
            (home / "opencode.json").write_text(custom_config)

            before = _tree(home)

            # Refresh runs exactly as a home would resolve its root.
            with mock.patch("company.runtime.paths.find_project_root",
                            return_value=home):
                receipt = refresh_home(force=True)

            self.assertGreater(receipt["refreshed_files"], 0)

            after = _tree(home)

            # 1. Nothing deleted.
            vanished = set(before) - set(after)
            self.assertEqual([], sorted(vanished))

            # 2. Every write landed inside the spine prefixes.
            changed = [rel for rel in after
                       if before.get(rel) != after[rel]]
            outside = [rel for rel in changed
                       if not rel.startswith(allowed_prefixes)]
            self.assertEqual(
                [], outside,
                f"refresh wrote outside the spine: {outside}")

            # 3. User layer is byte-identical.
            self.assertIn('version = "9.9.9"',
                          (dept / "department.py").read_text())
            self.assertEqual(custom_config,
                             (home / "opencode.json").read_text())
            self.assertEqual(b"user asset\n", assets_sentinel.read_bytes())
            for path, data in strategy_files.items():
                self.assertEqual(data, path.read_bytes(), str(path))
            self.assertEqual(outbound_py.read_bytes(),
                             before[str(outbound_py.relative_to(home))])

    def test_refresh_refuses_homes_without_a_spine(self):
        from company.runtime.export import refresh_home

        with tempfile.TemporaryDirectory() as raw:
            home = Path(raw).resolve()
            (home / ".agents").mkdir()
            with mock.patch("company.runtime.paths.find_project_root",
                            return_value=home):
                with self.assertRaises(ValueError):
                    refresh_home(force=True)


if __name__ == "__main__":
    unittest.main()
