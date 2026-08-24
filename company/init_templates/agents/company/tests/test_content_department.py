import json
import unittest
from pathlib import Path

from company.departments.campaign_contract import LINK_IN_BIO, SPIELOS_REMINDER, validate_campaign


ROOT = Path(__file__).resolve().parents[2]


class LeanContentDepartmentTests(unittest.TestCase):
    def manifests(self):
        # batch-02/03 approved manifests were archived; artifacts are
        # gitignored, so these fixtures only exist on the owner machine.
        manifests = []
        for number in (2, 3):
            for base in ("", "_archive/fresh-start-20260819/"):
                path = (ROOT / f".spielos/artifacts/content-growth-20260812/{base}"
                        f"batch-{number:02d}/campaign-approved.json")
                if path.is_file():
                    manifests.append(json.loads(path.read_text()))
                    break
            else:
                self.skipTest(f"local artifact batch-{number:02d}/campaign-approved.json not present")
        return manifests

    def test_batch_two_uses_the_lean_strategy_contract(self):
        for manifest in self.manifests():
            self.assertEqual(validate_campaign(manifest, manifest["phase"]), [])
            for item in manifest["items"]:
                self.assertEqual(item["one_idea"], item["brief"]["one_idea"])
                self.assertEqual(
                    set(item["brief"]),
                    {"reader", "customer_moment", "one_idea", "desired_result", "proof"},
                )

    def test_platform_copy_is_native_and_reminder_is_fifth_only(self):
        for manifest in self.manifests():
            for item in manifest["items"]:
                threads = item["renditions"]["threads"]
                youtube = item["renditions"]["youtube"]
                self.assertNotIn(r"\n", threads["copy"])
                self.assertNotIn("utm_", youtube["copy"].lower())
                self.assertNotIn("http", youtube["copy"].lower())
                if youtube["destination"]:
                    self.assertIn(LINK_IN_BIO, youtube["copy"])
                self.assertEqual(item["sequence"] == 5, SPIELOS_REMINDER in threads["copy"])
                self.assertEqual(item["sequence"] == 5, SPIELOS_REMINDER in youtube["copy"])


if __name__ == "__main__":
    unittest.main()
