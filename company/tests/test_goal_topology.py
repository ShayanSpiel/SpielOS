import tempfile
import unittest
from pathlib import Path

from company.runtime.loop import Runtime


class GoalTopologyTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.runtime = Runtime(Path(self.temporary.name) / "company.sqlite")

    def tearDown(self):
        self.temporary.cleanup()

    def create_root(self):
        return self.runtime.create_goal(
            goal_id="root", name="Book a qualified call", owner_id="director",
            metric="booked_calls", operator="ge", target=1)

    def test_first_goal_becomes_the_only_primary_root(self):
        root = self.create_root()

        self.assertEqual("primary_goal", root["config"]["pursuit_kind"])
        self.assertEqual("root", root["config"]["causal_lineage"]["root_goal_id"])
        with self.assertRaisesRegex(ValueError, "already has a control root"):
            self.runtime.create_goal(
                goal_id="another-root", name="A second outcome", owner_id="director",
                metric="booked_calls", operator="ge", target=1)

    def test_child_persists_control_causal_and_completion_lineage(self):
        self.create_root()
        child = self.runtime.create_goal(
            goal_id="child", name="Qualify enough prospects", owner_id="director",
            metric="booked_calls", operator="ge", target=1, parent_id="root")

        self.assertEqual("supporting_goal", child["config"]["pursuit_kind"])
        self.assertEqual(["root"], child["config"]["supports_goal_ids"])
        self.assertEqual({
            "root_goal_id": "root", "parent_goal_id": "root",
            "purpose": "Enables the parent Goal 'Book a qualified call' (root).",
            "after_completion": (
                "Re-observe parent Goal 'Book a qualified call' (root) and choose its next bottleneck."),
        }, child["config"]["causal_lineage"])
        summary = next(item for item in self.runtime.store.goal_summaries() if item["id"] == "child")
        self.assertEqual("supporting_goal", summary["pursuit_kind"])
        self.assertEqual(["root"], summary["supports_goal_ids"])

    def test_system_improvement_requires_and_inherits_parent_lineage(self):
        self.create_root()
        task = {
            "change_kind": "repair", "owner_id": "runtime", "from_version": "1.0.0",
            "target_version": "1.0.1", "problem": "Restore topology enforcement",
            "allowed_files": ["company/runtime/alignment.py"],
            "acceptance_tests": ["python -m unittest company.tests.test_goal_topology"],
        }
        with self.assertRaisesRegex(ValueError, "system_improvement_goal requires a parent"):
            self.runtime.create_goal(
                goal_id="orphan-repair", name="Orphan repair", owner_id="system-improvement",
                metric="acceptance_tests_passed", operator="eq", target=True, config=task)

        repair = self.runtime.create_goal(
            goal_id="repair", name="Repair topology", owner_id="system-improvement",
            metric="acceptance_tests_passed", operator="eq", target=True,
            parent_id="root", config=task)
        self.assertEqual("system_improvement_goal", repair["config"]["pursuit_kind"])
        self.assertEqual(["root"], repair["config"]["supports_goal_ids"])
        self.assertEqual("root", repair["config"]["causal_lineage"]["root_goal_id"])

    def test_audit_identifies_legacy_roots_without_mutating_them(self):
        self.runtime.store.create_goal(
            goal_id="old-a", name="Old A", owner_id="director", metric="booked_calls",
            operator="ge", target=1)
        self.runtime.store.create_goal(
            goal_id="old-b", name="Old B", owner_id="director", metric="booked_calls",
            operator="ge", target=1)

        audit = self.runtime.topology_audit()

        self.assertEqual(["old-a", "old-b"], audit["root_goal_ids"])
        self.assertIsNone(audit["canonical_root_goal_id"])
        self.assertTrue(any(item["kind"] == "missing_causal_lineage"
                            for item in audit["defects"]))
        self.assertEqual(["old-a", "old-b"], audit["migration_plan"]["owner_mapping_required"])
        self.assertEqual("Old A", self.runtime.store.goal("old-a")["name"])


if __name__ == "__main__":
    unittest.main()
