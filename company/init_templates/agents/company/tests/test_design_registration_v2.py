"""Design 3.4.0 registry regression (goal-design-register-v3-20260818).

Asserts the four creative-variety-v2 archetypes (loop-rail, heartbeat,
department-map, agent-brief) are registered in templates/registry.json, that
DesignDepartment.version has advanced to 3.4.0, and that every new archetype
points at an existing template file (registry validation mirrors
test_harness_structure.TemplateRegistryTests.file checks for the new set).
"""

import json
import unittest
from pathlib import Path

from company.departments.design.department import DesignDepartment

DESIGN_ROOT = Path(__file__).parents[1] / "departments" / "design"
REGISTRY_PATH = DESIGN_ROOT / "templates" / "registry.json"

# (archetype id, kind, template file relative to the design templates dir)
NEW_ARCHETYPES = (
    ("loop-rail", "shorts", "video/loop-rail.html"),
    ("heartbeat", "shorts", "video/heartbeat.html"),
    ("department-map", "social", "social/department-map.html"),
    ("agent-brief", "social", "social/agent-brief.html"),
)


class DesignRegistrationV2Tests(unittest.TestCase):
    """The creative-variety-v2 archetypes are registered and file-backed (v3.4.0)."""

    def setUp(self):
        self.registry = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))

    def test_registry_declares_the_four_new_archetype_ids(self):
        ids = [entry["id"] for entry in self.registry["archetypes"]]
        for archetype_id, _, _ in NEW_ARCHETYPES:
            self.assertIn(archetype_id, ids,
                          f"{archetype_id} must be a registered archetype")

    def test_design_department_version_is_3_4_0(self):
        self.assertEqual("3.4.0", DesignDepartment.version)

    def test_each_new_archetype_points_at_an_existing_template_file(self):
        for archetype_id, kind, file in NEW_ARCHETYPES:
            with self.subTest(archetype=archetype_id):
                entry = next(item for item in self.registry["archetypes"]
                             if item["id"] == archetype_id)
                self.assertEqual(kind, entry["kind"])
                self.assertEqual(file, entry["file"])
                self.assertTrue(
                    (DESIGN_ROOT / "templates" / file).is_file(),
                    f"{archetype_id}: missing template {file}")


if __name__ == "__main__":
    unittest.main()