"""Integrity 6.3: repair attempts are append-only and coherent."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from company.runtime.loop import Runtime
from company.runtime.system_improvement import SystemImprovement


class AppendOnlyRepairTests(unittest.TestCase):
    def runtime(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        return Runtime(Path(self.temp.name) / "state.sqlite",
                       {"system-improvement": SystemImprovement()})

    def _approved_task(self, runtime, name="Repair sender"):
        goal = runtime.create_goal(
            name=name, owner_id="system-improvement",
            metric="acceptance_tests_passed", operator="eq", target=True,
            run_type="system_improvement", evidence_validity="technical_only",
            config={
                "owner_id": "email", "from_version": "2.0.0", "target_version": "2.0.1",
                "problem": "provider mapping", "allowed_files": ["email.py"],
                "acceptance_tests": ["python -m unittest"],
                "owner_override": True,
            })
        runtime.once(goal["id"])
        runtime.approve(goal["id"])
        blocked = runtime.once(goal["id"])
        return goal, blocked["change_tasks"][0]

    def test_failed_task_cannot_be_completed_again(self):
        runtime = self.runtime()
        _goal, task = self._approved_task(runtime)
        runtime.complete_change(task["id"], passed=False,
                                result={"passed": False, "commands": ["python -m unittest"]})
        failed = runtime.store.change_task(task["id"])
        self.assertEqual(failed["status"], "failed")
        with self.assertRaisesRegex(RuntimeError, "only an approved task can be completed"):
            runtime.complete_change(task["id"], passed=True,
                                    result={"passed": True, "commands": ["python -m unittest"]})
        self.assertEqual(runtime.store.change_task(task["id"])["status"], "failed")

    def test_completed_task_cannot_be_completed_again(self):
        runtime = self.runtime()
        _goal, task = self._approved_task(runtime)
        runtime.complete_change(task["id"], passed=True,
                                result={"passed": True, "commands": ["python -m unittest"]})
        with self.assertRaisesRegex(RuntimeError, "only an approved task can be completed"):
            runtime.complete_change(task["id"], passed=False,
                                    result={"passed": False})
        self.assertEqual(runtime.store.change_task(task["id"])["status"], "completed")

    def test_proposed_task_cannot_skip_to_completed(self):
        runtime = self.runtime()
        goal = runtime.create_goal(
            name="Needs approval first", owner_id="system-improvement",
            metric="acceptance_tests_passed", operator="eq", target=True,
            run_type="system_improvement", evidence_validity="technical_only",
            config={
                "owner_id": "email", "from_version": "2.0.0", "target_version": "2.0.1",
                "problem": "mapping", "allowed_files": ["email.py"],
                "acceptance_tests": ["python -m unittest"],
                "owner_override": True,
            })
        parked = runtime.once(goal["id"])
        task = parked["change_tasks"][0]
        self.assertEqual(task["status"], "proposed")
        with self.assertRaisesRegex(RuntimeError, "cannot move from proposed to completed"):
            runtime.store.complete_change_task(task["id"], "completed", {"passed": True})

    def test_fail_then_succeed_produces_two_attempts(self):
        runtime = self.runtime()
        goal, first = self._approved_task(runtime, name="Retry after failure")
        runtime.complete_change(first["id"], passed=False,
                                result={"passed": False, "commands": ["python -m unittest"]})
        rejected = runtime.once(goal["id"])
        self.assertNotEqual(rejected["goal"]["goal_status"], "achieved")
        self.assertEqual(rejected["evaluation"]["verdict"], "reject")
        self.assertTrue(rejected["run"]["contamination_reason"])
        first_run_id = rejected["run"]["id"]
        first_contamination = rejected["run"]["contamination_reason"]

        retried = runtime.retry(goal["id"])
        self.assertNotEqual(retried["run"]["id"], first_run_id)
        self.assertIsNone(retried["run"]["contamination_reason"])
        self.assertEqual(runtime.store.run(first_run_id)["contamination_reason"],
                         first_contamination)
        self.assertEqual(runtime.store.evaluation(first_run_id)["verdict"], "reject")

        second_blocked = runtime.once(goal["id"])
        second = second_blocked["change_tasks"][0]
        self.assertNotEqual(second["id"], first["id"])
        runtime.complete_change(second["id"], passed=True,
                                result={"passed": True, "commands": ["python -m unittest"]})
        complete = runtime.once(goal["id"])
        self.assertEqual(complete["goal"]["goal_status"], "achieved")
        self.assertEqual(complete["evaluation"]["verdict"], "keep")
        self.assertIsNone(complete["run"]["contamination_reason"])

        tasks = runtime.store.change_tasks_for_goal(goal["id"])
        self.assertEqual([task["status"] for task in tasks], ["failed", "completed"])
        self.assertEqual({task["run_id"] for task in tasks},
                         {first_run_id, complete["run"]["id"]})
        self.assertEqual(runtime.store.evaluation(first_run_id)["verdict"], "reject")
        self.assertEqual(runtime.store.evaluation(complete["run"]["id"])["verdict"], "keep")
        versions = runtime.store.owner_versions("email")
        self.assertEqual(versions[-1]["version"], "2.0.1")
        self.assertEqual(versions[-1]["status"], "tested")

    def test_success_without_deploy_flag_is_tested_not_deployed(self):
        runtime = self.runtime()
        _goal, task = self._approved_task(runtime)
        runtime.complete_change(task["id"], passed=True, deployed=False,
                                result={"passed": True, "commands": ["python -m unittest"]})
        versions = runtime.store.owner_versions("email")
        self.assertEqual(versions[-1]["status"], "tested")
        self.assertIsNone(versions[-1]["deployed_at"])


class IterativeRepairTests(unittest.TestCase):
    def runtime(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        return Runtime(Path(self.temp.name) / "state.sqlite",
                       {"system-improvement": SystemImprovement()})

    def _failed_acceptance(self, runtime, **config):
        payload = {
            "owner_id": "email", "from_version": "2.0.0", "target_version": "2.0.1",
            "problem": "provider mapping", "allowed_files": ["email.py"],
            "acceptance_tests": ["python -m unittest"],
            "owner_override": True,
        }
        payload.update(config)
        goal = runtime.create_goal(
            name="Retry inside one repair", owner_id="system-improvement",
            metric="acceptance_tests_passed", operator="eq", target=True,
            run_type="system_improvement", evidence_validity="technical_only",
            config=payload)
        runtime.once(goal["id"])
        runtime.approve(goal["id"])
        blocked = runtime.once(goal["id"])
        runtime.complete_change(blocked["change_tasks"][0]["id"], passed=False,
                                result={"passed": False, "commands": ["python -m unittest"]})
        rejected = runtime.once(goal["id"])
        return goal, rejected

    def test_failed_acceptance_retries_same_goal_without_new_approval(self):
        runtime = self.runtime()
        goal, rejected = self._failed_acceptance(runtime)
        self.assertEqual(rejected["cycle"]["run_status"], "blocked")
        self.assertEqual(rejected["evaluation"]["next_experiment"]["action"], "retry_same_scope")
        first_run = rejected["run"]["id"]

        second = runtime.once(goal["id"])
        self.assertNotEqual(second["run"]["id"], first_run)
        self.assertEqual(second["cycle"]["step"], "execute_change")
        self.assertEqual(second["cycle"]["run_status"], "blocked")
        task = second["change_tasks"][0]
        self.assertEqual(task["status"], "approved")
        self.assertNotEqual(task["id"], rejected["change_tasks"][0]["id"])
        self.assertEqual(task["allowed_files"], ["email.py"])
        self.assertEqual(runtime.store.approval(goal["id"], second["cycle"]["id"], "execute"),
                         "approved")

        runtime.complete_change(task["id"], passed=True,
                                result={"passed": True, "commands": ["python -m unittest"]})
        complete = runtime.once(goal["id"])
        self.assertEqual(complete["goal"]["goal_status"], "achieved")
        self.assertEqual(
            [item["status"] for item in runtime.store.change_tasks_for_goal(goal["id"])],
            ["failed", "completed"])

    def test_scope_change_requires_a_fresh_approval(self):
        runtime = self.runtime()
        goal, rejected = self._failed_acceptance(runtime)
        config = dict(runtime.store.goal(goal["id"])["config"])
        config["allowed_files"] = ["email.py", "providers.py"]
        config["problem"] = "also repair providers"
        runtime.store.update_goal_config(goal["id"], config)
        retried = runtime.retry(goal["id"])
        self.assertIsNone(runtime.store.approval(
            goal["id"], retried["cycle"]["id"], "execute"))
        parked = runtime.once(goal["id"])
        self.assertEqual(parked["cycle"]["run_status"], "awaiting_approval")

    def test_attempt_limit_stops_automatic_iteration(self):
        runtime = self.runtime()
        goal, _rejected = self._failed_acceptance(runtime, max_attempts=1)
        again = runtime.once(goal["id"])
        self.assertEqual(again["cycle"]["sequence"], 1)
        self.assertEqual(runtime.repair_iteration_decision(goal["id"])["reason"],
                         "attempt_limit_reached")


if __name__ == "__main__":
    unittest.main()
