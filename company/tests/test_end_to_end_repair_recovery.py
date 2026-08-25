"""Real SpielOS1 journey: contaminated business run -> repair -> exact retest."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from company.runtime.director import Director
from company.runtime.loop import Runtime
from company.runtime.models import GoalHandler, GoalStatus, RunStatus, StageResult
from company.runtime.system_improvement import SystemImprovement


class _OutboundTransport(GoalHandler):
    id = "outbound_transport"
    version = "2.0.1"

    def observe(self, ctx):
        return StageResult("collect", {"sequence": ctx.cycle["sequence"]})

    def decide(self, ctx, observation):
        return StageResult("diagnose", {"action": "send", **observation})

    def act(self, ctx, decision):
        return StageResult("execute", dict(decision))

    def evaluate(self, ctx, action_result):
        if action_result["sequence"] == 1:
            reason = "provider mapping rejected 2 of 10 approved recipients"
            proposal = {
                "owner_id": self.id,
                "from_version": "2.0.0",
                "target_version": self.version,
                "problem": reason,
                "observed_reality": reason,
                "diagnosis_level": "system",
                "causal_hypothesis": "The provider mapping caused partial delivery.",
                "smallest_intervention": "Repair only the provider mapping.",
                "expected_measurable_effect": "The same 10 recipients send without contamination.",
                "stop_condition": "Acceptance passes and the exact retest is valid.",
                "allowed_files": ["company/departments/outbound/email_workflow.py"],
                "acceptance_tests": ["python3 -B -m pytest -q company/tests"],
            }
            return StageResult(
                "goal_check", {"delivery_rate": 0.8}, RunStatus.COMPLETED,
                evaluation={
                    "verdict": "invalid", "goal_met": False,
                    "metrics": {"delivery_rate": 0.8},
                    "validity": "contaminated", "contamination_reason": reason,
                    "next_experiment": {"system_improvement": proposal},
                },
                evidence=[{
                    "kind": "transport_failure", "source": "provider",
                    "validity": "contaminated", "payload": {"failed": 2, "total": 10},
                }],
            )
        return StageResult(
            "goal_check", {"delivery_rate": 1.0}, RunStatus.COMPLETED,
            goal_status=GoalStatus.ACHIEVED,
            evaluation={
                "verdict": "goal_met", "goal_met": True,
                "metrics": {"delivery_rate": 1.0}, "validity": "business",
                "next_experiment": {},
            },
            evidence=[{
                "kind": "delivery_result", "source": "provider",
                "validity": "business", "payload": {"delivery_rate": 1.0, "total": 10},
            }],
        )


class EndToEndRepairRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.runtime = Runtime(Path(self.temp.name) / "state.sqlite", {
            "director": Director(),
            "outbound_transport": _OutboundTransport(),
            "system-improvement": SystemImprovement(),
        })

    def test_contaminated_run_is_repaired_once_then_retested(self):
        primary = self.runtime.create_goal(
            name="Reach 30 percent qualified replies", owner_id="director",
            metric="reply_rate", operator="ge", target=0.3, config={})
        outbound = self.runtime.create_goal(
            name="Deliver the approved outbound batch", owner_id="outbound_transport",
            metric="delivery_rate", operator="ge", target=1.0,
            parent_id=primary["id"], run_type="business_experiment",
            controlled_variables={"recipients": 10, "offer": "fixed"},
            changed_variables={"provider_mapping": "2.0.0"}, config={})

        contaminated = self.runtime.once(outbound["id"])
        originating_run_id = contaminated["run"]["id"]
        self.assertEqual("contaminated", contaminated["evaluation"]["validity"])

        self.runtime.once(primary["id"])
        repairs = [goal for goal in self.runtime.store.goals(parent_id=primary["id"])
                   if goal["owner_id"] == "system-improvement"]
        self.assertEqual(1, len(repairs))
        repair_id = repairs[0]["id"]

        self.runtime.once(repair_id)
        self.runtime.approve(repair_id)
        blocked = self.runtime.once(repair_id)
        task = blocked["change_tasks"][0]
        self.runtime.complete_change(
            task["id"], passed=True,
            result={"passed": True, "commands": task["acceptance_tests"]})
        self.runtime.once(repair_id)

        retest = self.runtime.status(outbound["id"])
        self.assertEqual(2, retest["cycle"]["sequence"])
        self.assertNotEqual(originating_run_id, retest["run"]["id"])
        self.assertEqual(contaminated["run"]["config_snapshot"],
                         retest["run"]["config_snapshot"])
        self.assertEqual(contaminated["run"]["controlled_variables"],
                         retest["run"]["controlled_variables"])
        self.assertEqual(contaminated["run"]["changed_variables"],
                         retest["run"]["changed_variables"])

        # Re-observing the parent before the retest executes must dispatch the
        # existing retest, not manufacture another repair for historical truth.
        self.runtime.once(primary["id"])
        repairs = [goal for goal in self.runtime.store.goals(parent_id=primary["id"])
                   if goal["owner_id"] == "system-improvement"]
        self.assertEqual(1, len(repairs))
        self.assertEqual("achieved", self.runtime.store.goal(outbound["id"])["goal_status"])


if __name__ == "__main__":
    unittest.main()
