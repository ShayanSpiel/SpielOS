"""Email bundle tests: strict composition, validators, policy rules,
decider, evaluator. Synthetic data only — no network, no real master."""

import json
import sys
import tempfile
import unittest
import unittest.mock
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from company.departments.outbound.control import Control  # noqa: E402
from company.departments.outbound.data import OutboundStore  # noqa: E402
from company.departments.outbound.workflows.email import compose, decider, evaluator, policy_rules  # noqa: E402
from company.departments.outbound.workflows.email import config, outbound, providers, report as report_data  # noqa: E402
from company.departments.outbound.workflows.email.validators import validate  # noqa: E402
from company.departments.outbound.workflows.email.templates import (  # noqa: E402
    SIGNATURE_HTML, SIGNATURE_TEXT,
)


_CONFIG_ATTRS = ("SENT_LOG_PATH", "METRICS_PATH", "CONTENT_PATH", "DATABASE_PATH")
_CONFIG_SNAPSHOT = {}


def setUpModule():
    """Hermetic guard: tests in this module redirect config paths to temp
    dirs. Snapshot the real values so pollution can never leak into (or out
    of) this module — the shared `config` object is process-global."""
    for attr in _CONFIG_ATTRS:
        if hasattr(config, attr):
            _CONFIG_SNAPSHOT[attr] = getattr(config, attr)


def tearDownModule():
    for attr, value in _CONFIG_SNAPSHOT.items():
        setattr(config, attr, value)


def make_ctx():
    tmp = Path(tempfile.mkdtemp())
    config.SENT_LOG_PATH = tmp / "sent.json"
    config.METRICS_PATH = tmp / "metrics.json"
    config.CONTENT_PATH = tmp / "content.json"
    config.DATABASE_PATH = tmp / "master.xlsx"
    outbound.save_sent_log({"sent": [], "failed": []})
    with open(config.METRICS_PATH, "w") as f:
        json.dump({"emails": {}, "replies": []}, f)
    store = OutboundStore(tmp / "outbound.sqlite")
    return tmp, store, Control(tmp / "control.json")


RESEARCHED = {
    "lead_id": "EN-100",
    "email": "owner@acme-uk.com",
    "company": "Acme UK",
    "contact_name": "Jane Doe",
    "title": "Head of Recruitment",
    "segment": "recruitment agency",
    "country": "United Kingdom",
    "language": "English",
    "send_recommendation": "Ready to personalized",
    "outreach_tier": "A",
    "email_status": "Verified",
    "personalization_hook": ("Reference Jane Doe's role as Head of Recruitment by name "
                             "and one observable fact about Acme UK's staffing work"),
    "pain_hypothesis": ("Acme UK staffs 40 agency clients across the UK, and the shortlist "
                        "coordination is likely still handled by hand"),
    "suggested_cta": "map the shortlist stage with you",
}

PLACEHOLDER_PAIN = dict(RESEARCHED, **{
    "lead_id": "EN-101",
    "email": "owner2@acme2-uk.com",
    "pain_hypothesis": "The company likely has a staffing workflow",
})


class ComposeTests(unittest.TestCase):
    def test_researched_lead_composes(self):
        subject, html, text, reason = compose.render_checked(RESEARCHED, seq=0)
        self.assertIsNone(reason)
        self.assertIn("Acme UK", subject)
        self.assertIn("Jane", text)
        self.assertIn("shortlist", text.lower())

    def test_placeholder_pain_is_skipped(self):
        subject, html, text, reason = compose.render_checked(PLACEHOLDER_PAIN, seq=0)
        self.assertIsNone(subject)
        self.assertIn("unprepared", reason)

    def test_short_pain_is_skipped(self):
        c = dict(RESEARCHED, lead_id="EN-102", email="x@y-uk.com",
                 pain_hypothesis="They have staffing work")
        subject, *_rest, reason = compose.render_checked(c, seq=0)
        self.assertIsNone(subject)
        self.assertIn("unprepared", reason)

    def test_missing_hook_is_skipped(self):
        c = dict(RESEARCHED, lead_id="EN-103", email="x@z-uk.com",
                 personalization_hook="")
        subject, *_rest, reason = compose.render_checked(c, seq=0)
        self.assertIsNone(subject)
        self.assertIn("unprepared", reason)

    def test_em_dash_normalized(self):
        c = dict(RESEARCHED, lead_id="EN-104", email="x@w-uk.com",
                 pain_hypothesis="Acme UK staffs clients, and coordination is likely handled by hand — week after week")
        subject, html, text, reason = compose.render_checked(c, seq=0)
        self.assertIsNone(reason)
        self.assertNotIn("\u2014", text)

    def test_build_batch_dedupes_domains_and_skips_unprepared(self):
        c2 = dict(RESEARCHED, lead_id="EN-105", email="partner@acme-uk.com")
        built = compose.build_batch_emails("B1", [RESEARCHED, c2, PLACEHOLDER_PAIN], "h")
        self.assertEqual(len(built["emails"]), 1)
        skipped_ids = [s["lead_id"] for s in built["skipped"]]
        self.assertIn("EN-105", skipped_ids)  # same domain as EN-100
        self.assertIn("EN-101", skipped_ids)  # placeholder pain


class SignatureApplyTests(unittest.TestCase):
    """Owner directive 2026-08-22/23 (supersedes goal-booking-signature-
    outbound-20260819): every composed email carries the Apply-first CTA
    ("Apply — Free Review", no required call) in both signature layers, plus
    UTM parameters, and carries NO booking/cal.com CTA anywhere."""

    APPLY_LINE = "Apply for a Free Review"
    APPLY_LINK = "https://spielos.xyz/apply/"

    def test_signature_html_has_apply_line_and_link(self):
        self.assertIn(self.APPLY_LINE, SIGNATURE_HTML)
        self.assertIn(self.APPLY_LINK, SIGNATURE_HTML)

    def test_signature_text_has_apply_line_and_link(self):
        self.assertIn(self.APPLY_LINE, SIGNATURE_TEXT)
        self.assertIn(self.APPLY_LINK, SIGNATURE_TEXT)

    def test_signature_carries_no_booking_cta(self):
        for sig in (SIGNATURE_HTML, SIGNATURE_TEXT):
            self.assertNotIn("cal.com", sig, sig[:120])
            self.assertNotIn("/book/", sig, sig[:120])

    def test_apply_link_carries_signature_utm_params(self):
        for sig in (SIGNATURE_HTML, SIGNATURE_TEXT):
            self.assertIn("utm_source=outbound-email", sig, sig[:120])
            self.assertIn("utm_medium=email", sig, sig[:120])
            self.assertIn("utm_campaign=outbound-sig", sig, sig[:120])

    def test_rendered_email_carries_apply_cta(self):
        subject, html, text, reason = compose.render_checked(RESEARCHED, seq=0)
        self.assertIsNone(reason)
        self.assertIn(self.APPLY_LINE, html)
        self.assertIn(self.APPLY_LINK, html)
        self.assertIn(self.APPLY_LINE, text)
        self.assertIn(self.APPLY_LINK, text)
        self.assertNotIn("cal.com", html)


class ValidatorTests(unittest.TestCase):
    def test_segment_fallback_flagged(self):
        batch = {"emails": [{
            "lead_id": "L1",
            "subject": "Staffing loop at X",
            "body_html": "<p>hi</p>",
            "body_text": ("Recruitment runs on repeated shortlisting of candidates "
                          "with resume review and feedback email threads."),
        }]}
        issues = validate(None, batch)
        self.assertTrue(any(i["code"] == "segment_fallback" for i in issues))

    def test_clean_email_passes(self):
        batch = {"emails": [{
            "lead_id": "L1",
            "subject": "Staffing loop at Acme",
            "body_html": "<p>hi Jane</p>",
            "body_text": "Hi Jane, your shortlist stage looks manual. What do you think?",
        }]}
        self.assertEqual(validate(None, batch), [])

    def test_over_word_limit_flagged(self):
        words = "word " * 90
        batch = {"emails": [{"lead_id": "L1", "subject": "s",
                             "body_html": "<p>t</p>", "body_text": words}]}
        issues = validate(None, batch)
        self.assertTrue(any(i["code"] == "over_word_limit" for i in issues))


class PolicyRuleTests(unittest.TestCase):
    def _snapshot(self, **window):
        return {"window_totals": window, "meta": {"guardrails": [
            {"name": "bounce rate", "metric": "bounce_rate", "max": 0.02},
            {"name": "spam rate", "metric": "spam_rate", "max": 0.0008}]}}

    def test_bounce_breach_blocks(self):
        r = policy_rules.evaluate(self._snapshot(bounce_rate=0.05, spam_rate=0.0))
        self.assertFalse(r["ok"])
        self.assertEqual(r["breaches"][0]["name"], "bounce rate")

    def test_bounce_suppressed_is_downgraded(self):
        with unittest.mock.patch.object(outbound, "read_contacts", return_value=[
                {"email": "b@x.com", "email_status": "Bounced; suppressed"}]):
            snap = self._snapshot(bounce_rate=0.05, spam_rate=0.0)
            snap["bounced_emails"] = ["b@x.com"]
            r = policy_rules.evaluate(snap)
        self.assertTrue(r["ok"])

    def test_spam_override_timeboxed(self):
        snap = self._snapshot(bounce_rate=0.0, spam_rate=0.01)
        knobs = {"gate_spam_override_until": "2099-01-01T00:00:00+00:00"}
        r = policy_rules.evaluate(snap, knobs)
        self.assertTrue(r["ok"])
        knobs = {"gate_spam_override_until": "2001-01-01T00:00:00+00:00"}
        r = policy_rules.evaluate(snap, knobs)
        self.assertFalse(r["ok"])

    def test_noisy_data_is_a_problem(self):
        snap = self._snapshot(bounce_rate=0.0, spam_rate=0.0, sent=10, unknown=5)
        r = policy_rules.evaluate(snap)
        self.assertFalse(r["ok"])
        self.assertTrue(r["problems"])


class ProviderReplyTests(unittest.TestCase):
    def test_received_capability_can_be_selected_per_provider(self):
        self.assertTrue(providers.cap_received("resend"))
        self.assertFalse(providers.cap_received("smtp"))

    def test_received_listing_routes_by_explicit_provider(self):
        with unittest.mock.patch.object(providers, "_open", return_value={"data": []}) as opened:
            result = providers.list_received_emails("resend")
        self.assertEqual(result, {"data": []})
        self.assertIn("/emails/receiving", opened.call_args.args[0])
        unsupported = providers.list_received_emails("smtp")
        self.assertTrue(unsupported["error"])

    def test_receiving_domain_must_be_verified_and_enabled(self):
        domains = {"data": [{"name": "reply.spielos.xyz", "status": "verified",
                              "capabilities": {"sending": "enabled", "receiving": "enabled"}},
                            {"name": "spielos.xyz", "status": "verified",
                              "capabilities": {"sending": "enabled", "receiving": "disabled"}}]}
        with unittest.mock.patch.object(providers, "_open", return_value=domains):
            ready = providers.receiving_domain_status("runs@reply.spielos.xyz", "resend")
            disabled = providers.receiving_domain_status("shayan@spielos.xyz", "resend")
        self.assertTrue(ready["ready"])
        self.assertFalse(disabled["ready"])
        self.assertEqual(disabled["receiving"], "disabled")


class DeciderTests(unittest.TestCase):
    def _ctx(self, store, control):
        return type("Ctx", (), {"control": control, "store": store})()

    def _snap(self, **over):
        snap = {
            "gate": {"ok": True, "breaches": []},
            "cap": {"remaining": 100, "cap": 200, "sent_today": 0, "phase": "t"},
            "queue": {"size": 5},
            "totals": {"sent": 60},
            "window_totals": {"sent": 60, "open_rate": 0.4, "reply_rate": 0.1,
                              "bounce_rate": 0.0, "spam_rate": 0.0},
            "meta": {"goal": {"metric": "reply_rate", "target": 0.3},
                     "guardrails": [{"metric": "bounce_rate", "max": 0.02},
                                    {"metric": "spam_rate", "max": 0.0008}],
                     "supporting_kpis": [{"metric": "open_rate", "target": 0.8}]},
        }
        snap.update(over)
        return snap

    def test_config_broken_holds(self):
        _, store, control = make_ctx()
        ctx = self._ctx(store, control)
        i = decider.decide(ctx, self._snap(config={"ok": False, "error": "no key"}))
        self.assertEqual(i["action"], "hold")
        self.assertIn("config", i["reason"])

    def test_gate_blocked_holds(self):
        _, store, control = make_ctx()
        ctx = self._ctx(store, control)
        i = decider.decide(ctx, self._snap(
            gate={"ok": False, "breaches": [{"name": "bounce rate", "current": 0.05, "max": 0.02}]}))
        self.assertEqual(i["action"], "hold")
        self.assertIn("gate blocked", i["reason"])

    def test_cap_reached_holds(self):
        _, store, control = make_ctx()
        ctx = self._ctx(store, control)
        i = decider.decide(ctx, self._snap(
            cap={"remaining": 0, "cap": 200, "sent_today": 200, "phase": "steady"}))
        self.assertEqual(i["action"], "hold")
        self.assertIn("cap", i["reason"])

    def test_queue_empty_holds(self):
        _, store, control = make_ctx()
        ctx = self._ctx(store, control)
        i = decider.decide(ctx, self._snap(queue={"size": 0}))
        self.assertEqual(i["action"], "hold")
        self.assertIn("queue", i["reason"])

    def test_sample_too_small_keeps_sending(self):
        _, store, control = make_ctx()
        ctx = self._ctx(store, control)
        i = decider.decide(ctx, self._snap(totals={"sent": 5}, window_totals={
            "sent": 5, "open_rate": 0.0, "reply_rate": 0.0}))
        self.assertEqual(i["action"], "prepare_batch")
        self.assertIn("need 30", i["detail"])

    def test_open_stage_picks_subject_lever(self):
        _, store, control = make_ctx()
        ctx = self._ctx(store, control)
        i = decider.decide(ctx, self._snap())
        self.assertEqual(i["variable"], "subject")
        self.assertTrue(i["levers"].get("rotate_subjects"))

    def test_knowledge_reject_vetoes_repeat(self):
        _, store, control = make_ctx()
        store.record_trial("subject", {"verdict": "reject", "batch": "B0"})
        ctx = self._ctx(store, control)
        i = decider.decide(ctx, self._snap())
        self.assertEqual(i["variable"], "subject")
        self.assertIn("NEW angle", i["detail"])


class EvaluatorTests(unittest.TestCase):
    def _ctx(self):
        _, store, control = make_ctx()
        return type("Ctx", (), {"control": control, "store": store})()

    def test_verdict_inconclusive_without_baseline(self):
        outcome = evaluator.measure(self._ctx(), {"id": "B1", "intervention": {}})
        self.assertEqual(outcome["verdict"]["verdict"], "inconclusive")

    def test_verdict_keep_when_improved(self):
        ctx = self._ctx()
        ctx.store.upsert_batch({"id": "B0", "workflow": "email", "phase": "evaluate",
                                "metrics": {"sent": 30, "reply_rate": 0.10}})
        with unittest.mock.patch.object(evaluator.analytics, "aggregate",
                                        return_value={"sent": 30, "reply_rate": 0.20}):
            outcome = evaluator.measure(ctx, {"id": "B1", "intervention": {}})
        self.assertEqual(outcome["verdict"]["verdict"], "keep")

    def test_verdict_reject_when_worse(self):
        ctx = self._ctx()
        ctx.store.upsert_batch({"id": "B0", "workflow": "email", "phase": "evaluate",
                                "metrics": {"sent": 30, "reply_rate": 0.10}})
        with unittest.mock.patch.object(evaluator.analytics, "aggregate",
                                        return_value={"sent": 30, "reply_rate": 0.02}):
            outcome = evaluator.measure(ctx, {"id": "B1", "intervention": {}})
        self.assertEqual(outcome["verdict"]["verdict"], "reject")

    def test_verdict_inconclusive_within_noise(self):
        ctx = self._ctx()
        ctx.store.upsert_batch({"id": "B0", "workflow": "email", "phase": "evaluate",
                                "metrics": {"sent": 30, "reply_rate": 0.10}})
        with unittest.mock.patch.object(evaluator.analytics, "aggregate",
                                        return_value={"sent": 30, "reply_rate": 0.11}):
            outcome = evaluator.measure(ctx, {"id": "B1", "intervention": {}})
        self.assertEqual(outcome["verdict"]["verdict"], "inconclusive")

    def test_goal_check_states(self):
        ctx = self._ctx()
        with unittest.mock.patch.object(outbound, "load_sent_log", return_value={
                "sent": [], "failed": []}):
            with unittest.mock.patch.object(evaluator, "_window_totals", return_value={
                    "sent": 40, "reply_rate": 0.35, "unknown": 0,
                    "denied": 0, "unresolved": 0}):
                r = evaluator.goal_check(ctx, {"sent": 40})
                self.assertEqual(r["state"], "achieved")

            with unittest.mock.patch.object(evaluator, "_window_totals", return_value={
                    "sent": 40, "reply_rate": 0.10, "unknown": 0,
                    "denied": 0, "unresolved": 0}):
                r = evaluator.goal_check(ctx, {"sent": 40})
                self.assertEqual(r["state"], "not_yet")

            with unittest.mock.patch.object(evaluator, "_window_totals", return_value={
                    "sent": 40, "reply_rate": 0.10, "unknown": 12,
                    "denied": 0, "unresolved": 0}):
                r = evaluator.goal_check(ctx, {"sent": 40})
                self.assertEqual(r["state"], "blocked")


class ReportTests(unittest.TestCase):
    def _ctx(self):
        _, store, control = make_ctx()
        return type("Ctx", (), {"control": control, "store": store,
                                "workflow": type("W", (), {"name": "email"})})()

    def test_domain_report_has_all_sections(self):
        ctx = self._ctx()
        batch = {"id": "EMAIL-2026-08-09-b01", "batch": {
            "hypothesis": "research-first",
            "emails": [{"lead_id": "EN-100", "subject": "Shortlist stage",
                        "body_text": "Jane, the shortlist coordination is manual.",
                        "body_html": "<p>x</p>"}]},
            "intervention": {"variable": "subject", "detail": "rotate",
                             "prediction": "opens up"}}
        data = report_data.report(ctx, batch, None)
        self.assertIn("campaign", data)
        self.assertIn("providers", data)
        self.assertIn("example", data)
        self.assertIn("guardrails", data)
        self.assertIn("window", data)
        self.assertIn("leads", data)
        self.assertEqual(data["example"]["lead_id"], "EN-100")
        self.assertEqual(data["example"]["subject"], "Shortlist stage")
        self.assertIn("needed_to_gather", data["leads"])

    def test_domain_report_survives_missing_master(self):
        ctx = self._ctx()
        config.DATABASE_PATH = Path(tempfile.mkdtemp()) / "missing.xlsx"
        data = report_data.report(ctx, {"id": "B1", "batch": {}}, None)
        self.assertEqual(data["leads"]["total"], 0)
        self.assertEqual(data["leads"]["queue"], 0)


if __name__ == "__main__":
    unittest.main()


class GmailCaptureTests(unittest.TestCase):
    """Unified Gmail reply capture (owner direction 2026-08-10): parsing,
    provider resolution, and sync_replies matching. Hermetic — no network."""

    @staticmethod
    def _raw_message(subject="Re: Agentic ops at Acme UK", sender="owner@acme-uk.com",
                     msg_id="<gmailtest123@acme-uk.com>", date="Mon, 10 Aug 2026 09:00:00 +0000",
                     body="Yes, let's talk. Best, Jane"):
        import email as email_mod
        msg = email_mod.message.EmailMessage()
        msg["From"] = f"Jane Doe <{sender}>"
        msg["To"] = "replies@spielos.xyz"
        msg["Subject"] = subject
        msg["Message-ID"] = msg_id
        msg["Date"] = date
        msg["In-Reply-To"] = "<sent-msg-1@resend>"
        msg.set_content(body)
        return msg.as_bytes()

    def test_parse_email_date_utc(self):
        from company.departments.outbound.workflows.email import providers
        iso = providers._parse_email_date("Mon, 10 Aug 2026 09:00:00 +0000")
        self.assertTrue(iso.startswith("2026-08-10T09:00:00"))

    def test_decode_mime_header_encoded(self):
        from company.departments.outbound.workflows.email import providers
        raw = "=?utf-8?B?UmU6IEFnZW50aWMgb3BzIGF0IEFjbWU=?="
        self.assertEqual(providers._decode_mime_header(raw), "Re: Agentic ops at Acme")

    def test_body_text_multipart(self):
        from company.departments.outbound.workflows.email import providers
        raw = self._raw_message()
        from email import message_from_bytes as mfb
        msg = mfb(raw)
        self.assertIn("let's talk", providers._gmail_body_text(msg))

    def test_list_received_emails_resolves_gmail(self):
        from company.departments.outbound.workflows.email import providers
        cfg = providers._cfg_module
        fake = {"data": [{"id": "gmail-<gmailtest123@acme-uk.com>", "from": "owner@acme-uk.com",
                          "subject": "Re: Agentic ops at Acme UK", "message_id": "<gmailtest123@acme-uk.com>",
                          "created_at": "2026-08-10T09:00:00+00:00", "text": "Yes, let's talk."}]}
        with unittest.mock.patch.object(cfg, "REPLY_CAPTURE", "gmail_imap"), \
             unittest.mock.patch.object(cfg, "GMAIL_IMAP_USER", "66shayan@gmail.com"), \
             unittest.mock.patch.object(cfg, "GMAIL_IMAP_APP_PASSWORD", "app-pass"), \
             unittest.mock.patch.object(providers, "_list_gmail_imap", return_value=fake):
            self.assertTrue(providers.cap_received())
            self.assertEqual(providers.list_received_emails(), fake)

    def test_sync_replies_records_gmail_reply_and_auto(self):
        import json as _json
        from company.departments.outbound.workflows.email import analytics, providers
        tmp = Path(tempfile.mkdtemp())
        config.METRICS_PATH = tmp / "metrics.json"
        with open(config.METRICS_PATH, "w") as f:
            _json.dump({"emails": {}, "replies": []}, f)
        sent = {"sent": [{"lead_id": "EN-100", "email": "owner@acme-uk.com",
                          "company": "Acme UK", "subject": "Agentic ops at Acme UK",
                          "variant": "offer-1"}]}
        listing = {"data": [
            {"id": "gmail-<one@acme-uk.com>", "from": "owner@acme-uk.com",
             "subject": "Re: Agentic ops at Acme UK", "message_id": "<one@acme-uk.com>",
             "created_at": "2026-08-10T09:00:00+00:00"},
            {"id": "gmail-<two@acme-uk.com>", "from": "owner@acme-uk.com",
             "subject": "Out of office: away until Friday", "message_id": "<two@acme-uk.com>",
             "created_at": "2026-08-10T09:05:00+00:00"},
        ]}
        with unittest.mock.patch.object(providers, "cap_received", return_value=True), \
             unittest.mock.patch.object(providers, "list_received_emails", return_value=listing):
            metrics = {"emails": {}, "replies": []}
            added = analytics.sync_replies(sent, metrics)
        self.assertEqual(added, 2)
        kinds = {r["received_id"]: r["kind"] for r in metrics["replies"]}
        self.assertEqual(kinds["gmail-<one@acme-uk.com>"], "reply")
        self.assertEqual(kinds["gmail-<two@acme-uk.com>"], "auto")
        self.assertEqual(metrics["replies"][0]["lead_id"], "EN-100")
        self.assertEqual(metrics["replies"][0]["email"], "owner@acme-uk.com")

    def test_sync_replies_dedupes_by_received_id(self):
        import json as _json
        from company.departments.outbound.workflows.email import analytics, providers
        tmp = Path(tempfile.mkdtemp())
        config.METRICS_PATH = tmp / "metrics.json"
        sent = {"sent": [{"lead_id": "EN-100", "email": "owner@acme-uk.com",
                          "company": "Acme UK", "subject": "Agentic ops at Acme UK",
                          "variant": "offer-1"}]}
        listing = {"data": [
            {"id": "gmail-<one@acme-uk.com>", "from": "owner@acme-uk.com",
             "subject": "Re: Agentic ops at Acme UK", "message_id": "<one@acme-uk.com>",
             "created_at": "2026-08-10T09:00:00+00:00"},
        ]}
        with unittest.mock.patch.object(providers, "cap_received", return_value=True), \
             unittest.mock.patch.object(providers, "list_received_emails", return_value=listing):
            metrics = {"emails": {}, "replies": []}
            analytics.sync_replies(sent, metrics)
            second = analytics.sync_replies(sent, metrics)
        self.assertEqual(second, 0)
        self.assertEqual(len(metrics["replies"]), 1)

    def test_gmail_imap_status_requires_credentials(self):
        from company.departments.outbound.workflows.email import providers
        cfg = providers._cfg_module
        with unittest.mock.patch.object(cfg, "GMAIL_IMAP_USER", ""), \
             unittest.mock.patch.object(cfg, "GMAIL_IMAP_APP_PASSWORD", ""):
            status = providers.gmail_imap_status()
        self.assertFalse(status["ready"])
        self.assertIn("not configured", status["reason"])


class PendingStatusGateTests(unittest.TestCase):
    """Delivery gate semantics (owner direction 2026-08-10): provider-accepted
    pending sends (sent/delivery_delayed) are not failures; real losses still
    breach. Hermetic — no network."""

    def test_pending_does_not_breach_delivered_rate(self):
        snap = {"window_totals": {"bounce_rate": 0.0, "spam_rate": 0.0,
                                  "sent": 73, "delivered": 70, "pending": 3,
                                  "unknown": 0, "denied": 0, "unresolved": 0},
                "meta": {"guardrails": [
                    {"name": "bounce rate", "metric": "bounce_rate", "max": 0.02},
                    {"name": "spam rate", "metric": "spam_rate", "max": 0.0008}]}}
        r = policy_rules.evaluate(snap)
        self.assertTrue(r["ok"], r)

    def test_real_losses_still_breach_delivered_rate(self):
        snap = {"window_totals": {"bounce_rate": 0.0, "spam_rate": 0.0,
                                  "sent": 73, "delivered": 68, "pending": 3,
                                  "unknown": 0, "denied": 0, "unresolved": 0},
                "meta": {"guardrails": [
                    {"name": "bounce rate", "metric": "bounce_rate", "max": 0.02},
                    {"name": "spam rate", "metric": "spam_rate", "max": 0.0008}]}}
        r = policy_rules.evaluate(snap)
        self.assertFalse(r["ok"])
        self.assertEqual(r["breaches"][0]["name"], "delivered rate")
        self.assertAlmostEqual(r["breaches"][0]["current"], 71 / 73, places=3)

    def test_aggregate_counts_pending(self):
        from company.departments.outbound.workflows.email import analytics
        log = {"sent": [
            {"lead_id": "L1", "email": "a@x.com", "timestamp": "2026-08-10T10:00:00"},
            {"lead_id": "L2", "email": "b@x.com", "timestamp": "2026-08-10T10:01:00"},
            {"lead_id": "L3", "email": "c@x.com", "timestamp": "2026-08-10T10:02:00"},
        ]}
        metrics = {"emails": {
            "L1": {"status": "delivered"},
            "L2": {"status": "sent"},
            "L3": {"status": "delivery_delayed"},
        }, "replies": []}
        agg = analytics.aggregate(log, metrics)
        self.assertEqual(agg["delivered"], 1)
        self.assertEqual(agg["pending"], 2)


class IdempotentExecuteTests(unittest.TestCase):
    """Updated for resend_guard (goal-4357632a68, 2026-08-21): a batch that
    contains an already-sent lead fails fast BEFORE any provider send — no
    partial remainder, no silent dedupe. Supersedes the 2026-08-10
    skip-already-sent contract. Hermetic."""

    def _execute(self, sent_log, batch_leads, contacts):
        from company.departments.outbound.workflows.email import actor, outbound as ob, config
        sent_calls = []
        with unittest.mock.patch.object(ob, "load_sent_log", return_value=sent_log), \
                unittest.mock.patch.object(ob, "save_sent_log", lambda log: None), \
                unittest.mock.patch.object(ob, "read_contacts", return_value=contacts), \
                unittest.mock.patch.object(actor, "_provider_sent_id", return_value=None), \
                unittest.mock.patch.object(actor, "_send_with_cap",
                                           side_effect=lambda *a, **k: sent_calls.append(a[1]) or {"id": "m1"}), \
                unittest.mock.patch.object(config, "THROTTLE_SECONDS", 0), \
                unittest.mock.patch.object(actor.providers, "pick_provider", return_value="resend"):
            _, store, _ = make_ctx()
            ctx = type("Ctx", (), {"store": store})()
            batch = {"id": "B1", "emails": batch_leads}
            result = actor.execute(ctx, batch, dry=False)
        return result, sent_calls

    def test_mixed_batch_fails_fast_before_any_send(self):
        log = {"sent": [{"lead_id": "L1", "email": "a@x.com"}], "failed": []}
        contacts = [
            {"lead_id": "L1", "email": "a@x.com", "company": "A", "contact_name": "Ann"},
            {"lead_id": "L2", "email": "b@x.com", "company": "B", "contact_name": "Bob"},
        ]
        leads = [
            {"lead_id": "L1", "subject": "s1", "body_html": "h", "body_text": "t", "features": {}},
            {"lead_id": "L2", "subject": "s2", "body_html": "h", "body_text": "t", "features": {}},
        ]
        with self.assertRaises(RuntimeError) as guard:
            self._execute(log, leads, contacts)
        self.assertIn("resend_guard", str(guard.exception))
        # fail-fast: the fresh lead L2 is never dispatched either (the
        # guard raises before any _send_with_cap invocation).

    def test_all_already_sent_is_not_a_failure(self):
        log = {"sent": [{"lead_id": "L1", "email": "a@x.com"},
                        {"lead_id": "L2", "email": "b@x.com"}], "failed": []}
        contacts = [
            {"lead_id": "L1", "email": "a@x.com", "company": "A", "contact_name": "Ann"},
            {"lead_id": "L2", "email": "b@x.com", "company": "B", "contact_name": "Bob"},
        ]
        leads = [
            {"lead_id": "L1", "subject": "s1", "body_html": "h", "body_text": "t", "features": {}},
            {"lead_id": "L2", "subject": "s2", "body_html": "h", "body_text": "t", "features": {}},
        ]
        with self.assertRaises(RuntimeError) as guard:
            self._execute(log, leads, contacts)
        self.assertIn("resend_guard", str(guard.exception))
        self.assertIn("L1", str(guard.exception))
        self.assertIn("L2", str(guard.exception))


class SuppressedDeliveredRateTests(unittest.TestCase):
    """2026-08-11: suppressed window bounces leave the judged population
    for the delivered-rate rule too. Hermetic."""

    def _snap(self, **window):
        snap = {"window_totals": window, "meta": {"guardrails": [
            {"name": "bounce rate", "metric": "bounce_rate", "max": 0.02},
            {"name": "spam rate", "metric": "spam_rate", "max": 0.0008}]}}
        return snap

    def test_all_suppressed_bounces_do_not_block_delivered_rate(self):
        with unittest.mock.patch.object(outbound, "read_contacts", return_value=[
                {"email": "bad@x.com", "email_status": "Bounced; suppressed"}]):
            snap = self._snap(sent=37, delivered=28, bounced=5, pending=4,
                              bounce_rate=0.135, spam_rate=0.0,
                              unknown=0, denied=0, unresolved=0)
            snap["bounced_emails"] = ["bad@x.com"]
            r = policy_rules.evaluate(snap)
        self.assertTrue(r["ok"], r)

    def test_unsuppressed_bounce_still_blocks_delivered_rate(self):
        with unittest.mock.patch.object(outbound, "read_contacts", return_value=[
                {"email": "bad@x.com", "email_status": ""}]):
            snap = self._snap(sent=37, delivered=28, bounced=5, pending=4,
                              bounce_rate=0.135, spam_rate=0.0,
                              unknown=0, denied=0, unresolved=0)
            snap["bounced_emails"] = ["bad@x.com"]
            r = policy_rules.evaluate(snap)
        self.assertFalse(r["ok"])
        self.assertEqual(r["breaches"][0]["name"], "bounce rate")


class ReplyTruthReconcileTests(unittest.TestCase):
    """Bounded repair 2026-08-11 (change-326f0c32e6, goal-reply-truth-20260811):
    header-aware auto-reply detection with stored classification inputs,
    per-lead dedupe reconciliation, and inbox-truth metrics. The reply fixture
    is a synthetic ledger with the same shapes as production records."""

    LIVE_REPLIES = [
        {"received_id": None, "lead_id": "TEST-loop-001", "email": "tester@example.com",
         "company": "Test", "variant": "Test", "subject": "SpielOS outbound loop test",
         "message_id": None, "received_at": None,
         "recorded_at": "2026-08-07T19:45:08.453097+00:00",
         "kind": "reply", "note": "user reply to loop test"},
        {"received_id": "gmail-<CA+Y0w+cMpwH53Lar+dNUhSe-Yo832N=JAY8bfTX3ZYv6sWi=fA@mail.gmail.com>",
         "lead_id": "TEST-loop-001", "email": "tester@example.com", "company": "Test",
         "variant": "Test", "subject": "Re: SpielOS outbound loop test",
         "message_id": "<CA+Y0w+cMpwH53Lar+dNUhSe-Yo832N=JAY8bfTX3ZYv6sWi=fA@mail.gmail.com>",
         "received_at": "2026-08-07T19:42:33+00:00",
         "recorded_at": "2026-08-10T17:19:12.442354+00:00",
         "kind": "reply", "note": ""},
        {"received_id": "gmail-<aa02f018e7cf443d991a47ee13f7606b@CWLP123MB6411.GBRP123.PROD.OUTLOOK.COM>",
         "lead_id": "EN-1152", "email": "alex.lee@example-recruiting.test",
         "company": "Example Recruiting Co", "variant": "researched-personal",
         "subject": "Automatic reply: Recruiting ops at Example Recruiting Co",
         "message_id": "<aa02f018e7cf443d991a47ee13f7606b@CWLP123MB6411.GBRP123.PROD.OUTLOOK.COM>",
         "received_at": "2026-08-09T12:24:33+00:00",
         "recorded_at": "2026-08-10T17:19:12.442470+00:00",
         "kind": "auto", "note": "Alex Lee / Example Recruiting Co — OOO auto-reply 2026-08-09: "
         "'out of office with limited access, returning Monday 2026-08-10'. Accounts queries -> "
         "accounts@example-recruiting.test (role inbox, out of policy). Deliverability CONFIRMED by "
         "OOO reply; master status upgraded to Verified.",
         "subclass": "out-of-office"},
        {"received_id": "gmail-<26c91a6e846f485abb5890f30b5f3678@LO2P123MB5480.GBRP123.PROD.OUTLOOK.COM>",
         "lead_id": "EN-1153", "email": "jordan.west@example-group.test",
         "company": "Example Group", "variant": "researched-personal",
         "subject": "Automatic reply: Screening loop at Example Group",
         "message_id": "<26c91a6e846f485abb5890f30b5f3678@LO2P123MB5480.GBRP123.PROD.OUTLOOK.COM>",
         "received_at": "2026-08-09T12:27:06+00:00",
         "recorded_at": "2026-08-10T17:19:12.442482+00:00",
         "kind": "auto", "note": "Jordan West / Example Group — OOO auto-reply 2026-08-09: 'away on leave, "
         "no email access'. Urgent -> Casey Lee 07000 000000 / casey.lee@example-group.test (confirmed "
         "Group Candidate Manager on example-group.test/about). Deliverability CONFIRMED by OOO reply; "
         "master status upgraded to Verified.",
         "subclass": "out-of-office"},
        {"received_id": "gmail-<CA+Y0w+fzCSbC6Gks_hSva4Wz2u2jpLx00GfJgYpcx2HagZGyMQ@mail.gmail.com>",
         "lead_id": "TEST-loop-001", "email": "tester@example.com", "company": "Test",
         "variant": "Test", "subject": "Re: SpielOS loop test 617052",
         "message_id": "<CA+Y0w+fzCSbC6Gks_hSva4Wz2u2jpLx00GfJgYpcx2HagZGyMQ@mail.gmail.com>",
         "received_at": "2026-08-10T00:21:12+00:00",
         "recorded_at": "2026-08-10T17:19:12.442504+00:00",
         "kind": "reply", "note": ""},
        {"received_id": "gmail-<msmuuj62.b570adbe-95d2-46d2-9330-4c2d63d1e7bc@we.are.superhuman.com>",
         "lead_id": "EN-1157", "email": "riley@example-staffing.test",
         "company": "Example Staffing", "variant": "researched-personal",
         "subject": "Re: Staffing loop at Example Staffing",
         "message_id": "<msmuuj62.b570adbe-95d2-46d2-9330-4c2d63d1e7bc@we.are.superhuman.com>",
         "received_at": "2026-08-10T06:34:02+00:00",
         "recorded_at": "2026-08-10T17:19:12.442514+00:00",
         "kind": "reply", "note": ""},
        {"received_id": "gmail-<CABmWERz6j4fH1HjJWPwiF74y+m0hremvUUeTL-qMtbjtvTtLZg@mail.gmail.com>",
         "lead_id": "AP-7d1096", "email": "casey@example-agency.test",
         "company": "Example Agency", "variant": "researched-personal",
         "subject": "Re: Delivery loop cost",
         "message_id": "<CABmWERz6j4fH1HjJWPwiF74y+m0hremvUUeTL-qMtbjtvTtLZg@mail.gmail.com>",
         "received_at": "2026-08-10T10:10:12+00:00",
         "recorded_at": "2026-08-10T17:19:12.442526+00:00",
         "kind": "auto",
         "note": "Owner confirmed 2026-08-11: bot/away auto-reply (out of office), NOT a real reply"},
        {"lead_id": "AP-7d1096", "company": "Example Agency", "kind": "reply",
         "outcome": "rejected",
         "reason": "Not looking to bring in an external solution for this workflow at the moment — "
                   "pass for now",
         "note": "Owner-forwarded real reply 2026-08-11 (separate from earlier bot/away auto event). "
                 "Company type owner-confirmed: software agency. Rejection class R1: external-solution "
                 "readiness / in-house capability.",
         "subject": "Re: Example Agency client-delivery flow",
         "received_at": "2026-08-11T00:00:00"},
        {"received_id": "gmail-<CWXP265MB3191F6660D3E788F0E4C330BF5DD2@CWXP265MB3191.GBRP265.PROD.OUTLOOK.COM>",
         "lead_id": "EN-1157", "email": "riley@example-staffing.test",
         "company": "Example Staffing", "variant": "researched-personal",
         "subject": "Staffing loop at Example Staffing",
         "message_id": "<CWXP265MB3191F6660D3E788F0E4C330BF5DD2@CWXP265MB3191.GBRP265.PROD.OUTLOOK.COM>",
         "received_at": "2026-08-11T00:33:25+00:00",
         "recorded_at": "2026-08-11T00:35:58.225223+00:00",
         "kind": "reply", "note": ""},
    ]

    def _fixture_metrics(self):
        return {"emails": {}, "replies": [dict(r) for r in self.LIVE_REPLIES]}

    def test_classify_reply_kind_reliable_signals(self):
        from company.departments.outbound.workflows.email import analytics
        # OOO prefix (Outlook convention) is a strong auto signal
        self.assertEqual(analytics.classify_reply_kind(
            "Automatic reply: Recruiting ops at Example Recruiting Co"), "auto")
        # Auto-Submitted header (RFC 3834) beats an ordinary Re: subject
        self.assertEqual(analytics.classify_reply_kind(
            "Re: Staffing loop", auto_submitted="auto-replied"), "auto")
        # X-Autoreply header is a strong auto signal
        self.assertEqual(analytics.classify_reply_kind(
            "Re: Staffing loop", x_autoreply="yes"), "auto")
        # Configured keyword list still works
        self.assertEqual(analytics.classify_reply_kind(
            "Out of office: away until Friday"), "auto")
        # Ordinary Re: defaults to reply unless a strong signal says auto
        self.assertEqual(analytics.classify_reply_kind("Re: Delivery loop cost"), "reply")
        self.assertEqual(analytics.classify_reply_kind(
            "Re: Staffing loop", auto_submitted="no"), "reply")

    def test_gmail_record_extracts_autoreply_headers(self):
        import email as email_mod
        from company.departments.outbound.workflows.email import providers
        msg = email_mod.message.EmailMessage()
        msg["From"] = "Alex Lee <alex.lee@example-recruiting.test>"
        msg["To"] = "replies@spielos.xyz"
        msg["Subject"] = "Re: Recruiting ops"
        msg["Message-ID"] = "<m1@outlook.com>"
        msg["Date"] = "Mon, 10 Aug 2026 09:00:00 +0000"
        msg["Auto-Submitted"] = "auto-replied"
        msg["X-Autoreply"] = "yes"
        msg.set_content("I am away until Friday.")
        rec = providers._gmail_message_record(msg, b"1")
        self.assertEqual(rec["auto_submitted"], "auto-replied")
        self.assertEqual(rec["x_autoreply"], "yes")
        self.assertTrue(rec["id"].startswith("gmail-"))

    def test_sync_replies_stores_inputs_and_classifies_by_headers(self):
        import json as _json
        from company.departments.outbound.workflows.email import analytics, providers
        tmp = Path(tempfile.mkdtemp())
        config.METRICS_PATH = tmp / "metrics.json"
        with open(config.METRICS_PATH, "w") as f:
            _json.dump({"emails": {}, "replies": []}, f)
        sent = {"sent": [{"lead_id": "EN-1200", "email": "jay@acme.co.uk",
                          "company": "Acme", "subject": "Recruiting ops",
                          "variant": "offer-1"}]}
        listing = {"data": [
            {"id": "gmail-<h1@acme.co.uk>", "from": "jay@acme.co.uk",
             "subject": "Re: Recruiting ops", "message_id": "<h1@acme.co.uk>",
             "created_at": "2026-08-10T09:00:00+00:00",
             "auto_submitted": "auto-replied", "x_autoreply": ""},
            {"id": "gmail-<h2@acme.co.uk>", "from": "jay@acme.co.uk",
             "subject": "Re: Recruiting ops", "message_id": "<h2@acme.co.uk>",
             "created_at": "2026-08-10T09:05:00+00:00",
             "auto_submitted": "", "x_autoreply": ""},
        ]}
        with unittest.mock.patch.object(providers, "cap_received", return_value=True), \
             unittest.mock.patch.object(providers, "list_received_emails", return_value=listing):
            metrics = {"emails": {}, "replies": []}
            analytics.sync_replies(sent, metrics)
        by_id = {r["received_id"]: r for r in metrics["replies"]}
        self.assertEqual(by_id["gmail-<h1@acme.co.uk>"]["kind"], "auto")
        self.assertEqual(by_id["gmail-<h1@acme.co.uk>"]["auto_submitted"], "auto-replied")
        self.assertEqual(by_id["gmail-<h2@acme.co.uk>"]["kind"], "reply")
        self.assertEqual(by_id["gmail-<h2@acme.co.uk>"]["from"], "jay@acme.co.uk")

    def test_recheck_live_fixture(self):
        from company.departments.outbound.workflows.email import analytics
        metrics = self._fixture_metrics()
        report = analytics.recheck_replies(metrics, dry_run=True)
        # Dry-run must not mutate the ledger
        self.assertEqual(len(metrics["replies"]), 9)
        self.assertEqual(report["records_before"], 9)
        self.assertEqual(report["records_after"], 5)
        # AP-7d1096 "Re: Delivery loop cost" reclassifies auto -> reply
        self.assertTrue(any(
            item["lead_id"] == "AP-7d1096"
            and item["subject"] == "Re: Delivery loop cost"
            and item["old"] == "auto" and item["new"] == "reply"
            for item in report["reclassified"]), report["reclassified"])
        # EN-1157's two capture records collapse to one reply
        en1157 = [item for item in report["collapsed"] if item["lead_id"] == "EN-1157"]
        self.assertEqual(len(en1157), 1)
        self.assertEqual(en1157[0]["kept"]["kind"], "reply")
        self.assertEqual(len(en1157[0]["removed"]), 1)

        # Apply for real and verify the reconciled ledger
        report = analytics.recheck_replies(metrics, dry_run=False)
        by_lead = {}
        for r in metrics["replies"]:
            by_lead.setdefault(r["lead_id"], []).append(r)
        self.assertEqual(report["records_after"], 5)
        self.assertEqual(len(metrics["replies"]), 5)
        # EN-1152 / EN-1153 stay auto
        self.assertEqual([r["kind"] for r in by_lead["EN-1152"]], ["auto"])
        self.assertEqual([r["kind"] for r in by_lead["EN-1153"]], ["auto"])
        # EN-1157 collapses to exactly one reply
        self.assertEqual(len(by_lead["EN-1157"]), 1)
        self.assertEqual(by_lead["EN-1157"][0]["kind"], "reply")
        # AP-7d1096 keeps one reply record (newest kept, metadata merged)
        self.assertEqual(len(by_lead["AP-7d1096"]), 1)
        self.assertEqual(by_lead["AP-7d1096"][0]["kind"], "reply")
        self.assertEqual(len(by_lead["TEST-loop-001"]), 1)

        # Idempotent: a second pass reports no changes
        again = analytics.recheck_replies(metrics, dry_run=False)
        self.assertEqual(again["records_after"], 5)
        self.assertEqual(again["reclassified"], [])
        self.assertEqual(again["collapsed"], [])

        # Aggregate: replied=2 (windowed sends — goal metric unchanged), auto=2
        log = {"sent": [
            {"lead_id": "EN-1157", "email": "riley@example-staffing.test"},
            {"lead_id": "AP-7d1096", "email": "casey@example-agency.test"},
        ]}
        agg = analytics.aggregate(log, metrics)
        self.assertEqual(agg["replied"], 2)
        self.assertEqual(agg["auto"], 2)
        # Inbox truth: replies received in the 48h window regardless of send
        agg = analytics.aggregate(
            log, metrics, now=datetime(2026, 8, 11, 12, 0, tzinfo=timezone.utc))
        self.assertEqual(agg["replies_received"], 2)

    def test_replies_received_inbox_truth_independent_of_send(self):
        """A reply received inside the window counts even when its send is
        older than the window (inbox truth vs window attribution)."""
        from company.departments.outbound.workflows.email import analytics
        metrics = {"emails": {}, "replies": [
            {"lead_id": "EN-2000", "email": "old@acme.co.uk", "variant": "offer-1",
             "subject": "Re: Old send", "received_at": "2026-08-10T08:00:00+00:00",
             "kind": "reply", "recorded_at": "2026-08-10T08:00:00+00:00"},
            {"lead_id": "EN-2001", "email": "auto@acme.co.uk", "variant": "offer-1",
             "subject": "Automatic reply: Ops", "received_at": "2026-08-10T08:05:00+00:00",
             "kind": "auto", "recorded_at": "2026-08-10T08:05:00+00:00"},
            {"lead_id": "EN-2002", "email": "oldtest@acme.co.uk", "variant": "TEST-a",
             "subject": "Re: Loop", "received_at": "2026-08-10T08:10:00+00:00",
             "kind": "reply", "recorded_at": "2026-08-10T08:10:00+00:00"},
        ]}
        # send log has NO windowed sends for these leads
        log = {"sent": [
            {"lead_id": "EN-3000", "email": "unrelated@acme.co.uk",
             "timestamp": "2026-08-11T10:00:00"},
        ]}
        agg = analytics.aggregate(
            log, metrics, now=datetime(2026, 8, 11, 12, 0, tzinfo=timezone.utc))
        self.assertEqual(agg["replied"], 0)              # window attribution unchanged
        self.assertEqual(agg["replies_received"], 1)     # inbox truth: 1 human reply
        self.assertEqual(agg["auto"], 1)                 # auto not counted as reply
        self.assertIn("replies_received", agg)


class ReplyTombstoneTests(unittest.TestCase):
    """Bounded repair 2026-08-11 (change-b28800611b, goal-recheck-tombstones-20260811):
    the recheck persists every received_id it collapses
    (metrics.collapsed_received_ids) and the live sweep path skips tombstoned
    ids BEFORE recording. Tombstones survive repeated sweeps and repeated
    rechecks (idempotent, no unbounded growth); genuinely new messages with
    fresh ids are still recorded. Classification, window semantics, and the
    3.3.0/3.3.1 display tolerance are unchanged. Hermetic — no network."""

    # The three received_ids the live recheck collapsed at ~13:28Z on
    # 2026-08-11 and that the 13:33:36Z sweep re-added (growing the ledger
    # 5 -> 8). These are the ids the tombstone list must hold.
    COLLAPSED_IDS = [
        "gmail-<CA+Y0w+cMpwH53Lar+dNUhSe-Yo832N=JAY8bfTX3ZYv6sWi=fA@mail.gmail.com>",
        "gmail-<msmuuj62.b570adbe-95d2-46d2-9330-4c2d63d1e7bc@we.are.superhuman.com>",
        "gmail-<CABmWERz6j4fH1HjJWPwiF74y+m0hremvUUeTL-qMtbjtvTtLZg@mail.gmail.com>",
    ]

    @staticmethod
    def _listing(*ids):
        return {"data": [
            {"id": eid, "from": "owner@acme-uk.com", "subject": "Re: Agentic ops at Acme UK",
             "message_id": eid[len("gmail-"):] if eid.startswith("gmail-") else eid,
             "created_at": "2026-08-11T13:33:36+00:00"}
            for eid in ids
        ]}

    @staticmethod
    def _sent():
        return {"sent": [{"lead_id": "EN-2000", "email": "owner@acme-uk.com",
                          "company": "Acme UK", "subject": "Agentic ops at Acme UK",
                          "variant": "offer-1"}]}

    def test_sync_skips_collapsed_id_reappearing_in_sweep_listing(self):
        """(a) A fixture where a collapsed received_id reappears in a sweep
        listing is skipped — the ledger stays collapsed and the tombstone list
        is untouched (the live path never writes tombstones)."""
        import json as _json
        from company.departments.outbound.workflows.email import analytics, providers
        tmp = Path(tempfile.mkdtemp())
        config.METRICS_PATH = tmp / "metrics.json"
        kept = {"received_id": "gmail-<fresh@mail.gmail.com>", "lead_id": "EN-2000",
                "email": "owner@acme-uk.com", "company": "Acme UK", "variant": "offer-1",
                "subject": "Re: Agentic ops at Acme UK",
                "message_id": "<fresh@mail.gmail.com>",
                "received_at": "2026-08-11T10:00:00+00:00",
                "recorded_at": "2026-08-11T10:05:00+00:00", "kind": "reply", "note": ""}
        with open(config.METRICS_PATH, "w") as f:
            _json.dump({"emails": {}, "replies": [kept],
                        "collapsed_received_ids": list(self.COLLAPSED_IDS)}, f)
        # The 13:33:36Z-style sweep listing re-presents ALL three collapsed ids
        listing = self._listing(*self.COLLAPSED_IDS)
        with unittest.mock.patch.object(providers, "cap_received", return_value=True), \
             unittest.mock.patch.object(providers, "list_received_emails", return_value=listing):
            metrics = analytics.load_metrics()
            added = analytics.sync_replies(self._sent(), metrics)
        self.assertEqual(added, 0)
        self.assertEqual(len(metrics["replies"]), 1)
        self.assertEqual(metrics["replies"][0]["received_id"], "gmail-<fresh@mail.gmail.com>")
        # Tombstones untouched on the live path: same ids, same order, no growth
        self.assertEqual(metrics["collapsed_received_ids"], list(self.COLLAPSED_IDS))

    def test_recheck_twice_identical_ledger_and_tombstones(self):
        """(b) Running the recheck twice on the live 9-record fixture produces
        an identical ledger AND an identical tombstone list; the second pass
        adds no tombstones (no unbounded growth)."""
        import json as _json
        from company.departments.outbound.workflows.email import analytics
        metrics = {"emails": {}, "replies": [dict(r) for r in ReplyTruthReconcileTests.LIVE_REPLIES]}
        first = analytics.recheck_replies(metrics, dry_run=False)
        ledger_after_first = _json.dumps(metrics["replies"], sort_keys=True)
        tombstones_after_first = list(metrics.get("collapsed_received_ids") or [])
        self.assertEqual(first["records_after"], 5)
        # Exactly the three collapsed ids — the ones the sweep re-added live
        self.assertEqual(sorted(tombstones_after_first), sorted(self.COLLAPSED_IDS))

        second = analytics.recheck_replies(metrics, dry_run=False)
        self.assertEqual(_json.dumps(metrics["replies"], sort_keys=True), ledger_after_first)
        self.assertEqual(list(metrics.get("collapsed_received_ids") or []), tombstones_after_first)
        self.assertEqual(second["tombstones_added"], [])
        self.assertEqual(second["collapsed"], [])
        self.assertEqual(second["tombstones_before"], 3)
        self.assertEqual(second["tombstones_total"], 3)

    def test_new_message_with_fresh_id_still_recorded(self):
        """(c) A genuinely new message with a fresh received_id is still
        recorded even when the same sweep listing also carries tombstoned
        ids — tombstones suppress only the collapsed messages."""
        import json as _json
        from company.departments.outbound.workflows.email import analytics, providers
        tmp = Path(tempfile.mkdtemp())
        config.METRICS_PATH = tmp / "metrics.json"
        with open(config.METRICS_PATH, "w") as f:
            _json.dump({"emails": {}, "replies": [],
                        "collapsed_received_ids": list(self.COLLAPSED_IDS)}, f)
        fresh = "gmail-<brand-new@mail.gmail.com>"
        listing = self._listing(*self.COLLAPSED_IDS, fresh)
        with unittest.mock.patch.object(providers, "cap_received", return_value=True), \
             unittest.mock.patch.object(providers, "list_received_emails", return_value=listing):
            metrics = analytics.load_metrics()
            added = analytics.sync_replies(self._sent(), metrics)
        self.assertEqual(added, 1)
        self.assertEqual([r["received_id"] for r in metrics["replies"]], [fresh])
        self.assertEqual(metrics["collapsed_received_ids"], list(self.COLLAPSED_IDS))


class ReplyDisplayToleranceTests(unittest.TestCase):
    """Bounded repair 2026-08-11 (change-d1459e3624, goal-replies-display-20260811):
    the `replies` listing must render ANY stored record shape (merged records
    may lack recorded_at/email) and the recheck merge must preserve identity
    fields (email, contact_name, company) across collapsed records. Display/
    merge robustness only — classification and window semantics unchanged."""

    def test_replies_renders_merged_record_missing_recorded_at_and_email(self):
        """A merged record with recorded_at=null and email=null (the live
        AP-7d1096 shape) renders without crashing and prints the fallbacks:
        received_at for the timestamp, sent-log lead email for the address."""
        import contextlib
        import io
        from company.departments.outbound.workflows.email import analytics, cli, outbound
        tmp = Path(tempfile.mkdtemp())
        config.METRICS_PATH = tmp / "metrics.json"
        config.SENT_LOG_PATH = tmp / "sent.json"
        merged = {"received_id": None, "lead_id": "AP-7d1096", "email": None,
                  "company": "Example Agency", "variant": "researched-personal",
                  "subject": "Re: Example Agency client-delivery flow",
                  "received_at": "2026-08-11T00:00:00+00:00", "recorded_at": None,
                  "kind": "reply", "note": ""}
        with open(config.METRICS_PATH, "w") as f:
            json.dump({"emails": {}, "replies": [merged]}, f)
        outbound.save_sent_log({"sent": [
            {"lead_id": "AP-7d1096", "email": "casey@example-agency.test",
             "contact_name": "Casey Example", "company": "Example Agency"},
        ]})
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            cli.replies()  # must not raise KeyError
        out = buf.getvalue()
        self.assertIn("REPLIES (1)", out)
        # recorded_at missing -> received_at fallback rendered
        self.assertIn("2026-08-11T00:00", out)
        # email missing -> lead email from the sent log rendered
        self.assertIn("casey@example-agency.test", out)

    def test_replies_renders_record_with_only_lead_id_no_timestamps(self):
        """Even a record with no timestamps and no sent-log match renders
        (lead_id and '?' fallbacks) instead of crashing."""
        import contextlib
        import io
        from company.departments.outbound.workflows.email import analytics, cli, outbound
        tmp = Path(tempfile.mkdtemp())
        config.METRICS_PATH = tmp / "metrics.json"
        config.SENT_LOG_PATH = tmp / "sent.json"
        bare = {"lead_id": "AP-0000", "kind": "reply"}
        with open(config.METRICS_PATH, "w") as f:
            json.dump({"emails": {}, "replies": [bare]}, f)
        outbound.save_sent_log({"sent": []})
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            cli.replies()
        out = buf.getvalue()
        self.assertIn("AP-0000", out)
        self.assertIn("?", out)

    def test_recheck_merge_backfills_identity_from_oldest_in_group(self):
        """Collapsing a per-lead group keeps the newest record and backfills
        identity fields (email, contact_name) it lacks from the other record;
        fields the newest DOES carry win (newest-wins rule)."""
        from company.departments.outbound.workflows.email import analytics
        oldest = {"received_id": "gmail-<o1@example.com>", "lead_id": "AP-9x",
                  "email": "old@example.com", "contact_name": "Old Name",
                  "company": "OldCo", "variant": "researched-personal",
                  "subject": "Re: Old capture", "message_id": "<o1@example.com>",
                  "received_at": "2026-08-10T00:00:00+00:00",
                  "recorded_at": "2026-08-10T01:00:00+00:00", "kind": "reply",
                  "note": ""}
        newest = {"received_id": "gmail-<n1@example.com>", "lead_id": "AP-9x",
                  "email": None, "company": "NewCo", "variant": "researched-personal",
                  "subject": "Re: Example Agency client-delivery flow",
                  "message_id": "<n1@example.com>",
                  "received_at": "2026-08-11T00:00:00+00:00", "recorded_at": None,
                  "kind": "reply", "note": ""}
        metrics = {"emails": {}, "replies": [dict(oldest), dict(newest)]}
        report = analytics.recheck_replies(metrics, dry_run=False)
        self.assertEqual(report["records_after"], 1)
        self.assertEqual(len(metrics["replies"]), 1)
        kept = metrics["replies"][0]
        # Newest record is kept (received_at 2026-08-11 beats 2026-08-10)
        self.assertEqual(kept["subject"], "Re: Example Agency client-delivery flow")
        self.assertEqual(kept["received_id"], "gmail-<n1@example.com>")
        # Identity the newest lacks is backfilled from the group (oldest)
        self.assertEqual(kept["email"], "old@example.com")
        self.assertEqual(kept["contact_name"], "Old Name")
        # Identity the newest carries wins (newest-wins rule)
        self.assertEqual(kept["company"], "NewCo")


class BatchFillLimitTests(unittest.TestCase):
    """Bounded repair 2026-08-11 (goal-email-batch-fill-20260811, outbound
    3.3.2 -> 3.3.3): build_batch_emails(limit=N) walks the WHOLE queue and
    stops once N emails are composed, so unprepared leads and same-domain
    duplicates inside the first block no longer shrink the batch below the
    50-lead floor (live: 35/50 on goal-email-send-20260811-b1). Strict
    compose rules and the domain dedupe policy are unchanged — skipped leads
    still carry their real reasons; when the queue cannot fill the limit the
    available remainder is returned with queue_exhausted=true. Hermetic —
    synthetic leads only, no network, no master.

    Fixture arithmetic note: the recorded spec pairs "60 leads" with "exactly
    50 emails and 15 skipped", which cannot both hold (60 - 15 = 45). The
    fixture uses 65 leads (first 50 contain the 15 skips; 15 sendable leads
    follow) so the recorded assertion holds exactly and the deep-pull is
    exercised."""

    @staticmethod
    def _lead(seq, prepared=True, domain=None):
        c = dict(RESEARCHED, lead_id=f"EN-{3000 + seq}",
                 email=f"owner{seq}@{domain or f'acme{seq}-uk.com'}",
                 company=f"Acme {seq}")
        if not prepared:
            c["pain_hypothesis"] = "The company likely has a staffing workflow"
        return c

    @staticmethod
    def _first_50_with_15_skips_and_15_after():
        """65 leads: first 50 = 35 sendable + 9 unprepared + 6 same-domain
        duplicates (15 skips inside the first block); 15 sendable leads
        follow. Without the fix a queue[:50] slice yields only 35 emails."""
        leads = [BatchFillLimitTests._lead(s) for s in range(35)]
        leads += [BatchFillLimitTests._lead(s, prepared=False)
                  for s in range(35, 44)]
        leads += [BatchFillLimitTests._lead(s, domain=f"acme{s - 44}-uk.com")
                  for s in range(44, 50)]
        leads += [BatchFillLimitTests._lead(s) for s in range(50, 65)]
        return leads

    def test_BatchFillLimit_fills_50_despite_15_skips_in_first_50(self):
        """(a) limit=50 with skips inside the first 50 pulls deeper into the
        queue and returns exactly 50 emails and 15 skipped — the strict skip
        reasons are preserved, nothing is fabricated."""
        leads = self._first_50_with_15_skips_and_15_after()
        self.assertEqual(len(leads), 65)
        built = compose.build_batch_emails("B1", leads, "h", limit=50)
        self.assertEqual(len(built["emails"]), 50)
        self.assertEqual(len(built["skipped"]), 15)
        reasons = [s["reason"] for s in built["skipped"]]
        self.assertEqual(sum("unprepared" in r for r in reasons), 9)
        self.assertEqual(sum("already in this batch" in r for r in reasons), 6)
        self.assertFalse(built["queue_exhausted"])
        # The fill pulled past the first 50: the deepest sendable lead (the
        # 65th queue entry) is composed; no lead is composed twice.
        self.assertEqual(built["emails"][-1]["lead_id"], "EN-3064")
        ids = [e["lead_id"] for e in built["emails"]]
        self.assertEqual(len(ids), len(set(ids)))

    def test_BatchFillLimit_queue_exhausted_returns_available(self):
        """(b) 40 sendable leads with limit=50 returns the 40 available
        emails plus queue_exhausted=true — never fabricated content."""
        leads = [self._lead(s) for s in range(40)]
        built = compose.build_batch_emails("B1", leads, "h", limit=50)
        self.assertEqual(len(built["emails"]), 40)
        self.assertEqual(built["skipped"], [])
        self.assertTrue(built["queue_exhausted"])

    def test_BatchFillLimit_no_limit_backward_compatible(self):
        """(c) Without a limit the behavior and result shape are unchanged:
        every sendable lead is composed, skips carry real reasons, and no
        queue_exhausted key is added."""
        leads = ([self._lead(s) for s in range(3)]
                 + [self._lead(3, prepared=False)]
                 + [self._lead(4, domain="acme0-uk.com")])
        built = compose.build_batch_emails("B1", leads, "h")
        self.assertEqual(len(built["emails"]), 3)
        self.assertEqual(len(built["skipped"]), 2)
        self.assertEqual(set(built.keys()), {"emails", "skipped"})

    def test_BatchFillLimit_prepare_passes_full_queue_with_limit(self):
        """actor.prepare hands the WHOLE queue to compose with limit=slice_size
        (min(block_size, daily cap remaining)) and reports emails count,
        skipped, queue size, limit, and queue_exhausted in the result. The
        daily cap is still honored: slice_size stays 50 with cap 200 / 0
        used, and the fill never exceeds it."""
        from company.departments.outbound.workflows.email import actor
        leads = self._first_50_with_15_skips_and_15_after()
        knobs = {"block_size": 50, "daily_cap": 200, "cohort_filters": {}}
        control = type("C", (), {"knobs": lambda self: knobs})()
        ctx = type("Ctx", (), {"control": control})()
        with unittest.mock.patch.object(compose, "pick_queue", return_value=leads), \
                unittest.mock.patch.object(outbound, "daily_cap",
                                           return_value=(200, "steady")), \
                unittest.mock.patch.object(outbound, "sent_today",
                                           return_value=0), \
                unittest.mock.patch.object(outbound, "load_sent_log",
                                           return_value={"sent": []}):
            result = actor.prepare(ctx, {"batch_id": "B1", "prediction": "p"})
        self.assertEqual(result["emails_count"], 50)
        self.assertEqual(len(result["emails"]), 50)
        self.assertEqual(len(result["skipped"]), 15)
        self.assertEqual(result["queue_size"], 65)
        self.assertEqual(result["limit"], 50)
        self.assertFalse(result["queue_exhausted"])
        self.assertEqual(result["cap"]["cap"], 200)
        self.assertEqual(result["emails"][-1]["lead_id"], "EN-3064")
