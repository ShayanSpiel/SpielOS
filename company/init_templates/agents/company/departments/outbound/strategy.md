# SpielOS Outbound — Execution (implements the canonical ICP)

The buyer profile, exclusions, and positioning live in the canonical file:
**`../../strategy/icp.md`**. This file only contains what the Department needs on top of it —
target countries, verification tiers, and lead flow. Never redefine the buyer here.

## Target countries

United Kingdom · United Arab Emirates · Canada · Australia · United
States · Germany · France · Netherlands · Sweden · Norway · Denmark ·
Finland · Ireland · Saudi Arabia · Qatar.

## Never targets (matches canonical exclusions, regardless of score)

- AI companies / AI agencies / AI consultancies / agent builders
- Software / development agencies and studios (they build — not buyers)
- Open-source / coding-agent audiences, harness builders, technical founders
- Enterprise (>250 employees)
- Tiny pre-revenue startups and creators with no operational workload
- Free-mail domains (gmail/yahoo/outlook/hotmail/proton) — personal mail,
  not a business buyer

## Lead quality ladder (the verification tiers)

| Tier | Meaning | Queue priority |
|---|---|---|
| Verified | Apollo "Verified" + MX, or L2 SMTP probe accepted (250/251/252) | 0 — send first |
| Catch-all; unverified | Domain accepts everything; mailbox unknowable | 1 |
| Publicly listed; not deliverability-verified | Real MX, non-disposable; may open/click (proven); probe pending | 2 |
| Bounced; suppressed | Provider bounce event, or L1 fail (syntax/disposable/no-MX) | NEVER |

The Department never sends to the bottom tier. Bounce events auto-downgrade
(sync-bounces); L2 probing upgrades in idle time.

## Scoring (deterministic, in scripts/leads.py)

Base 40 · segment present +15 · targeted segment +25 · employees 5–50 +20
(51–250 +12, <5 +4, >250 −15) · revenue ≥ $1M +15 (revenue < $1M −10) ·
target country +10 · ranked title up to +20 · research hook +10.

- ≥70 → "Ready to personalized"
- ≥45 → "Routing email only"
- else → "Backup; wait"

`scripts/leads.py` is the only place scoring is implemented; this file and
`../../strategy/icp.md` are its specification.

## Lead flow

1. Research (assistant websearch + site visits, or owner Apollo export)
   → CSV into `scripts/leads/staging/`
2. Daemon ingests (≤30 min): dedupe vs master+log, score, L1-verify,
   Apollo verification fields mapped → tier
3. Queue consumes tiers in order; idle time = L2 probe time
4. Bounce events downgrade the email forever

## Reply feedback & lead classification (v1 — 2026-08-11)

Every human reply is classified and fed back into the master and future
research. Reply ledger is `.spielos/state/outbound/metrics.json` -> `replies`;
per-lead feedback is appended to the row `Notes`; durable knowledge lives in
`.agents/company/assets/outbound-feedback.md`.

Classification fields per reply: `kind` (reply|auto|test), `outcome`
(accepted|rejected|interested|awaiting), `reason` (verbatim owner/lead
language), `company_type` (owner-confirmed if it corrects the segment).

Research rules for every new lead (apply at qualification, write into the row):
1. **Company type precision** — record the exact deliverable type (e.g.,
   software agency vs marketing agency vs recruitment firm). Segment must
   describe what the company sells, owner-confirmed where available.
2. **External-solution readiness signal** — capture in `Need / Buying
   Signals` any evidence of openness to external/tooling solutions
   (job ads for internal automation, "we use tool X", mentioning pain with
   current process). No evidence = unproven; the email may carry the
   objection-handling variant.
3. **Rejection classes** (for reply classification):
   - R1 "not looking for an external solution at the moment" — in-house
     capability / timing objection (Web Katalyst 2026-08-11)
   - R2 generic pass / no reason given
   - R3 budget / cost objection
   - R4 wrong fit (segment mismatch)
   - R5 follow-up later / revisit
4. **Lead editor in Notes** after any reply: outcome + class + date, so the
   master carries feedback into re-qualification.
5. **Manual-loop hook (locked 2026-08-15)** — every lead gets ONE researched, named
   operational loop in `research_fact` (what the loop is, where it runs, who does it
   by hand). This is the proven converting hook: "Manual loop at SDG Accountant"
   (EN-1358, researched-personal) produced a qualified reply 2026-08-14 —
   "Can you build it out using our Ring Central?" (interested, accounting &
   bookkeeping, owner-confirmed). Continue defaulting the researched single-loop
   pain paragraph; keep subject family "Manual loop / One workflow / Repetitive work
   at {company}" in the generic-workflow bank.

## OOO auto-reply handling (v1 — 2026-08-11)
1. An out-of-office auto-reply CONFIRMS deliverability: the mailbox is live.
   Upgrade the row `Email Status` to Verified (evidence: OOO reply received).
2. Record in the row `Notes`: OOO date, return date if stated, and any named
   alternative contact (phone/email) from the OOO text.
3. A NAMED alternative with a published email becomes a new verified lead
   (source: OOO + company page; score normally; EN-1279 Josh Barlow precedent).
4. ROLE inboxes (accounts@, info@...) from OOO texts are OUT OF POLICY —
   do not create leads from them; surface to the owner instead.
5. If the OOO gives a return date and the contact is back, flag the row for
   follow-up re-send (no re-send route exists yet; owner replies in-thread).

## Deliverability hardening (v1 — 2026-08-11)
Research must treat "Verified" as necessary-not-sufficient:
1. Prefer addresses on corporate domains with established MX (Google/Outlook/
   Microsoft-hosted) and company-age signals.
2. firstname@ mailboxes on small/startup domains bounce at ~20% even when
   published + MX-verified — flag them as higher-risk in `Contactability`.
3. Every bounce is suppressed in the master immediately (status
   "Bounced; suppressed") so the gate's suppression downgrade keeps the
   window green.
4. Batch sizing assumes ~20% hard-bounce attrition in the verified class.

## PROVEN PATTERN — the only sendable pattern (locked 2026-08-18, goal-40946f9dab)

Evidence (see `.agents/company/assets/outbound-feedback.md` and
`outbound-proof-2026-08-15-sdg-accountant.md`):

| Lead | Source | Content | Result |
|---|---|---|---|
| EN-1358 SDG Accountant | Director web research w/ source URL (accountingtoronto.ca/teams/sami-ghaith/) | researched-personal: "Manual loop at SDG Accountant" + named loop pain + soft CTA | **Interested reply** ("Can you build it out using our Ring Central?") |
| EN-1157 Sigma Recruitment | Company website (sigmarecruitment.co.uk) | researched-personal: "Staffing loop at Sigma Recruitment" + shortlist-stage pain + "Reply map" CTA | **Accepted reply** ("happy to have a demo") |
| 324-run (EN-14xx/15xx/18xx bulk) | GCA framework public supplier contacts (one bulk list) | segment-generic pain + "named framework contact" hook | **0 replies, 3 clicks, 51% opens** |

The bulk-framework run proves opens measure deliverability, not interest:
51% of unverified bulk leads opened and still produced zero replies. The
replies came only from leads with a per-lead researched operational loop.

### RULE 1 — Source pattern (mandatory)
1. Every sendable lead must come from a researched source: **company website
   review** or **Director/lead-researcher web research with a recorded source
   URL**. Record the source and URL in the lead row (`Source`, `Source URL`).
2. **Bulk public framework/supplier lists are NOT a sendable source by
   themselves.** If a bulk list is used at all, every lead from it must clear
   the full per-lead research gate (named contact, researched loop, pain,
   hook) before it can enter the ready queue — no exceptions.
3. Prefer **personal inboxes** of the owning operator (Founder/Managing
   Director/CEO/COO). Role inboxes (info@, accounts@, sales@) are not the
   proven buyer surface for this pattern.

### RULE 2 — ICP pattern (mandatory)
1. The proven buyer is an **owner-operator in an established service
   business** (accounting/bookkeeping, recruitment & staffing, and the other
   canonical ICP segments) with a **named, observable manual operational
   loop** — the loop must be written into the lead's `research_fact` and pain
   hypothesis before sending.
2. Sales-style bulk-list contacts without a researched operational loop are
   **not qualified**, regardless of score.
3. Enterprise (>250) and tiny/no-workload leads remain excluded (canonical).

### RULE 3 — Content pattern (mandatory — researched-personal is the only variant)
1. **Variant:** `researched-personal` ONLY. No segment-generic copy, no
   generic "Hi {company} team" greeting for named contacts, no
   "named framework contact" opener.
2. **Subject:** name the lead's actual loop, from the
   generic-workflow/recruitment-workflow subject banks, per segment: proven
   families "Manual loop at {company}" / "Staffing loop at {company}" /
   "One workflow at {company}" / "Repetitive work at {company}".
3. **Body:** greeting to the NAMED contact · one researched pain paragraph
   naming THAT company's loop · supervised-agents offer · soft CTA ("happy to
   map it with you") · founder sign-off.
4. `content_variables.json` subject rotation stays WITHIN the proven families;
   do not rotate into generic "stage" subjects for unproven segments.

### RULE 4 — Hard non-sendable gate
A lead is NON-SENDABLE (skip, "unprepared") until it has ALL of:
`research_fact` (named loop), `pain_hypothesis` (that loop's consequence),
`personalization_hook` (owner-relevant fact), named contact, personal email,
and a recorded source + source URL. The prepare_batch stage must skip any
lead missing any of these — this is the rule, not a request.
