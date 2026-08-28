import tempfile
import unittest
from pathlib import Path

from company.runtime.loop import Runtime
from company.runtime.models import GoalHandler, GoalStatus, RunStatus, Stage, StageResult


class QuietHandler(GoalHandler):
    id = "quiet"

    def observe(self, ctx):
        return StageResult("collect", {})

    def decide(self, ctx, observation):
        return StageResult("wait", {}, RunStatus.WAITING, Stage.OBSERVE)

    def act(self, ctx, decision):
        raise AssertionError("not reached")

    def evaluate(self, ctx, action_result):
        raise AssertionError("not reached")


class GoalSupportGraphTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.runtime = Runtime(Path(self.temp.name) / "state.sqlite",
                               {"quiet": QuietHandler()})

    def goal(self, goal_id, **config):
        return self.runtime.create_goal(
            goal_id=goal_id, name=goal_id, owner_id="quiet",
            metric="done", operator="eq", target=True, config=config)

    def test_one_control_parent_and_multiple_support_targets(self):
        root = self.goal("root", pursuit_kind="primary_goal")
        other = self.goal("other")
        branch = self.runtime.create_goal(
            goal_id="branch", name="branch", owner_id="quiet",
            metric="done", operator="eq", target=True, parent_id=root["id"],
            config={"pursuit_kind": "supporting_goal",
                    "supports_goal_ids": [root["id"], other["id"]]})
        self.assertEqual(root["id"], branch["parent_id"])
        links = self.runtime.company_snapshot()["support_links"]
        self.assertEqual({("branch", "root"), ("branch", "other")},
                         {(item["goal_id"], item["supports_goal_id"]) for item in links})

    def test_support_cycles_are_rejected(self):
        self.goal("a")
        self.goal("b", supports_goal_ids=["a"])
        with self.assertRaisesRegex(ValueError, "creates a cycle"):
            self.runtime.link_support("a", "b")

    def test_material_source_change_wakes_supported_goal_without_achieving_it(self):
        target = self.goal("target")
        source = self.goal("source", supports_goal_ids=[target["id"]])
        cycle = self.runtime.store.cycle(target["id"])
        self.runtime.store.update_cycle(
            cycle["id"], stage="OBSERVE", step="wait", run_status="waiting",
            resume_at=None, data={})
        self.runtime.set_goal_status(source["id"], GoalStatus.PAUSED)
        self.assertEqual("idle", self.runtime.store.cycle(target["id"])["run_status"])
        self.assertEqual("active", self.runtime.store.goal(target["id"])["goal_status"])


if __name__ == "__main__":
    unittest.main()
