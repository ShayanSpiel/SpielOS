from __future__ import annotations

import unittest
from pathlib import Path


class MigrationGuidancePackagingTests(unittest.TestCase):
    def setUp(self):
        self.company = Path(__file__).resolve().parents[1]
        self.shipped = self.company / "init_templates" / "agents" / "company"

    def test_migration_skill_is_shipped_byte_identically(self):
        source = self.company / "skills" / "migration-planning" / "SKILL.md"
        shipped = self.shipped / "skills" / "migration-planning" / "SKILL.md"
        self.assertTrue(source.is_file())
        self.assertEqual(source.read_bytes(), shipped.read_bytes())

    def test_director_routes_migration_detail_to_dedicated_skill(self):
        director = (self.company / "skills" / "director" / "SKILL.md").read_text()
        self.assertIn("skills/migration-planning/SKILL.md", director)
        self.assertIn("requested plan from authorization to execute", director)
        self.assertLess(director.index("## Communication") - director.index("## Fresh-home migration"), 1200)

    def test_skill_preserves_plan_only_and_arbitrary_source_contracts(self):
        guidance = (self.company / "skills" / "migration-planning" / "SKILL.md").read_text()
        normalized = " ".join(guidance.split())
        required = (
            "planning never authorizes execution",
            "any collection",
            "never fabricate an inventory",
            "100% ledger reconciliation",
            "If the owner excludes Goals, omit them completely",
            "Deployment always remains a separate external approval",
        )
        for contract in required:
            self.assertIn(contract, normalized)


if __name__ == "__main__":
    unittest.main()
