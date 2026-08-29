"""Bounded self-improvement: approve, execute, validate, and return."""

from .models import GoalHandler, GoalStatus, RunStatus, Stage, StageResult


class SystemImprovement(GoalHandler):
    id = "system-improvement"
    version = "2.0.0"
    description = "Coordinates bounded runtime or Workgroup repairs with approval and test evidence."
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
            "change_kind": {"enum": ["repair"]},
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
        if config.get("change_kind", "repair") != "repair":
            missing.append("change_kind(repair)")
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
                return self._wait(task)
            if not ctx.create_change_task:
                return StageResult("prepare", {"error": "change-task capability unavailable"},
                                   RunStatus.FAILED, Stage.ACT)
            task = ctx.create_change_task({
                "owner_id": config["owner_id"],
                "from_version": config["from_version"],
                "target_version": config["target_version"],
                "problem": config["problem"],
                "allowed_files": list(config["allowed_files"]),
                "acceptance_tests": list(config["acceptance_tests"]),
                "originating_run_id": config.get("originating_run_id"),
                "change_kind": "repair", "specification": {},
            })
            if ctx.approval_status("execute") == "approved":
                if ctx.update_change_task and task.get("status") == "proposed":
                    task = ctx.update_change_task(task["id"], "approved",
                                                  {"carried_scope_approval": True})
                return self._wait(task)
            return StageResult("review", {"task": task},
                               RunStatus.AWAITING_APPROVAL, Stage.ACT,
                               message="Approve the bounded change task before execution")
        if action == "approve_change_task":
            if ctx.approval_status("execute") != "approved":
                return StageResult("review", decision,
                                   RunStatus.AWAITING_APPROVAL, Stage.ACT)
            return self._wait(ctx.update_change_task(decision["task_id"], "approved", {}))
        if action == "wait_for_executor":
            return StageResult("execute_change", decision, RunStatus.BLOCKED, Stage.ACT)
        return StageResult("validate_change", decision, next_stage=Stage.EVALUATE)

    @staticmethod
    def _wait(task):
        return StageResult(
            "execute_change", {"task": task}, RunStatus.BLOCKED, Stage.ACT,
            message="Executor must modify only allowed files and record actual acceptance results")

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
