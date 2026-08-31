"""Bounded self-improvement: approve, execute, validate, and return."""

import os
import shlex
import subprocess
import sys
import tempfile

from .install import (
    REPO_ROOT, allowed_install_files, install_department,
    normalize_department_spec, validate_department_spec)
from .models import GoalHandler, GoalStatus, RunStatus, Stage, StageResult


class SystemImprovement(GoalHandler):
    id = "system-improvement"
    version = "2.0.0"
    description = "Coordinates bounded runtime repairs or new Departments with approval and test evidence."
    goal_schema = {
        "metrics": ["acceptance_tests_passed"],
        "config": {
            "owner_id": {"type": "string", "required": True},
            "from_version": {"type": "string", "required": True},
            "target_version": {"type": "string", "required": True},
            "problem": {"type": "string", "required": True},
            "allowed_files": {"type": "array", "required": True},
            "acceptance_tests": {"type": "array", "required": True},
            "originating_run_id": {"type": "string"},
            "change_kind": {"enum": ["repair", "create_department"]},
            "department_spec": {"type": "object", "required_when": {
                "change_kind": "create_department"}},
            "force_install": {"type": "boolean"},
            "owner_override": {"type": "boolean"},
            "alignment": {"type": "object"},
            "max_attempts": {"type": "integer"},
        },
    }

    def observe(self, ctx):
        tasks = list(ctx.cycle.get("change_tasks") or ())
        return StageResult(
            "collect", {"tasks": tasks, "config": ctx.goal.config},
            evidence=[{"kind": "change_task_state", "source": self.id,
                       "validity": "technical_only",
                       "payload": {"task_count": len(tasks),
                                   "statuses": [task["status"] for task in tasks]}}])

    def decide(self, ctx, observation):
        config = observation.get("config") or {}
        alignment = config.get("alignment") or {}
        if (alignment.get("judgment") == "defer_recommended"
                and not alignment.get("owner_override")
                and not config.get("owner_override")):
            return StageResult(
                "diagnose", {"alignment": alignment}, RunStatus.BLOCKED, Stage.DECIDE,
                decision={"type": "block_unaligned_system_improvement",
                          "rationale": alignment.get("rationale")
                          or "Director recommended deferral; owner override required"})
        required = ("owner_id", "from_version", "target_version", "problem",
                    "allowed_files", "acceptance_tests")
        missing = [key for key in required if not config.get(key)]
        change_kind = config.get("change_kind", "repair")
        if change_kind not in {"repair", "create_department"}:
            missing.append("change_kind(repair|create_department)")
        if change_kind == "create_department" and not config.get("department_spec"):
            missing.append("department_spec")
        if change_kind == "create_department" and config.get("department_spec"):
            department_spec = dict(config["department_spec"])
            department_spec.setdefault("id", config.get("owner_id"))
            department_spec.setdefault("version", config.get("target_version"))
            defects = validate_department_spec(department_spec)
            if defects:
                return StageResult(
                    "diagnose", {"missing": defects}, RunStatus.BLOCKED, Stage.DECIDE,
                    decision={"type": "block_invalid_department_spec",
                              "rationale": "department_spec failed package validation",
                              "payload": {"defects": defects}})
        if missing:
            return StageResult(
                "diagnose", {"missing": missing}, RunStatus.BLOCKED, Stage.DECIDE,
                decision={"type": "block_invalid_change_task",
                          "rationale": f"Missing bounded task fields: {', '.join(missing)}"})
        tasks = observation.get("tasks") or []
        if not tasks:
            action = {"action": "create_change_task"}
        elif tasks[-1]["status"] == "proposed":
            action = {"action": "approve_change_task", "task_id": tasks[-1]["id"]}
        elif (tasks[-1]["status"] == "approved"
              and config.get("change_kind") == "create_department"):
            action = {"action": "install_department", "task_id": tasks[-1]["id"]}
        elif tasks[-1]["status"] in ("completed", "failed"):
            action = {"action": "evaluate_change", "task_id": tasks[-1]["id"]}
        else:
            action = {"action": "wait_for_executor", "task_id": tasks[-1]["id"]}
        return StageResult(
            "choose_intervention", action,
            decision={"type": action["action"],
                      "rationale": "Keep system work bounded and separate from outcome evidence",
                      "next_run_type": "system_improvement", "payload": action})

    def act(self, ctx, decision):
        config = ctx.goal.config
        action = decision.get("action")
        if action == "create_change_task":
            previous = (ctx.cycle.get("data") or {}).get("action_result") or {}
            if previous.get("task"):
                task = previous["task"]
                if ctx.approval_status("execute") != "approved":
                    return StageResult("review", previous, RunStatus.AWAITING_APPROVAL, Stage.ACT)
                if ctx.update_change_task and task.get("status") == "proposed":
                    task = ctx.update_change_task(task["id"], "approved", {})
                return self._after_approval(ctx, task)
            if not ctx.create_change_task:
                return StageResult("prepare", {"error": "change-task capability unavailable"},
                                   RunStatus.FAILED, Stage.ACT)
            allowed = list(config["allowed_files"])
            if config.get("change_kind") == "create_department":
                department_id = ((config.get("department_spec") or {}).get("id")
                                 or config["owner_id"])
                preview = normalize_department_spec(
                    dict(config.get("department_spec") or {}),
                    default_id=str(department_id).replace("-", "_"),
                    default_version=config.get("target_version"))
                for path in allowed_install_files(preview["id"], preview["agent_ids"]):
                    if path not in allowed:
                        allowed.append(path)
            task = ctx.create_change_task({
                "owner_id": config["owner_id"],
                "from_version": config["from_version"],
                "target_version": config["target_version"],
                "problem": config["problem"],
                "allowed_files": allowed,
                "acceptance_tests": list(config["acceptance_tests"]),
                "originating_run_id": config.get("originating_run_id"),
                "change_kind": config.get("change_kind", "repair"),
                "specification": config.get("department_spec", {}),
            })
            if ctx.approval_status("execute") == "approved":
                if ctx.update_change_task and task.get("status") == "proposed":
                    task = ctx.update_change_task(task["id"], "approved",
                                                  {"carried_scope_approval": True})
                return self._after_approval(ctx, task)
            return StageResult("review", {"task": task},
                               RunStatus.AWAITING_APPROVAL, Stage.ACT,
                               message="Approve the bounded change task before execution")
        if action == "approve_change_task":
            if ctx.approval_status("execute") != "approved":
                return StageResult("review", decision,
                                   RunStatus.AWAITING_APPROVAL, Stage.ACT)
            task = ctx.update_change_task(decision["task_id"], "approved", {})
            return self._after_approval(ctx, task)
        if action == "install_department":
            task = next((item for item in (ctx.cycle.get("change_tasks") or ())
                         if item["id"] == decision.get("task_id")), None)
            if not task:
                return StageResult("install", {"error": "change task missing"},
                                   RunStatus.FAILED, Stage.ACT)
            return self._install_department(ctx, task)
        if action == "wait_for_executor":
            return StageResult("execute_change", decision, RunStatus.BLOCKED, Stage.ACT)
        return StageResult("validate_change", decision, next_stage=Stage.EVALUATE)

    @staticmethod
    def _wait(task):
        return StageResult(
            "execute_change", {"task": task}, RunStatus.BLOCKED, Stage.ACT,
            message="Executor must modify only allowed files and record actual acceptance results")

    def _after_approval(self, ctx, task):
        if ctx.goal.config.get("change_kind") == "create_department":
            return self._install_department(ctx, task)
        return self._wait(task)

    def _install_department(self, ctx, task):
        config = ctx.goal.config
        spec = dict(config.get("department_spec") or task.get("specification") or {})
        department_id = str(spec.get("id") or config.get("owner_id") or "").replace("-", "_")
        try:
            receipt = install_department(
                spec, default_id=department_id,
                default_version=config.get("target_version"),
                force=bool(config.get("force_install")),
                allowed_files=task.get("allowed_files") or config.get("allowed_files"))
        except (ValueError, FileExistsError, PermissionError, OSError) as error:
            if ctx.update_change_task:
                ctx.update_change_task(task["id"], "failed", {
                    "passed": False, "error": str(error),
                    "commands": ["company department install"]})
            return StageResult(
                "install", {"task_id": task["id"], "error": str(error)},
                RunStatus.BLOCKED, Stage.ACT,
                message=f"Department install failed: {error}")

        acceptance = self._run_department_acceptance(
            list(config.get("acceptance_tests") or []))
        result = {"passed": acceptance["passed"], "deployed": True,
                  "acceptance": acceptance, "install": receipt}
        status = "completed" if acceptance["passed"] else "failed"
        if ctx.update_change_task:
            task = ctx.update_change_task(task["id"], status, result)
        if not acceptance["passed"]:
            return StageResult(
                "install", result, RunStatus.BLOCKED, Stage.ACT,
                message="Department installed but its acceptance command failed")
        return StageResult(
            "install", {"task": task, "install": receipt}, next_stage=Stage.EVALUATE,
            evidence=[{"kind": "department_installed", "source": self.id,
                       "validity": "technical_only",
                       "payload": {"department_id": receipt["id"],
                                   "version": receipt["version"],
                                   "written": receipt["written"]}}],
            message=f"Installed Department package `{receipt['id']}`")

    @staticmethod
    def _run_department_acceptance(commands):
        """Run only the bounded read-only commands accepted for installs."""

        results = []
        allowed = {("department", "list"), ("catalog",), ("departments",)}
        environment = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1", "PYTHONPATH": "."}
        with tempfile.TemporaryDirectory() as directory:
            acceptance_db = os.path.join(directory, "company.sqlite")
            for command in commands:
                parts = shlex.split(str(command))
                if parts and parts[0] == "company":
                    company_args = tuple(parts[1:])
                elif parts[:4] == ["python3", "-B", "-m", "company"]:
                    company_args = tuple(parts[4:])
                else:
                    company_args = ()
                if company_args not in allowed:
                    return {"passed": False, "results": results,
                            "error": f"unsupported Department acceptance command: {command}"}
                completed = subprocess.run(
                    [sys.executable, "-B", "-m", "company", "--db", acceptance_db,
                     *company_args], cwd=REPO_ROOT, env=environment,
                    capture_output=True, text=True)
                results.append({"command": command,
                                "returncode": completed.returncode,
                                "stdout": completed.stdout[-2000:],
                                "stderr": completed.stderr[-2000:]})
                if completed.returncode != 0:
                    return {"passed": False, "results": results}
        return {"passed": True, "results": results}

    def evaluate(self, ctx, action_result):
        tasks = list(ctx.cycle.get("change_tasks") or ())
        task = tasks[-1] if tasks else None
        passed = bool(task and task["status"] == "completed"
                      and task.get("result", {}).get("passed", True))
        metrics = {"acceptance_tests_passed": passed}
        evaluation = {
            "verdict": "keep" if passed else "reject", "goal_met": passed,
            "metrics": metrics, "validity": "technical_only",
            "contamination_reason": None if passed else "Change did not pass acceptance",
            "next_experiment": ({"resume_run_id": ctx.goal.config.get("originating_run_id")}
                                if passed else {"action": "retry_same_scope"}),
        }
        if passed:
            return StageResult("goal_check", metrics, RunStatus.IDLE,
                               goal_status=GoalStatus.ACHIEVED,
                               evaluation=evaluation,
                               message="System change validated and versioned")
        return StageResult("goal_check", metrics, RunStatus.BLOCKED, Stage.EVALUATE,
                           evaluation=evaluation,
                           message="System change failed acceptance; same-scope retry is allowed")
