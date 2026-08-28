import tempfile
import unittest
from pathlib import Path

from company.runtime.loop import Runtime
from company.runtime.models import GoalHandler, RunStatus, Stage, StageResult
from company.runtime.runner import Runner


class PriorityHandler(GoalHandler):
    id = "priority"

    def observe(self, ctx):
        return StageResult("collect", {
            "directives": [item["text"] for item in ctx.directives]})

    def decide(self, ctx, observation):
        return StageResult("wait", observation, RunStatus.WAITING, Stage.OBSERVE)

    def act(self, ctx, decision):
        raise AssertionError("not reached")

    def evaluate(self, ctx, action_result):
        raise AssertionError("not reached")


class CompanyPriorityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.runtime = Runtime(Path(self.temp.name) / "state.sqlite",
                               {"priority": PriorityHandler()})

    def goal(self, goal_id, priority="normal", parent_id=None):
        return self.runtime.create_goal(
            goal_id=goal_id, name=goal_id, owner_id="priority",
            metric="done", operator="eq", target=True, parent_id=parent_id,
            config={"priority": priority})

    def test_runner_and_snapshot_choose_highest_priority_outcome(self):
        self.goal("low", "low")
        self.goal("high", "critical")
        self.assertEqual("high", Runner(self.runtime)._candidates(None)[0])
        self.assertEqual("high", self.runtime.company_snapshot()["focus_goal"]["id"])

    def test_company_directive_is_available_in_goal_context(self):
        self.runtime.store.record_directive("Subtract before adding.")
        goal = self.goal("directed")
        state = self.runtime.once(goal["id"])
        self.assertIn("Subtract before adding.",
                      state["cycle"]["data"]["observation"]["directives"])

    def test_everything_approved_on_root_is_inherited_by_descendant(self):
        root = self.goal("root")
        child = self.goal("child", parent_id=root["id"])
        self.runtime.approve(root["id"], scope="everything_approved")
        cycle = self.runtime.store.cycle(child["id"])
        self.assertEqual("approved", self.runtime._approval_status(
            self.runtime.store.goal(child["id"]), cycle, "execute"))


if __name__ == "__main__":
    unittest.main()
