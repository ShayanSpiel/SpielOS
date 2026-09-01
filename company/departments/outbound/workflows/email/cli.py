"""Email workflow — admin commands (record-reply, replies, stats).

Domain-specific convenience commands for the owner session, dispatched by
These helpers are called through bounded Department actions; they do not own a CLI loop.

Entrypoint (same convention as leads.py / verify.py — module dispatch):

  PYTHONPATH=.agents python3 -m company.departments.outbound.workflows.email.cli \
      replies --recheck [--dry-run]

`replies --recheck` reconciles the stored reply ledger: re-runs classification
on every reply record from its stored inputs (subject, from, Auto-Submitted /
X-Autoreply headers), corrects stale kinds, dedupes per lead across capture
paths (keep newest record, merge metadata), persists idempotently, and prints
a change report. `--dry-run` reports what would change without writing.
"""

import sys
from datetime import datetime, timezone

from . import analytics, outbound


def record_reply(identifier: str, note: str = "") -> None:
    log = outbound.load_sent_log()
    s = next(
        (x for x in log.get("sent", []) if x.get("lead_id") == identifier or x.get("email") == identifier),
        None,
    )
    if not s:
        print(f"ERROR: no sent email found for '{identifier}' (use lead_id or email).")
        raise SystemExit(1)

    metrics = analytics.load_metrics()
    for r in metrics.get("replies", []):
        if r["lead_id"] == s["lead_id"]:
            at = r.get("recorded_at") or r.get("received_at") or "?"
            print(f"ERROR: reply already recorded for {s['email']} on {at}.")
            raise SystemExit(1)

    metrics.setdefault("replies", []).append({
        "received_id": None,
        "lead_id": s["lead_id"],
        "email": s["email"],
        "company": s.get("company"),
        "variant": s.get("variant"),
        "subject": s.get("subject"),
        "message_id": None,
        "received_at": None,
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "kind": "reply",
        "note": note or "",
    })
    analytics.save_metrics(metrics)
    print(f"✅ Reply recorded for {s.get('contact_name', '?')} <{s['email']}> ({s.get('company', '?')})")


def replies(recheck: bool = False, dry_run: bool = False) -> None:
    metrics = analytics.load_metrics()
    if recheck:
        report = analytics.recheck_replies(metrics, dry_run=dry_run)
        changed = (report["records_after"] != report["records_before"]
                   or bool(report["reclassified"]))
        if not dry_run and changed:
            analytics.save_metrics(metrics)
        _print_recheck_report(report)
        return
    rs = metrics.get("replies", [])
    if not rs:
        print("No replies recorded yet. Use `record-reply <email|lead_id>` when one lands "
              "in the inbox, or set REPLY_TO to a Resend receiving domain to auto-detect.")
        return
    # Render ANY stored record shape: merged records (owner evidence 2026-08-11,
    # change-d1459e3624) can carry recorded_at=null and email=null after the
    # recheck collapse. Fall back to received_at for the timestamp and to the
    # sent-log lead email (then lead_id) for the address; never crash on
    # null/absent fields.
    lead_emails = {s.get("lead_id"): s.get("email")
                   for s in outbound.load_sent_log().get("sent", [])}
    print(f"\n{'='*60}")
    print(f"  REPLIES ({len(rs)})")
    print(f"{'='*60}")
    for r in rs:
        note = f" — {r['note']}" if r.get("note") else ""
        source = "auto" if r.get("received_id") else "manual"
        at = str(r.get("recorded_at") or r.get("received_at") or "?")[:16]
        email = r.get("email") or lead_emails.get(r.get("lead_id")) or r.get("lead_id") or "?"
        print(f"  {at}  {email} ({r.get('company', '?')})  "
              f"[{r.get('variant', '?')} · {r.get('kind')} · {source}]{note}")
    print(f"{'='*60}\n")


def _print_recheck_report(report: dict) -> None:
    mode = "DRY-RUN — no changes written" if report.get("dry_run") else "applied to ledger"
    print(f"\n{'='*60}")
    print(f"  REPLY RECHECK — {mode}")
    print(f"{'='*60}")
    print(f"  Records: {report['records_before']} -> {report['records_after']} "
          f"(per-lead duplicates collapsed)")
    print(f"  Kind corrections: {len(report['reclassified'])}")
    for item in report["reclassified"]:
        print(f"    - {item['lead_id']} {item['subject']!r} ({item['from']}) "
              f"{item['old']} -> {item['new']}")
    print(f"  Duplicate groups collapsed: {len(report['collapsed'])}")
    for item in report["collapsed"]:
        kept = item["kept"]
        removed = ", ".join(str(r.get('received_id') or r.get('subject'))
                            for r in item["removed"])
        print(f"    - {item['lead_id']}: kept "
              f"{kept.get('received_id') or kept.get('subject')} ({kept.get('kind')})")
        print(f"      removed {len(item['removed'])} record(s): {removed}")
    print(f"  Unchanged: {report['unchanged']}")
    print(f"{'='*60}\n")


def main(argv=None) -> None:
    args = list(sys.argv[1:] if argv is None else argv)
    cmd = args[0] if args else "help"
    if cmd == "record-reply" and len(args) >= 2:
        record_reply(args[1], note=args[2] if len(args) > 2 else "")
    elif cmd == "replies":
        replies(recheck="--recheck" in args, dry_run="--dry-run" in args)
    elif cmd == "stats":
        stats()
    else:
        print(__doc__)
        raise SystemExit(1)


if __name__ == "__main__":
    main()


def stats() -> None:
    contacts = outbound.read_contacts()
    langs = {}
    tiers = {}
    statuses = {}
    recs = {}
    for c in contacts:
        langs[c["language"]] = langs.get(c["language"], 0) + 1
        tiers[c["outreach_tier"]] = tiers.get(c["outreach_tier"], 0) + 1
        statuses[c["sequence_status"]] = statuses.get(c["sequence_status"], 0) + 1
        recs[c["send_recommendation"]] = recs.get(c["send_recommendation"], 0) + 1

    log = outbound.load_sent_log()
    sent_count = len(log.get("sent", []))

    print(f"\n{'='*55}")
    print(f"  DATABASE STATS — Master Outreach")
    print(f"{'='*55}")
    print(f"  Total contacts:       {len(contacts)}")
    print(f"  Already sent:         {sent_count}")
    print(f"  Remaining:            {len(contacts) - sent_count}")
    print("")
    print("  By Language:")
    for k, v in sorted(langs.items()):
        print(f"    {k:<12} {v}")
    print("")
    print("  By Tier:")
    for k, v in sorted(tiers.items()):
        print(f"    {k:<12} {v}")
    print("")
    print("  By Sequence Status:")
    for k, v in sorted(statuses.items()):
        print(f"    {k:<12} {v}")
    print("")
    print("  By Send Recommendation:")
    for k, v in sorted(recs.items()):
        print(f"    {k:<12} {v}")
    print(f"{'='*55}\n")
