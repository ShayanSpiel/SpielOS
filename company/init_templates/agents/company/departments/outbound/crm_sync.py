#!/usr/bin/env python3
"""Outbound -> Attio CRM state sync adapter (FIRST iteration, bounded).

Scope
-----
Reads durable Outbound send state that the guarded send engine already
wrote, and maps sent / replied / booked-call state onto existing Attio
people by their unique email key (``email_addresses``):

  * sent records        — the sent log ``.spielos/state/outbound/sent.json``
                          (``sent[]`` entries: lead_id, email, company,
                          contact_name, subject, provider, provider_id,
                          timestamp, variant, batch; failed[] is never
                          synced — only accepted sends are CRM state).
  * replied records     — the department reply ledger
                          ``metrics.json -> replies[]`` (analytics is the
                          department's own reply data access).
  * booked-call records — the company runtime's ``booked_call`` evidence
                          rows (company.sqlite), the department data layer's
                          durable record of booked calls.

The send engine is untouched: this module NEVER writes the sent log, the
SQLite store, leads.xlsx, the dedupe layers, or the approval gates. It
never creates Attio people — only existing matched people receive state;
unmatched emails are reported, never created.

Host-mediated Attio writes
--------------------------
This process has no MCP client. The registered ``attio`` connection lives
in the OpenCode host (``.agents/company/connections/registry.py``) and is
invoked through the host's MCP tools. The module therefore:

  1. maps durable state into an apply-plan (JSON) of exact operations
     (email -> sent-history note for that person),
  2. prints the operations for the host to execute through the attio MCP
     connection (search-records by email, then create-note on the matched
     people record), and
  3. offers a read-back verification helper (``--verify``) that prints the
     expected per-email assertions to compare against Attio after applying.

``--dry-run`` performs NO Attio interaction of any kind: it only reads
local durable state and writes the plan file locally.

Usage
-----
    python3 -m company.departments.outbound.crm_sync --dry-run
    python3 -m company.departments.outbound.crm_sync --dry-run --batch send-f3d15c092d49
    python3 -m company.departments.outbound.crm_sync --batch send-f3d15c092d49 --limit 5 [--plan PATH]
    python3 -m company.departments.outbound.crm_sync --verify --plan PATH

Exit codes: 0 ok, 1 invalid invocation / unreadable durable state.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# ── Department data access (reused, never reinvented) ────────────────────────

from .data import OutboundStore
from .workflows.email.analytics import load_metrics
from .workflows.email.config import METRICS_PATH, SENT_LOG_PATH
from .workflows.email.outbound import load_sent_log


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def project_root() -> Path:
    """Repo root — `.agents/company/departments/outbound/` parents[3] is
    `.agents` (same convention as context.py)."""
    return Path(__file__).resolve().parents[4]


def outbound_store() -> OutboundStore:
    """The department's canonical SQLite store (same path as
    context.build_context)."""
    return OutboundStore(project_root() / ".spielos" / "state" / "outbound" / "outbound.sqlite")


def runtime_db_path() -> Path:
    return project_root() / ".spielos" / "state" / "company.sqlite"


# ── Durable state readers ─────────────────────────────────────────────────────

def batch_lead_ids(batch_id: str) -> list[str]:
    """Lead ids claimed by a registered batch (department batch registry).
    Returns [] for an unknown batch id."""
    store = outbound_store()
    try:
        row = store.get_batch(batch_id)
    finally:
        store.close()
    if not row:
        return []
    return list(row.get("lead_ids") or [])


def booked_call_records() -> list[dict]:
    """Booked-call evidence rows from the company runtime store — the
    department data layer's durable record of booked calls. Read-only."""
    records: list[dict] = []
    db_path = runtime_db_path()
    if not db_path.exists():
        return records
    try:
        con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        con.row_factory = sqlite3.Row
        try:
            rows = con.execute(
                "SELECT payload_json FROM evidence WHERE kind='booked_call'"
                " ORDER BY observed_at, id").fetchall()
        finally:
            con.close()
    except sqlite3.Error:
        return records
    for row in rows:
        try:
            payload = json.loads(row["payload_json"])
        except (TypeError, ValueError):
            continue
        if isinstance(payload, dict):
            records.append(payload)
    return records


# ── State mapping ─────────────────────────────────────────────────────────────

def _dedupe_newest(items: list[dict], key: str) -> list[dict]:
    """One operation per unique key value; the newest record wins
    (operations follow the email unique key the CRM matches on)."""
    newest: dict[str, dict] = {}
    for item in items:
        value = str(item.get(key) or "").strip().lower()
        if not value:
            continue
        if value not in newest or _ts(item) >= _ts(newest[value]):
            newest[value] = item
    return list(newest.values())


def _ts(record: dict) -> str:
    for k in ("timestamp", "received_at", "recorded_at", "date", "observed_at"):
        if record.get(k):
            return str(record[k])
    return ""


def sent_note(record: dict, batch_id: str | None) -> tuple[str, str]:
    ts = str(record.get("timestamp") or "").split("T", 1)[0]
    provider = str(record.get("provider") or "?")
    subject = str(record.get("subject") or "")
    lead = str(record.get("lead_id") or "?")
    batch = batch_id or str(record.get("batch") or "?")
    title = "SpielOS outbound — sent"
    content = (f"Sent {ts} via {provider} · \"{subject}\" · "
               f"lead {lead} · batch {batch}")
    return title, content


def reply_note(record: dict) -> tuple[str, str]:
    ts = str(record.get("received_at") or record.get("recorded_at") or "").split("T", 1)[0]
    subject = str(record.get("subject") or "")
    lead = str(record.get("lead_id") or "?")
    title = "SpielOS outbound — reply"
    content = f"Replied {ts} · \"{subject}\" · lead {lead}"
    return title, content


def booked_note(record: dict) -> tuple[str, str]:
    date = str(record.get("date") or _ts(record).split("T", 1)[0] or "?")
    lead = str(record.get("lead_id") or "?")
    note = str(record.get("note") or "").strip()
    content = f"Booked call {date} · lead {lead}"
    if note:
        content += f" · {note}"
    title = "SpielOS outbound — booked call"
    return title, content


def collect(batch_id: str | None = None, limit: int | None = None) -> dict:
    """Map durable send/reply/booked-call state onto email-keyed operations.

    Returns a plan dict:
      counts: {sent, replied, auto, booked_call} — distinct emails per kind
      operations: [{kind, email, lead_id, subject, provider, provider_id,
                    timestamp, note_title, note_content}]
      sources: paths/timestamps of the durable state read (evidence trail)
    """
    log = load_sent_log()
    sent_log_path = str(SENT_LOG_PATH)
    sent_log_mtime = SENT_LOG_PATH.stat().st_mtime if SENT_LOG_PATH.exists() else None
    sent_total = len(log.get("sent", []))

    # Batch scoping: exact sent-log batch key (same match the email workflow
    # evidence uses) OR the batch registry's claimed lead ids, whichever the
    # durable log carries.
    batch_lead_ids_list: list[str] = []
    if batch_id:
        batch_lead_ids_list = batch_lead_ids(batch_id)
        in_log = [s for s in log.get("sent", [])
                  if str(s.get("batch") or "") == batch_id]
        if in_log:
            sent = in_log
        elif batch_lead_ids_list:
            claimed = set(batch_lead_ids_list)
            sent = [s for s in log.get("sent", []) if s.get("lead_id") in claimed]
        else:
            sent = []
    else:
        sent = list(log.get("sent", []))

    # Newest-first for the controlled --limit sample.
    sent = sorted(sent, key=_ts, reverse=True)
    if limit is not None and limit > 0:
        sent = sent[:limit]

    ops: list[dict] = []
    for record in _dedupe_newest(sent, "email"):
        title, content = sent_note(record, batch_id)
        ops.append({
            "kind": "sent", "email": str(record.get("email") or "").lower(),
            "lead_id": record.get("lead_id"), "company": record.get("company"),
            "contact_name": record.get("contact_name"),
            "subject": record.get("subject"),
            "provider": record.get("provider"), "provider_id": record.get("provider_id"),
            "timestamp": record.get("timestamp"),
            "note_title": title, "note_content": content,
        })

    # Replies: department reply ledger (kind=reply counts as replied; kind=auto
    # is out-of-office and reported separately, matching analytics semantics).
    metrics = load_metrics()
    replies = [r for r in (metrics.get("replies") or []) if r.get("lead_id")]
    if batch_id:
        claimed = set(batch_lead_ids_list) or {o["lead_id"] for o in ops}
        replies = [r for r in replies if r.get("lead_id") in claimed]
    replied = [r for r in replies if str(r.get("kind") or "reply") == "reply"]
    auto = [r for r in replies if str(r.get("kind") or "reply") != "reply"]
    for record in _dedupe_newest(replied, "lead_id"):
        title, content = reply_note(record)
        ops.append({
            "kind": "reply", "email": str(record.get("email") or "").lower(),
            "lead_id": record.get("lead_id"),
            "subject": record.get("subject"),
            "received_at": record.get("received_at"),
            "note_title": title, "note_content": content,
        })

    # Booked calls: runtime evidence rows (kind='booked_call').
    booked = booked_call_records()
    if batch_id:
        claimed = set(batch_lead_ids_list) or {o["lead_id"] for o in ops}
        booked = [b for b in booked if b.get("lead_id") in claimed]
    for record in _dedupe_newest(booked, "lead_id"):
        title, content = booked_note(record)
        ops.append({
            "kind": "booked_call", "email": "",
            "lead_id": record.get("lead_id"),
            "company": record.get("company"), "date": record.get("date"),
            "note": record.get("note"),
            "note_title": title, "note_content": content,
        })

    counts = {
        "sent": sum(1 for o in ops if o["kind"] == "sent"),
        "replied": sum(1 for o in ops if o["kind"] == "reply"),
        "auto": len(auto),
        "booked_call": sum(1 for o in ops if o["kind"] == "booked_call"),
    }
    return {
        "generated_at": utc_now(),
        "batch_id": batch_id,
        "dry_run": True,  # refreshed by the caller (live mode prints the plan)
        "counts": counts,
        "operations": ops,
        "sources": {
            "sent_log": sent_log_path,
            "sent_log_mtime": sent_log_mtime,
            "sent_total": sent_total,
            "reply_ledger": str(METRICS_PATH),
            "booked_call_evidence_db": str(runtime_db_path()),
            "batch_lead_ids": batch_lead_ids_list,
        },
    }


def print_plan(state: dict) -> None:
    counts = state["counts"]
    print("=" * 64)
    print(f"CRM sync plan · generated {state['generated_at']}")
    print(f"  batch: {state['batch_id'] or '(entire durable sent log)'}")
    print(f"  mapped: {counts['sent']} sent / {counts['replied']} replied"
          f" / {counts['booked_call']} booked-call"
          + (f" / {counts['auto']} auto-reply (not synced)"
             if counts["auto"] else ""))
    print(f"  operations: {len(state['operations'])} (email-keyed, no people created)")
    print("=" * 64)
    for op in state["operations"]:
        print(f"  [{op['kind']:<11}] {op.get('email') or ('lead ' + str(op.get('lead_id')))}"
              f" · {op['note_title']}")
        print(f"      {op['note_content']}")
    if not state["operations"]:
        print("  (no state to sync — nothing would be written to Attio)")


def write_plan(state: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w") as f:
        json.dump(state, f, indent=2, default=str)
    import os
    os.replace(tmp, path)


def verify_plan(path: Path) -> int:
    """Read-back verification helper: prints the expected Attio assertions
    for an apply-plan so the host can compare against the CRM after
    applying (search-records by email -> note present with the expected
    title/content)."""
    if not path.exists():
        print(f"plan not found: {path}", file=sys.stderr)
        return 1
    try:
        state = json.loads(path.read_text())
    except (OSError, ValueError) as exc:
        print(f"cannot read plan {path}: {exc}", file=sys.stderr)
        return 1
    print("=" * 64)
    print(f"Read-back verification expectations · {path}")
    print(f"  batch: {state.get('batch_id') or '(full log)'} ·"
          f" generated {state.get('generated_at')}")
    counts = state.get("counts") or {}
    print(f"  expected: {counts.get('sent', 0)} sent /"
          f" {counts.get('replied', 0)} replied /"
          f" {counts.get('booked_call', 0)} booked-call operations")
    print("=" * 64)
    for op in state.get("operations") or []:
        print(f"  email {op.get('email') or '(no email)'} -> people record")
        print(f"      note title:   {op.get('note_title')}")
        print(f"      note content: {op.get('note_content')}")
    print("- Verify by: search-records(object='people', query=<email>), then")
    print("  get-note-body(<note_id>) for the created note; every expected")
    print("  email must resolve to an existing person (never created) and")
    print("  carry the expected note.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python3 -m company.departments.outbound.crm_sync",
        description="Map durable Outbound send state onto existing Attio people "
                    "(host apply via the attio MCP connection; dry-run never talks to Attio).")
    parser.add_argument("--dry-run", action="store_true",
                        help="map durable state, report counts, write the plan — "
                             "no Attio interaction at all")
    parser.add_argument("--batch", help="batch id to scope to (e.g. send-f3d15c092d49)")
    parser.add_argument("--limit", type=int, default=None,
                        help="controlled sample: only the N newest sent records")
    parser.add_argument("--plan", default=str(
        Path(__file__).resolve().parents[4] / ".spielos" / "state" / "outbound" / "crm_sync_plan.json"),
        help="plan file path (default .spielos/state/outbound/crm_sync_plan.json)")
    parser.add_argument("--verify", action="store_true",
                        help="print read-back verification expectations for an apply-plan")
    args = parser.parse_args(argv)

    if args.verify:
        return verify_plan(Path(args.plan))

    if args.dry_run:
        state = collect(batch_id=args.batch, limit=args.limit)
        state["dry_run"] = True
        print_plan(state)
        write_plan(state, Path(args.plan))
        print(f"\nPlan written (dry-run, no Attio calls): {args.plan}")
        return 0

    if args.batch or args.limit:
        # Live gate: same mapping, plan written for host apply through the
        # attio MCP connection. The host executes search-records(<email>) for
        # each operation, creates the note on the matched people record, and
        # read-back verifies with --verify.
        state = collect(batch_id=args.batch, limit=args.limit)
        state["dry_run"] = False
        print_plan(state)
        write_plan(state, Path(args.plan))
        print(f"\nApply plan: {args.plan}")
        print("Host apply (attio MCP connection, read+write):")
        for op in state["operations"]:
            print(f"  1. search-records(object='people', query='{op.get('email') or op.get('lead_id')}')")
            print(f"  2. create-note(parent_object='people', parent_record_id=<matched id>,"
                  f" title='{op.get('note_title')}', content='{op.get('note_content')}')")
        print(f"  3. read-back: python3 -m company.departments.outbound.crm_sync --verify --plan {args.plan}")
        return 0

    parser.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())