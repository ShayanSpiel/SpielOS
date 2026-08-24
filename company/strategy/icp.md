# SpielOS Ideal Customer Profile (canonical)

Single source of truth for the customer. Every skill, outbound rule, lead score, and
piece of site copy reads from this file — never restate or reinterpret the ICP in
another file; reference this one.

Supersedes all earlier ICP definitions: the technical-founder ICP, the
Session-as-Content ICP, and any profile centered on developers, AI founders, or
harness builders. Owner directive 2026-08-08.

---

## Who it is

Established online businesses and service providers that already have real customers,
an active website/product, and a working sales or delivery funnel — but are doing too
much repetitive knowledge-work by hand. They have high-volume operational workflows
(intake, delivery, support, reporting, scheduling, triage,
bookkeeping runs, reconciliations, payroll, filing) where replacing or
augmenting manual work with AI agents meaningfully reduces cost, speeds delivery, or
doubles throughput. Typically **$1M–$25M+ annual revenue**.

Main business types:

- Ecommerce brands
- Marketplaces
- Travel companies
- Non-AI agencies
- Consultancies
- Coaches / education businesses
- Online service businesses
- Accounting & bookkeeping firms
- Product businesses / SaaS with a clear operational workflow to automate

**Buyer:** the person who owns the operation and the money — owner, CEO, COO, or
senior operator. Technical expertise is neither required nor assumed.

**Positioning idea:** businesses that already work, but are doing too much repetitive
work manually — not startups looking for "an AI idea."

---

## Who it is NOT

The exclusions are the filter that keeps everything honest. A prospect matching any
bullet below is never a target, regardless of score:

- **AI founders** — building AI products themselves; competitors, not buyers
- **AI agencies** — they sell AI services; they are channels or competitors, never buyers
- **Agent builders** — people who build agents for a living or as a hobby
- **Developers / technical builders** — people whose primary interest is building their own harness; they have opinions about architecture, not a budget for one
- **People whose main interest is building their own harness** — open-source / coding-agent enthusiasts convinced they will build the next OpenAI themselves (Claude Code, Codex, Cursor users with an opinion)
- **Open-source / coding-agent audiences** — power users who will never pay for a system they believe they can build
- **Tiny pre-revenue startups** — no real customers, no funnel, no money, no repetitive workload worth automating
- **Random creators with no meaningful operational workload** — nothing to automate means nothing to sell
- **Companies with no obvious high-volume workflow** — no repetitive work to replace or augment

---

## Operational notes

- Behavioral profile is identical in English and Persian. The Persian market is served
  through the site's FA mirror; it is the same buyer, not a different one.
- Outbound execution details (target countries, verification tiers, lead flow, scoring)
  live in `.agents/company/departments/outbound/strategy.md`, which implements this profile and nothing
  more.
- Buyer-fit proof lives in `.agents/company/assets/` (outbound-proof files); listed
  segments are validated by real owner-operator replies.
- The site's published copy must always speak to this buyer: an operator solving
  repetitive work for an established business — never a technical founder building a
  harness.

## Validated buyer pattern (proof, locked 2026-08-18 — goal-40946f9dab)

The proven converting buyer is an **owner-operator (Founder / Managing
Director) at an established service business with a named, observable manual
operational loop** — validated by two qualified real replies:

- EN-1358 SDG Accountant — accounting & bookkeeping (owner, Canada) —
  interested, "Can you build it out using our Ring Central?" (proof:
  `.agents/company/assets/outbound-proof-2026-08-15-sdg-accountant.md`)
- EN-1157 Sigma Recruitment — recruitment & staffing (owner, UK) — accepted,
  demo request.

By contrast, 324 emails from a bulk framework contact list (same segments,
51% open rate) produced 0 replies — the buyer is NOT "a name on a list"; it
is the operator who owns a manual loop. All future outbound qualification and
site copy must hold this pattern. Execution rules: Outbound Department
strategy PROVEN PATTERN (RULES 1–4).
