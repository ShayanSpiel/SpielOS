#!/usr/bin/env python3
"""Cal.com -> Attio booked-call sync adapter (bounded, host-mediated).

Scope
-----
Reads booked Discovery Calls from the official Cal.com API v2
(GET https://api.cal.com/v2/bookings) with the local ``CALCOM_API_KEY``
(private, gitignored, read from ``.spielos/.env``), dedupes them against the
last-sync state file, and produces:

  * ``booked_call`` evidence operations for the company runtime — emitted as
    exact ``company evidence add`` commands on the runtime command surface so
    the active booked-calls outcome (``goal-booked-calls-primary-20260815``)
    measures real bookings, and
  * Attio note operations for the host/approval to execute through the attio
    MCP connection (``search-records`` by attendee email, then ``create-note``
    on the matched existing people record — never creates people).

Evidence validity
-----------------
The runtime's director only counts goal-level ``booked_call`` evidence whose
validity is ``business`` (see runtime/director.py and
tests/test_booked_calls_director_metric.py). A confirmed booking returned by
Cal.com is an observed business fact, so the emitted evidence command carries
``--validity business``. This module itself never executes that command.

Write discipline (mirrors ``crm_sync.py``)
------------------------------------------
This process has no Cal.com write path and no Attio MCP client. It NEVER:

  * writes to Attio (host applies the printed operations),
  * executes the runtime evidence command (host runs the printed commands),
  * writes the dedupe state on its own.

It only:
  * reads Cal.com (GET /v2/bookings — read-only),
  * writes the local apply-plan JSON under ``.spielos/state/outbound/``
    (dry-run and apply both),
  * merges a *committed* plan's booking uids into the sync-state file via the
    explicit ``--commit-state`` step the host runs AFTER the evidence/Attio
    writes actually landed (atomic tmp + replace, same pattern as crm_sync).

Booking -> booked_call definition
---------------------------------
A booking "counts" as a booked call when Cal.com reports its own ``status`` as
``accepted`` (confirmed) and its event-type slug is in scope (default: the
Discovery Call link ``15min``). Pending/unconfirmed, cancelled, and rejected
bookings never produce evidence or Attio operations. ``upcoming``, ``recurring``
and ``past`` are fetched (one request per status, cursor-walked) so accepted
bookings in every time bucket are seen; client-side uid dedupe makes repeated
runs idempotent.

API contract notes (docs: https://cal.com/docs/api-reference/v2/introduction)
-----------------------------------------------------------------------------
  * Auth: ``Authorization: Bearer <api-key>``; must pass
    ``cal-api-version: 2026-05-01`` (required header).
  * ``GET /v2/bookings`` — cursor pagination: pass ``pagination.nextCursor``
    back as ``cursor``; repeat while ``pagination.hasMore`` is true.
    ``limit`` (default 50, max 100) per page.
  * ``status`` accepts ONE value per request (upcoming | recurring | past |
    cancelled | unconfirmed); multiple statuses need parallel/sequential
    requests merged client-side. Sort/walk anchors differ per status.
  * BookingOutput carries: uid, id, status (accepted | cancelled | rejected |
    pending), start/end (ISO-8601), createdAt, eventType { id, slug },
    attendees [{ name, email, displayEmail, timeZone, language, absent }],
    title, location.
  * Rate limits: API-key auth 120 requests/minute.

Usage
-----
    python3 -m company.departments.outbound.calcom_sync --dry-run
    python3 -m company.departments.outbound.calcom_sync --apply
    python3 -m company.departments.outbound.calcom_sync --verify --plan PATH
    python3 -m company.departments.outbound.calcom_sync --commit-state PATH

Exit codes: 0 ok, 1 invalid invocation / unreadable state / Cal.com failure.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

API_URL = "https://api.cal.com/v2/bookings"
API_VERSION_HEADER = "2026-05-01"
TIMEOUT_SECONDS = 30
PAGE_SIZE = 100  # documented maximum per page
# The Discovery Call booking link owned by the founder (goal config 2026-08-19).
BOOKING_URL = "https://cal.com/shayanspiel/15min"
DEFAULT_EVENT_SLUGS = ("15min",)
DEFAULT_STATUSES = ("upcoming", "recurring", "past")
# Goal that owns the booked_calls outcome metric (goal config 2026-08-19).
DEFAULT_GOAL = "goal-booked-calls-primary-20260815"
# Cal.com BookingOutput statuses that mean "confirmed" (lowercase per API).
ACCEPTED_STATUSES = frozenset({"accepted"})

REPO_ROOT = Path(__file__).resolve().parents[3]
ENV_PATH = REPO_ROOT / ".spielos" / ".env"
STATE_PATH_DEFAULT = REPO_ROOT / ".spielos" / "state" / "outbound" / "calcom_sync.json"
PLAN_PATH_DEFAULT = REPO_ROOT / ".spielos" / "state" / "outbound" / "calcom_sync_plan.json"


class CalComError(RuntimeError):
    """A safe Cal.com error message that never embeds credentials."""


def _env_values(path: Path = ENV_PATH) -> dict[str, str]:
    """Read dotenv assignments without executing the file as shell code
    (same parser as the buffer connection)."""
    if not path.exists():
        return {}
    values: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].lstrip()
        key, separator, value = line.partition("=")
        if not separator or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key.strip()):
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        values[key.strip()] = value
    return values


def environment() -> dict[str, str]:
    values = _env_values()
    return {**values, **{key: value for key, value in os.environ.items() if value}}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _rate_limits(headers: Any) -> dict[str, str]:
    items = headers.items() if hasattr(headers, "items") else []
    return {str(key): str(value) for key, value in items
            if "rate" in str(key).lower() or "limit" in str(key).lower()}


def _first_attendee(booking: dict[str, Any]) -> dict[str, Any]:
    attendees = booking.get("attendees") or []
    return attendees[0] if attendees else {}


def normalize_booking(booking: dict[str, Any]) -> dict[str, Any] | None:
    """Normalize one Cal.com BookingOutput into a sync record, or None.

    Only bookings Cal.com itself reports as ``accepted`` are booked calls;
    pending/unconfirmed, cancelled, and rejected bookings are excluded here
    (the fetch already requests upcoming/recurring/past buckets — the record's
    own status decides).
    """
    uid = str(booking.get("uid") or "").strip()
    status = str(booking.get("status") or "").strip().lower()
    if not uid or status not in ACCEPTED_STATUSES:
        return None
    event = booking.get("eventType") or {}
    attendee = _first_attendee(booking)
    return {
        "uid": uid,
        "cal_id": booking.get("id"),
        "status": status,
        "title": str(booking.get("title") or "").strip(),
        "event_type_id": event.get("id"),
        "event_type_slug": str(event.get("slug") or "").strip(),
        "start": str(booking.get("start") or "").strip(),
        "end": str(booking.get("end") or "").strip(),
        "created_at": str(booking.get("createdAt") or "").strip(),
        "attendee_name": str(attendee.get("name") or "").strip(),
        "attendee_email": str(attendee.get("email") or "").strip().lower(),
        "attendee_timezone": str(attendee.get("timeZone") or "").strip(),
        "location": str(booking.get("location") or "").strip(),
    }


class CalComClient:
    """Read-only Cal.com API v2 bookings client (direct HTTP, local key)."""

    def __init__(self, api_key: str | None = None):
        values = environment()
        self.api_key = (api_key or values.get("CALCOM_API_KEY", "")).strip()
        if not self.api_key:
            raise CalComError("CALCOM_API_KEY is not configured (keep it only in .spielos/.env)")
        self.last_rate_limits: dict[str, str] = {}

    def _get(self, params: dict[str, Any]) -> dict[str, Any]:
        query = urlencode({key: str(value) for key, value in params.items() if value is not None})
        url = API_URL + ("?" + query if query else "")
        request = Request(url, method="GET", headers={
            "Authorization": f"Bearer {self.api_key}",
            "cal-api-version": API_VERSION_HEADER,
            "Accept": "application/json",
        })
        try:
            with urlopen(request, timeout=TIMEOUT_SECONDS) as response:  # nosec B310: fixed HTTPS endpoint
                self.last_rate_limits = _rate_limits(response.headers)
                payload = json.loads(response.read().decode("utf-8"))
        except HTTPError as error:
            self.last_rate_limits = _rate_limits(error.headers)
            raise CalComError(f"Cal.com request failed with HTTP {error.code}") from error
        except (URLError, TimeoutError) as error:
            raise CalComError("Cal.com API could not be reached") from error
        except ValueError as error:  # malformed JSON body
            raise CalComError("Cal.com API returned an unreadable response") from error
        if not isinstance(payload, dict) or payload.get("status") == "error":
            message = str((payload or {}).get("error") or "unknown error")
            raise CalComError("Cal.com API error: " + message)
        return payload

    def _walk_status(self, status: str) -> list[dict[str, Any]]:
        """Cursor-walk one status bucket until ``pagination.hasMore`` is false."""
        bookings: list[dict[str, Any]] = []
        cursor: str | None = None
        while True:
            params: dict[str, Any] = {"status": status, "limit": PAGE_SIZE}
            if cursor:
                params["cursor"] = cursor
            payload = self._get(params)
            bookings.extend(payload.get("data") or [])
            pagination = payload.get("pagination") or {}
            if not pagination.get("hasMore"):
                return bookings
            cursor = pagination.get("nextCursor")
            if not cursor:
                return bookings

    def fetch_bookings(self, statuses: tuple[str, ...] = DEFAULT_STATUSES) -> list[dict[str, Any]]:
        """All bookings across the given status buckets (read-only).

        The API accepts ONE status per request, so each status is walked
        separately and merged client-side (the merge the docs prescribe for
        multi-status reads). A booking uid seen in more than one bucket is
        kept once — the client-side merge is idempotent.
        """
        fetched: list[dict[str, Any]] = []
        seen_uids: set[str] = set()
        for status in statuses or DEFAULT_STATUSES:
            for booking in self._walk_status(str(status)):
                uid = str(booking.get("uid") or "").strip()
                if uid:
                    if uid in seen_uids:
                        continue
                    seen_uids.add(uid)
                fetched.append(booking)
        return fetched


# ── Durable sync state (outbound state pattern under .spielos/state/) ───────

def load_state(path: Path) -> dict[str, Any]:
    """Last-sync state: ``{"version": 1, "last_sync_at": str|None,
    "booked_uids": [str, ...]}``. Missing or malformed files start empty."""
    if not path.exists():
        return {"version": 1, "last_sync_at": None, "booked_uids": []}
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"version": 1, "last_sync_at": None, "booked_uids": []}
    if not isinstance(state, dict):
        return {"version": 1, "last_sync_at": None, "booked_uids": []}
    state.setdefault("version", 1)
    state.setdefault("last_sync_at", None)
    state.setdefault("booked_uids", [])
    return state


def dedupe(records: list[dict[str, Any]], state: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Split records into not-yet-synced vs already-synced by booking uid."""
    known = set(str(item) for item in (state.get("booked_uids") or []))
    new = [record for record in records if str(record.get("uid") or "") not in known]
    seen = [record for record in records if str(record.get("uid") or "") in known]
    return new, seen


def _shell_single_quote(value: str) -> str:
    """Escape a value for embedding inside a single-quoted shell argument."""
    return str(value).replace("'", "'\\''")


def booked_note(record: dict[str, Any]) -> tuple[str, str]:
    """Attio note title/content for one booked call (same voice as crm_sync)."""
    date = str(record.get("start") or record.get("created_at") or "").split("T", 1)[0] or "?"
    lead = str(record.get("uid") or "?")
    content = f"Booked call {date} · cal:{lead} · {BOOKING_URL}"
    title = "SpielOS outbound — booked call"
    return title, content


def evidence_payload(record: dict[str, Any]) -> dict[str, Any]:
    """Runtime ``booked_call`` evidence payload for one accepted booking."""
    return {
        "booking_uid": record["uid"],
        "cal_booking_id": record.get("cal_id"),
        "event_type_slug": record.get("event_type_slug") or "",
        "title": record.get("title") or "",
        "attendee_name": record.get("attendee_name") or "",
        "attendee_email": record.get("attendee_email") or "",
        "date": record.get("start") or record.get("created_at") or "",
        "end": record.get("end") or "",
        "status": record.get("status") or "accepted",
        "lead_id": f"cal:{record['uid']}",
        "source": "cal.com",
        "note": f"Discovery Call booked via {BOOKING_URL}",
    }


def evidence_command(goal: str, payload: dict[str, Any]) -> str:
    """The exact runtime evidence command the host executes on approval.

    kind=booked_call, source=calcom_sync, validity=business (the director only
    counts business-valid booked_call evidence toward the booked_calls metric).
    """
    rendered = json.dumps(payload, separators=(",", ":"), ensure_ascii=False)
    return (f"PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=.agents python3 -B -m company "
            f"evidence add {goal} --kind booked_call --source calcom_sync "
            f"--validity business --payload '{_shell_single_quote(rendered)}'")


def collect(client: CalComClient, *, state_path: Path = STATE_PATH_DEFAULT,
            goal: str = DEFAULT_GOAL, slugs: tuple[str, ...] = DEFAULT_EVENT_SLUGS,
            statuses: tuple[str, ...] = DEFAULT_STATUSES,
            limit: int | None = None) -> dict[str, Any]:
    """Fetch + dedupe + map into an apply-plan (no writes beyond the caller's
    plan file; state, evidence, and Attio stay untouched here)."""
    state = load_state(state_path)
    bookings = client.fetch_bookings(statuses=statuses)
    records = [item for booking in bookings for item in [normalize_booking(booking)] if item]
    if slugs:
        records = [record for record in records if record.get("event_type_slug") in slugs]
    # Newest first for the controlled --limit sample (same convention as crm_sync).
    records.sort(key=lambda record: record.get("start") or record.get("created_at") or "",
                 reverse=True)
    new, seen = dedupe(records, state)
    if limit is not None and limit > 0:
        new = new[:limit]
    unmatched = [record for record in new if not record.get("attendee_email")]

    booked_calls = [{"record": record, "attio_note": booked_note(record),
                     "evidence_payload": evidence_payload(record)} for record in new]
    counts = {
        "fetched_bookings": len(bookings),
        "accepted_in_scope": len(records),
        "new_booked_calls": len(new),
        "already_synced": len(seen),
        "unmatched_attendee_email": len(unmatched),
    }
    return {
        "generated_at": utc_now(),
        "goal": goal,
        "dry_run": True,  # refreshed by the caller
        "api": API_URL,
        "counts": counts,
        "booked_calls": booked_calls,
        "sources": {
            "state": str(state_path),
            "api_version_header": API_VERSION_HEADER,
            "event_slugs": list(slugs),
            "statuses": list(statuses),
        },
        "commit_state": {
            "booked_uids": [record["uid"] for record in new],
        },
    }


def print_plan(state: dict[str, Any]) -> None:
    counts = state["counts"]
    print("=" * 64)
    print(f"Cal.com -> Attio booked-call sync plan · {state['generated_at']}")
    print(f"  goal: {state['goal']}")
    print(f"  fetched: {counts['fetched_bookings']} bookings ·"
          f" accepted in scope: {counts['accepted_in_scope']}"
          f" · new: {counts['new_booked_calls']}"
          f" · already synced: {counts['already_synced']}")
    if counts["unmatched_attendee_email"]:
        print(f"  WARNING: {counts['unmatched_attendee_email']} booking(s) have no"
              " attendee email — evidence only, no Attio note")
    print("=" * 64)
    for item in state["booked_calls"]:
        record = item["record"]
        title, content = item["attio_note"]
        print(f"  [{record['status']:<9}] {record['attendee_email'] or '(no email)'}"
              f" · {record['event_type_slug']} · {record.get('start') or '?'}")
        print(f"      {title}: {content}")
    if not state["booked_calls"]:
        print("  (no new accepted bookings — nothing to record)")


def write_plan(state: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, default=str)
    os.replace(tmp, path)


def commit_state(plan_path: Path, state_path: Path = STATE_PATH_DEFAULT) -> int:
    """Mark a plan's bookings as synced AFTER the host applied the evidence
    and Attio operations (local-only, no network; atomic tmp + replace)."""
    if not plan_path.exists():
        print(f"plan not found: {plan_path}", file=sys.stderr)
        return 1
    try:
        plan = json.loads(plan_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        print(f"cannot read plan {plan_path}: {exc}", file=sys.stderr)
        return 1
    uids = list(plan.get("commit_state", {}).get("booked_uids") or [])
    state = load_state(state_path)
    known = [str(item) for item in (state.get("booked_uids") or [])]
    known_set = set(known)
    merged = list(known)
    for uid in uids:  # dedupe within the plan's uids and against the state set
        uid = str(uid)
        if uid not in known_set:
            known_set.add(uid)
            merged.append(uid)
    state["booked_uids"] = merged
    state["last_sync_at"] = utc_now()
    state["version"] = 1
    state_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = state_path.with_suffix(state_path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, default=str)
    os.replace(tmp, state_path)
    print(f"committed {len(uids)} booking uid(s) to sync state: {state_path}")
    print(f"  total known uids: {len(merged)} · last_sync_at: {state['last_sync_at']}")
    return 0


def verify_plan(path: Path) -> int:
    """Read-back verification helper for an apply-plan (same contract as
    crm_sync --verify): prints the expected runtime evidence and Attio
    assertions so the host can compare after applying."""
    if not path.exists():
        print(f"plan not found: {path}", file=sys.stderr)
        return 1
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        print(f"cannot read plan {path}: {exc}", file=sys.stderr)
        return 1
    counts = state.get("counts") or {}
    print("=" * 64)
    print(f"Read-back verification expectations · {path}")
    print(f"  goal: {state.get('goal')} · generated {state.get('generated_at')}")
    print(f"  expected: {counts.get('new_booked_calls', 0)} booked_call evidence"
          f" + {counts.get('new_booked_calls', 0)} Attio notes (unmatched:"
          f" {counts.get('unmatched_attendee_email', 0)})")
    print("=" * 64)
    for item in state.get("booked_calls") or []:
        record = item["record"]
        payload = item["evidence_payload"]
        title, content = item["attio_note"]
        print(f"  evidence: company evidence add {state.get('goal')}"
              f" --kind booked_call --source calcom_sync"
              f" --payload '{json.dumps(payload, separators=(',', ':'))}'")
        print(f"  attio: email {record['attendee_email'] or '(no email)'}"
              f" -> people record")
        print(f"      note title:   {title}")
        print(f"      note content: {content}")
    print("- Verify by: (1) company status <goal> shows booked_call evidence;")
    print("  (2) search-records(object='people', query=<attendee email>) resolves")
    print("  to an existing person (never created) carrying the expected note.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python3 -m company.departments.outbound.calcom_sync",
        description="Sync booked Cal.com Discovery Calls into runtime booked_call "
                    "evidence + Attio notes (host-mediated; dry-run never writes "
                    "state, evidence, or Attio).")
    parser.add_argument("--dry-run", action="store_true",
                        help="fetch (read-only), dedupe, print the plan, write the "
                             "local plan JSON — no state/evidence/Attio writes")
    parser.add_argument("--apply", action="store_true",
                        help="live gate: write the plan and print the exact commands "
                             "the host runs on approval (evidence add + attio MCP)")
    parser.add_argument("--commit-state", metavar="PLAN",
                        help="mark a PLAN's bookings as synced (run after the host "
                             "applied evidence + Attio notes; local-only)")
    parser.add_argument("--verify", action="store_true",
                        help="print read-back verification expectations for --plan")
    parser.add_argument("--plan", default=str(PLAN_PATH_DEFAULT),
                        help="plan file path (default .spielos/state/outbound/calcom_sync_plan.json)")
    parser.add_argument("--state", default=str(STATE_PATH_DEFAULT),
                        help="sync-state file path (default .spielos/state/outbound/calcom_sync.json)")
    parser.add_argument("--goal", default=DEFAULT_GOAL,
                        help=f"goal id receiving booked_call evidence (default {DEFAULT_GOAL})")
    parser.add_argument("--slugs", default=",".join(DEFAULT_EVENT_SLUGS),
                        help="comma-separated event-type slugs to count (empty = all;"
                             f" default {','.join(DEFAULT_EVENT_SLUGS)})")
    parser.add_argument("--statuses", default=",".join(DEFAULT_STATUSES),
                        help="comma-separated Cal.com status buckets to walk"
                             f" (default {','.join(DEFAULT_STATUSES)})")
    parser.add_argument("--limit", type=int, default=None,
                        help="controlled sample: only the N newest new bookings")
    args = parser.parse_args(argv)

    if args.commit_state:
        return commit_state(Path(args.commit_state), Path(args.state))
    if args.verify:
        return verify_plan(Path(args.plan))

    slugs = tuple(item.strip() for item in args.slugs.split(",") if item.strip())
    statuses = tuple(item.strip() for item in args.statuses.split(",") if item.strip())
    try:
        client = CalComClient()
    except CalComError as exc:
        print(f"calcom_sync: {exc}", file=sys.stderr)
        return 1
    try:
        state = collect(client, state_path=Path(args.state), goal=args.goal,
                        slugs=slugs, statuses=statuses, limit=args.limit)
    except CalComError as exc:
        print(f"calcom_sync: {exc}", file=sys.stderr)
        return 1

    if args.apply:
        state["dry_run"] = False
        print_plan(state)
        write_plan(state, Path(args.plan))
        print(f"\nApply plan: {args.plan}")
        print("Host apply (approval required — the connector never writes):")
        if state["booked_calls"]:
            print("  1. record runtime evidence (booked_call, business validity):")
            for item in state["booked_calls"]:
                print(f"     {evidence_command(args.goal, item['evidence_payload'])}")
            print("  2. Attio notes via the attio MCP connection (existing people only):")
            for item in state["booked_calls"]:
                record = item["record"]
                title, content = item["attio_note"]
                print(f"     search-records(object='people', query='{record['attendee_email']}')")
                print(f"     create-note(parent_object='people', parent_record_id=<matched id>,"
                      f" title='{_shell_single_quote(title)}', content='{_shell_single_quote(content)}')")
        else:
            print("  (no new bookings — nothing to apply)")
        print("  3. after the evidence and Attio notes are applied and verified,")
        print("     mark the plan as synced:")
        print(f"     python3 -m company.departments.outbound.calcom_sync"
              f" --commit-state {args.plan}")
        return 0

    # --dry-run (safe default when no other mode flag is given).
    state["dry_run"] = True
    print_plan(state)
    write_plan(state, Path(args.plan))
    print(f"\nPlan written (dry-run — no state, evidence, or Attio writes): {args.plan}")
    print("Re-run with --apply to print the host operations for approval.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())