"""Unit tests for the Cal.com -> Attio booked-call sync adapter.

Coverage: fetch (mocked HTTP, no live network), pagination, auth/version
headers, dedupe against last-sync state, booking -> booked_call evidence
mapping, event-slug scoping, dry-run/apply/commit-state/verify CLI behavior,
and the safe dotenv parser.
"""

from __future__ import annotations

import io
import json
import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from company.departments.outbound.calcom_sync import (
    API_URL,
    BOOKING_URL,
    CalComClient,
    CalComError,
    _env_values,
    collect,
    commit_state,
    evidence_command,
    evidence_payload,
    main,
    normalize_booking,
    verify_plan,
)


class _FakeResponse:
    """Fake urllib response for mocked HTTP: context manager, .read(), .headers."""
    def __init__(self, payload: dict, headers: dict | None = None):
        self.headers = {"x-ratelimit-remaining": "119", **(headers or {})}
        self._payload = payload

    def read(self) -> bytes:
        return json.dumps(self._payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _json_response(payload: dict, headers: dict | None = None) -> _FakeResponse:
    return _FakeResponse(payload, headers)


def _booking(uid: str, *, status: str = "accepted", slug: str = "15min",
             start: str = "2026-08-20T15:30:00Z", email: str = "John@Example.com",
             name: str = "John Doe") -> dict:
    return {
        "id": 1000 + abs(hash(uid)) % 1000,
        "uid": uid,
        "title": "Discovery Call",
        "status": status,
        "start": start,
        "end": "2026-08-20T15:45:00Z",
        "createdAt": "2026-08-19T09:00:00Z",
        "eventType": {"id": 15, "slug": slug},
        "location": "integrations:google-meet",
        "attendees": [{"name": name, "email": email, "displayEmail": email,
                       "timeZone": "America/New_York", "absent": False}],
    }


class CalComClientTests(unittest.TestCase):
    def test_dotenv_parser_never_executes_shell_syntax(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / ".env"
            path.write_text("CALCOM_API_KEY='cal_live_secret'\nPAYLOAD $(echo nope)\n")
            values = _env_values(path)
        self.assertEqual({"CALCOM_API_KEY": "cal_live_secret"}, values)

    @patch.dict(os.environ, {"CALCOM_API_KEY": "cal_live_test"}, clear=False)
    def test_client_requires_api_key(self):
        # The real key lives in .spielos/.env, so the dotenv fallback must be
        # stubbed too — tests never depend on the real (gitignored) env file.
        with patch.dict(os.environ, {}, clear=True), \
             patch("company.departments.outbound.calcom_sync._env_values", return_value={}):
            with self.assertRaisesRegex(CalComError, "CALCOM_API_KEY is not configured"):
                CalComClient()

    @patch.dict(os.environ, {"CALCOM_API_KEY": "cal_live_test"}, clear=False)
    def test_fetch_uses_bearer_auth_and_api_version_header(self):
        seen = {}

        def fake_open(request, timeout=None):
            # urllib capitalizes custom header keys; HTTP header names are
            # case-insensitive, so assert on the wire-level header items.
            headers = dict(request.header_items())
            seen["auth"] = headers.get("Authorization")
            seen["version"] = headers.get("Cal-api-version")
            seen["url"] = request.full_url
            return _json_response({"status": "success", "data": [],
                                   "pagination": {"nextCursor": None, "hasMore": False}})

        client = CalComClient()
        with patch("company.departments.outbound.calcom_sync.urlopen", side_effect=fake_open):
            client.fetch_bookings(statuses=("upcoming",))

        self.assertEqual("Bearer cal_live_test", seen["auth"])
        self.assertEqual("2026-05-01", seen["version"])
        self.assertIn("/v2/bookings", seen["url"])
        self.assertIn("status=upcoming", seen["url"])
        self.assertEqual("119", client.last_rate_limits["x-ratelimit-remaining"])

    @patch.dict(os.environ, {"CALCOM_API_KEY": "cal_live_test"}, clear=False)
    def test_fetch_walks_cursor_pages_and_merges(self):
        calls = []

        def fake_open(request, timeout=None):
            calls.append(request.full_url)
            if "cursor=next-1" in request.full_url:
                return _json_response({"status": "success",
                                       "data": [_booking("b-2", start="2026-08-21T10:00:00Z")],
                                       "pagination": {"nextCursor": None, "hasMore": False}})
            return _json_response({"status": "success",
                                   "data": [_booking("b-1"), _booking("b-2", start="2026-08-21T10:00:00Z")],
                                   "pagination": {"nextCursor": "next-1", "hasMore": True}})

        client = CalComClient()
        with patch("company.departments.outbound.calcom_sync.urlopen", side_effect=fake_open):
            bookings = client.fetch_bookings(statuses=("upcoming",))

        self.assertEqual(2, len(calls))  # page 1 + page 2 of the single status
        self.assertEqual({"b-1", "b-2"}, {item["uid"] for item in bookings})
        self.assertIn("limit=100", calls[0])

    @patch.dict(os.environ, {"CALCOM_API_KEY": "cal_live_test"}, clear=False)
    def test_fetch_walks_each_status_separately(self):
        calls = []

        def fake_open(request, timeout=None):
            calls.append(request.full_url)
            return _json_response({"status": "success", "data": [],
                                   "pagination": {"nextCursor": None, "hasMore": False}})

        client = CalComClient()
        with patch("company.departments.outbound.calcom_sync.urlopen", side_effect=fake_open):
            client.fetch_bookings(statuses=("upcoming", "past"))

        self.assertEqual(2, len(calls))
        self.assertTrue(any("status=upcoming" in url for url in calls))
        self.assertTrue(any("status=past" in url for url in calls))

    @patch.dict(os.environ, {"CALCOM_API_KEY": "cal_live_test"}, clear=False)
    def test_fetch_http_error_is_safe(self):
        from urllib.error import HTTPError

        def fake_open(request, timeout=None):
            raise HTTPError(API_URL, 401, "Unauthorized", {}, None)

        client = CalComClient()
        with patch("company.departments.outbound.calcom_sync.urlopen", side_effect=fake_open):
            with self.assertRaisesRegex(CalComError, "HTTP 401"):
                client.fetch_bookings()
        # The key never leaks into the error surface.
        self.assertNotIn("cal_live_test", str(client.last_rate_limits))

    @patch.dict(os.environ, {"CALCOM_API_KEY": "cal_live_test"}, clear=False)
    def test_fetch_network_error_is_safe(self):
        from urllib.error import URLError

        client = CalComClient()
        with patch("company.departments.outbound.calcom_sync.urlopen",
                   side_effect=URLError("boom")):
            with self.assertRaisesRegex(CalComError, "could not be reached"):
                client.fetch_bookings()

    @patch.dict(os.environ, {"CALCOM_API_KEY": "cal_live_test"}, clear=False)
    def test_fetch_api_error_status_raises(self):
        client = CalComClient()
        with patch("company.departments.outbound.calcom_sync.urlopen",
                   return_value=_json_response({"status": "error", "error": "nope"})):
            with self.assertRaisesRegex(CalComError, "API error: nope"):
                client.fetch_bookings()


class BookingMappingTests(unittest.TestCase):
    def test_normalize_accepts_only_confirmed_bookings(self):
        self.assertIsNotNone(normalize_booking(_booking("ok-1", status="accepted")))
        for status in ("pending", "cancelled", "rejected"):
            self.assertIsNone(normalize_booking(_booking(f"{status}-1", status=status)),
                              f"{status} must not be a booked call")

    def test_normalize_lowercases_attendee_email_and_carries_identity(self):
        record = normalize_booking(_booking("uid-1", email="John@Example.COM", name="John Doe"))
        self.assertEqual("john@example.com", record["attendee_email"])
        self.assertEqual("John Doe", record["attendee_name"])
        self.assertEqual("uid-1", record["uid"])
        self.assertEqual("15min", record["event_type_slug"])
        self.assertEqual("2026-08-20T15:30:00Z", record["start"])

    @patch.dict(os.environ, {"CALCOM_API_KEY": "cal_live_test"}, clear=False)
    def test_collect_dedupes_against_last_sync_state(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            state_path = root / "calcom_sync.json"
            state_path.write_text(json.dumps({"version": 1,
                                              "last_sync_at": "2026-08-19T00:00:00+00:00",
                                              "booked_uids": ["old-1"]}))
            client = CalComClient()
            with patch("company.departments.outbound.calcom_sync.urlopen",
                       return_value=_json_response({
                           "status": "success",
                           "data": [_booking("old-1", start="2026-08-18T10:00:00Z"),
                                    _booking("new-1", start="2026-08-20T15:30:00Z")],
                           "pagination": {"nextCursor": None, "hasMore": False}})):
                plan = collect(client, state_path=state_path)

        self.assertEqual(["new-1"], [item["record"]["uid"] for item in plan["booked_calls"]])
        self.assertEqual(1, plan["counts"]["new_booked_calls"])
        self.assertEqual(1, plan["counts"]["already_synced"])
        self.assertEqual(["new-1"], plan["commit_state"]["booked_uids"])

    @patch.dict(os.environ, {"CALCOM_API_KEY": "cal_live_test"}, clear=False)
    def test_collect_scopes_to_discovery_call_event_slug(self):
        client = CalComClient()
        with patch("company.departments.outbound.calcom_sync.urlopen",
                   return_value=_json_response({
                       "status": "success",
                       "data": [_booking("dc-1", slug="15min"),
                                _booking("other-1", slug="30min")],
                       "pagination": {"nextCursor": None, "hasMore": False}})):
            plan = collect(client, state_path=Path("/nonexistent/state.json"),
                           slugs=("15min",))

        self.assertEqual(["dc-1"], [item["record"]["uid"] for item in plan["booked_calls"]])
        self.assertEqual(1, plan["counts"]["accepted_in_scope"])

    @patch.dict(os.environ, {"CALCOM_API_KEY": "cal_live_test"}, clear=False)
    def test_slugs_unset_includes_every_accepted_booking(self):
        client = CalComClient()
        with patch("company.departments.outbound.calcom_sync.urlopen",
                   return_value=_json_response({
                       "status": "success",
                       "data": [_booking("dc-1", slug="15min"),
                                _booking("other-1", slug="30min")],
                       "pagination": {"nextCursor": None, "hasMore": False}})):
            plan = collect(client, state_path=Path("/nonexistent/state.json"), slugs=())

        self.assertEqual({"dc-1", "other-1"},
                         {item["record"]["uid"] for item in plan["booked_calls"]})

    def test_evidence_payload_feeds_runtime_and_crm_sync_readers(self):
        record = normalize_booking(_booking("uid-1", email="jane@example.com",
                                            start="2026-08-20T15:30:00Z"))
        payload = evidence_payload(record)
        self.assertNotIn("kind", payload)  # kind is the evidence command's --kind flag
        self.assertEqual("jane@example.com", payload["attendee_email"])
        self.assertEqual("2026-08-20T15:30:00Z", payload["date"])
        self.assertEqual("cal:uid-1", payload["lead_id"])  # crm_sync booked_note key
        self.assertEqual("cal.com", payload["source"])
        self.assertIn(BOOKING_URL, payload["note"])

    def test_evidence_command_targets_the_booked_calls_goal_with_business_validity(self):
        record = normalize_booking(_booking("uid-1"))
        command = evidence_command("goal-booked-calls-primary-20260815",
                                   evidence_payload(record))
        self.assertIn("evidence add goal-booked-calls-primary-20260815", command)
        self.assertIn("--kind booked_call", command)
        self.assertIn("--source calcom_sync", command)
        self.assertIn("--validity business", command)  # runtime counts only business-valid
        self.assertIn('"booking_uid":"uid-1"', command)


class SyncStateAndCliTests(unittest.TestCase):
    def _plan(self, directory: Path, uids: list[str] | None = None) -> Path:
        plan_path = directory / "calcom_sync_plan.json"
        plan_path.write_text(json.dumps({
            "generated_at": "2026-08-19T01:00:00+00:00",
            "goal": "goal-booked-calls-primary-20260815",
            "counts": {"new_booked_calls": len(uids or [])},
            "booked_calls": [],
            "commit_state": {"booked_uids": uids or ["uid-1", "uid-2"]},
        }))
        return plan_path

    def test_commit_state_merges_uids_and_preserves_previous(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            state_path = root / "calcom_sync.json"
            state_path.write_text(json.dumps({"version": 1,
                                              "last_sync_at": "2026-08-18T00:00:00+00:00",
                                              "booked_uids": ["old-1"]}))
            plan_path = self._plan(root, uids=["uid-2", "uid-2"])
            code = commit_state(plan_path, state_path)
            state = json.loads(state_path.read_text())

        self.assertEqual(0, code)
        self.assertEqual(["old-1", "uid-2"], state["booked_uids"])
        self.assertTrue(state["last_sync_at"])

    def test_commit_state_creates_state_from_nothing(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            plan_path = self._plan(root, uids=["uid-1"])
            code = commit_state(plan_path, root / "new_state.json")
            state = json.loads((root / "new_state.json").read_text())

        self.assertEqual(0, code)
        self.assertEqual(["uid-1"], state["booked_uids"])
        self.assertEqual(1, state["version"])

    def test_commit_state_missing_plan_fails(self):
        with TemporaryDirectory() as directory:
            code = commit_state(Path(directory) / "nope.json",
                                Path(directory) / "state.json")
        self.assertEqual(1, code)

    @patch.dict(os.environ, {"CALCOM_API_KEY": "cal_live_test"}, clear=False)
    def test_dry_run_never_writes_state_and_only_writes_plan(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            state_path = root / "calcom_sync.json"
            plan_path = root / "calcom_sync_plan.json"
            with patch("company.departments.outbound.calcom_sync.urlopen",
                       return_value=_json_response({
                           "status": "success",
                           "data": [_booking("uid-1")],
                           "pagination": {"nextCursor": None, "hasMore": False}})):
                with patch("sys.stdout", new_callable=io.StringIO) as out:
                    code = main(["--dry-run", "--state", str(state_path),
                                 "--plan", str(plan_path)])

            self.assertEqual(0, code)
            self.assertFalse(state_path.exists(), "dry-run must not touch sync state")
            self.assertTrue(plan_path.exists())
            plan = json.loads(plan_path.read_text())
            self.assertTrue(plan["dry_run"])
            self.assertEqual(1, plan["counts"]["new_booked_calls"])
            self.assertIn("no state, evidence, or Attio writes", out.getvalue())

    @patch.dict(os.environ, {"CALCOM_API_KEY": "cal_live_test"}, clear=False)
    def test_apply_prints_host_operations_and_never_writes_state(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            state_path = root / "calcom_sync.json"
            plan_path = root / "calcom_sync_plan.json"
            with patch("company.departments.outbound.calcom_sync.urlopen",
                       return_value=_json_response({
                           "status": "success",
                           "data": [_booking("uid-1", email="jane@example.com")],
                           "pagination": {"nextCursor": None, "hasMore": False}})):
                with patch("sys.stdout", new_callable=io.StringIO) as out:
                    code = main(["--apply", "--state", str(state_path),
                                 "--plan", str(plan_path)])

            self.assertEqual(0, code)
            self.assertFalse(state_path.exists())
            rendered = out.getvalue()
            self.assertIn("company evidence add goal-booked-calls-primary-20260815", rendered)
            self.assertIn("search-records(object='people', query='jane@example.com')", rendered)
            self.assertIn("create-note(", rendered)
            self.assertIn("--commit-state", rendered)
            plan = json.loads(plan_path.read_text())
            self.assertFalse(plan["dry_run"])

    @patch.dict(os.environ, {"CALCOM_API_KEY": "cal_live_test"}, clear=False)
    def test_apply_with_no_new_bookings_prints_nothing_to_apply(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            with patch("company.departments.outbound.calcom_sync.urlopen",
                       return_value=_json_response({
                           "status": "success", "data": [],
                           "pagination": {"nextCursor": None, "hasMore": False}})):
                with patch("sys.stdout", new_callable=io.StringIO) as out:
                    code = main(["--apply", "--state", str(root / "s.json"),
                                 "--plan", str(root / "p.json")])
        self.assertEqual(0, code)
        self.assertIn("no new bookings", out.getvalue())

    def test_verify_plan_prints_read_back_expectations(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            plan_path = root / "plan.json"
            plan_path.write_text(json.dumps({
                "generated_at": "2026-08-19T01:00:00+00:00",
                "goal": "goal-booked-calls-primary-20260815",
                "counts": {"new_booked_calls": 1, "unmatched_attendee_email": 0},
                "booked_calls": [{
                    "record": {"uid": "uid-1", "status": "accepted", "attendee_email": "a@b.com",
                               "event_type_slug": "15min", "start": "2026-08-20T15:30:00Z"},
                    "evidence_payload": {"booking_uid": "uid-1"},
                    "attio_note": ("SpielOS outbound — booked call",
                                   "Booked call 2026-08-20 · cal:uid-1 · " + BOOKING_URL),
                }],
            }))
            with patch("sys.stdout", new_callable=io.StringIO) as out:
                code = verify_plan(plan_path)
        self.assertEqual(0, code)
        self.assertIn("a@b.com", out.getvalue())
        self.assertIn("booked_call evidence", out.getvalue())

    def test_verify_plan_missing_file_fails(self):
        self.assertEqual(1, verify_plan(Path("/nonexistent/plan.json")))

    @patch.dict(os.environ, {"CALCOM_API_KEY": "cal_live_test"}, clear=False)
    def test_missing_api_key_fails_cleanly(self):
        with patch.dict(os.environ, {}, clear=True):
            with patch("company.departments.outbound.calcom_sync._env_values", return_value={}):
                with patch("sys.stdout", new_callable=io.StringIO) as out, \
                     patch("sys.stderr", new_callable=io.StringIO) as err:
                    code = main(["--dry-run"])
        self.assertEqual(1, code)
        self.assertIn("CALCOM_API_KEY is not configured", err.getvalue())


if __name__ == "__main__":
    unittest.main()