# Skill: client-delivery

Operating method for the Client Delivery Department: take workflow orders
(real client builds) and demo workflow orders (client presentations), build
them on the configured automation provider, and keep every order organized in
a lean, scalable folder and registry structure.

## Order types

- `real` — a working workflow for a paying customer, connected to real customer
  tools and data where the order scope allows.
- `demo` — a presentation workflow only. Demo orders use placeholder/demo data,
  clearly labeled (`DEMO — not connected to customer systems` in the flow name
  or description), and are never wired to real customer accounts, domains,
  inboxes, or data sources.

## Provider abstraction (scalability)

Every order spec carries a `provider` field. Today the provider is
`activepieces` (built through the Activepieces host MCP). The folder layout,
naming, registry, evidence kinds, and approval gates are provider-agnostic so
adding Zapier, n8n, Make, or another builder later means adding one Connection
plus one provider section here — never restructuring orders.

## Naming convention

- Real order id:   `wf-YYYYMMDD-<short-slug>`      e.g. `wf-20260826-acme-followup`
- Demo order id:   `demo-YYYYMMDD-<short-slug>`    e.g. `demo-20260826-acme-demo`
- Activepieces flow names use the same id so the online flow is traceable to
  its folder and registry row.

## Lean folder structure

Local ledger (source of truth for company memory):

```
.agents/company/assets/client-delivery/
  README.md                  # this structure + rules, one page
  orders/
    wf-YYYYMMDD-<slug>/
      brief.md               # what the client asked for (real or demo)
      spec.md                # trigger, steps, connections, provider, demo-data note
      delivery-record.md     # final record: links, run evidence, handoff state
  registry.csv               # one row per order: id,type,provider,client,status,links
```

Online mirror (Google Drive, via google-drive / google-sheets Connections):

```
SpielOS Client Delivery/
  Clients/<client>/Workflows/       # real builds, one subfolder per order id
  Demos/<prospect-or-client>/       # demo builds, same order-id naming
  Registry (Google Sheets)          # mirror of registry.csv
```

Rules: one folder per order; no stray files at the root; the order id appears
identically in the folder name, the flow name, and both registries. A delivery
is not complete until its local folder, Drive folder, and registry row all
exist and agree.

## Build gates

1. Scope approval (`order_scope_approved`) before any external build action.
2. Build on the provider MCP; validate before publish; demos stay unpublished
   unless the order explicitly asks for a live demo link.
3. Verify: run once with safe sample data (real) or demo fixtures (demo);
   capture the run receipt into `delivery-record.md`.
4. Archive: update local folder, Drive mirror, registry row; produce
   `workflow_delivery_record` (real) or `demo_delivery_record` (demo).

## Evidence kinds

- `order_brief`, `workflow_spec` — intake and scoping artifacts.
- `flow_receipt` — provider confirmation the flow exists/published.
- `workflow_delivery_record` — accepted business evidence for `workflows_delivered`.
- `demo_delivery_record` — accepted business evidence for `demos_delivered`.

## Hard rule — verify 100% before delivery

No demo or real workflow order is marked delivered until it has been **run end-to-end
through the real input path** and the produced result (and any save/persist step) is
confirmed:
- For form/UI triggers that cannot be driven by curl, exercise the AI/transform logic
  with an equivalent real input (e.g. a hardcoded sample fed through the same step) and
  confirm the output, then restore the live trigger reference.
- Any save/persist step (Drive, Sheet, email) must be confirmed to actually write —
  capture the resulting file/row/link as evidence. A step that reaches the provider but
  fails on permissions/scope is NOT verified: fix the connection and re-run.
- Capture the run receipt + any save artifact link into `delivery-record.md`.
