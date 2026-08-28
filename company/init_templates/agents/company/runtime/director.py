"""Recursive orchestrator using the same four-stage contract as its children."""

from datetime import datetime, timezone

from . import config
from .alignment import (
    UNKNOWN, as_goal_record, is_market_outcome, judge_alignment, present,
    priority_score,
)
from .models import GoalHandler, GoalStatus, RunStatus, Stage, StageResult
from .strategic import strategic_frontier
from .truth import (
    DIRECTOR_ROLLUPS, accepted_validities, child_supports_parent,
    derive_evaluation_validity,
)
from .util import compare as _shared_compare, parse_dt


class Director(GoalHandler):
    id = "director"
    description = "Coordinates child goals while preserving their state and approvals."
    version = "2.9.0"
    default_strategy_context = {
        "topics": ["company", "focus", "goals", "priorities", "evidence"],
        "scopes": ["director"],
        "layers": ["intent", "policy", "constitution"],
    }
    goal_schema = {
        "metrics": list(config.director_metrics()),
        "config": {"accepted_evidence_validity": {"type": "array"}},
    }

    def observe(self, ctx):
        children = list(ctx.cycle.get("children") or ())
        evaluations = [child.get("evaluation") for child in children if child.get("evaluation")]
        # One observation record per run/cycle: re-observing the same run must
        # update the picture in the payload that DECIDE reads, not append a
        # duplicate director_observation row every cycle.
        already_observed = any(item.get("kind") == "director_observation"
                               for item in (ctx.cycle.get("evidence") or ()))
        evidence = [] if already_observed else [{
            "kind": "director_observation", "source": "director",
            "payload": {"child_count": len(children),
                        "evaluation_count": len(evaluations)}}]
        return StageResult(
            "collect", {"children": children, "evaluations": evaluations},
            evidence=evidence,
            message=f"Observed {len(children)} child goals and {len(evaluations)} evaluations")

    def decide(self, ctx, observation):
        children = observation.get("children") or []
        if not children:
            return StageResult("diagnose", {"reason": "no child goals"}, RunStatus.BLOCKED,
                               Stage.DECIDE, message="Director needs at least one child goal")
        attention = sorted(
            [c for c in children if c["cycle"]["run_status"] in
             ("awaiting_approval", "blocked", "failed")],
            key=lambda item: (-priority_score(item), item.get("created_at") or ""))
        if attention:
            child = attention[0]
            payload = {"action": "surface", "child_id": child["id"],
                       "child_status": child["cycle"]["run_status"]}
            return StageResult("choose_intervention", payload,
                               decision={"type": "surface_attention",
                                         "rationale": "A child run requires approval or remediation",
                                         "payload": payload})
        invalid = [
            c for c in children
            if c.get("evaluation")
            and c["evaluation"].get("validity") in ("contaminated", "invalid")
            and not _existing_repair(children, c)
        ]
        if invalid:
            child = invalid[0]
            child_evidence_ids = [
                item["id"] for item in (child.get("evidence") or ())
                if item.get("id") and item.get("validity") in ("contaminated", "invalid")
            ]
            proposal = (child["evaluation"].get("next_experiment") or {}).get("system_improvement")
            if proposal:
                lineage = _system_intervention_lineage(ctx.goal, child, proposal)
                defects = _lineage_defects(lineage)
                if defects:
                    payload = {"action": "block_untraceable_system_improvement",
                               "child_id": child["id"], "defects": defects,
                               "proposal": proposal}
                    return StageResult(
                        "diagnose", payload, RunStatus.BLOCKED, Stage.DECIDE,
                        decision={"type": "block_untraceable_system_improvement",
                                  "rationale": "A system change cannot proceed without complete strategic lineage",
                                  "evidence_ids": child_evidence_ids,
                                  "payload": payload},
                        message="Director blocked a system intervention that lost its strategic lineage")
                parent = as_goal_record(ctx.goal)
                alignment = judge_alignment(
                    {"owner_id": "system-improvement",
                     "metric": "acceptance_tests_passed",
                     "run_type": "system_improvement", "config": proposal},
                    active_outcomes=[parent] if is_market_outcome(parent) else [],
                    parent=parent,
                )
                if alignment["judgment"] != "aligned":
                    payload = {"action": "request_owner_override",
                               "child_id": child["id"],
                               "originating_run_id": child["evaluation"]["run_id"],
                               "proposal": proposal, "strategic_lineage": lineage,
                               "alignment": alignment}
                    return StageResult(
                        "review", payload,
                        decision={"type": "recommend_defer",
                                  "rationale": alignment["rationale"],
                                  "next_run_type": "system_improvement",
                                  "evidence_ids": child_evidence_ids,
                                  "payload": payload})
                payload = {"action": "create_system_improvement", "child_id": child["id"],
                           "originating_run_id": child["evaluation"]["run_id"],
                           "proposal": proposal, "strategic_lineage": lineage,
                           "alignment": alignment}
                return StageResult("choose_intervention", payload,
                                   decision={"type": "system_improvement",
                                             "rationale": lineage["causal_hypothesis"],
                                             "next_run_type": "system_improvement",
                                             "evidence_ids": child_evidence_ids,
                                             "payload": payload})
        strategic = strategic_frontier(children)
        if strategic:
            return StageResult(
                "choose_intervention", strategic,
                decision={
                    "type": "strategic_experiment",
                    "rationale": (
                        "Competent execution and a trustworthy system produced "
                        "three rejected business hypotheses; test the declared "
                        f"{strategic['strategic_level']} candidate next"),
                    "evidence_ids": strategic["supporting_evidence_ids"],
                    "next_run_type": "business_experiment",
                    "payload": strategic,
                })
        runnable = sorted(
            [c for c in children if c["goal_status"] == "active" and _runnable(c)],
            key=lambda item: (-priority_score(item), item.get("created_at") or ""))
        if runnable:
            payload = {"action": "dispatch", "child_id": runnable[0]["id"]}
            return StageResult("choose_intervention", payload,
                               decision={"type": "dispatch", "rationale": "Next active child can progress",
                                         "payload": payload})
        carried = (ctx.cycle.get("run") or {}).get("changed_variables") or {}
        carried_hypothesis = (carried or {}).get("next_hypothesis")
        data_action = dict(ctx.cycle.get("data") or {}).get("action") or {}
        if (carried_hypothesis and not data_action.get("child_id")
                and not any(c["goal_status"] == "active" for c in children)):
            spec = _concrete_test_spec(ctx.goal, ctx.cycle.get("run") or {},
                                       children, carried_hypothesis)
            if spec:
                payload = {"action": "test_next_hypothesis", "child_spec": spec}
                return StageResult("choose_intervention", payload,
                                   decision={"type": "test_next_hypothesis",
                                             "rationale": "Test the carried hypothesis with a concrete child task",
                                             "payload": payload})
        completed = [c for c in children if c["cycle"]["run_status"] == "completed"]
        if completed:
            payload = {"action": "evaluate_children",
                       "completed_run_ids": [c["cycle"]["id"] for c in completed]}
            return StageResult("choose_intervention", payload,
                               decision={"type": "evaluate",
                                         "rationale": "Child runs completed and produced evidence",
                                         "payload": payload})
        active = [c for c in children if c["goal_status"] == "active"]
        if active:
            resume_at = min((c["cycle"].get("resume_at") for c in active
                             if c["cycle"].get("resume_at")), default=None)
            payload = {"action": "wait_for_children", "resume_at": resume_at,
                       "child_ids": [c["id"] for c in active]}
            return StageResult("choose_intervention", payload,
                               decision={"type": "wait_for_children",
                                         "rationale": "Active children are suspended awaiting evidence",
                                         "payload": payload})
        payload = {"action": "evaluate_children"}
        return StageResult("choose_intervention", payload,
                           decision={"type": "evaluate", "rationale": "No child can currently execute",
                                     "payload": payload})

    def act(self, ctx, decision):
        if decision.get("action") == "propose_strategic_experiment":
            if ctx.approval_status("execute") != "approved":
                return StageResult(
                    "review_strategy", decision, RunStatus.AWAITING_APPROVAL, Stage.ACT,
                    message=(
                        "Owner authority is required before running this strategic "
                        "experiment; no Policy or Model has been changed"))
            return StageResult(
                "authorize_strategy_test",
                {**decision, "owner_authorized": True, "strategy_mutated": False},
                message="Strategic experiment authorized; Policy and Model remain proposals")
        if decision.get("action") == "surface":
            return StageResult("review", decision, RunStatus.WAITING, Stage.OBSERVE,
                               resume_at=None,
                               message=f"Child {decision.get('child_id')} requires user or executor attention")
        if decision.get("action") == "dispatch":
            if not ctx.dispatch_goal:
                return StageResult("execute", {"error": "dispatcher unavailable"}, RunStatus.FAILED, Stage.ACT)
            outcome = ctx.dispatch_goal(decision["child_id"])
            child_cycle = outcome["cycle"]
            if child_cycle["run_status"] in {"blocked", "failed"}:
                child_id = decision["child_id"]
                child_status = child_cycle["run_status"]
                attention = {
                    "child_id": child_id,
                    "child_status": child_status,
                    "required_user_action": (
                        f"Review child {child_id}; the parent metric is not satisfied"),
                }
                return StageResult(
                    "review_child", {"child_id": child_id, "outcome": outcome},
                    RunStatus.WAITING, Stage.OBSERVE, resume_at=None,
                    attention=attention,
                    message=f"Child {child_id} needs attention ({child_status})")
            if outcome["goal"]["goal_status"] == "active" and child_cycle["run_status"] in {
                "waiting", "awaiting_approval"
            }:
                return StageResult("wait_for_child", {"child_id": decision["child_id"],
                                                       "outcome": outcome},
                                   RunStatus.WAITING, Stage.OBSERVE,
                                   resume_at=child_cycle.get("resume_at"),
                                   message="Director parked until the child run changes")
            return StageResult("execute", {"child_id": decision["child_id"], "outcome": outcome})
        if decision.get("action") == "request_owner_override":
            if ctx.approval_status("alignment_override") != "approved":
                return StageResult(
                    "review", decision, RunStatus.AWAITING_APPROVAL, Stage.ACT,
                    message=decision.get("alignment", {}).get("rationale")
                    or "Director recommends deferral; owner override required")
            return self._create_system_improvement(
                ctx, decision, owner_override=True)
        if decision.get("action") == "create_system_improvement":
            return self._create_system_improvement(ctx, decision, owner_override=False)
        if decision.get("action") == "wait_for_children":
            return StageResult("wait_for_children", decision, RunStatus.WAITING,
                               Stage.OBSERVE, resume_at=decision.get("resume_at"),
                               message="Director is waiting for child evidence or a child transition")
        if decision.get("action") == "test_next_hypothesis":
            if not ctx.create_child_goal or not ctx.dispatch_goal:
                return StageResult("execute", {"error": "child creator or dispatcher unavailable"},
                                   RunStatus.FAILED, Stage.ACT)
            child = ctx.create_child_goal(decision.get("child_spec") or {})
            outcome = ctx.dispatch_goal(child["id"])
            child_cycle = outcome["cycle"]
            if child_cycle["run_status"] in {"blocked", "failed"}:
                return StageResult(
                    "review_child", {"child_id": child["id"], "outcome": outcome},
                    RunStatus.WAITING, Stage.OBSERVE, resume_at=None,
                    attention={"child_id": child["id"],
                               "child_status": child_cycle["run_status"],
                               "required_user_action": (
                                   f"Review hypothesis test child {child['id']}; "
                                   "the parent metric is not satisfied")},
                    message=f"Hypothesis test child {child['id']} needs attention ({child_cycle['run_status']})")
            if child_cycle["run_status"] == "completed":
                return StageResult("execute", {"child_id": child["id"], "outcome": outcome},
                                   message="Hypothesis test child completed in-step")
            return StageResult("wait_for_child", {"child_id": child["id"], "outcome": outcome},
                               RunStatus.WAITING, Stage.OBSERVE,
                               resume_at=child_cycle.get("resume_at"),
                               message="Parent waits for the hypothesis test child")
        return StageResult("execute", {"action": decision.get("action")})

    def evaluate(self, ctx, action_result):
        children = list(ctx.cycle.get("children") or ())
        run = ctx.cycle.get("run") or {}
        accepted = accepted_validities(ctx.goal, run)
        supporting = [child for child in children
                      if child_supports_parent(ctx.goal.metric, child, accepted)]
        raw_achieved = sum(child["goal_status"] == "achieved" for child in children)
        accepted_achieved = len(supporting)
        evaluations = [child.get("evaluation") for child in supporting if child.get("evaluation")]
        metric_values = [item.get("metrics", {}).get(ctx.goal.metric) for item in evaluations
                         if item.get("metrics", {}).get(ctx.goal.metric) is not None]
        goal_booked_calls = []
        if ctx.goal.metric == "all_children_achieved":
            met = bool(children) and accepted_achieved == len(children)
            measured = accepted_achieved
        elif ctx.goal.metric == "achieved_children":
            measured = accepted_achieved
            met = _compare(measured, ctx.goal.operator, ctx.goal.target)
        else:
            measured = max(metric_values) if metric_values else None
            if ctx.goal.metric == "booked_calls":
                goal_booked_calls = [
                    item for item in (ctx.cycle.get("evidence") or ())
                    if item.get("kind") == "booked_call"
                    and (item.get("validity") or "business") in accepted]
                if goal_booked_calls:
                    measured = (len(goal_booked_calls) if measured is None
                                else max(measured, len(goal_booked_calls)))
            met = measured is not None and _compare(measured, ctx.goal.operator, ctx.goal.target)
        validity = derive_evaluation_validity(
            [{"validity": (child.get("evaluation") or {}).get("validity")
              or (child.get("run") or {}).get("evidence_validity")}
             for child in supporting] + goal_booked_calls,
            ctx.goal, run)
        if met and validity not in accepted:
            met = False
        payload = {"achieved_children": raw_achieved,
                   "accepted_achieved_children": accepted_achieved,
                   "total_children": len(children),
                   "metric": ctx.goal.metric, "metric_value": measured, "goal_met": met,
                   "accepted_evidence_validity": sorted(accepted)}
        evaluation = {"verdict": "goal_met" if met else "continue", "goal_met": met,
                      "metrics": {ctx.goal.metric: measured, "achieved_children": accepted_achieved},
                      "validity": validity,
                      "next_experiment": {} if met else {"action": "continue_child_runs"}}
        if met:
            return StageResult("goal_check", payload, RunStatus.COMPLETED, goal_status=GoalStatus.ACHIEVED,
                               evaluation=evaluation, message="Director goal achieved")
        if not any(child["goal_status"] == "active" for child in children):
            data_action = dict((ctx.cycle.get("data") or {}).get("action") or {})
            if data_action.get("child_id"):
                evaluation["next_experiment"] = {"action": "reobserve_children"}
                return StageResult("goal_check", payload, RunStatus.COMPLETED, Stage.EVALUATE,
                                   evaluation=evaluation,
                                   next_run={"run_type": "evaluation",
                                             "evidence_validity": validity},
                                   message="Hypothesis test dispatched; re-observing child evidence on the next run")
            derived = _derive_next_hypothesis(supporting, ctx.goal, measured)
            if derived:
                evaluation["next_experiment"] = derived["experiment"]
                return StageResult("goal_check", payload, RunStatus.COMPLETED, Stage.EVALUATE,
                                   evaluation=evaluation,
                                   next_run={"run_type": "business_experiment",
                                             "hypothesis": derived["hypothesis"],
                                             "changed_variables": derived["changed_variables"],
                                             "evidence_validity": validity},
                                   message="Director derived the next hypothesis from completed child evidence; continuing automatically")
            evaluation["verdict"] = "blocked"
            evaluation["next_experiment"] = {}
            return StageResult("goal_check", payload, RunStatus.BLOCKED, Stage.EVALUATE,
                               evaluation=evaluation,
                               message="Director cannot derive the next experiment from completed child work; external input is required")
        return StageResult("goal_check", payload, RunStatus.COMPLETED, evaluation=evaluation,
                           next_run={"run_type": "evaluation",
                                     "evidence_validity": validity},
                           message="Director evaluated the run; the next valid run continues automatically")

    def _create_system_improvement(self, ctx, decision, *, owner_override: bool):
        if not ctx.create_child_goal:
            return StageResult("execute", {"error": "child creator unavailable"}, RunStatus.FAILED, Stage.ACT)
        proposal = decision["proposal"]
        lineage = decision["strategic_lineage"]
        alignment = dict(decision.get("alignment") or {})
        if owner_override:
            alignment["owner_override"] = True
        config = {**proposal, "originating_run_id": decision["originating_run_id"],
                  "strategic_lineage": lineage, "alignment": alignment}
        if owner_override:
            config["owner_override"] = True
        child = ctx.create_child_goal({
            "name": f"Repair {proposal['owner_id']}: {proposal['problem']}",
            "owner_id": "system-improvement", "metric": "acceptance_tests_passed",
            "operator": "eq", "target": True, "run_type": "system_improvement",
            "evidence_validity": "technical_only", "resume_run_id": decision["originating_run_id"],
            "config": config,
            "hypothesis": {"statement": proposal["problem"], "variable": "owner_version",
                           "prediction": "The bounded repair restores valid execution"},
        })
        return StageResult("execute", {"created_goal": child["id"], "action": "system_improvement",
                                       "alignment": alignment})


def _compare(value, operator, target):
    return _shared_compare(value, operator, target)


def _system_intervention_lineage(goal, child, proposal):
    evaluation = child.get("evaluation") or {}
    observed = (present(proposal.get("observed_reality"))
                or present(evaluation.get("contamination_reason")))
    return {
        "business_goal": {"id": goal.id, "name": goal.name, "metric": goal.metric,
                          "operator": goal.operator, "target": goal.target},
        "observed_reality": observed or UNKNOWN,
        "diagnosis_level": present(proposal.get("diagnosis_level")) or "system",
        "causal_hypothesis": present(proposal.get("causal_hypothesis")) or UNKNOWN,
        "smallest_intervention": present(proposal.get("smallest_intervention")) or UNKNOWN,
        "expected_measurable_effect": present(
            proposal.get("expected_measurable_effect") or proposal.get("expected_effect")) or UNKNOWN,
        "stop_condition": present(proposal.get("stop_condition")) or UNKNOWN,
        "non_goals": list(proposal.get("non_goals") or (
            "Change the parent business goal",
            "Change controlled business variables",
            "Redesign unrelated runtime or Department architecture",
        )),
    }


def _lineage_defects(lineage):
    defects = []
    goal = lineage.get("business_goal") or {}
    if not all(goal.get(key) not in (None, "") for key in ("id", "name", "metric", "operator")):
        defects.append("business_goal")
    if lineage.get("diagnosis_level") != "system":
        defects.append("diagnosis_level(system)")
    for key in ("observed_reality", "causal_hypothesis", "smallest_intervention",
                "expected_measurable_effect", "stop_condition"):
        if not present(lineage.get(key)):
            defects.append(key)
    if not lineage.get("non_goals"):
        defects.append("non_goals")
    return defects


def _existing_repair(children, originating_child):
    """Return the durable repair already assigned to one invalid Run.

    Historical invalid evidence remains invalid after a repair. Without this
    lookup every later Director observation creates the same repair again.
    The originating Run is the identity boundary; failed same-scope attempts
    stay on their existing system-improvement Goal.
    """
    evaluation = originating_child.get("evaluation") or {}
    originating_run_id = evaluation.get("run_id")
    proposal = (evaluation.get("next_experiment") or {}).get("system_improvement") or {}
    if not originating_run_id or not proposal:
        return None
    for candidate in children:
        if candidate.get("owner_id") != "system-improvement":
            continue
        if candidate.get("goal_status") in {"abandoned", "expired"}:
            continue
        config = candidate.get("config") or {}
        if config.get("originating_run_id") != originating_run_id:
            continue
        if config.get("owner_id") != proposal.get("owner_id"):
            continue
        if config.get("target_version") != proposal.get("target_version"):
            continue
        return candidate
    return None


def _runnable(child):
    cycle = child["cycle"]
    if cycle["run_status"] == "idle":
        return True
    if cycle["run_status"] != "waiting" or not cycle.get("resume_at"):
        return False
    # parse_dt normalizes legacy naive resume_at values to UTC; a raw
    # fromisoformat comparison here used to raise TypeError and kill the tick.
    due = parse_dt(cycle["resume_at"])
    return due is not None and due <= datetime.now(timezone.utc)


def _derive_next_hypothesis(supporting, goal, measured):
    """Next experiment hypothesis derived from the completed run's evidence.

    Returns None when no accepted business evidence supports a next step; only
    then does the Director treat the gap as a genuine external blocker.
    """
    if not supporting:
        return None
    source = supporting[-1]
    run = source.get("run") or {}
    changed = run.get("changed_variables") or {}
    variable = goal.metric
    if isinstance(changed, dict) and changed:
        variable = next(iter(changed))
    hypothesis = {
        "statement": (
            f"Continue the {source.get('owner_id')} line that produced "
            f"{goal.metric}={measured}: a fresh experiment on '{variable}' moves "
            f"{goal.metric} from {measured} toward target {goal.target}."),
        "variable": variable,
        "prediction": f"{goal.metric} reaches {goal.target} after the next child experiment.",
    }
    return {
        "hypothesis": hypothesis,
        "experiment": {
            "action": "test_next_hypothesis",
            "change_one_variable": variable,
            "hypothesis": dict(hypothesis),
        },
        "changed_variables": {"next_hypothesis": hypothesis},
    }


def _concrete_test_spec(goal, run, children, hypothesis):
    """Concrete child task that tests the carried hypothesis (no clone/template)."""
    accepted = accepted_validities(goal, run)
    sources = [c for c in (children or [])
               if c.get("goal_status") == "achieved"
               and ((c.get("evaluation") or {}).get("validity")
                    or (c.get("run") or {}).get("evidence_validity")) in accepted]
    if not sources:
        return None
    source = sources[-1]
    variable = (hypothesis or {}).get("variable") or goal.metric
    return {
        "name": f"Test hypothesis: {variable}",
        "owner_id": source["owner_id"],
        "metric": source["metric"],
        "operator": source["operator"],
        "target": source["target"],
        "config": {
            "purpose": "test_next_hypothesis",
            "hypothesis": dict(hypothesis or {}),
            "lineage": {
                "reason": "test_next_hypothesis",
                "originating_goal_id": goal.id,
                "originating_run_id": run.get("id") if isinstance(run, dict) else None,
                "source_child_id": source["id"],
            },
        },
        "run_type": "business_experiment",
        "evidence_validity": "business",
    }
