"""The executable SpielOS1 source and shipped init template are one contract."""

from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "company"
TEMPLATE = SOURCE / "init_templates" / "agents" / "company"


class TemplateParityTests(unittest.TestCase):
    def test_executable_spine_matches_the_shipped_template(self):
        if not TEMPLATE.is_dir():
            self.skipTest("vendored harness has no packaging template tree")
        relative = [Path("__main__.py"), Path("agents/__init__.py")]
        relative.extend(path.relative_to(SOURCE) for path in
                        sorted((SOURCE / "runtime").glob("*.py")))
        relative.append(Path("departments/outbound/email_workflow.py"))
        relative.extend(path.relative_to(SOURCE) for path in
                        sorted((SOURCE / "departments/outbound/workflows/email").glob("*.py")))
        mismatches = []
        for item in relative:
            shipped = TEMPLATE / item
            if not shipped.is_file() or (SOURCE / item).read_bytes() != shipped.read_bytes():
                mismatches.append(item.as_posix())
        self.assertEqual([], mismatches,
                         "sync executable source changes into init_templates: "
                         + ", ".join(mismatches))


if __name__ == "__main__":
    unittest.main()
