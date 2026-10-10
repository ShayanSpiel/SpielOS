"""Repository roles reject runtime installation and database creation before writes."""

import json
import tempfile
import unittest
from pathlib import Path

from company.runtime.paths import validate_home_destination
from company.state import Database
from company.runtime.service import RunnerService


class RepositoryBoundaryTests(unittest.TestCase):
    def test_restricted_roles_reject_nested_install_and_state(self):
        for role in ("source", "website"):
            with self.subTest(role=role), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                (root / ".spielos-boundary.json").write_text(json.dumps({"role": role}))
                with self.assertRaisesRegex(ValueError, role):
                    validate_home_destination(root / "nested")
                with self.assertRaisesRegex(ValueError, role):
                    Database(root / ".spielos/state/company.sqlite")
                with self.assertRaisesRegex(ValueError, role):
                    RunnerService(root, root / ".spielos/state/company.sqlite")
                self.assertFalse((root / ".spielos").exists())

    def test_home_role_allows_database_creation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / ".spielos-boundary.json").write_text('{"role":"home"}')
            self.assertEqual(validate_home_destination(root), root.resolve())
            database = Database(root / ".spielos/state/company.sqlite")
            with database.connect() as connection:
                self.assertEqual(connection.execute("PRAGMA integrity_check").fetchone()[0], "ok")

    def test_symlink_cannot_bypass_restricted_role(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            website = root / "website"
            website.mkdir()
            (website / ".spielos-boundary.json").write_text('{"role":"website"}')
            alias = root / "alias"
            alias.symlink_to(website, target_is_directory=True)
            with self.assertRaises(ValueError):
                validate_home_destination(alias / "nested")

    def test_nested_home_marker_cannot_override_website_boundary(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / ".spielos-boundary.json").write_text('{"role":"website"}')
            nested = root / "nested"
            nested.mkdir()
            (nested / ".spielos-boundary.json").write_text('{"role":"home"}')
            with self.assertRaises(ValueError):
                validate_home_destination(nested)

    def test_shipping_profile_contains_no_owner_seed(self):
        company = Path(__file__).resolve().parents[1]
        profile = company / "assets/company-profile.md"
        template = company / "init_templates/agents/company/assets/company-profile.md"
        self.assertEqual(profile.read_bytes(), template.read_bytes())
        self.assertNotIn("Founder:", profile.read_text())
        self.assertNotIn("Primary conversion paths:", profile.read_text())
