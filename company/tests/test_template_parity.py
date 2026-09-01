from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


class TemplateParityTests(unittest.TestCase):
    def test_executable_runtime_spine_is_byte_identical(self):
        relative = (
            "ARCHITECTURE.md",
            "README.md",
            "__main__.py",
            "__init__.py",
            "runtime/artifacts.py",
            "runtime/agent_compile.py",
            "runtime/bootstrap.py",
            "runtime/friction.py",
            "runtime/migration.py",
            "runtime/catalog.py",
            "runtime/store.py",
            "runtime/memory.py",
            "runtime/memory_capture.py",
            "runtime/context.py",
            "commands/__init__.py",
            "commands/goal_runtime.py",
            "capabilities/__init__.py",
            "capabilities/core.py",
            "hosts/core.py",
            "runtime/loop.py",
            "runtime/interpreter.py",
            "runtime/__init__.py",
            "runtime/engine.py",
            "state/__init__.py",
            "state/database.py",
            "state/migration.py",
            "goals/__init__.py",
            "goals/core.py",
            "context/__init__.py",
            "context/core.py",
            "resolution/__init__.py",
            "resolution/core.py",
            "workflows/__init__.py",
            "workflows/core.py",
            "work_orders/__init__.py",
            "work_orders/core.py",
            "evidence/__init__.py",
            "evidence/records.py",
            "memory/__init__.py",
            "memory/records.py",
            "observability/__init__.py",
            "observability/read_model.py",
            "hosts/__init__.py",
            "hosts/core.py",
            "agents/__init__.py",
            "agents/core.py",
            "skills/__init__.py",
            "skills/core.py",
            "skills/director/SKILL.md",
            "skills/system-improvement/SKILL.md",
            "connections/__init__.py",
            "connections/core.py",
            "departments/__init__.py",
            "departments/core.py",
        )
        shipped = ROOT / "company/init_templates/agents/company"
        source = ROOT / "company"
        for path in relative:
            self.assertEqual((source / path).read_bytes(), (shipped / path).read_bytes(), path)



if __name__ == "__main__":
    unittest.main()
