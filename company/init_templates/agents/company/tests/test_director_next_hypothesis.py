"""P2.5D bridge: a finished child lets the Director derive the next
hypothesis from the completed run's evidence and automatically start the
next experiment, instead of dead-ending in BLOCKED.

Regression: Director.evaluate returned RunStatus.BLOCKED with
``set_or_reopen_child_goal`` when a finite child finished and the parent
metric was still unmet. That action had no executor, so the parent
hierarchy stopped. Now the parent derives a new hypothesis/experiment,
continues automatically, tests it by creating/dispatching a concrete
child task, and re-observes the new evidence before deriving again.
BLOCKED is reserved for when no accepted business evidence supports a
next experiment.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from company.runtime.director import Director
from company.runtime.loop import Runtime
from company.runtime.models import GoalHandler, GoalStatus, RunStatus, Stage, StageResult
from company.tests.test_runtime import ImmediateHandler


class TechnicalOnlyHandler(GoalHandler):
    """Achieves with technical-only evidence: not countable toward a business parent."""

    id = "technical_only_test"

    def observe(self, ctx):
        return StageResult("collect", {"probe": True})

    def decide(self, ctx, observation):
        return StageResult("diagnose", {"action": "do_it"})

    def act(self, ctx, decision):
        return StageResult("execute", {"done": True})

    def evaluate(self, ctx, action_result):
        return StageResult("goal_check", {"done": True}, RunStatus.IDLE,
                           goal_status=GoalStatus.ACHIEVED,
                           evaluation={"verdict": "goal_met", "goal_met": True,
                                       "metrics": {"done": True},
                                       "validity": "technical_only"})


class DirectorNextHypothesisTests(unittest.TestCase):
    def runtime(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        return Runtime(Path(self.temp.name) / "state.sqlite", {
            "director": Director(),
            "immediate_test": ImmediateHandler(),
            "technical_only_test": TechnicalOnlyHandler(),
        })

    def test_finished_child_derives_next_hypothesis_and_auto_starts_experiment(self):
        runtime = self.runtime()
        parent = runtime.create_goal(name="Achieve two child tasks", owner_id="director",
                                     metric="achieved_children", operator="ge", target=2,
                                     config={})
        child1 = runtime.create_goal(name="Task one", owner_id="immediate_test",
                                     metric="done", operator="eq", target=True,
                                     parent_id=parent["id"], config={})
        self.assertEqual(runtime.once(child1["id"])["goal"]["goal_status"], "achieved")

        # Run 1: the parent learns from the finished child and derives the next
        # hypothesis. It must CONTINUE automatically, never dead-end BLOCKED.
        first = runtime.once(parent["id"])
        self.assertEqual(first["cycle"]["run_status"], "completed")
        self.assertEqual(first["cycle"]["sequence"], 1)
        evaluation = runtime.store.latest_evaluation_for_goal(parent["id"])
        self.assertEqual(evaluation["next_experiment"]["action"], "test_next_hypothesis")
        hypothesis = evaluation["next_experiment"]["hypothesis"]
        self.assertTrue(hypothesis["statement"])
        self.assertEqual(hypothesis["variable"], "achieved_children")
        self.assertTrue(hypothesis["prediction"])

        # Run 2 (automatic continuation): DECIDE sees the carried hypothesis and
        # ACT creates/dispatches the concrete test task (a NEW child, not a clone).
        # EVALUATE re-reads the children after ACT, so the new child's evidence
        # is counted in this same run and the parent achieves.
        second = runtime.once(parent["id"])
        self.assertEqual(second["goal"]["goal_status"], "achieved")
        self.assertEqual(second["cycle"]["run_status"], "completed")
        self.assertEqual(second["cycle"]["sequence"], 2)
        self.assertIsNotNone(second["run"]["hypothesis_id"])
        hypothesis_row = runtime.store.hypothesis(second["run"]["hypothesis_id"])
        self.assertEqual(hypothesis_row["status"], "active")
        self.assertTrue(hypothesis_row["statement"])
        children = runtime.store.goals(parent_id=parent["id"])
        self.assertEqual(len(children), 2)
        experiment = children[-1]
        self.assertEqual(experiment["config"].get("purpose"), "test_next_hypothesis")
        self.assertNotEqual(experiment["id"], child1["id"])
        self.assertEqual(experiment["owner_id"], "immediate_test")
        self.assertEqual(runtime.store.cycle(experiment["id"])["run_status"], "completed")

        # A further once is idempotent: the goal is terminal, no new run starts.
        third = runtime.once(parent["id"])
        self.assertEqual(third["goal"]["goal_status"], "achieved")
        self.assertEqual(third["cycle"]["sequence"], 2)

    def test_blocked_only_when_no_next_experiment_can_be_derived(self):
        runtime = self.runtime()
        parent = runtime.create_goal(name="Two achieved child tasks", owner_id="director",
                                     metric="achieved_children", operator="ge", target=2,
                                     config={})
        technical = runtime.create_goal(name="Technical task", owner_id="technical_only_test",
                                        metric="done", operator="eq", target=True,
                                        parent_id=parent["id"], config={})
        self.assertEqual(runtime.once(technical["id"])["goal"]["goal_status"], "achieved")

        # Technical-only evidence is not accepted business evidence, so the
        # Director cannot derive a next experiment: this is a genuine BLOCK.
        result = runtime.once(parent["id"])
        self.assertEqual(result["cycle"]["run_status"], "blocked")
        self.assertEqual(result["cycle"]["stage"], "EVALUATE")
        self.assertEqual(result["goal"]["goal_status"], "active")
        evaluation = runtime.store.latest_evaluation_for_goal(parent["id"])
        self.assertEqual(evaluation["verdict"], "blocked")
        self.assertEqual(evaluation["goal_met"], False)
        self.assertEqual(evaluation["next_experiment"], {})


if __name__ == "__main__":
    unittest.main()
