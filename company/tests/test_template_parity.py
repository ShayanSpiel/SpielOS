from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


class TemplateParityTests(unittest.TestCase):
    def test_executable_runtime_spine_is_byte_identical(self):
        relative = (
            "__main__.py",
            "runtime/artifacts.py",
            "runtime/friction.py",
            "runtime/migration.py",
            "runtime/catalog.py",
            "runtime/store.py",
            "runtime/memory.py",
            "runtime/memory_capture.py",
            "runtime/context.py",
            "runtime/loop.py",
            "runtime/interpreter.py",
        )
        shipped = ROOT / "company/init_templates/agents/company"
        source = ROOT / "company"
        for path in relative:
            self.assertEqual((source / path).read_bytes(), (shipped / path).read_bytes(), path)



if __name__ == "__main__":
    unittest.main()
