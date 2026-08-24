"""Regression 6.5.0: director ``booked_calls`` metering counts goal-level evidence.

Owner-confirmed ``booked_call`` evidence recorded on the goal itself (kind
``booked_call``, business validity, e.g. via ``company evidence add``) must be
visible to the director ``evaluate`` metric. Before this repair the director
read metric values only from supporting child evaluations, so a parent with
metric ``booked_calls`` could never be satisfied even with recorded calls.

Assertions:
1. Goal-level business-valid ``booked_call`` evidence makes measured >= count.
2. Non-business or non-``booked_call`` evidence is ignored.
3. Child-reported ``booked_calls`` values still win when larger than the
   goal-level count (max semantics preserved).
4. Existing child-based metrics (``reply_rate`` style) evaluate unchanged.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from company.runtime.director import Director
from company.runtime.loop import Runtime
from company.runtime.models import Goal, GoalContext
from company.tests.test_runtime import ImmediateHandler


def _booked_call_evidence(evidence_id: str, validity: str = "business") -> dict:
    """A goal-level evidence row in the decoded store shape."""
    return {"id": evidence_id, "goal_id": "parent", "run_id": "run-parent",
            "kind": "booked_call", "source": "owner", "payload": {},
            "validity": validity}


class BookedCallsDirectorMetricTests(unittest.TestCase):
    def runtime(self, registry):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        return Runtime(Path(self.temp.name) / "state.sqlite", registry)

    def test_goal_level_business_booked_call_evidence_achieves_parent(self):
        """(1) Two business-valid booked_call items on the parent satisfy it."""
        runtime = self.runtime({"director": Director(), "immediate_test": ImmediateHandler()})
        parent = runtime.create_goal(
            name="Book 2 calls", owner_id="director",
            metric="booked_calls", operator="ge", target=2, config={})
        runtime.create_goal(
            name="Child", owner_id="immediate_test", metric="done",
            operator="eq", target=True, parent_id=parent["id"], config={})
        runtime.add_evidence(parent["id"], kind="booked_call", source="owner",
                             payload={"lead_id": "EN-1157"}, validity="business")
        runtime.add_evidence(parent["id"], kind="booked_call", source="owner",
                             payload={"lead_id": "EN-1358"}, validity="business")

        result = runtime.once(parent["id"])

        self.assertEqual(result["goal"]["goal_status"], "achieved")
        self.assertEqual(result["evaluation"]["metrics"]["booked_calls"], 2)
        self.assertEqual(result["evaluation"]["validity"], "business")
        self.assertTrue(result["evaluation"]["goal_met"])

    def test_non_business_or_non_booked_call_evidence_ignored(self):
        """(2) Technical booked_call and business non-booked_call do not count."""
        runtime = self.runtime({"director": Director(), "immediate_test": ImmediateHandler()})
        parent = runtime.create_goal(
            name="Book 2 calls", owner_id="director",
            metric="booked_calls", operator="ge", target=2, config={})
        runtime.create_goal(
            name="Child", owner_id="immediate_test", metric="done",
            operator="eq", target=True, parent_id=parent["id"], config={})
        runtime.add_evidence(parent["id"], kind="booked_call", source="owner",
                             payload={}, validity="technical_only")
        runtime.add_evidence(parent["id"], kind="reply", source="owner",
                             payload={}, validity="business")

        result = runtime.once(parent["id"])

        self.assertNotEqual(result["goal"]["goal_status"], "achieved")
        self.assertFalse(result["evaluation"]["goal_met"])
        self.assertIsNone(result["evaluation"]["metrics"]["booked_calls"])

    def test_child_reported_booked_calls_wins_when_larger(self):
        """(3) Child metric value beats a smaller goal-level count (max)."""
        goal = Goal("parent", "Book calls", "director", "booked_calls",
                    "ge", 2, None, None, "active", {})
        child = {"id": "child-1", "goal_status": "achieved",
                 "cycle": {"run_status": "completed"},
                 "run": {"evidence_validity": "business"},
                 "evaluation": {"validity": "business",
                                "metrics": {"booked_calls": 5},
                                "run_id": "run-child"}}
        cycle = {"children": (child,), "run": {"evidence_validity": "business"},
                 "evidence": (_booked_call_evidence("ev-1"),
                              _booked_call_evidence("ev-2"))}

        result = Director().evaluate(GoalContext(goal, cycle, (), lambda _key: None), {})

        self.assertEqual(result.payload["metric_value"], 5)
        self.assertTrue(result.payload["goal_met"])
        self.assertEqual(result.evaluation["metrics"]["booked_calls"], 5)

    def test_reply_rate_child_metering_unchanged_by_goal_evidence(self):
        """(4) reply_rate parents are untouched by booked_call goal evidence."""
        goal = Goal("parent", "Reply rate", "director", "reply_rate",
                    "ge", 0.3, None, None, "active", {})
        child = {"id": "child-1", "goal_status": "achieved",
                 "cycle": {"run_status": "completed"},
                 "run": {"evidence_validity": "business"},
                 "evaluation": {"validity": "business",
                                "metrics": {"reply_rate": 0.5},
                                "run_id": "run-child"}}
        cycle = {"children": (child,), "run": {"evidence_validity": "business"},
                 "evidence": (_booked_call_evidence("ev-1"),
                              _booked_call_evidence("ev-2"))}

        result = Director().evaluate(GoalContext(goal, cycle, (), lambda _key: None), {})

        self.assertEqual(result.payload["metric_value"], 0.5)
        self.assertTrue(result.payload["goal_met"])

        # booked_call goal evidence alone must not satisfy a reply_rate parent.
        bare = {"children": (), "run": {"evidence_validity": "business"},
                "evidence": (_booked_call_evidence("ev-3"),)}
        bare_result = Director().evaluate(
            GoalContext(goal, bare, (), lambda _key: None), {})
        self.assertIsNone(bare_result.payload["metric_value"])
        self.assertFalse(bare_result.payload["goal_met"])


if __name__ == "__main__":
    unittest.main()
