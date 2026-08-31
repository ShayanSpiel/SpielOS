import tempfile
import unittest
from pathlib import Path

from company.runtime.install import install_department, validate_department_spec


SPEC = {
    "id": "research",
    "description": "Research capability",
    "metrics": ["research_records"],
    "evidence_metrics": {"research_records": ["research_record"]},
    "agent_ids": ["researcher"],
    "agents": [{
        "id": "researcher", "description": "Finds verified source material",
        "skill_ids": [], "permissions": ["read_public_sources", "write_evidence"],
        "produces": ["research_record"],
    }],
    "workflows": [{
        "id": "source-research",
        "description": "Produce one verified research record",
        "steps": ["research"], "agents": ["researcher"],
        "evidence": ["research_record"],
        "graph": [{"id": "research", "kind": "agent",
                   "agent_id": "researcher", "produces": ["research_record"]}],
    }],
}


class DepartmentCreationTests(unittest.TestCase):
    def test_validated_package_installs_as_agent_owned_workflow(self):
        self.assertEqual([], validate_department_spec(SPEC))
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            receipt = install_department(
                SPEC, root=root / "departments",
                agents_root=root / "agents/installed")
            self.assertTrue(receipt["ok"])
            self.assertEqual(["researcher"], receipt["agents"])
            self.assertTrue((root / "departments/research/department.py").is_file())
            self.assertTrue((root / "agents/installed/researcher.json").is_file())


if __name__ == "__main__":
    unittest.main()
