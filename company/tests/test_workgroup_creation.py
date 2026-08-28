import json
import tempfile
import unittest
from pathlib import Path

from company.runtime.workgroup_install import install_workgroup, validate_workgroup_spec
from company.workgroups.registry import _group


SPEC = {
    "id": "research",
    "description": "Research capability",
    "metrics": ["research_record"],
    "evidence_metrics": {"research_record": ["research_record"]},
    "workers": [{
        "id": "researcher",
        "description": "Finds verified source material",
        "workbook": ["source-check"],
        "workkit": ["web-research"],
        "produces": ["research_record"],
        "workflows": [{
            "id": "source-research",
            "description": "Produce one verified research record",
            "evidence": ["research_record"],
            "worksteps": [{"id": "research", "kind": "employee",
                           "produces": ["research_record"]}],
        }],
    }],
}


class WorkgroupCreationTests(unittest.TestCase):
    def test_validated_package_installs_as_worker_owned_workflow(self):
        self.assertEqual(validate_workgroup_spec(SPEC), [])
        with tempfile.TemporaryDirectory() as directory:
            receipt = install_workgroup(SPEC, root=Path(directory))
            self.assertEqual(receipt["workers"], ["researcher"])
            loaded = _group(Path(directory) / "research")
            self.assertEqual(loaded.workers[0].workflows[0].id, "source-research")
            workflow = json.loads((Path(directory) / "research" / "workers" / "researcher"
                                   / "workflows" / "source-research.json").read_text())
            self.assertEqual(workflow["worksteps"][0]["worker_id"], "researcher")
