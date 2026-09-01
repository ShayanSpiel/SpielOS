"""Send-path idempotency acceptance tests.

Goal goal-email-send-idempotency-20260815 (change-fb825a5769, 6.9.0 ->
6.10.0): unique persisted batch allocation per prepare (never the shared
"unset" fallback), disjoint concurrent prepares (leads claimed by a
prepared-not-executed batch are excluded), and a durable per-lead submission
registry (in_flight written BEFORE the first provider attempt; resolved to
accepted / failed / submitted_unknown; 12h cooldown blocks re-submission by
any worker, generation, or goal) — without weakening the daily cap,
throttle, quota switching, transient retry policy, or the existing sent-log
dedupe contract.

Hermetic: every provider/network call is mocked (no real providers, no DNS);
the store is a temp SQLite file; .spielos live state is never touched.
"""

import json
import sys
import tempfile
import time
import types
import unittest
import unittest.mock
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from company.departments.outbound.control import Control  # noqa: E402
from company.departments.outbound.data import OutboundStore  # noqa: E402
from company.departments.outbound.workflows.email import (  # noqa: E402
    actor, compose, config, outbound,
)

HUNG_CAP_MESSAGE = "send exceeded 180s cap (hung transport); not sent"


def _lead(n: int, domain: str, company: str) -> dict:
    name = f"person{n}"
    return {
        "lead_id": f"EN-T{n}",
        "email": f"{name}@{domain}",
        "company": company,
        "contact_name": name,
        "title": "Head of Recruitment",
        "segment": "recruitment agency",
        "country": "United Kingdom",
        "language": "English",
        "send_recommendation": "Ready to personalized",
        "outreach_tier": "A",
        "email_status": "Verified",
        "personalization_hook": (
            f"Reference {name}'s role as Head of Recruitment by name and one "
            "observable fact about the company's staffing work"),
        "pain_hypothesis": (
            f"{company} staffs 40 agency clients across the UK, and the "
            "shortlist coordination is likely still handled by hand"),
        "suggested_cta": "map the shortlist stage with you",
    }


LEADS = [_lead(n, f"dom{n}.test", f"Company {n}") for n in range(1, 9)]
LEAD_BY_ID = {c["lead_id"]: c for c in LEADS}
EMAIL_TO_LEAD = {c["email"]: c["lead_id"] for c in LEADS}


_CONFIG_ATTRS = ("SENT_LOG_PATH", "METRICS_PATH", "CONTENT_PATH", "DATABASE_PATH")
_CONFIG_SNAPSHOT = {}


def setUpModule():
    """Hermetic guard for the process-global `config` path attributes."""
    for attr in _CONFIG_ATTRS:
        if hasattr(config, attr):
            _CONFIG_SNAPSHOT[attr] = getattr(config, attr)


def tearDownModule():
    for attr, value in _CONFIG_SNAPSHOT.items():
        setattr(config, attr, value)


def make_env(block_size: int = 50):
    """Hermetic environment: temp paths, fresh store, control with knobs."""
    tmp = Path(tempfile.mkdtemp())
    config.SENT_LOG_PATH = tmp / "sent.json"
    config.METRICS_PATH = tmp / "metrics.json"
    config.CONTENT_PATH = tmp / "content.json"
    config.DATABASE_PATH = tmp / "master.xlsx"
    control_path = tmp / "control.json"
    control_path.write_text(json.dumps({
        "workflow": "email",
        "knobs": {"block_size": block_size, "daily_cap": 200,
                  "cohort_filters": {}},
    }))
    store = OutboundStore(tmp / "outbound.sqlite")
    return store, Control(control_path), tmp


def prepare_ctx(store, control):
    return types.SimpleNamespace(store=store, control=control, goal_id=None)


def execute_ctx(store):
    return types.SimpleNamespace(store=store)


def email_for(lead: dict) -> dict:
    return {"lead_id": lead["lead_id"], "subject": f"S {lead['lead_id']}",
            "body_html": "<p>hi</p>", "body_text": "hi",
            "features": {"variant": "offer-1"}}


def patches(**overrides):
    """Default hermetic patch set; override with per-test callables."""
    return {
        "read_contacts": overrides.get("read_contacts", lambda *a, **k: LEADS),
        "load_sent_log": overrides.get(
            "load_sent_log", lambda: {"sent": [], "failed": []}),
        "save_sent_log": overrides.get("save_sent_log", lambda log: None),
        "daily_cap": overrides.get("daily_cap", lambda: (200, "steady")),
        "sent_today": overrides.get("sent_today", lambda log: 0),
        "provider_sent_id": overrides.get("provider_sent_id", lambda email: None),
        "pick_provider": overrides.get("pick_provider", lambda log, exclude=(): "resend"),
        "sleep": overrides.get("sleep", lambda s: None),
    }


class _PatchStack:
    """Apply the hermetic patch set for the duration of a test body."""

    def __init__(self, **kwargs):
        self.kwargs = kwargs

    def __enter__(self):
        p = patches(**self.kwargs)
        self._mocks = []
        self._mocks.append(unittest.mock.patch.object(outbound, "read_contacts", p["read_contacts"]))
        self._mocks.append(unittest.mock.patch.object(outbound, "load_sent_log", p["load_sent_log"]))
        self._mocks.append(unittest.mock.patch.object(outbound, "save_sent_log", p["save_sent_log"]))
        self._mocks.append(unittest.mock.patch.object(outbound, "daily_cap", p["daily_cap"]))
        self._mocks.append(unittest.mock.patch.object(outbound, "sent_today", p["sent_today"]))
        self._mocks.append(unittest.mock.patch.object(actor, "_provider_sent_id", p["provider_sent_id"]))
        self._mocks.append(unittest.mock.patch.object(actor.providers, "pick_provider", p["pick_provider"]))
        self._mocks.append(unittest.mock.patch.object(config, "THROTTLE_SECONDS", 0))
        self._mocks.append(unittest.mock.patch.object(time, "sleep", p["sleep"]))
        for m in self._mocks:
            m.start()
        return self

    def __exit__(self, *exc):
        for m in reversed(self._mocks):
            m.stop()
        return False


class BatchAllocationTests(unittest.TestCase):
    """T1 — unique persisted batch ids, disjoint concurrent prepares,
    foreign/executed id rejection, claim release on execution."""

    def test_two_no_batch_id_prepares_allocate_distinct_disjoint_batches(self):
        store, control, _tmp = make_env(block_size=4)
        with _PatchStack():
            r1 = actor.prepare(prepare_ctx(store, control), {"prediction": "p"})
            r2 = actor.prepare(prepare_ctx(store, control), {"prediction": "p"})
        self.assertNotEqual(r1["id"], "unset")
        self.assertNotEqual(r2["id"], "unset")
        self.assertNotEqual(r1["id"], r2["id"])
        self.assertTrue(store.batch_registered(r1["id"]))
        self.assertTrue(store.batch_registered(r2["id"]))
        b1 = store.get_batch(r1["id"])
        b2 = store.get_batch(r2["id"])
        self.assertEqual(len(b1["lead_ids"]), 4)
        self.assertEqual(len(b2["lead_ids"]), 4)
        self.assertEqual(set(b1["lead_ids"]) & set(b2["lead_ids"]), set())
        self.assertEqual(set(b1["lead_ids"]) | set(b2["lead_ids"]),
                         {c["lead_id"] for c in LEADS})
        # both batches composed the full slice
        self.assertEqual(r1["emails_count"], 4)
        self.assertEqual(r2["emails_count"], 4)

    def test_registered_and_foreign_batch_ids_are_rejected(self):
        store, control, _tmp = make_env(block_size=4)
        with _PatchStack():
            r1 = actor.prepare(prepare_ctx(store, control), {"prediction": "p"})
            # same id re-prepared (registered, not yet executed)
            with self.assertRaisesRegex(ValueError, "already registered"):
                actor.prepare(prepare_ctx(store, control),
                              {"batch_id": r1["id"], "prediction": "p"})
            # executed id is still rejectable — ids never recycle
            store.mark_batch_executed(r1["id"])
            with self.assertRaisesRegex(ValueError, "already registered"):
                actor.prepare(prepare_ctx(store, control),
                              {"batch_id": r1["id"], "prediction": "p"})
            # a foreign goal's registered batch id
            store.register_batch("B-FOREIGN", owner="goal-other-goal",
                                 lead_ids=["EN-T9"])
            with self.assertRaisesRegex(ValueError, "already registered"):
                actor.prepare(prepare_ctx(store, control),
                              {"batch_id": "B-FOREIGN", "prediction": "p"})

    def test_cap_reached_still_allocates_a_unique_registered_id(self):
        store, control, _tmp = make_env(block_size=4)
        with _PatchStack(sent_today=lambda log: 200):
            r = actor.prepare(prepare_ctx(store, control), {"prediction": "p"})
        self.assertEqual(r["reason"], "daily cap reached")
        self.assertNotEqual(r["id"], "unset")
        self.assertTrue(store.batch_registered(r["id"]))
        self.assertEqual(store.get_batch(r["id"])["lead_ids"], [])

    def test_mark_executed_releases_claims_for_later_prepares(self):
        store, control, _tmp = make_env(block_size=4)
        with _PatchStack():
            r1 = actor.prepare(prepare_ctx(store, control), {"prediction": "p"})
            self.assertEqual(len(store.reserved_lead_ids()), 4)
            store.mark_batch_executed(r1["id"])
            self.assertEqual(store.reserved_lead_ids(), set())
            # after release, the same leads can be claimed again
            r2 = actor.prepare(prepare_ctx(store, control), {"prediction": "p"})
            self.assertEqual(len(store.get_batch(r2["id"])["lead_ids"]), 4)
        self.assertTrue(store.get_batch(r1["id"])["executed"])

    def test_pick_queue_excludes_reserved_leads(self):
        with _PatchStack():
            q_all = compose.pick_queue({})
            q_res = compose.pick_queue({}, reserved_lead_ids={"EN-T1", "EN-T2"})
        ids = [c["lead_id"] for c in q_res]
        self.assertEqual(len(ids), len(q_all) - 2)
        self.assertNotIn("EN-T1", ids)
        self.assertNotIn("EN-T2", ids)


class WorkerDeathRegistryTests(unittest.TestCase):
    """T2 — an in_flight marker written before the first provider attempt
    survives worker death; the next worker skips and the provider is called
    exactly once for the lead."""

    def test_in_flight_marker_blocks_second_worker_after_worker_death(self):
        store, _control, _tmp = make_env()
        ctx = execute_ctx(store)
        batch = {"id": "B-DEAD", "emails": [email_for(LEAD_BY_ID["EN-T1"])]}
        contacts = [LEAD_BY_ID["EN-T1"]]
        provider_calls = []

        def die(provider, to_email, subject, body_html, body_text, **kwargs):
            provider_calls.append(to_email)
            raise RuntimeError("worker killed mid-call (hung transport)")

        with _PatchStack(read_contacts=lambda *a, **k: contacts,
                         provider_sent_id=lambda email: None):
            with unittest.mock.patch.object(actor, "_send_with_cap", side_effect=die):
                with self.assertRaises(RuntimeError):
                    actor._execute_emails(ctx, batch)

        # the durable in_flight marker is the only trace of the dead worker
        sub = store.get_submission("EN-T1")
        self.assertIsNotNone(sub)
        self.assertEqual(sub["status"], "in_flight")
        self.assertEqual(provider_calls, ["person1@dom1.test"])

        second_calls = []

        def ok_send(provider, to_email, subject, body_html, body_text, **kwargs):
            second_calls.append(to_email)
            return {"id": "m1"}

        with _PatchStack(read_contacts=lambda *a, **k: contacts,
                         provider_sent_id=lambda email: None):
            with unittest.mock.patch.object(actor, "_send_with_cap", side_effect=ok_send):
                result = actor._execute_emails(ctx, batch)

        self.assertEqual(result["sent"], 0)
        self.assertEqual(result["failed"], 0)
        self.assertEqual(result["deduped"], 1)
        self.assertEqual(second_calls, [])
        # provider saw exactly one submission across both workers
        self.assertEqual(provider_calls + second_calls,
                         ["person1@dom1.test"])
        self.assertEqual(store.get_submission("EN-T1")["status"], "in_flight")


class CooldownTests(unittest.TestCase):
    """T3 — submitted_unknown (hung-cap outcome) blocks re-submission inside
    the 12h cooldown and is claimable again outside it; failed entries never
    block."""

    def test_submitted_unknown_blocks_then_resends_after_cooldown(self):
        store, _control, _tmp = make_env()
        ctx = execute_ctx(store)
        batch = {"id": "B-HUNG", "emails": [email_for(LEAD_BY_ID["EN-T1"])]}
        contacts = [LEAD_BY_ID["EN-T1"]]
        calls = []
        saved = {}

        hung = {"error": True, "status": 0, "message": HUNG_CAP_MESSAGE}

        def hang(provider, to_email, *a, **k):
            calls.append(to_email)
            return hung

        # worker A: hung transport three times -> submitted_unknown
        with _PatchStack(read_contacts=lambda *a, **k: contacts,
                         save_sent_log=lambda log: saved.update(log=log)):
            with unittest.mock.patch.object(actor, "_send_with_cap", side_effect=hang):
                result = actor._execute_emails(ctx, batch)
        self.assertEqual(result["sent"], 0)
        self.assertEqual(result["failed"], 1)  # failed log entry: existing contract
        sub = store.get_submission("EN-T1")
        self.assertEqual(sub["status"], "submitted_unknown")
        self.assertTrue(sub["message"].startswith("send exceeded"))
        self.assertTrue(any(f.get("lead_id") == "EN-T1"
                            for f in saved["log"].get("failed", [])))

        # worker B inside the cooldown: skipped, provider not called again
        second_calls = []
        with _PatchStack(read_contacts=lambda *a, **k: contacts):
            with unittest.mock.patch.object(
                    actor, "_send_with_cap",
                    side_effect=lambda provider, to, *a, **k:
                        second_calls.append(to) or {"id": "m-x"}):
                result2 = actor._execute_emails(ctx, batch)
        self.assertEqual(result2["sent"], 0)
        self.assertEqual(result2["deduped"], 1)
        self.assertEqual(second_calls, [])
        # worker A kept the existing transient policy (3 bounded attempts on
        # a status-0 hung response); worker B added zero submissions
        self.assertEqual(calls, ["person1@dom1.test"] * 3)

        # age the entry past the 12h cooldown, then worker C resends
        old = (datetime.now(timezone.utc) - timedelta(hours=13)).isoformat()
        store.record_submission("EN-T1", "person1@dom1.test", "resend",
                                attempted_at=old,
                                status="submitted_unknown",
                                message=HUNG_CAP_MESSAGE)
        third_calls = []
        with _PatchStack(read_contacts=lambda *a, **k: contacts):
            with unittest.mock.patch.object(
                    actor, "_send_with_cap",
                    side_effect=lambda provider, to, *a, **k:
                        third_calls.append(to) or {"id": "m2"}):
                result3 = actor._execute_emails(ctx, batch)
        self.assertEqual(result3["sent"], 1)
        self.assertEqual(result3["deduped"], 0)
        self.assertEqual(third_calls, ["person1@dom1.test"])
        final = store.get_submission("EN-T1")
        self.assertEqual(final["status"], "accepted")
        self.assertEqual(final["provider_id"], "m2")
        self.assertEqual(final["attempts"], 2)  # re-claim bumped the counter

    def test_failed_entry_never_blocks_reclaim(self):
        store, _control, _tmp = make_env()
        now = datetime.now(timezone.utc).isoformat()
        store.record_submission("EN-T1", "person1@dom1.test", "resend",
                                attempted_at=now, status="failed",
                                message="definite rejection")
        claim = store.claim_or_active("EN-T1", "person1@dom1.test", "resend")
        self.assertTrue(claim["claimed"])
        self.assertEqual(store.get_submission("EN-T1")["status"], "in_flight")
        self.assertEqual(store.get_submission("EN-T1")["attempts"], 2)


class NormalSendSemanticsTests(unittest.TestCase):
    """T4 — a normal first send keeps the existing contracts: sent-log entry
    with provider_id, failed-row resolution, action ledger, dedupe counts,
    daily-cap note — plus the new registry resolutions."""

    def test_first_send_semantics_unchanged(self):
        """Updated for resend_guard (goal-4357632a68, 2026-08-21): a batch
        containing an already-sent lead fails fast before any provider send,
        so this first-send scenario uses only unsent leads. Registry order,
        dedupe pre-check, and resolution semantics are unchanged."""
        store, _control, _tmp = make_env()
        ctx = execute_ctx(store)
        t1, t3 = LEAD_BY_ID["EN-T1"], LEAD_BY_ID["EN-T3"]
        log = {
            "sent": [{"lead_id": "EN-T2", "email": "person2@dom2.test",
                      "timestamp": "2026-08-14T10:00:00+00:00"}],
            "failed": [{"lead_id": "EN-T1", "email": "person1@dom1.test",
                        "company": "Company 1", "provider": "resend",
                        "error": "old transport failure",
                        "timestamp": "2026-08-14T10:00:00+00:00"}],
        }
        saved = {}
        batch = {"id": "B4", "emails": [email_for(t1), email_for(t3)]}
        contacts = [t1, t3]
        send_calls = []
        status_at_call = []

        def do_send(provider, to_email, *a, **k):
            send_calls.append(to_email)
            status_at_call.append(store.get_submission(
                EMAIL_TO_LEAD[to_email])["status"])
            return {"id": "m1"}

        def provider_sent_id(email):
            return "prov-9" if email == "person3@dom3.test" else None

        with _PatchStack(read_contacts=lambda *a, **k: contacts,
                         load_sent_log=lambda: log,
                         save_sent_log=lambda l: saved.update(log=l),
                         provider_sent_id=provider_sent_id):
            with unittest.mock.patch.object(actor, "_send_with_cap", side_effect=do_send):
                result = actor._execute_emails(ctx, batch)

        # counts: 1 sent, 0 failed, 1 deduped (provider pre-check)
        self.assertEqual(result["sent"], 1)
        self.assertEqual(result["failed"], 0)
        self.assertEqual(result["deduped"], 1)
        self.assertIn("cap", result["note"])
        # provider called once, and the registry was in_flight BEFORE the call
        self.assertEqual(send_calls, ["person1@dom1.test"])
        self.assertEqual(status_at_call, ["in_flight"])

        sent = saved["log"]["sent"]
        t1_entry = next(s for s in sent if s["lead_id"] == "EN-T1")
        self.assertEqual(t1_entry["provider_id"], "m1")
        self.assertEqual(t1_entry["batch"], "B4")
        t3_entry = next(s for s in sent if s["lead_id"] == "EN-T3")
        self.assertTrue(t3_entry["deduped"])
        self.assertEqual(t3_entry["provider_id"], "prov-9")
        # failed row for EN-T1 resolved
        f1 = next(f for f in saved["log"]["failed"] if f["lead_id"] == "EN-T1")
        self.assertTrue(f1.get("resolved_at"))

        # registry resolutions: accepted with provider ids; the already-sent
        # lead (EN-T2) is untouched by this batch entirely
        self.assertEqual(store.get_submission("EN-T1")["status"], "accepted")
        self.assertEqual(store.get_submission("EN-T1")["provider_id"], "m1")
        self.assertEqual(store.get_submission("EN-T3")["status"], "accepted")
        self.assertEqual(store.get_submission("EN-T3")["provider_id"], "prov-9")
        self.assertIsNone(store.get_submission("EN-T2"))

        # resend guard: a batch that includes the already-sent EN-T2 must
        # fail fast before any provider dispatch — no partial remainder.
        batch_with_sent = {"id": "B5",
                           "emails": [email_for(t1), email_for(LEAD_BY_ID["EN-T2"])]}
        send_calls.clear()
        with _PatchStack(read_contacts=lambda *a, **k: [t1, LEAD_BY_ID["EN-T2"]],
                         load_sent_log=lambda: saved["log"],
                         save_sent_log=lambda l: None,
                         provider_sent_id=lambda email: None):
            with unittest.mock.patch.object(actor, "_send_with_cap", side_effect=do_send):
                with self.assertRaises(RuntimeError) as guard:
                    actor._execute_emails(ctx, batch_with_sent)
        self.assertIn("resend_guard", str(guard.exception))
        self.assertIn("EN-T2", str(guard.exception))
        self.assertEqual(send_calls, [])

        # action ledger unchanged: exactly one recorded send
        self.assertEqual(store.action_count("email", "send_email", "sent"), 1)


if __name__ == "__main__":
    unittest.main()