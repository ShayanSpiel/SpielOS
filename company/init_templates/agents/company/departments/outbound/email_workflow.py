"""Email workflow implementation and v4 goal compatibility handler."""

import html
import re
import time
from datetime import datetime, timedelta, timezone
from email.utils import parseaddr
from pathlib import Path

from ...runtime.models import GoalHandler, GoalStatus, RunStatus, Stage, StageResult


def outbound_context(dry=False, goal_config=None):
    from .context import build_context
    context = build_context(dry=dry)
    knobs = (goal_config or {}).get("knobs")
    if knobs:
        context.control._data["knobs"] = {**context.control.knobs(), **knobs}
    return context


class EmailWorkflow(GoalHandler):
    id = "email"
    description = "Deprecated compatibility id for persisted email goals; new work uses the Outbound Department."
    version = "2.1.0"
    deprecated = True
    goal_schema = {
        "metrics": ["reply_rate", "positive_reply_rate", "booked_calls", "sales"],
        "config": {
            "execution_mode": {"enum": ["dry_run", "live"], "required": True},
            "batch_size": {"type": "integer", "description": "Required eligible leads for one complete run"},
            "evidence_window_hours": {"type": "number", "required_when": {"execution_mode": "live"}},
            "knobs": {"type": "object", "description": "Per-goal overrides of Outbound campaign knobs"},
            "audience_type": {"enum": ["business", "test_inbox"]},
            "test_recipients": {"type": "array", "required_when": {"audience_type": "test_inbox"}},
            "throttle_seconds": {"type": "number", "required_when": {"execution_mode": "live"}},
            "reply_capture": {"enum": ["manual_inbox", "resend_inbound", "gmail_inbox"],
                              "required_when": {"audience_type": "test_inbox"}},
            "observer_interval_seconds": {"type": "number", "description": "Provider polling cadence while evidence is open"},
        },
    }

    def observe(self, ctx):
        if ctx.goal.config.get("audience_type") == "test_inbox":
            evidence = list(ctx.cycle.get("evidence") or ())
            sent = {item["payload"].get("recipient") for item in evidence if item["kind"] == "email_sent"}
            replies = {item["payload"].get("recipient") for item in evidence if item["kind"] == "reply"}
            sent.discard(None); replies.discard(None)
            payload = {"audience_type": "test_inbox", "sent": len(sent), "replies": len(replies),
                       "reply_rate": len(replies) / len(sent) if sent else 0.0,
                       "recipients": ctx.goal.config.get("test_recipients", [])}
            return StageResult("collect", payload,
                               evidence=[{"kind": "email_test_observation", "source": self.id,
                                          "validity": "technical_only", "payload": payload}],
                               message="Controlled test-inbox state observed")
        outbound = outbound_context(ctx.goal.config.get("execution_mode") == "dry_run", ctx.goal.config)
        if outbound.stop_file.exists():
            return StageResult("collect", {"stop_file": str(outbound.stop_file)},
                               RunStatus.BLOCKED, Stage.OBSERVE,
                               message="Legacy outreach STOP switch is raised")
        return StageResult("collect", outbound.workflow.observe(outbound), message="Campaign reality observed")

    def decide(self, ctx, observation):
        if ctx.goal.config.get("audience_type") == "test_inbox":
            payload = {"action": "prepare_test_batch", "variable": "pipeline_execution",
                       "prediction": "All controlled messages send and replies are captured",
                       "recipients": observation.get("recipients", [])}
            return StageResult("choose_intervention", payload,
                               decision={"type": "run_system_test",
                                         "rationale": "Validate transport, tracking, reply capture, and Director control",
                                         "next_run_type": "system_test", "payload": payload})
        outbound = outbound_context(goal_config=ctx.goal.config)
        queue_size = int((observation.get("queue") or {}).get("size") or 0)
        knobs = outbound.control.knobs()
        desired = int(ctx.goal.config.get("batch_size") or knobs.get("block_size") or 0)
        if desired > 0 and queue_size < desired:
            needed = desired - queue_size
            payload = {"action": "replenish_leads", "queue_size": queue_size,
                       "desired_batch_size": desired, "needed_leads": needed,
                       "filters": knobs.get("cohort_filters") or {}}
            attention = {
                "capability": "lead_research",
                "owner": "director",
                "required_user_action": (
                    f"Let the Director research, qualify, and ingest at least {needed} additional leads"),
                "completion_evidence": f"eligible email queue is at least {desired}",
                "next_trigger": f"company retry {ctx.goal.id}",
                "payload": payload,
            }
            return StageResult("diagnose", payload, RunStatus.BLOCKED, Stage.DECIDE,
                               message=(f"Email run needs {needed} more qualified, researched leads "
                                        f"before a {desired}-email batch can be prepared"),
                               decision={"type": "request_capability",
                                         "rationale": "A partial batch would change the planned run scope",
                                         "payload": payload},
                               attention=attention)
        decision = outbound.workflow.decide(outbound, observation)
        if not decision:
            return StageResult("diagnose", {"action": "hold", "reason": "no intervention"},
                               RunStatus.BLOCKED, Stage.DECIDE)
        if decision.get("action") in {"hold", "stop"}:
            terminal = GoalStatus.ACHIEVED if decision.get("action") == "stop" else None
            return StageResult("diagnose", decision, RunStatus.BLOCKED, Stage.DECIDE, terminal)
        return StageResult("choose_intervention", decision)

    def act(self, ctx, decision):
        if ctx.goal.config.get("audience_type") == "test_inbox":
            return self._act_test_inbox(ctx, decision)
        from . import execution as outbound_execution
        mode = ctx.goal.config.get("execution_mode")
        capture = _capture_mode(ctx.goal.config)
        if mode == "live" and ctx.goal.metric in {"reply_rate", "positive_reply_rate"}:
            if "reply_capture" not in ctx.goal.config or capture not in {"manual_inbox", "resend_inbound", "gmail_inbox"}:
                return _capture_setup_required(ctx, "Select an explicit reply evidence source")
            if capture == "resend_inbound":
                from .workflows.email import config as email_config, providers
                readiness = providers.receiving_domain_status(
                    email_config.REPLY_TO,
                    provider=ctx.goal.config.get("provider") or providers.EMAIL_PROVIDER)
                if not readiness.get("ready"):
                    return _capture_setup_required(
                        ctx, readiness.get("reason") or "Automatic reply capture is not ready", readiness)
        outbound = outbound_context(mode == "dry_run", ctx.goal.config)
        # Stamp the goal identity so the actor can reconcile background
        # dispatch files for THIS goal (outbound context has no goal id).
        setattr(outbound, "goal_id", ctx.goal.id)
        if outbound.stop_file.exists():
            return StageResult("guardrail", {"stop_file": str(outbound.stop_file)},
                               RunStatus.BLOCKED, Stage.ACT,
                               message="Legacy outreach STOP switch is raised")
        previous = (ctx.cycle.get("data") or {}).get("action_result") or {}
        batch_id = previous.get("batch_id")
        if not batch_id:
            row = outbound_execution.prepare(outbound, decision)
            issues = outbound_execution.validate(outbound, row)
            if not row["batch"].get("emails"):
                return StageResult("validate", {"batch_id": row["id"], "issues": issues},
                                   RunStatus.BLOCKED, Stage.ACT, message="No valid emails remain")
            gate = outbound_execution.gate(outbound)
            if not gate.get("ok"):
                return StageResult("guardrail", {"batch_id": row["id"], "gate": gate},
                                   RunStatus.BLOCKED, Stage.ACT, message="Email guardrail blocked execution")
            return StageResult("review", {"batch_id": row["id"], "preview_path": row.get("preview_path"),
                               "email_count": len(row["batch"].get("emails", []))},
                               RunStatus.AWAITING_APPROVAL, Stage.ACT,
                               message="Review the batch before execution")
        if ctx.approval_status("execute") != "approved":
            return StageResult("review", previous, RunStatus.AWAITING_APPROVAL, Stage.ACT)
        if mode not in {"dry_run", "live"}:
            return StageResult("guardrail", {**previous, "error": "set execution_mode to dry_run or live"},
                               RunStatus.BLOCKED, Stage.ACT)
        if mode == "live" and "evidence_window_hours" not in ctx.goal.config:
            return StageResult("guardrail", {**previous, "error": "live mode requires evidence_window_hours"},
                               RunStatus.BLOCKED, Stage.ACT)
        row = outbound.store.get_batch(batch_id)
        if not row:
            return StageResult("execute", {**previous, "error": "outbound batch missing"},
                               RunStatus.FAILED, Stage.ACT)

        # Check if there's already a pending dispatch
        from .workflows.email import actor
        if actor.is_pending(ctx, batch_id):
            return StageResult(
                "review",
                previous,
                RunStatus.WAITING,
                Stage.ACT,
                resume_at=_dispatch_poll(ctx.goal.config).isoformat(),
                evidence=None,
            )

        # Execute the batch (may dispatch to background)
        result = outbound_execution.execute(outbound, row, dry=mode == "dry_run")

        # Check if dispatched to background
        if result.get("dispatched"):
            return StageResult(
                "review",
                {**previous, "dispatched": True},
                RunStatus.WAITING,
                Stage.ACT,
                resume_at=_dispatch_poll(ctx.goal.config).isoformat(),
                evidence=None,
            )

        # Otherwise, continue to evidence collection
        evidence = []
        if mode == "live":
            from .workflows.email import outbound
            sent_log = outbound.load_sent_log()
            batch_leads = {email.get("lead_id") for email in row["batch"].get("emails", [])}
            for item in sent_log.get("sent", []):
                if item.get("batch") == batch_id:
                    evidence.append({"kind": "email_sent", "source": item.get("provider") or self.id,
                                     "validity": "business", "payload": {
                                         "recipient": item.get("email"), "lead_id": item.get("lead_id"),
                                         "provider": item.get("provider"),
                                         "provider_id": item.get("provider_id"), "batch_id": batch_id}})
            for item in sent_log.get("failed", []):
                if item.get("lead_id") in batch_leads:
                    evidence.append({"kind": "email_send_failed", "source": item.get("provider") or self.id,
                                     "validity": "business", "payload": {
                                         "recipient": item.get("email"), "lead_id": item.get("lead_id"),
                                         "provider": item.get("provider"), "error": item.get("error"),
                                         "batch_id": batch_id}})
        hours = 0 if mode == "dry_run" else float(ctx.goal.config["evidence_window_hours"])
        deadline = datetime.now(timezone.utc) + timedelta(hours=hours)
        due = _next_poll(ctx.goal.config, deadline).isoformat()
        return StageResult("measure", {"batch_id": batch_id, "execution": result,
                                       "evidence_deadline": deadline.isoformat()},
                           RunStatus.WAITING, Stage.EVALUATE, resume_at=due, evidence=evidence,
                           message="Execution complete; evidence window armed")

    def evaluate(self, ctx, action_result):
        if ctx.goal.config.get("audience_type") == "test_inbox":
            return self._evaluate_test_inbox(ctx, action_result)
        outbound = outbound_context(goal_config=ctx.goal.config)
        row = outbound.store.get_batch(action_result.get("batch_id")) if action_result.get("batch_id") else None
        if not row:
            return StageResult("measure", {"error": "batch unavailable"}, RunStatus.FAILED, Stage.EVALUATE)
        snapshot = outbound.workflow.observe(outbound)
        outcome = outbound.workflow.measure(outbound, row["batch"])
        verdict, metrics = outcome.get("verdict") or {}, outcome.get("metrics") or {}
        value = metrics.get(ctx.goal.metric)
        met = value is not None and _compare(value, ctx.goal.operator, ctx.goal.target)
        deadline = _parse_time(action_result.get("evidence_deadline"))
        if not met and deadline and datetime.now(timezone.utc) < deadline:
            poll_evidence = {"batch_id": row["id"], "metrics": metrics,
                             "provider_state": snapshot.get("providers", {}),
                             "evidence_deadline": deadline.isoformat()}
            return StageResult("measure", poll_evidence, RunStatus.WAITING, Stage.EVALUATE,
                               resume_at=_next_poll(ctx.goal.config, deadline).isoformat(),
                               evidence=[{"kind": "email_metrics_snapshot", "source": self.id,
                                          "validity": "business", "payload": poll_evidence}],
                               message="Provider evidence refreshed; evidence window remains open")
        if outbound.workflow.learn:
            outbound.workflow.learn(outbound, row.get("intervention") or {}, verdict)
        payload = {"batch_id": row["id"], "metrics": metrics, "verdict": verdict,
                   "metric_value": value, "goal_met": met}
        label = verdict.get("verdict") or "inconclusive"
        learning = {"claim": f"Email intervention verdict: {label}",
                    "evidence": {"batch_id": row["id"], "metrics": metrics, "verdict": verdict},
                    "confidence": 0.4 if label == "inconclusive" else 0.8}
        next_decision = outbound.workflow.decide(outbound, snapshot) or {}
        next_experiment = {} if met else {
            "action": "run_email_batch",
            "change_one_variable": next_decision.get("variable"),
            "reason": next_decision.get("detail") or next_decision.get("reason"),
            "hypothesis": next_decision.get("prediction") or "Collect a larger qualified sample",
            "batch_size": int(ctx.goal.config.get("batch_size") or outbound.control.knobs().get("block_size") or 0),
            "keep_fixed": ["offer", "ICP", "sender_domain"],
        }
        evaluation = {"verdict": "goal_met" if met else label, "goal_met": met,
                      "metrics": metrics, "validity": "business",
                      "contamination_reason": None, "next_experiment": next_experiment}
        next_run = {} if met else {
            "run_type": "business_experiment", "evidence_validity": "business",
            "hypothesis": {"statement": next_experiment["hypothesis"],
                           "variable": next_experiment["change_one_variable"],
                           "prediction": next_experiment["hypothesis"]},
            "controlled_variables": {"offer": "fixed", "ICP": "fixed", "sender_domain": "fixed"},
            "changed_variables": ({next_experiment["change_one_variable"]: "next_intervention"}
                                  if next_experiment["change_one_variable"] else {}),
        }
        return StageResult("goal_check", payload, RunStatus.COMPLETED,
                           goal_status=GoalStatus.ACHIEVED if met else None,
                           message="Email goal achieved" if met else "Email run completed; next experiment proposed",
                           learnings=[learning], evaluation=evaluation, next_run=next_run)

    def _act_test_inbox(self, ctx, decision):
        outbound = outbound_context(goal_config=ctx.goal.config)
        if outbound.stop_file.exists():
            return StageResult("guardrail", {"stop_file": str(outbound.stop_file)},
                               RunStatus.BLOCKED, Stage.ACT, message="Outbound STOP switch is raised")
        recipients = list(dict.fromkeys(ctx.goal.config.get("test_recipients") or []))
        invalid = [address for address in recipients if not _valid_email(address)]
        if invalid or not recipients:
            return StageResult("validate", {"invalid": invalid, "recipient_count": len(recipients)},
                               RunStatus.BLOCKED, Stage.ACT, message="Test recipient validation failed")
        previous = (ctx.cycle.get("data") or {}).get("action_result") or {}
        if not previous.get("batch_id"):
            batch_id = ctx.cycle["id"]
            token = batch_id[-6:].upper()
            subject = ctx.goal.config.get("test_subject") or f"SpielOS loop test {token}"
            body = (ctx.goal.config.get("test_body") or
                    f"This is a controlled SpielOS system test. Please reply with: received {token}\n\n"
                    "This message validates sending, reply capture, evidence, and Director goal checking. "
                    "It is not a marketing email or business experiment.")
            batch = {"batch_id": batch_id, "token": token, "subject": subject, "body": body,
                     "recipients": recipients, "audience_type": "test_inbox",
                     "evidence_validity": "technical_only"}
            preview = _write_test_preview(ctx.goal.id, batch)
            return StageResult("review", {**batch, "preview_path": str(preview)},
                               RunStatus.AWAITING_APPROVAL, Stage.ACT,
                               message="Controlled four-inbox batch prepared for approval")
        if ctx.approval_status("execute") != "approved":
            return StageResult("review", previous, RunStatus.AWAITING_APPROVAL, Stage.ACT)
        if ctx.goal.config.get("execution_mode") != "live":
            return StageResult("guardrail", {**previous, "error": "test-inbox execution requires explicit live mode"},
                               RunStatus.BLOCKED, Stage.ACT)
        if "throttle_seconds" not in ctx.goal.config or "evidence_window_hours" not in ctx.goal.config:
            return StageResult("guardrail", {**previous, "error": "live mode requires throttle_seconds and evidence_window_hours"},
                               RunStatus.BLOCKED, Stage.ACT)
        from .workflows.email import config as email_config, providers
        capture = _capture_mode(ctx.goal.config)
        if capture == "resend_inbound":
            provider_name = (ctx.goal.config.get("provider") or providers.EMAIL_PROVIDER).strip().lower()
            if provider_name != "resend":
                return StageResult("guardrail", {**previous, "error": "resend_inbound requires provider=resend"},
                                   RunStatus.BLOCKED, Stage.ACT)
            if not email_config.REPLY_TO:
                return StageResult("guardrail", {**previous, "error": "resend_inbound requires REPLY_TO on a receiving-enabled domain"},
                                   RunStatus.BLOCKED, Stage.ACT,
                                   message="Automatic reply capture is not configured")
            readiness = providers.receiving_domain_status(email_config.REPLY_TO, provider=provider_name)
            if not readiness.get("ready"):
                return _capture_setup_required(
                    ctx, readiness.get("reason") or "Automatic reply capture is not ready", readiness)
        if capture == "gmail_inbox":
            if not email_config.REPLY_TO:
                return StageResult("guardrail", {**previous, "error": "gmail_inbox requires REPLY_TO on the captured address"},
                                   RunStatus.BLOCKED, Stage.ACT,
                                   message="Automatic reply capture is not configured")
            readiness = providers.gmail_imap_status()
            if not readiness.get("ready"):
                return _capture_setup_required(
                    ctx, readiness.get("reason") or "Gmail IMAP capture is not ready", readiness)
        results, evidence = [], []
        provider = ctx.goal.config.get("provider")
        for index, recipient in enumerate(previous["recipients"]):
            if index:
                time.sleep(float(ctx.goal.config["throttle_seconds"]))
            sender = providers.send_email_via if provider else None
            if sender:
                result = sender(provider, recipient, previous["subject"],
                                _as_html(previous["body"]), previous["body"], reply_to=email_config.REPLY_TO)
            else:
                result = providers.send_email(recipient, previous["subject"],
                                              _as_html(previous["body"]), previous["body"],
                                              reply_to=email_config.REPLY_TO)
            item = {"recipient": recipient, "provider": provider or providers.EMAIL_PROVIDER,
                    "provider_id": result.get("id"), "error": bool(result.get("error")),
                    "status": result.get("status"), "message": result.get("message")}
            results.append(item)
            evidence.append({"kind": "email_send_failed" if item["error"] else "email_sent",
                             "source": item["provider"], "validity": "technical_only", "payload": item})
        deadline = datetime.now(timezone.utc) + timedelta(
            hours=float(ctx.goal.config["evidence_window_hours"]))
        due = _next_poll(ctx.goal.config, deadline).isoformat()
        return StageResult("measure", {**previous, "execution": results,
                                       "reply_capture": capture,
                                       "reply_to": email_config.REPLY_TO or None,
                                       "evidence_deadline": deadline.isoformat()}, RunStatus.WAITING,
                           Stage.EVALUATE, resume_at=due, evidence=evidence,
                           message="Controlled batch executed; provider observer armed")

    def _evaluate_test_inbox(self, ctx, action_result):
        observed = _observe_test_provider(ctx, action_result)
        evidence = list(ctx.cycle.get("evidence") or ()) + observed
        sent = {item["payload"].get("recipient") for item in evidence if item["kind"] == "email_sent"}
        failed = [item for item in evidence if item["kind"] == "email_send_failed"]
        all_replies = [item for item in evidence if item["kind"] == "reply"]
        automatic = {item["payload"].get("recipient") for item in all_replies
                     if item.get("source") == "resend_inbound" and item["payload"].get("received_id")}
        manual = {item["payload"].get("recipient") for item in all_replies} - automatic
        capture = action_result.get("reply_capture") or _capture_mode(ctx.goal.config)
        replies = automatic if capture == "resend_inbound" else automatic | manual
        sent.discard(None); replies.discard(None)
        automatic.discard(None); manual.discard(None)
        reply_rate = len(replies) / len(sent) if sent else 0.0
        metrics = {"attempted": len(action_result.get("recipients", [])), "sent": len(sent),
                   "failed": len(failed), "replies": len(replies), "reply_rate": reply_rate,
                   "automatic_replies": len(automatic), "manual_replies": len(manual),
                   "reply_capture": capture,
                   "opened": len({item["payload"].get("recipient") for item in evidence
                                  if item["kind"] == "email_opened"}),
                   "delivered": len({item["payload"].get("recipient") for item in evidence
                                     if item["kind"] in {"email_delivered", "email_opened", "email_clicked"}})}
        if failed or len(sent) != len(action_result.get("recipients", [])):
            reason = f"Transport failed for {len(failed)} of {len(action_result.get('recipients', []))} recipients"
            proposal = {"owner_id": "outbound", "from_version": self.version,
                        "target_version": ctx.goal.config.get("system_improvement_target_version", "2.0.1-compat"),
                        "problem": reason,
                        "allowed_files": [".agents/company/departments/outbound/email_workflow.py", ".agents/company/departments/outbound/workflows/email/providers.py"],
                        "acceptance_tests": [
                            "PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=.agents python3 -B -m unittest discover -s .agents/company/tests -q",
                            "PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=.agents python3 -B -m unittest discover -s .agents/company/tests -q",
                        ]}
            evaluation = {"verdict": "invalid", "goal_met": False, "metrics": metrics,
                          "validity": "contaminated", "contamination_reason": reason,
                          "next_experiment": {"system_improvement": proposal}}
            return StageResult("goal_check", metrics, RunStatus.COMPLETED, evaluation=evaluation,
                               evidence=observed,
                               next_run={"run_type": "diagnostic", "evidence_validity": "technical_only"},
                               message="Infrastructure failure contaminated this run")
        met = _compare(reply_rate, ctx.goal.operator, ctx.goal.target)
        deadline = _parse_time(action_result.get("evidence_deadline"))
        if not met and deadline and datetime.now(timezone.utc) < deadline:
            return StageResult("measure", metrics, RunStatus.WAITING, Stage.EVALUATE,
                               resume_at=_next_poll(ctx.goal.config, deadline).isoformat(),
                               evidence=observed,
                               message="Provider evidence refreshed; waiting for more replies")
        next_experiment = {} if met else {
            "run_type": "system_test", "change_one_variable": "test_token",
            "keep_fixed": ["recipients", "provider", "body_instruction", "reply_capture"],
            "prediction": "A fresh trace token isolates the next reply-capture attempt"}
        evaluation = {"verdict": "goal_met" if met else "not_yet", "goal_met": met,
                      "metrics": metrics, "validity": "technical_only",
                      "contamination_reason": None, "next_experiment": next_experiment}
        learning = {"claim": f"Technical test reply rate was {reply_rate:.1%}",
                    "evidence": metrics, "confidence": 1.0}
        if met:
            return StageResult("goal_check", metrics, RunStatus.COMPLETED, goal_status=GoalStatus.ACHIEVED,
                               evaluation=evaluation, learnings=[learning],
                               evidence=observed,
                               message="Controlled reply-rate goal achieved")
        return StageResult("goal_check", metrics, RunStatus.COMPLETED, evaluation=evaluation,
                           learnings=[learning], evidence=observed, next_run={
                               "run_type": "system_test", "evidence_validity": "technical_only",
                               "hypothesis": {"statement": next_experiment["prediction"],
                                              "variable": "test_token", "prediction": next_experiment["prediction"]},
                               "controlled_variables": {"recipients": action_result.get("recipients", []),
                                                        "provider": ctx.goal.config.get("provider"),
                                                        "reply_capture": capture},
                               "changed_variables": {"test_token": "new_run_token"}},
                           message="Reply-rate goal not met; next controlled test proposed")


_PROVIDER_EVENT_KINDS = {
    "sent": "email_provider_sent",
    "delivered": "email_delivered",
    "delivery_delayed": "email_delivery_delayed",
    "opened": "email_opened",
    "clicked": "email_clicked",
    "bounced": "email_bounced",
    "complained": "email_complained",
    "failed": "email_provider_failed",
    "suppressed": "email_suppressed",
}


def _observe_test_provider(ctx, action_result):
    """Read provider truth and return only evidence not already stored."""
    from .workflows.email import analytics, providers

    existing = list(ctx.cycle.get("evidence") or ())
    known_events = {
        (item["payload"].get("provider_id"), item["payload"].get("provider_event"))
        for item in existing if item["kind"].startswith("email_")
    }
    known_received = {
        item["payload"].get("received_id") for item in existing
        if item["kind"] in {"reply", "email_auto_reply"}
    }
    observed = []
    sent_items = [item["payload"] for item in existing if item["kind"] == "email_sent"]
    for sent in sent_items:
        provider = (sent.get("provider") or providers.EMAIL_PROVIDER or "").strip().lower()
        provider_id = sent.get("provider_id")
        if not provider_id:
            continue
        status = providers.fetch_email_status(str(provider_id), provider=provider)
        if status.get("error"):
            event = f"error:{status.get('status')}:{status.get('message')}"
            key = (provider_id, event)
            if key not in known_events:
                observed.append({"kind": "email_observer_error", "source": provider,
                                 "validity": "technical_only", "payload": {
                                     "recipient": sent.get("recipient"), "provider": provider,
                                     "provider_id": provider_id, "provider_event": event}})
                known_events.add(key)
            continue
        event = str(status.get("last_event") or "unknown").strip().lower()
        key = (provider_id, event)
        if key in known_events:
            continue
        observed.append({"kind": _PROVIDER_EVENT_KINDS.get(event, "email_provider_event"),
                         "source": provider, "validity": "technical_only", "payload": {
                             "recipient": sent.get("recipient"), "provider": provider,
                             "provider_id": provider_id, "provider_event": event}})
        known_events.add(key)

    capture = action_result.get("reply_capture") or _capture_mode(ctx.goal.config)
    if capture not in {"resend_inbound", "gmail_inbox"}:
        return observed
    provider = (ctx.goal.config.get("provider") or providers.EMAIL_PROVIDER or "").strip().lower()
    list_provider = "gmail_imap" if capture == "gmail_inbox" else provider
    if not providers.cap_received(list_provider):
        return observed
    listing = providers.list_received_emails(provider=list_provider)
    if listing.get("error"):
        return observed
    recipients = {str(item.get("recipient") or "").strip().lower() for item in sent_items}
    token = str(action_result.get("token") or "").casefold()
    for received in listing.get("data") or []:
        received_id = received.get("id")
        if not received_id or received_id in known_received:
            continue
        sender = parseaddr(str(received.get("from") or ""))[1].strip().lower()
        subject = str(received.get("subject") or "")
        if sender not in recipients or (token and token not in subject.casefold()):
            continue
        auto = (analytics.classify_reply_kind(
            subject, received.get("auto_submitted"), received.get("x_autoreply"))
            == "auto")
        observed.append({"kind": "email_auto_reply" if auto else "reply",
                         "source": capture, "validity": "technical_only",
                         "payload": {"recipient": sender, "received_id": received_id,
                                     "provider": provider, "subject": subject,
                                     "received_at": received.get("created_at")}})
        known_received.add(received_id)
    return observed


def _capture_mode(config):
    value = str(config.get("reply_capture") or "manual_inbox").strip().lower()
    if value in {"manual", "manual_director_evidence", "company_evidence"}:
        return "manual_inbox"
    return value


def _capture_setup_required(ctx, reason, readiness=None):
    payload = {"action": "configure_reply_capture", "reason": reason,
               "readiness": readiness or {}, "metric": ctx.goal.metric}
    return StageResult("guardrail", payload, RunStatus.BLOCKED, Stage.ACT,
                       message="Reply-rate evidence is not automatically observable",
                       attention={
                           "capability": "inbound_email_setup",
                           "owner": "director",
                           "required_user_action": (
                               "Configure reply capture (receiving-enabled domain or Gmail IMAP credentials) and Reply-To, then retry this run"),
                           "completion_evidence": "reply capture readiness probe passes (Gmail IMAP login OK or receiving-enabled domain)",
                           "next_trigger": f"company retry {ctx.goal.id}",
                           "payload": payload,
                       })


def _parse_time(value):
    if not value:
        return None
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _next_poll(config, deadline):
    seconds = max(1.0, float(config.get("observer_interval_seconds", 300)))
    return min(deadline, datetime.now(timezone.utc) + timedelta(seconds=seconds))


def _dispatch_poll(config):
    """Next wake-up while a background dispatch is still pending.

    The runner re-advances the run at resume_at; each re-entry re-checks
    the dispatch file (is_pending / execute reconciliation), so the poll is
    a cheap file read and the batch never blocks the runner tick.
    """
    seconds = max(5.0, float(config.get("observer_interval_seconds", 300)))
    return datetime.now(timezone.utc) + timedelta(seconds=seconds)


def _compare(value, operator, target):
    return {"ge": value >= target, "gt": value > target, "eq": value == target,
            "le": value <= target, "lt": value < target}.get(operator, False)


def _valid_email(address):
    return bool(re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", str(address or "")))


def _as_html(body):
    return "<p>" + html.escape(body).replace("\n\n", "</p><p>").replace("\n", "<br>") + "</p>"


def _write_test_preview(goal_id, batch):
    root = Path(__file__).resolve().parents[3]
    directory = root / ".spielos" / "artifacts" / goal_id
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{batch['batch_id']}-preview.md"
    lines = ["# Controlled email system test", "", f"Run: `{batch['batch_id']}`",
             "Validity: `technical_only`", "", f"Subject: {batch['subject']}", "", batch["body"],
             "", "Recipients:"] + [f"- {recipient}" for recipient in batch["recipients"]]
    path.write_text("\n".join(lines) + "\n")
    return path
