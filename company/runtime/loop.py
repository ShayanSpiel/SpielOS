"""Legacy-home command adapter.

New code uses :mod:`company.runtime.engine`. Existing commands keep this adapter
so installed homes can operate while their historical tables are migrated.
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timedelta, timezone

from . import config
from .alignment import (
    active_market_outcomes, alignment_override_interaction, approval_key,
    judge_alignment, needs_alignment, resolve_originating_goal,
    priority_score, support_goal_ids, prepare_goal_topology, audit_goal_topology,
    validate_goal_topology,
    validate_support_edges,
)
from .continuation import ancestors_allow, conflicting_goal, continuation_decision
from .errors import is_transient
from .hooks import run_transition_hook
from .repair_iteration import iteration_decision, same_scope
from .contracts import approval_interaction, enrich_work_order_source, validate_goal_request
from .models import (
    ApprovalPolicy, GoalContext, Goal, GoalStatus, RetryPolicy, RunStatus,
    Stage, StageResult,
)
from .notifications import followup_payload, terminal_state_payload
from .memory import eligible_memory
from .strategy import select_strategy_context
from .registry import handlers as installed_handlers
from .service import automation_enabled
from .store import Store
from .truth import achievement_allowed, countable_evidence, hypothesis_resolution
from .util import compare as _shared_compare, parse_dt

TERMINAL = {"achieved", "abandoned", "expired"}
SUSPENDED = {RunStatus.WAITING, RunStatus.AWAITING_APPROVAL, RunStatus.BLOCKED,
             RunStatus.FAILED, RunStatus.COMPLETED}

# Map capability tokens from Department attention payloads to catalog defaults.
# Identity-owned mapping lives in the user configuration layer
# (runtime/config.py + config.user.json).
CAPABILITY_AGENTS = config.capability_agents()
CAPABILITY_WORKFLOWS = config.capability_workflows()

logger = logging.getLogger("company.runtime.loop")


class CompatibilityRuntime:
    def __init__(self, db_path: str | Path, registry: dict | None = None,
                 *, readonly: bool = False):
        self.readonly = readonly
        self.store = Store(db_path, readonly=readonly)
        self.registry = registry or installed_handlers()

    def _assert_goal_write_authority(self) -> None:
        """Never let the historical Goal loop write beside an activated clean core."""

        if self.readonly:
            return
        with self.store.connect() as connection:
            tables = {row[0] for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'")}
            count = (connection.execute("SELECT COUNT(*) FROM core_goals").fetchone()[0]
                     if "core_goals" in tables else 0)
        if count:
            raise RuntimeError(
                "clean-core authority is active; compatibility Runtime is read-only")

    def create_goal(self, **values) -> dict:
        self._assert_goal_write_authority()
        if values["owner_id"] not in self.registry:
            raise KeyError(f"goal owner '{values['owner_id']}' is not installed")
        if values.get("deadline"):
            _timestamp(values["deadline"])
        handler = self.registry[values["owner_id"]]
        values["config"] = validate_goal_request(
            handler, metric=values["metric"], config=values.get("config"))
        values.setdefault("goal_id", f"goal-{uuid.uuid4().hex[:10]}")
        values = prepare_goal_topology(self.store, values)
        validate_goal_topology(values)
        supports = support_goal_ids({"config": values["config"]})
        if supports:
            validate_support_edges(self.store, values["goal_id"], supports)
            values["config"]["supports_goal_ids"] = list(supports)
        policy = (values["config"] or {}).get("approval_policy")
        if policy is not None:
            try:
                ApprovalPolicy(policy)
            except ValueError as exc:
                raise ValueError(
                    f"unknown approval_policy: {policy!r}; "
                    f"use one of: {', '.join(item.value for item in ApprovalPolicy)}") from exc
        values.setdefault("owner_version", handler.version)
        if needs_alignment(values):
            return self._create_aligned_goal(values)
        return self.store.create_goal(**values)

    def topology_audit(self) -> dict:
        """Return a non-destructive audit and owner-reviewed migration plan."""

        return audit_goal_topology(self.store)

    def _create_aligned_goal(self, values: dict) -> dict:
        config = dict(values.get("config") or {})
        parent = None
        if values.get("parent_id"):
            try:
                parent = self.store.goal(values["parent_id"])
            except KeyError:
                parent = None
        judgment = judge_alignment(
            {**values, "config": config},
            active_outcomes=active_market_outcomes(self.store.goals()),
            parent=parent,
            originating_goal=resolve_originating_goal(self.store, values, config),
        )
        config["alignment"] = judgment
        if judgment.get("owner_override"):
            config["owner_override"] = True
        values["config"] = config
        goal = self.store.create_goal(**values)
        cycle = self.store.cycle(goal["id"])
        self.store.add_decision(goal["id"], cycle["id"], {
            "type": "alignment",
            "rationale": judgment["rationale"],
            "payload": judgment,
        })
        self.store.event(goal["id"], cycle["id"], "alignment.judged", judgment)
        if judgment["judgment"] == "defer_recommended" and not judgment.get("owner_override"):
            self._park_alignment_deferral(goal, cycle, judgment)
            return self.store.goal(goal["id"])
        return self.store.goal(goal["id"])

    def _park_alignment_deferral(self, goal: dict, cycle: dict, judgment: dict) -> None:
        self.store.set_goal_status(goal["id"], GoalStatus.PROPOSED.value)
        data = {"decision": {"action": "alignment_override", "alignment": judgment}}
        self.store.update_cycle(
            cycle["id"], stage=Stage.DECIDE.value, step="alignment",
            run_status=RunStatus.AWAITING_APPROVAL.value, resume_at=None, data=data)
        self.store.notify(goal["id"], cycle["id"], "approval_required", {
            "result": {"message": judgment["rationale"]},
            "required_user_action": (
                "Override the recommended deferral to start this work, or leave it proposed"),
            "approval_interaction": alignment_override_interaction(goal, judgment),
            "alignment": judgment,
        }, reopen=True)

    def _automation_gate(self, action: str) -> None:
        """Foreground commands honor the stop switch like the daemon tick.

        `company runner stop` writes automation.json beside the database; a
        disabled flag refuses manual once/next/retry/approve too, so a stop
        really stops every path that could advance a goal. Internal callers
        never reach here while stopped because their entry point already
        raised.
        """
        if not automation_enabled(self.store.path.parent):
            raise RuntimeError(
                f"automation is disabled (company runner stop); "
                f"`company {action}` is refused until `company runner enable`")

    def once(self, goal_id: str, holder: str | None = None) -> dict:
        self._assert_goal_write_authority()
        self._automation_gate("once")
        holder = holder or f"runtime-{uuid.uuid4().hex[:8]}"
        goal = self.store.goal(goal_id)
        if goal["goal_status"] in TERMINAL:
            return self.status(goal_id)
        if goal.get("deadline") and datetime.now(timezone.utc) >= _timestamp(goal["deadline"]):
            self.store.set_goal_status(goal_id, GoalStatus.EXPIRED.value)
            self.store.event(goal_id, self.store.cycle(goal_id)["id"], "goal.expired", {"deadline": goal["deadline"]})
            cycle = self.store.cycle(goal_id)
            terminal = terminal_state_payload(
                goal=goal, cycle=cycle, goal_status=GoalStatus.EXPIRED.value,
                message=(f"goal {goal_id} expired: deadline {goal['deadline']} "
                         "passed before the target was reached"))
            self.store.notify(goal_id, cycle["id"], "goal_expired", terminal,
                              reopen=True)
            self.store.notify(goal_id, cycle["id"], "goal_completed_followup",
                              followup_payload(terminal, goal=goal,
                                               goal_status=GoalStatus.EXPIRED.value),
                              reopen=True)
            return self.status(goal_id)
        if goal["goal_status"] == "proposed":
            raise RuntimeError(
                f"goal {goal_id} is proposed; Director recommended deferral. "
                "Approve or resume to override — that record is not strategic justification")
        if goal["goal_status"] != "active":
            raise RuntimeError(f"goal {goal_id} is {goal['goal_status']}; resume it before running")
        if self.store.cycle(goal_id)["run_status"] == "completed":
            decision = self.continuation_decision(goal_id)
            if not decision["eligible"]:
                return self.status(goal_id)
            self.next(goal_id, automatic=True)
        elif self.store.cycle(goal_id)["run_status"] in {"blocked", "failed"}:
            decision = self.repair_iteration_decision(goal_id)
            if not decision["eligible"]:
                return self.status(goal_id)
            self.retry(goal_id, automatic=True)
        if not self.store.acquire(goal_id, holder):
            raise RuntimeError(f"goal {goal_id} is already running in another client")
        try:
            before = self._state_signature(goal_id)
            result = self._advance(goal_id, holder)
            after = self._state_signature(goal_id)
            if before != after:
                self._return_to_dependents(goal_id)
            return result
        finally:
            self.store.release(goal_id, holder)

    def _approval_status(self, goal: dict, cycle: dict, key: str) -> str | None:
        """Policy-aware read of one approval key.

        `per_action` (the default) keeps today's behavior: every key is read
        from the store. `everything_approved` reads every key as "approved" so
        guarded execute actions never park. `per_run` reads every key as
        "approved" once the run-level key (approval_key(cycle)) is approved in
        the store — the first approval carries the rest of the Run. The
        alignment_override gate is excluded: it is an owner judgment, not an
        execute action, and policies never bypass it.
        """
        run_key = approval_key(cycle)
        if run_key == "alignment_override":
            return self.store.approval(goal["id"], cycle["id"], key)
        policy = self._effective_approval_policy(goal)
        if policy == ApprovalPolicy.EVERYTHING_APPROVED.value:
            return "approved"
        if (policy == ApprovalPolicy.PER_RUN.value
                and self.store.approval(goal["id"], cycle["id"], run_key) == "approved"):
            return "approved"
        return self.store.approval(goal["id"], cycle["id"], key)

    def _effective_approval_policy(self, goal: dict) -> str | None:
        """Local policy, plus durable authority inherited from ancestors.

        Only ``everything_approved`` inherits. A per-Run grant belongs to the
        exact Run that received it and never leaks into child work.
        """

        current = goal
        local_policy = (goal.get("config") or {}).get("approval_policy")
        while current:
            policy = (current.get("config") or {}).get("approval_policy")
            if policy == ApprovalPolicy.EVERYTHING_APPROVED.value:
                return policy
            parent_id = current.get("parent_id")
            if not parent_id:
                break
            try:
                current = self.store.goal(parent_id)
            except KeyError:
                break
        return local_policy

    def _set_approval_policy(self, goal_id: str, policy: str) -> None:
        """Persist the Goal's approval mode in config; reject unknown modes."""
        try:
            ApprovalPolicy(policy)
        except ValueError as exc:
            raise ValueError(
                f"unknown approval_policy: {policy!r}; "
                f"use one of: {', '.join(item.value for item in ApprovalPolicy)}") from exc
        goal = self.store.goal(goal_id)
        config = dict(goal.get("config") or {})
        config["approval_policy"] = policy
        self.store.update_goal_config(goal_id, config)
        self.store.event(goal_id, self.store.cycle(goal_id)["id"],
                         "goal.approval_policy", {"policy": policy})

    def _advance(self, goal_id: str, holder: str) -> dict:
        start_sequence = self.store.cycle(goal_id)["sequence"]
        for _ in range(8):
            row = self.store.goal(goal_id)
            cycle = self.store.cycle(goal_id)
            if cycle["run_status"] == "waiting":
                due = parse_dt(cycle.get("resume_at"))
                if not due or datetime.now(timezone.utc) < due:
                    return self.status(goal_id)
            if cycle["run_status"] in {"blocked", "failed"}:
                return self.status(goal_id)
            if cycle["run_status"] == "completed":
                return self.status(goal_id)
            if (cycle["run_status"] == "awaiting_approval"
                    and self._approval_status(row, cycle, approval_key(cycle)) != "approved"):
                return self.status(goal_id)

            handler = self.registry[row["owner_id"]]
            goal = Goal(id=row["id"], name=row["name"], owner_id=row["owner_id"],
                        metric=row["metric"], operator=row["operator"], target=row["target"],
                        deadline=row["deadline"], parent_id=row["parent_id"],
                        goal_status=row["goal_status"], config=row["config"])
            children = []
            for child in self.store.goals(parent_id=goal_id):
                child_cycle = self.store.cycle(child["id"])
                child_evaluation = self.store.latest_evaluation_for_goal(child["id"])
                evaluated_run_id = ((child_evaluation or {}).get("run_id")
                                    or child_cycle["id"])
                children.append({**child, "cycle": child_cycle,
                                 "run": self.store.run(child_cycle["id"]),
                                 "evaluation": child_evaluation,
                                 "evidence": tuple(self.store.evidence(evaluated_run_id)),
                                 "history": self.store.goal_run_history(child["id"], limit=5)})
            run = self.store.run(cycle["id"])
            ancestor_goal_ids = []
            ancestor_id = goal.parent_id
            while ancestor_id:
                ancestor = self.store.goal(ancestor_id)
                ancestor_goal_ids.append(ancestor["id"])
                ancestor_id = ancestor.get("parent_id")
            local_memory = self.store.memories(
                goal.owner_id, goal.id, tuple(ancestor_goal_ids))
            memory_topics = goal.config.get("memory_topics") or ()
            if not isinstance(memory_topics, (list, tuple)):
                memory_topics = ()
            shared_memory = self.store.shared_memories(
                goal.owner_id, tuple(str(item) for item in memory_topics if item), limit=10)
            directives = self.store.directives(
                goal_ids=tuple((goal.id, *ancestor_goal_ids)), limit=20)
            context = GoalContext(
                goal=goal, cycle={**cycle, "run": run, "children": tuple(children),
                                  "evidence": tuple(self.store.evidence(cycle["id"])),
                                  "evaluation": self.store.evaluation(cycle["id"]),
                                  "change_tasks": tuple(self.store.change_tasks_for_run(cycle["id"]))},
                memory=tuple((*local_memory, *shared_memory)),
                approval_status=lambda key, g=row, c=cycle: self._approval_status(g, c, key),
                dispatch_goal=lambda child_id: self.once(child_id, holder=f"{holder}:{goal_id}"),
                create_child_goal=lambda spec, p=goal_id, r=cycle["id"]: self._create_child(p, r, spec),
                create_change_task=lambda spec, g=goal_id, r=cycle["id"]: self.store.create_change_task(
                    goal_id=g, run_id=r, **spec),
                update_change_task=lambda task_id, status, result: self.store.complete_change_task(
                    task_id, status, result),
                strategy=select_strategy_context(goal),
                directives=directives)
            try:
                result = self._call(handler, Stage(cycle["stage"]), context)
            except Exception as exc:
                result = self._failure_result(goal, cycle, exc)
            if Stage(cycle["stage"]) is Stage.EVALUATE and result.run_status is RunStatus.IDLE:
                result.run_status = RunStatus.COMPLETED
            self._persist(goal, cycle, result)
            # Generic post-transition hook (website decoupling): replaces the
            # hardcoded /live snapshot + git push pipeline. No-op unless
            # SPIELOS_TRANSITION_HOOK is set; best-effort, hard-bounded.
            run_transition_hook("goal_transition", {
                "goal_id": goal_id,
                "run_id": cycle["id"],
                "step": result.step,
                "run_status": result.run_status.value,
                "goal_status": self.store.goal(goal_id)["goal_status"],
            })
            current = self.store.cycle(goal_id)
            if result.run_status in SUSPENDED or self.store.goal(goal_id)["goal_status"] in TERMINAL:
                return self.status(goal_id)
            if current["sequence"] != start_sequence:
                return self.status(goal_id)
        raise RuntimeError("goal owner exceeded the eight-transition safety limit")

    @staticmethod
    def _call(handler, stage, ctx):
        data = ctx.cycle.get("data") or {}
        if stage is Stage.OBSERVE:
            return handler.observe(ctx)
        if stage is Stage.DECIDE:
            return handler.decide(ctx, data.get("observation") or {})
        if stage is Stage.ACT:
            return handler.act(ctx, data.get("decision") or {})
        return handler.evaluate(ctx, data.get("action_result") or {})

    def _failure_result(self, goal, cycle, exc) -> StageResult:
        """Translate a handler exception into a persisted loop outcome.

        A transient provider failure (rate limit, timeout, 5xx, DNS — see
        ``company.runtime.errors``) raised by an ACT action with a configured
        ``retry_policy`` parks the run in WAITING with ``resume_at`` set to
        now + backoff, so the next automatic Runner tick retries the same
        ACT step with no manual ``company retry``. Every other case keeps
        today's manual-retry world: the run is marked FAILED. Exceptions at
        OBSERVE/DECIDE/EVALUATE are re-raised unchanged.
        """
        if Stage(cycle["stage"]) is not Stage.ACT:
            raise
        error = {"type": type(exc).__name__, "message": str(exc)}
        policy = RetryPolicy.from_config(goal.config)
        if is_transient(exc) and policy is not None:
            data = dict(cycle.get("data") or {})
            previous = data.get("action_result") or {}
            previous_retry = previous.get("retry") if isinstance(previous, dict) else {}
            failures = int((previous_retry or {}).get("failures") or 0) + 1
            if failures <= policy.max_retries:
                resume_at = (datetime.now(timezone.utc)
                             + timedelta(seconds=policy.backoff_seconds)).isoformat()
                return StageResult(
                    step=cycle["step"], next_stage=Stage.ACT,
                    run_status=RunStatus.WAITING, resume_at=resume_at,
                    message=(f"Transient {type(exc).__name__} on attempt {failures}; "
                             f"scheduled retry in {policy.backoff_seconds:g}s"),
                    payload={"error": error, "retry": {
                        "failures": failures, "max_retries": policy.max_retries,
                        "resume_at": resume_at}})
        return StageResult(
            step=cycle["step"], run_status=RunStatus.FAILED,
            message=f"{type(exc).__name__}: {exc}",
            payload={"error": error})

    def _persist(self, goal, cycle, result):
        stage = Stage(cycle["stage"])
        next_stage = result.next_stage or {
            Stage.OBSERVE: Stage.DECIDE, Stage.DECIDE: Stage.ACT,
            Stage.ACT: Stage.EVALUATE, Stage.EVALUATE: Stage.OBSERVE}[stage]
        # Evidence-producing actions must re-enter through OBSERVE. Jumping
        # straight from ACT to DECIDE would reuse the observation captured
        # before that evidence existed, so graph interpreters can select and
        # execute the same machine node repeatedly within one advance.
        if result.evidence and result.step == "machine" and next_stage is Stage.DECIDE:
            next_stage = Stage.OBSERVE
        data = dict(cycle.get("data") or {})
        data[{Stage.OBSERVE: "observation", Stage.DECIDE: "decision",
              Stage.ACT: "action_result", Stage.EVALUATE: "evaluation"}[stage]] = result.payload
        if stage is Stage.EVALUATE:
            data["next_run"] = dict(result.next_run or {})
        if result.goal_status is GoalStatus.ACHIEVED:
            run = self.store.run(cycle["id"])
            children = []
            for child in self.store.goals(parent_id=goal.id):
                child_cycle = self.store.cycle(child["id"])
                children.append({
                    **child, "run": self.store.run(child_cycle["id"]),
                    "evaluation": self.store.latest_evaluation_for_goal(child["id"]),
                })
            if not achievement_allowed(goal, run, result.evaluation, children=children):
                result.goal_status = None
                if result.evaluation is not None:
                    result.evaluation["goal_met"] = False
                    result.evaluation["verdict"] = result.evaluation.get("verdict") or "continue"
        goal_status = result.goal_status.value if result.goal_status else goal.goal_status
        # Audit-trail ordering (bug 8): the justifying PROOF — learnings,
        # evidence, decisions, evaluations — is persisted BEFORE the terminal
        # goal status, so the record never shows an achievement preceding its
        # evidence.
        run = self.store.run(cycle["id"])
        evidence_refs = {}
        for evidence in (result.evidence or ()):
            persisted = self.store.add_evidence(
                goal.id, cycle["id"], evidence["kind"],
                evidence.get("source", goal.owner_id), evidence.get("payload", {}),
                evidence.get("validity", run["evidence_validity"]))
            if evidence.get("ref"):
                evidence_refs[str(evidence["ref"])] = persisted["id"]
        # A reusable learning may cite evidence produced by this same result.
        # Persist evidence first, then evaluate the claim against the complete
        # current-Run evidence set.
        current_evidence = list(self.store.evidence(cycle["id"]))
        for learning in (result.learnings or ()):
            normalized = dict(learning)
            refs = normalized.pop("evidence_refs", ())
            if isinstance(refs, (list, tuple)):
                resolved = [evidence_refs[str(ref)] for ref in refs
                            if str(ref) in evidence_refs]
                normalized["evidence_ids"] = list(dict.fromkeys([
                    *(normalized.get("evidence_ids") or ()), *resolved]))
            memory = eligible_memory(normalized, current_evidence, goal, run)
            if memory:
                self.store.learn(goal.owner_id, goal.id, memory["claim"],
                                 memory["evidence"], memory["confidence"])
                self.store.record_experiment_memory(
                    owner_id=goal.owner_id,
                    goal_id=goal.id,
                    run_id=cycle["id"],
                    claim=memory["claim"],
                    verdict=memory["verdict"],
                    context=memory["context"],
                    evidence_ids=list(memory["evidence"]["evidence_ids"]),
                    confidence=memory["confidence"],
                )
        if result.decision:
            decision = dict(result.decision)
            requested = list(decision.get("evidence_ids") or ())
            allowed = self._decision_evidence_scope(goal.id, cycle["id"])
            decision["evidence_ids"] = [item for item in requested if item in allowed]
            self.store.add_decision(goal.id, cycle["id"], decision)
        if result.evaluation:
            evaluation = self.store.add_evaluation(goal.id, cycle["id"], result.evaluation)
            hypothesis_status = hypothesis_resolution(goal, run, result.evaluation)
            if (hypothesis_status
                    and self.store.hypothesis(run["hypothesis_id"])["status"] == "active"):
                hypothesis = self.store.resolve_hypothesis(
                    run["hypothesis_id"], hypothesis_status)
                self.store.event(goal.id, cycle["id"], "hypothesis.resolved", {
                    "hypothesis_id": hypothesis["id"],
                    "status": hypothesis["status"],
                    "evaluation_id": evaluation["id"],
                })
        # Proof persisted; now the state transitions.
        self.store.set_goal_status(goal.id, goal_status)
        self.store.update_cycle(cycle["id"], stage=next_stage.value, step=result.step,
                                run_status=result.run_status.value, resume_at=result.resume_at, data=data)
        validity = result.evaluation.get("validity") if result.evaluation else None
        contamination = result.evaluation.get("contamination_reason") if result.evaluation else None
        self.store.update_run(cycle["id"], status=result.run_status.value,
                              validity=validity, contamination_reason=contamination)
        self.store.resolve_actionable_notifications(goal.id, cycle["id"])
        self.store.event(goal.id, cycle["id"], f"{stage.value.lower()}.{result.step}", {
            "status": result.run_status.value, "next_stage": next_stage.value,
            "message": result.message, "payload": result.payload})
        work_order = self._maybe_open_work_order(goal, cycle, result)
        payload = self._notification_payload(goal, cycle, result, next_stage, work_order)
        if result.run_status is RunStatus.AWAITING_APPROVAL:
            self.store.notify(goal.id, cycle["id"], "approval_required", payload,
                              reopen=True)
        elif result.attention:
            self.store.notify(goal.id, cycle["id"], "action_required", payload,
                              reopen=True)
        elif result.run_status in (RunStatus.BLOCKED, RunStatus.FAILED):
            self.store.notify(goal.id, cycle["id"], result.run_status.value, payload,
                              reopen=True)
        if goal_status in TERMINAL:
            terminal = self._notification_payload(
                goal, cycle, result, next_stage, work_order)
            self.store.notify(goal.id, cycle["id"], f"goal_{goal_status}", terminal,
                              reopen=True)
            # Terminal follow-up (goal-chat-visible-supervision-20260815): the
            # goal_<status> row alone goes silent once delivered; a follow-up
            # carrying a recommended next action surfaces a concrete step into
            # the chat instead.
            self.store.notify(goal.id, cycle["id"], "goal_completed_followup",
                              followup_payload(terminal, goal=goal,
                                               goal_status=goal_status),
                              reopen=True)
        elif stage is Stage.EVALUATE and result.run_status is RunStatus.COMPLETED:
            self.store.notify(goal.id, cycle["id"], "run_completed",
                              self._notification_payload(goal, cycle, result, next_stage, work_order),
                              reopen=True)

    def _decision_evidence_scope(self, goal_id: str, run_id: str) -> set[str]:
        """Evidence reachable from the current Run, evaluated children, or ancestors."""

        allowed = {item["id"] for item in self.store.evidence(run_id)}
        for child in self.store.goals(parent_id=goal_id):
            history = self.store.goal_run_history(child["id"], limit=5)
            if history:
                for item in history:
                    allowed.update(row["id"] for row in item["evidence"])
            else:
                child_run_id = self.store.cycle(child["id"])["id"]
                allowed.update(item["id"] for item in self.store.evidence(child_run_id))
        parent_id = self.store.goal(goal_id).get("parent_id")
        while parent_id:
            parent_cycle = self.store.cycle(parent_id)
            parent_evaluation = self.store.latest_evaluation_for_goal(parent_id)
            parent_run_id = ((parent_evaluation or {}).get("run_id")
                             or parent_cycle["id"])
            allowed.update(item["id"] for item in self.store.evidence(parent_run_id))
            parent_id = self.store.goal(parent_id).get("parent_id")
        return allowed

    def _maybe_open_work_order(self, goal, cycle, result):
        """Persist a durable Agent assignment when a run parks on Agent work.

        Approvals are not work orders. Only blocked runs that name an Agent
        (or a known capability / Connection handoff) create one. Missing Agent
        or evidence kinds are filled from the Department Workflow catalog.
        """

        if result.run_status is not RunStatus.BLOCKED:
            return None
        attention = dict(result.attention or {})
        payload = result.payload if isinstance(result.payload, dict) else {}
        source = {**payload, **attention}
        connection_request = source.get("connection_request")
        if not isinstance(connection_request, dict):
            connection_request = None

        if source.get("capability") in CAPABILITY_WORKFLOWS and not source.get("workflow_id"):
            source["workflow_id"] = CAPABILITY_WORKFLOWS[source["capability"]]
        if source.get("capability") in CAPABILITY_AGENTS and not source.get("agent_id"):
            source["agent_id"] = CAPABILITY_AGENTS[source["capability"]]
        if connection_request is not None:
            source.setdefault("agent_id", connection_request.get("agent_id") or "publisher")
            if connection_request.get("required_evidence") and not source.get("accepted_evidence_kinds"):
                source["accepted_evidence_kinds"] = [connection_request["required_evidence"]]

        # A blocked machine gate is a validation failure, not an Agent
        # assignment. Do not let catalog enrichment turn a missing ICP or
        # failed editorial check into a generic strategist work order.
        if source.get("action") == "run_machine_step" and connection_request is None \
                and not source.get("agent_id") and not source.get("employee_id"):
            return None

        handler = self.registry.get(goal.owner_id)
        goal_row = {"metric": goal.metric, "config": goal.config, "owner_id": goal.owner_id}
        source = enrich_work_order_source(handler, goal_row, source)

        agent_id = source.get("agent_id") or source.get("employee_id")
        if not agent_id:
            return None

        accepts = list(source.get("accepted_evidence_kinds") or source.get("accepts_evidence") or [])
        needed = int(source.get("needed") or source.get("needed_leads") or 1)
        brief = {
            "goal_id": goal.id,
            "goal_name": goal.name,
            "owner_id": goal.owner_id,
            "metric": goal.metric,
            "operator": goal.operator,
            "target": goal.target,
            "message": result.message,
            "action": source.get("action") or "request_agent",
            "capability": source.get("capability") or (
                connection_request.get("capability") if connection_request else None),
            "skill_ids": source.get("skill_ids") or [],
            "connection_ids": source.get("connection_ids") or [],
            "workflow_id": source.get("workflow_id") or goal.config.get("workflow"),
            "step_id": source.get("step_id") or result.step,
            "required_user_action": source.get("required_user_action") or (
                f"{agent_id} must produce {needed} validated artifact(s)"),
            "next_trigger": source.get("next_trigger") or f"company retry {goal.id}",
            "connection_request": connection_request,
            "accepted_evidence_kinds": accepts,
            # Preserve the complete bounded request in the durable assignment.
            # An Agent must not have to infer the ICP from the Goal name or
            # rediscover it from an unrelated local file.
            "goal_config": dict(goal.config or {}),
            "content_request": dict((goal.config or {}).get("content_request") or {})
                if isinstance((goal.config or {}).get("content_request"), dict) else {},
            # The Interpreter places bounded, selected context in the action
            # payload. Preserve it in the persisted assignment; otherwise
            # cross-Department Memory and Strategy only affect an audit row.
            "memory": list(source.get("memory") or ()),
            "strategy": dict(source.get("strategy") or {}),
            "strategy_context": dict(source.get("strategy") or {}),
        }
        return self.store.open_work_order(
            goal_id=goal.id, run_id=cycle["id"], agent_id=agent_id,
            needed=needed, accepts_evidence=accepts,
            workflow_id=brief["workflow_id"],
            step_id=source.get("step_id") or result.step, brief=brief)

    def _notification_payload(self, goal, cycle, result, next_stage, work_order=None):
        evaluation = result.evaluation or {}
        attention = result.attention or {}
        goal_met = bool(evaluation.get("goal_met")) or result.goal_status is GoalStatus.ACHIEVED
        payload = {
            "goal": {"id": goal.id, "name": goal.name, "metric": goal.metric,
                     "operator": goal.operator, "target": goal.target},
            "run": {"id": cycle["id"], "sequence": cycle["sequence"],
                    "owner_id": goal.owner_id, "owner_version": self.registry[goal.owner_id].version},
            "runtime": {"stage": next_stage.value, "step": result.step,
                        "status": result.run_status.value},
            "result": {"message": result.message, "verdict": evaluation.get("verdict"),
                       "goal_met": goal_met,
                       "metrics": evaluation.get("metrics", result.payload)},
            "next_experiment": evaluation.get("next_experiment", {}),
            "next_trigger": attention.get("next_trigger"),
            "required_user_action": attention.get("required_user_action") or (
                "Approve the prepared action" if result.run_status is RunStatus.AWAITING_APPROVAL else None),
            "attention": attention,
            "artifact": result.payload.get("preview_path") if isinstance(result.payload, dict) else None,
        }
        if result.run_status is RunStatus.AWAITING_APPROVAL:
            payload["approval_interaction"] = approval_interaction(goal, result)
        if work_order:
            payload["work_order_id"] = work_order["id"]
            payload["work_order"] = {
                "id": work_order["id"], "agent_id": work_order["agent_id"],
                "needed": work_order["needed"],
                "accepts_evidence": work_order.get("accepts_evidence") or [],
                "status": work_order["status"],
            }
            if not payload.get("required_user_action"):
                payload["required_user_action"] = (
                    f"{work_order['agent_id']} must produce "
                    f"{work_order['needed']} accepted artifact(s)")
            if not payload.get("next_trigger"):
                payload["next_trigger"] = f"company retry {goal.id}"
        return payload

    def _create_child(self, parent_goal_id: str, parent_run_id: str, spec: dict) -> dict:
        required = ("name", "owner_id", "metric", "operator", "target")
        missing = [key for key in required if key not in spec]
        if missing:
            raise ValueError(f"child goal spec missing: {', '.join(missing)}")
        return self.create_goal(
            name=spec["name"], owner_id=spec["owner_id"], metric=spec["metric"],
            operator=spec["operator"], target=spec["target"], deadline=spec.get("deadline"),
            parent_id=parent_goal_id, config=spec.get("config", {}),
            run_type=spec.get("run_type", "execution"), parent_run_id=parent_run_id,
            triggered_by_run_id=parent_run_id, hypothesis=spec.get("hypothesis"),
            controlled_variables=spec.get("controlled_variables", {}),
            changed_variables=spec.get("changed_variables", {}),
            evidence_validity=spec.get("evidence_validity", "business"),
            resume_run_id=spec.get("resume_run_id"))

    def approve(self, goal_id: str, note: str = "", scope: str | None = None) -> dict:
        """Approve the parked action; with ``scope`` also set the Goal policy.

        ``scope`` is an ApprovalPolicy mode ("per_action", "per_run",
        "everything_approved"). ``per_run`` / ``everything_approved`` record
        ``config["approval_policy"]`` on the Goal in addition to granting the
        current action; ``per_action`` (or no scope) never changes the policy.
        """
        self._assert_goal_write_authority()
        self._automation_gate("approve")
        cycle = self.store.cycle(goal_id)
        if cycle["run_status"] != "awaiting_approval":
            if scope == ApprovalPolicy.EVERYTHING_APPROVED.value:
                self._set_approval_policy(goal_id, scope)
                return self.status(goal_id)
            raise RuntimeError(f"goal is not awaiting approval (status: {cycle['run_status']})")
        if approval_key(cycle) == "alignment_override":
            result = self._apply_alignment_override(goal_id, note)
            if scope:
                self._set_approval_policy(goal_id, scope)
            return result
        action = (cycle.get("data") or {}).get("action_result") or {}
        decision = (cycle.get("data") or {}).get("decision") or {}
        step_id = action.get("step_id") or decision.get("step_id")
        self.store.approve(goal_id, cycle["id"], "execute", note)
        if step_id:
            # Explicit Workflow approval nodes get their own key. The run-level
            # execute grant still prevents follow-up prompts for ordinary steps.
            self.store.approve(goal_id, cycle["id"], f"step:{step_id}", note)
        if scope:
            self._set_approval_policy(goal_id, scope)
        return self.status(goal_id)

    def _apply_alignment_override(self, goal_id: str, note: str = "") -> dict:
        goal = self.store.goal(goal_id)
        cycle = self.store.cycle(goal_id)
        config = dict(goal.get("config") or {})
        alignment = dict(config.get("alignment") or {})
        alignment["owner_override"] = True
        if note:
            alignment["override_note"] = note
        config["owner_override"] = True
        config["alignment"] = alignment
        self.store.update_goal_config(goal_id, config)
        self.store.approve(goal_id, cycle["id"], "alignment_override", note)
        self.store.add_decision(goal_id, cycle["id"], {
            "type": "owner_override",
            "rationale": "Owner overrode Director deferral; this is not strategic justification",
            "payload": alignment,
        })
        self.store.event(goal_id, cycle["id"], "alignment.overridden", alignment)
        if goal["goal_status"] == "proposed" or goal["owner_id"] == "system-improvement":
            self.store.set_goal_status(goal_id, GoalStatus.ACTIVE.value)
            self.store.update_cycle(
                cycle["id"], stage=Stage.OBSERVE.value, step="collect",
                run_status=RunStatus.IDLE.value, resume_at=None, data={})
            self.store.resolve_actionable_notifications(goal_id, cycle["id"])
        return self.status(goal_id)

    def set_goal_status(self, goal_id: str, status: GoalStatus) -> dict:
        self._assert_goal_write_authority()
        previous = self.store.goal(goal_id)["goal_status"]
        if (status is GoalStatus.ACTIVE and previous == "proposed"
                and ((self.store.goal(goal_id).get("config") or {}).get("alignment") or {})
                .get("judgment") == "defer_recommended"):
            return self._apply_alignment_override(goal_id, note="resume")
        self.store.set_goal_status(goal_id, status.value)
        if status is GoalStatus.ACTIVE and previous in TERMINAL:
            self.store.new_cycle(goal_id)
        self.store.event(goal_id, self.store.cycle(goal_id)["id"], f"goal.{status.value}", {})
        if status.value in TERMINAL:
            # Terminal follow-up (goal-chat-visible-supervision-20260815):
            # abandoned/expired/achieved goals emit goal_<status> plus a
            # follow-up carrying a recommended next action (owner abandon and
            # deadline expiry do not pass through _persist, so they get the
            # same notification pair here).
            row = self.store.goal(goal_id)
            cycle = self.store.cycle(goal_id)
            terminal = terminal_state_payload(
                goal=row, cycle=cycle, goal_status=status.value,
                message=f"goal {goal_id} reached {status.value}")
            self.store.notify(goal_id, cycle["id"], f"goal_{status.value}", terminal,
                              reopen=True)
            self.store.notify(goal_id, cycle["id"], "goal_completed_followup",
                              followup_payload(terminal, goal=row,
                                               goal_status=status.value),
                              reopen=True)
        if status in {GoalStatus.PAUSED, GoalStatus.ABANDONED, GoalStatus.EXPIRED, GoalStatus.ACHIEVED}:
            self._halt_descendants(goal_id)
            if status is GoalStatus.PAUSED:
                self.store.cancel_work_orders(goal_id, include_claimed=True)
        if previous != status.value:
            self._return_to_dependents(goal_id)
        return self.status(goal_id)

    def _halt_descendants(self, ancestor_id: str) -> None:
        for child in self.store.goals(parent_id=ancestor_id):
            if child["goal_status"] != "active":
                continue
            self.store.set_goal_status(child["id"], GoalStatus.PAUSED.value)
            self.store.cancel_work_orders(child["id"], include_claimed=True)
            self.store.event(child["id"], self.store.cycle(child["id"])["id"],
                             "goal.paused", {"reason": f"ancestor_halted:{ancestor_id}"})
            self._halt_descendants(child["id"])

    def _return_to_parent(self, child_id: str) -> None:
        child = self.store.goal(child_id)
        parent_id = child.get("parent_id")
        if not parent_id:
            return
        try:
            parent = self.store.goal(parent_id)
        except KeyError:
            return
        if parent["goal_status"] != "active":
            return
        child_cycle = self.store.cycle(child_id)
        reason = f"child_changed:{child_id}"
        self.store.wake_goal(parent_id, reason)
        if child["goal_status"] == "achieved":
            self._resume_originating(child, child_cycle)
            return
        if child["goal_status"] in {"paused", "abandoned"} or child_cycle["run_status"] in {
                "failed", "blocked"}:
            parent_cycle = self.store.cycle(parent_id)
            self.store.notify(parent_id, parent_cycle["id"], "action_required", {
                "result": {"message": f"Child {child_id} needs attention"},
                "required_user_action": "Review the child; the parent metric is not satisfied",
                "child_id": child_id,
                "child_status": child["goal_status"],
                "child_run_status": child_cycle["run_status"],
            }, reopen=True)

    def _return_to_dependents(self, source_id: str) -> None:
        """Wake the control parent and every semantically supported Goal.

        Waking means re-observe its own metric. It never copies success,
        evidence, or approval from the source Goal.
        """

        self._return_to_parent(source_id)
        source = self.store.goal(source_id)
        for target_id in support_goal_ids(source):
            try:
                target = self.store.goal(target_id)
            except KeyError:
                continue
            if target["goal_status"] == "active":
                self.store.wake_goal(target_id, f"support_changed:{source_id}")

    def link_support(self, goal_id: str, target_id: str) -> dict:
        self._assert_goal_write_authority()
        goal = self.store.goal(goal_id)
        targets = validate_support_edges(
            self.store, goal_id, (*support_goal_ids(goal), target_id))
        config = dict(goal.get("config") or {})
        config["supports_goal_ids"] = list(targets)
        self.store.update_goal_config(goal_id, config)
        self.store.event(goal_id, self.store.cycle(goal_id)["id"],
                         "goal.support_linked", {"supports_goal_id": target_id})
        self.store.wake_goal(target_id, f"support_linked:{goal_id}")
        return self.status(goal_id)

    def _resume_originating(self, child: dict, child_cycle: dict) -> None:
        child_run = self.store.run(child_cycle["id"])
        resume_id = (child_run.get("resume_run_id")
                     or (child.get("config") or {}).get("originating_run_id"))
        if not resume_id:
            return
        try:
            origin = self.store.run(resume_id)
            origin_goal_id = origin["goal_id"]
        except KeyError:
            return
        origin_goal = self.store.goal(origin_goal_id)
        if origin_goal["goal_status"] != "active":
            return
        origin_cycle = self.store.cycle(origin_goal_id)
        # A repair resumes one exact historical run. If the originating Goal
        # has already moved beyond it, the repair-return hook is an idempotent
        # no-op rather than a second continuation.
        if origin_cycle["id"] != resume_id:
            return
        if origin_cycle["run_status"] == "completed":
            evaluation = self.store.evaluation(resume_id)
            if evaluation and evaluation.get("goal_met"):
                return
            # Technical repair recovery is deliberately not normal automatic
            # continuation. The originating run is commonly contaminated or
            # invalid, which correctly makes continuation_decision ineligible.
            # Successful repair instead creates a fresh retest with the same
            # business snapshot and controlled/changed variables, while the
            # current owner version records the repaired implementation.
            metadata = {
                "run_type": origin["run_type"],
                "parent_run_id": resume_id,
                "triggered_by_run_id": child_cycle["id"],
                "owner_version": self.registry[origin_goal["owner_id"]].version,
                "config_snapshot": origin["config_snapshot"],
                "controlled_variables": origin["controlled_variables"],
                "changed_variables": origin["changed_variables"],
                "evidence_validity": origin["evidence_validity"],
            }
            created = self.store.new_cycle(origin_goal_id, metadata)
            self.store.event(origin_goal_id, created["id"], "run.started", {
                "previous_run_id": resume_id,
                "reason": "retest_after_technical_repair",
                "repair_goal_id": child["id"],
                "repair_run_id": child_cycle["id"],
                "business_variables_preserved": True,
            })
            return
        self.store.wake_goal(origin_goal_id, f"resume_run:{resume_id}")

    def repair_iteration_decision(self, goal_id: str) -> dict:
        goal = self.store.goal(goal_id)
        cycle = self.store.cycle(goal_id)
        tasks = self.store.change_tasks_for_run(cycle["id"])
        return iteration_decision(
            goal=goal, cycle=cycle,
            evaluation=self.store.evaluation(cycle["id"]),
            tasks_for_goal=self.store.change_tasks_for_goal(goal_id),
            last_task=tasks[-1] if tasks else None,
        )

    def retry(self, goal_id: str, *, automatic: bool = False) -> dict:
        self._assert_goal_write_authority()
        self._automation_gate("retry")
        cycle = self.store.cycle(goal_id)
        if cycle["run_status"] not in {"blocked", "failed"}:
            raise RuntimeError(f"retry requires blocked or failed status (current: {cycle['run_status']})")
        tasks = self.store.change_tasks_for_run(cycle["id"])
        last_task = tasks[-1] if tasks else None
        evaluation = self.store.evaluation(cycle["id"])
        if last_task and last_task["status"] == "failed" and evaluation:
            if automatic:
                decision = self.repair_iteration_decision(goal_id)
                if not decision["eligible"]:
                    raise RuntimeError(f"automatic repair iteration refused: {decision['reason']}")
            previous = self.store.run(cycle["id"])
            created = self.store.new_cycle(goal_id, {
                "run_type": previous["run_type"],
                "evidence_validity": previous["evidence_validity"],
            })
            if (self.store.approval(goal_id, cycle["id"], "execute") == "approved"
                    and same_scope(self.store.goal(goal_id).get("config") or {}, last_task)):
                self.store.approve(goal_id, created["id"], "execute",
                                   "carried same-scope approval")
            self.store.event(goal_id, created["id"], "run.started", {
                "previous_run_id": cycle["id"], "reason": "new_change_attempt",
                "failed_task_id": last_task["id"], "automatic": automatic})
            return self.status(goal_id)
        # Complete work orders whose evidence is already present before the run restarts.
        self.store.refresh_work_orders_for_run(goal_id, cycle["id"])
        # Capability handoffs (no typed evidence kinds) treat explicit retry as completion.
        for order in self.store.work_orders(status="active", goal_id=goal_id, run_id=cycle["id"], limit=100):
            if not (order.get("accepts_evidence") or []):
                self.store.complete_work_order(
                    order["id"], [], agent_id=order.get("claimed_by"))
        self.store.update_cycle(cycle["id"], stage="OBSERVE", step="collect",
                                run_status="idle", resume_at=None, data={})
        self.store.resolve_actionable_notifications(goal_id, cycle["id"])
        self.store.event(goal_id, cycle["id"], "run.retried", {})
        return self.status(goal_id)

    def continuation_decision(self, goal_id: str) -> dict:
        goal = self.store.goal(goal_id)
        cycle = self.store.cycle(goal_id)
        return continuation_decision(
            goal=goal, cycle=cycle,
            evaluation=self.store.evaluation(cycle["id"]),
            run_count=cycle.get("sequence") or 1,
            ancestor_active=ancestors_allow(self.store, goal),
            conflicting=conflicting_goal(self.store, goal),
        )

    def next(self, goal_id: str, *, automatic: bool = False) -> dict:
        self._assert_goal_write_authority()
        self._automation_gate("next")
        goal = self.store.goal(goal_id)
        if goal["goal_status"] != "active":
            raise RuntimeError(f"next run requires an active goal (current: {goal['goal_status']})")
        cycle = self.store.cycle(goal_id)
        if cycle["run_status"] != "completed":
            raise RuntimeError(f"next run requires a completed run (current: {cycle['run_status']})")
        evaluation = self.store.evaluation(cycle["id"])
        if not evaluation:
            raise RuntimeError("completed run has no evaluation")
        if evaluation["goal_met"]:
            raise RuntimeError("goal is already met; do not start another run")
        if automatic:
            decision = self.continuation_decision(goal_id)
            if not decision["eligible"]:
                raise RuntimeError(f"automatic continuation refused: {decision['reason']}")
        if goal["owner_id"] == "director":
            for child in self.store.goals(parent_id=goal_id):
                child_cycle = self.store.cycle(child["id"])
                if child["goal_status"] == "active" and child_cycle["run_status"] == "completed":
                    child_decision = self.continuation_decision(child["id"])
                    if child_decision["eligible"] or not automatic:
                        self.next(child["id"], automatic=automatic)
        metadata = dict((cycle.get("data") or {}).get("next_run") or {})
        metadata.setdefault("owner_version", self.registry[goal["owner_id"]].version)
        created = self.store.new_cycle(goal_id, metadata)
        self.store.event(goal_id, created["id"], "run.started", {
            "previous_run_id": cycle["id"],
            "approved_experiment": evaluation["next_experiment"],
            "automatic": automatic})
        return self.status(goal_id)

    def add_evidence(self, goal_id: str, *, kind: str, source: str, payload: dict,
                     validity: str | None = None,
                     work_order_id: str | None = None) -> dict:
        self._assert_goal_write_authority()
        cycle = self.store.cycle(goal_id)
        run = self.store.run(cycle["id"])
        payload = dict(payload or {})
        if work_order_id:
            order = self.store.work_order(work_order_id)
            if order["goal_id"] != goal_id or order["run_id"] != cycle["id"]:
                raise ValueError("work order does not belong to the current goal run")
            accepts = list(order.get("accepts_evidence") or [])
            if accepts and kind not in accepts:
                raise ValueError(
                    f"evidence kind '{kind}' is not accepted; use: {', '.join(accepts)}")
            payload["work_order_id"] = work_order_id
        evidence = self.store.add_evidence(goal_id, cycle["id"], kind, source, payload,
                                           validity or run["evidence_validity"])
        self.store.event(goal_id, cycle["id"], "evidence.recorded", {"evidence_id": evidence["id"], "kind": kind})
        self.store.refresh_work_orders_for_run(goal_id, cycle["id"])
        if cycle["run_status"] == "waiting" and self._goal_met_from_evidence(goal_id, cycle["id"]):
            self.store.update_cycle(cycle["id"], stage="EVALUATE", step="measure", run_status="waiting",
                                    resume_at=now_iso(), data=cycle["data"])
        return self.status(goal_id)

    def claim_work_order(self, work_order_id: str, agent_id: str) -> dict:
        """Claim one assignment without changing its Goal or run state."""

        self._assert_goal_write_authority()
        order = self.store.claim_work_order(work_order_id, agent_id)
        goal = self.store.goal(order["goal_id"])
        if goal["goal_status"] != "active":
            raise RuntimeError(f"work order goal is {goal['goal_status']}, not active")
        return order

    def complete_work_order(self, work_order_id: str, agent_id: str,
                            evidence: list[dict]) -> dict:
        """Validate linked evidence, close one claimed assignment, and resume its Goal."""

        self._assert_goal_write_authority()
        order = self.store.work_order(work_order_id)
        if order["status"] != "claimed" or order.get("claimed_by") != agent_id:
            owner = order.get("claimed_by") or order["status"]
            raise RuntimeError(f"work order must be claimed by {agent_id!r} (current: {owner})")
        accepts = set(order.get("accepts_evidence") or [])
        records = [dict(item) for item in (evidence or [])]
        accepted = [item for item in records if not accepts or item.get("kind") in accepts]
        needed = int(order.get("needed") or 1)
        if accepts and len(accepted) < needed:
            raise ValueError(
                f"work order needs {needed} accepted evidence item(s): {', '.join(sorted(accepts))}")
        if not accepts and not records:
            accepted = []
        elif not accepts:
            accepted = records

        evidence_ids = []
        for item in accepted:
            kind = str(item.get("kind") or "").strip()
            if not kind:
                raise ValueError("each evidence item needs kind")
            state = self.add_evidence(
                order["goal_id"], kind=kind,
                source=str(item.get("source") or agent_id),
                payload=dict(item.get("payload") or {}),
                validity=item.get("validity"), work_order_id=work_order_id)
            linked = [value for value in state["evidence"]
                      if (value.get("payload") or {}).get("work_order_id") == work_order_id]
            evidence_ids = [value["id"] for value in linked]

        completed = self.store.complete_work_order(
            work_order_id, evidence_ids[:needed] if needed else evidence_ids,
            agent_id=agent_id)
        cycle = self.store.cycle(order["goal_id"])
        if cycle["run_status"] in {"blocked", "failed"}:
            self.retry(order["goal_id"])
            from .runner import Runner
            Runner(self).tick(order["goal_id"])
        return {"work_order": completed, "goal": self.status(order["goal_id"])}

    def complete_change(self, task_id: str, *, passed: bool, result: dict,
                        deployed: bool = False) -> dict:
        self._assert_goal_write_authority()
        task = self.store.change_task(task_id)
        if task["status"] != "approved":
            raise RuntimeError(
                f"change task {task_id} is {task['status']}; only an approved task can be completed")
        status = "completed" if passed else "failed"
        task = self.store.complete_change_task(task_id, status, result)
        validity = "technical_only" if passed else "invalid"
        self.store.add_evidence(task["goal_id"], task["run_id"], "change_validation", "coding_executor",
                                {"task_id": task_id, "passed": passed, **result}, validity)
        if passed:
            self.store.register_owner_version(task["owner_id"], task["target_version"],
                                              status="deployed" if deployed else "tested",
                                              test_summary=result)
        cycle = self.store.cycle(task["goal_id"])
        self.store.update_cycle(cycle["id"], stage="EVALUATE", step="validate_change",
                                run_status="idle", resume_at=None, data=cycle["data"])
        self.store.update_run(cycle["id"], status="idle",
                              validity="technical_only" if passed else "invalid",
                              contamination_reason=None if passed else "Acceptance tests failed")
        return self.status(task["goal_id"])

    def _goal_met_from_evidence(self, goal_id: str, run_id: str) -> bool:
        goal = self.store.goal(goal_id)
        run = self.store.run(run_id)
        evidence = countable_evidence(self.store.evidence(run_id), goal, run)
        sent = len({item["payload"].get("recipient") for item in evidence
                    if item["kind"] == "email_sent" and item["payload"].get("recipient")})
        replies = len({item["payload"].get("recipient") for item in evidence
                       if item["kind"] == "reply" and item["payload"].get("recipient")})
        if goal["metric"] != "reply_rate" or not sent:
            return False
        return _compare(replies / sent, goal["operator"], goal["target"])

    def status(self, goal_id: str) -> dict:
        children = [{"goal": child, "cycle": self.store.cycle(child["id"])}
                    for child in self.store.goals(parent_id=goal_id)]
        cycle = self.store.cycle(goal_id)
        latest_evaluation = self.store.latest_evaluation_for_goal(goal_id)
        latest_result = None
        if latest_evaluation:
            result_run_id = latest_evaluation["run_id"]
            latest_result = {"run": self.store.run(result_run_id),
                             "evaluation": latest_evaluation,
                             "evidence": self.store.evidence(result_run_id),
                             "decisions": self.store.decisions(result_run_id)}
        goal = self.store.goal(goal_id)
        return {"goal": goal, "cycle": cycle, "run": self.store.run(cycle["id"]),
                "evidence": self.store.evidence(cycle["id"]),
                "decisions": self.store.decisions(cycle["id"]),
                "evaluation": self.store.evaluation(cycle["id"]),
                "latest_result": latest_result,
                "change_tasks": self.store.change_tasks_for_run(cycle["id"]),
                "work_orders": self.store.work_orders(status=None, goal_id=goal_id, limit=20),
                "children": children,
                "pending_notifications": [item for item in self.store.notifications("pending")
                                          if item["goal_id"] == goal_id]}

    def list_goals(self) -> list[dict]:
        """All goals with their current cycle; malformed goals are skipped.

        change-a8869554dd (runner-resilience-1): a goal row without a cycle
        row used to raise KeyError here and kill every caller that enumerates
        goals — including the runner watch loop. One malformed row must never
        stop the whole company; skip it with a warning instead.
        """
        rows = []
        for goal in self.store.goals():
            try:
                cycle = self.store.cycle(goal["id"])
            except KeyError:
                logger.warning("skipping goal %s: no cycle row (malformed goal)",
                               goal["id"])
                continue
            rows.append({"goal": goal, "cycle": cycle})
        return rows

    def goal_summary(self, goal_id: str) -> dict:
        rows = self.store.goal_summaries(goal_id=goal_id, limit=1)
        if not rows:
            raise KeyError(f"unknown goal: {goal_id}")
        return {
            "goal": rows[0],
            "attention": [item for item in self.store.attention(100)
                          if item["goal_id"] == goal_id],
            "unread_results": [item for item in self.store.unread_results(100)
                               if item["goal_id"] == goal_id],
            "work_orders": self.store.work_orders(status="active", goal_id=goal_id, limit=20),
        }

    def company_snapshot(self, recent_limit: int = 5) -> dict:
        """Small current-state projection; immutable history remains in SQLite."""

        active = self.store.goal_summaries(statuses=("active",), limit=100)
        active.sort(key=lambda item: (-priority_score(item), item.get("created_at") or ""))
        roots = [item for item in active if not item.get("parent_id")]
        focus = (roots or active or [None])[0]
        all_goals = self.store.goals()
        return {
            "counts": self.store.goal_counts(),
            "focus_goal": focus,
            "attention": self.store.attention(10),
            "work_orders": self.store.work_orders(status="active", limit=20),
            "active_goals": active[:20],
            "proposed_goals": self.store.goal_summaries(statuses=("proposed",), limit=10),
            "paused_goals": self.store.goal_summaries(statuses=("paused",), limit=10),
            "unread_results": self.store.unread_results(5),
            "directives": self.store.directives(limit=10),
            "recent_memory": self.store.recent_memories(5),
            "support_links": [
                {"goal_id": goal["id"], "supports_goal_id": target}
                for goal in all_goals for target in support_goal_ids(goal)
            ],
            "recent_results": self.store.goal_summaries(
                statuses=TERMINAL, limit=recent_limit),
        }

    def goal_history(self, limit: int = 10) -> list[dict]:
        return self.store.goal_summaries(statuses=TERMINAL, limit=limit)

    def _state_signature(self, goal_id: str):
        goal = self.store.goal(goal_id)
        cycle = self.store.cycle(goal_id)
        return (goal["goal_status"], cycle["id"], cycle["stage"], cycle["step"],
                cycle["run_status"], cycle.get("resume_at"),
                len(self.store.evidence(cycle["id"])), bool(self.store.evaluation(cycle["id"])))


def _timestamp(value: str) -> datetime:
    # Shared normalization: legacy naive timestamps are read as UTC instead
    # of raising on comparison (bug 1).
    parsed = parse_dt(value)
    if parsed is None:
        raise ValueError(f"invalid timestamp: {value!r}")
    return parsed


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _compare(value, operator, target):
    return _shared_compare(value, operator, target)


# Historical import compatibility. New code uses the explicit class name so
# this loop cannot be mistaken for the canonical clean-core GoalRuntime.
Runtime = CompatibilityRuntime
