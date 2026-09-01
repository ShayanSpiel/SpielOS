---
name: outbound-email
description: Research and write highly specific SpielOS outbound emails and operate email goals through the guarded shared runtime. Use for cold-email research, copy, review, replies, or email campaign execution.
---

# Outbound Email

## Runtime authority

The research and copy rules below remain authoritative for email content. For
goal state, orchestration, approval, execution, evaluation, and reporting, use
`.agents/company/` through the `outbound` Department. Never invoke a channel
module directly.

From the repository root, operate email goals with:

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=.agents python3 -B -m company status GOAL_ID
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=.agents python3 -B -m company once GOAL_ID
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=.agents python3 -B -m company approve GOAL_ID
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=.agents python3 -B -m company report GOAL_ID
```

Never select `execution_mode: live` or approve a prepared batch for the user.
An unmet run with a valid next experiment continues automatically; the next
send still parks for approval. `company next` is only a manual escape hatch.

# Personal Cold Email + Sending Workflow

Three parts, one loop:

0. **ICP**: read `../../../company/strategy/icp.md` before any outreach. The
   Department-specific countries, tiers, and lead-flow rules live in
   `../../../company/departments/outbound/strategy.md`; they may not redefine ICP.

1. **Content**: research-first, one-person voice, personal cold emails (and DMs) that read like a specific human wrote them to one specific human.
2. **Sending**: the Outbound Department reads the master lead list
   (`.spielos/data/outbound/`) and acts through guarded provider adapters.
3. **Email Data**: the feedback loop. The Department pulls provider status for every sent email, scores the funnel against the persisted goal's metric and target, and produces a verdict plus one proposed next action. A valid next experiment continues automatically; the next send still parks for approval.

Use this skill for any SpielOS outbound email, DM, or follow-up, and for operating the Outbound Department.

---

## Part 1 — Content: The Personal Cold Email

### Rule 1: Research before writing. Always.

Never write from the spreadsheet. The spreadsheet gives you a name and a company; it does not give you a reason to write.

Research for 5-15 minutes per lead, looking at (most recent 6-12 months):

- Their LinkedIn profile and activity (posts, comments, rebrands, new roles, hires)
- Company site: about page, news, client lists, services page, team page
- Recent press, podcasts, talks, awards, launches
- Their own writing (newsletters, blogs, threads)

From everything you find, extract exactly ONE **operative fact**: a verifiable fact that has a consequence for how their business actually runs. Not a pile of impressive facts. One fact, with a consequence.

### Rule 2: Subject line

- 2-5 words (hard cap)
- Names the actual topic of the email, in the reader's vocabulary
- Never repeat the prospect's own words or phrase unless you add new meaning to it. Quoting their content back at them is echoing, not connecting: it tells them nothing.
- Test: does the subject alone tell the reader what this email is about? If it only makes sense after reading the body, it fails.

### Rule 3: Body structure

90-120 words target. Order:

1. **Warm opener** — one short sentence showing attention: "I've been reading about VisaAffix, and the thing that caught me was...". No fact stacking; the opener only shows you looked.
2. **Observation** — one promise or fact that caught you, attributed naturally ("the promise on your front page"). Max 2-3 supporting facts ("1,000+ cases, a small team, and rules constantly changing"). Boring = stacking research; cut anything that does not build the tension.
3. **Thought** — the consequence: "that's a hard promise to scale." Must be an inference from the fact, never an industry cliché.
4. **Who you are** — one plain line: "I build AI employees around repetitive knowledge work." For licensed or professional leads, position around their judgment: "In your case, I'd be curious about everything before the final human judgment." Never imply replacing the expert.
5. **Specific question** — grounded in their domain, shaped as "is X still done manually, or have you systemized it?" If it could be asked to any company in their industry, the thought is wrong.
6. **Conditional close** — "If part of that is still manual, I'd be happy to map it with you." The condition covers the wrong-hypothesis case, so no separate fallback question is needed. Only add the fallback ("What's the one thing you'd automate...?") when the specific question cannot carry the risk.

Short paragraphs (1-3 sentences). No bullets. No bold.

### Rule 4: One operative fact per email

One email = one operative fact + one consequence + one specific question + one fallback question + one offer. If research surfaces nothing with a consequence, do not write; move to the next lead. Writing anyway is how bullshit happens.

### Rule 5: No decorative facts

Every number and name must do work in its sentence: it must change the reader's understanding of their own situation. Impressive counts used as decoration get cut unless they carry the argument.

### Rule 6: Voice and language (hard bans)

- Never "my agency" — use "I". Never "every week" — use "this week".
- No em-dashes (—) anywhere in the email.
- Any URL in the email body must match the sending domain (spielos.xyz).
  No external links in the copy; reference pages by name instead ("your 14-day
  case study"). Mismatched-domain links are a spam trigger flagged by Resend
  (2026-08-08: EN-002 to E-Frontiers was flagged for an e-frontiers.ie link).
  Signature socials (LinkedIn, X) and spielos.xyz links are allowed.
- No filler sentences: "it shows", "exactly that", "for a reason". Every sentence must carry information about the reader's specific situation; anything else is cut.
- Forbidden words: leverage, streamline, optimize, elevate, empower, "AI-powered", "cutting-edge", "I wanted to reach out", "I'm reaching out", "As a [job title]", "hope this finds you well", "circle back", "2x output", "half the cost", "cost-effective".
- No fake scarcity: no "only 3 slots left" unless it is literally true and checkable.
- Never claim "2x"/"half" numbers you cannot back.
- One exclamation mark per email max (prefer none).
- No superlatives about the product ("game-changing", "revolutionary").

### Rule 7: Personalization test (run all three)

1. Delete the first sentence. If the rest could plausibly apply to 50 other leads, rewrite or abandon.
2. Delete the question. It must only be answerable by this specific lead.
3. Read it cold, as the recipient. Any sentence that does not carry information about their specific situation is filler. Cut it.

### Rule 8: Output format

Every email is delivered with all four fields:

```
TITLE: <subject line>

BODY:
<email body, 45-80 words>

ANGLE:
<the one operative fact and its consequence, in one sentence>

RESEARCH USED:
<bullet list of the specific facts found and where>
```

---

## Part 2 — Content: DM variant (LinkedIn / X)

Same research, compressed:

- 25-45 words
- No link in the first message (you can reference the page by name)
- One observation with a consequence, one question. Question ends the DM.
- No "hi", no "I hope", no em-dashes, no forbidden words
- Never pitch the product; pitch the observation
- Never echo the reader's own words; the message must name the topic, not repeat their content

Example shape:

```
<Observation about a fact from their post/site, with its consequence>

<Question that only makes sense given that fact>
```

---

## Part 3 — Operating the Outbound Department

### Layout

```text
.agents/company/departments/outbound/
  workflows/email/           # email domain operations
  workflows/social.py        # social prospect and DM evidence validation
  strategy.md                # execution details; references company ICP
  assets/                    # approved channel templates
.spielos/.env                # secrets + local config (gitignored)
.spielos/data/outbound/      # operational campaign inputs (gitignored)
  # Lead DB (EMAIL_LIST_PATH) = Desktop canonical SPIELOS_MASTER_LEADS_v4.xlsx, sheet "Master Leads"
.spielos/state/outbound/      # ignored ledgers and domain data
.spielos/artifacts/outbound/  # previews and reports
```

### Commands

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=.agents python3 -B -m company catalog
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=.agents python3 -B -m company status GOAL_ID
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=.agents python3 -B -m company once GOAL_ID
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=.agents python3 -B -m company approve GOAL_ID
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=.agents python3 -B -m company report GOAL_ID
```

### Behavioral rules

- Sends are throttled (`THROTTLE_SECONDS`, default 144s) and variant-rotated (`VARIANT_ROTATE`, default 10), block size `BLOCK_SIZE` (default 50).
- Already-sent lead_ids are skipped via `sent.json` + provider-side dedupe. Failed sends land in `failed[]` with error and timestamp.
- Free-tier limits to respect: Resend 100/day, Mailgun 100/day, Brevo 300/day; bounce rate under 2%; spam complaints under 0.08%. New-domain warmup ramps 30→60→100/day (owner override via `.env`).
- The templates in `templates.py` are the fallback; the researched personal emails from Part 1 are the default path (STRICT composition: no hook+pain research → skipped).

## Part 4 — Runtime behavior

The only loop is `GOAL → OBSERVE → DECIDE → ACT → EVALUATE` in the company
runtime. Prepare, validate, gate, review, send, and measure are internal
workflow steps recorded through `StageResult.step`; they are not phases in a
second state machine.

- **observe** — snapshot: totals, 48h window, gate verdict, queue depth, caps, providers.
- **decide** — the weakest link in fixed order: data problems → guardrails →
  reply rate → open rate (subject lever) → reply (cta lever). Produces ONE
  intervention with a hypothesis; knowledge store vetoes a lever whose last
  verdict was `reject`.
- **prepare** — composes per-lead emails in STRICT mode (unprepared leads
  skipped with a reason), dedupes domains within the batch, writes the preview.
- **validate** — mechanical rules (word limit, links, em dashes, segment fallback).
- **gate** — policy hard veto on a FRESH observation: bounce ≥2% or spam
  ≥0.08% on the 48h window halts everything (bounce downgraded only when
  `cohort_filters.skip_unverified` is active).
- **review** — company-runtime human approval.
- **execute** — paced sends: daily cap honored, provider rotation by headroom,
  provider-side dedupe, every send recorded with `feat_*` features.
- **evaluate** — waits for the evidence window, then MEASURE (verdict vs the
  previous batch, sample-aware: ≥20 per batch, ≥2pt movement), LEARN (verdict
  into the knowledge store), GOAL CHECK against the persisted goal target,
  and writes the journal/report.
- **completion** — the runtime records the completed run and, when the next
  experiment is valid, starts that Run automatically. The next send still
  parks for approval.

**Variables the Department may propose**:
- `subject` — subject bank rotation per segment (`rotate_subjects` lever)
- `cohort_unverified` — `skip_unverified=true` (the bounce lever)
- `providers` — provider order/health
- reserved: `body`, `cta` variant sets

**Operating rules for the AI:** never hand-edit variables mid-run. Put changes
in persisted goal configuration or accept the runtime's proposed next run.

### Lead generation + verification

1. **L2-verify the pool** using the bounded lead-verification workflow:
   SMTP-probe plausible leads from this box's IP (never sending infra). 250/251/252 →
   Verified, 550/551/553 → Invalid, 450/451/452/unreachable → stays Plausible.
2. **Ingest staging** through the lead-research workflow: dedupe against the
   master + sent log, ICP score, L1-verify, map Apollo verification fields.
3. **Notify research needed** — queue-empty holds tell the owner/AI; the
   assistant researches (Part 1 rules) and drops CSVs into staging.

Verification tiers (queue order): Verified → Catch-all; unverified → Publicly
listed; not deliverability-verified → **never** Bounced/suppressed or Invalid.
`cohort_filters.min_tier` (`data/control.json`) controls queue depth.

Bounce events auto-suppress in the master; a bounced address never re-enters
the queue.

Lead file flow: staging drops → bounded lead-research Workflow → canonical lead table
(`/Users/shayan/Desktop/Spiel Logos/Outbound/SPIELOS_MASTER_LEADS_v4.xlsx (sheet "Master Leads")`). Sources are tagged for cohort diagnosis.
