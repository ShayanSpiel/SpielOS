# Outbound Department

The Outbound Department pursues qualified buyer conversations across email and
approved social workflows. It shares one ICP, prospect record, research dossier,
contact history, suppression policy, and outcome model.

## Workflows

- `lead-research` — discover, qualify, research, and verify prospects.
- `email-outreach` — compose, validate, approve, send, and measure email.
- `social-lead-research` — find and research LinkedIn/X prospects against ICP.
- `social-dm` — write and validate platform-native personalized DM drafts.

LinkedIn and X research must use public or owner-authorized access. The runtime
does not bulk-send unsolicited social messages. Drafts require an explicit
human/external-channel action before sending.

The company runtime owns goals and loop transitions. These workflows never run
their own scheduler, approval system, or state machine.

## CRM state sync (`crm_sync.py`)

After each dispatched email batch, the sync adapter pushes send/reply/booked-call
state from the durable send engine into Attio (people matched by the
`email_addresses` unique key; sent-history notes mirror the goal-7bbd594426
deployment style). The send engine itself is never touched: the canonical Master Leads (Desktop `SPIELOS_MASTER_LEADS_v4.xlsx`) remains
the master lead list, SQLite + sent.json remain the durable send authority, and
the dedupe/approval gates are unchanged.

Scope (first iteration, bounded):

- Read-only reuse of the department data layer: `data.py` (OutboundStore batch
  registry), `workflows/email/outbound.py` (sent log + master contacts),
  `workflows/email/analytics.py` (reply ledger), and the company runtime store
  (owner-recorded `booked_call` evidence).
- `--dry-run` reports mapped sent/reply/booked-call counts and performs no Attio
  calls (the module has no Attio client). Live application is executed by the
  OpenCode host through the registered `attio` MCP connection
  (`search-records` -> `create-note`) from the plan this module emits.
- People not found by email are reported, never created.

Entrypoints:

```sh
python3 crm_sync.py --dry-run --batch send-f3d15c092d49 [--limit N]
python3 crm_sync.py --batch send-f3d15c092d49 --limit 5 --plan-out plan.json
python3 crm_sync.py --verify-plan plan.json --readback readback.json
```

See `.agents/company/README.md` for the company architecture.
