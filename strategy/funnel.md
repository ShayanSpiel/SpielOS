---
title: Funnel
type: concept
tags: [engine, spec, routing]
created: 2026-06-11
updated: 2026-06-21
confidence: high
status: living — engine-canonical
sources: [content/sessions/2026-06-06-corpus-analysis.md, content/sessions/2026-06-07-content-system-build.md, content/sessions/2026-06-09-strategy-layer-build.md]
aliases: [funnel-and-matrix]
---

# Funnel

The pipeline that walks a technical founder from "I don't know this exists" to "I want the Spiel Engine." Every session produces content. That content is classified into a funnel stage. Each funnel stage moves the ICP closer to the offer.

**Engine priority tier:** 2 (Routing). Overridden by Tier 1 (Runtime). Overrides Tier 3 (Targeting) and Tier 4 (Output).

**The S1–S10 session archetypes live in `strategy/archetypes.md` (the canonical engine-internal labels). The funnel mechanics live here. The matrix at the bottom is funnel × archetype, so it stays here as a routing reference — but the archetype column itself is sourced from `archetypes.md`.**

> **Public-facing label:** Awareness → Consideration → Conversion.
> TOFU/MOFU/BOFU are internal engine labels. Never expose them in drafts.

---

## The 4 Strategic Questions (Engine Pre-Routing)

Run these 4 questions in order BEFORE any content is produced. Each question is a gate:

1. **Who is this for?**
   - **IF** session does not target the ICP (see [[icp]]) → route TOFU-only or SKIP
   - **IF** session targets the ICP → proceed to Q2

2. **What problem layer does it hit?**
   - **IF** L1 (surface) → route TOFU
   - **IF** L2-L3 (mid-deep) → route MOFU
   - **IF** L4 (root) → route MOFU-BOFU

3. **What funnel stage does it feed?**
   - Assign CTA per the matrix below.

4. **Does it serve the offer?**
   - **IF** no AND session is L1 → output = SKIP (not every session needs a post)
   - **IF** yes → classify as demonstrative/proof/authority per the matrix

---

## The Funnel

```
TOFU (Unaware → Problem-aware)
  │
  ▼
MOFU (Problem-aware → Solution-aware)
  │
  ▼
BOFU (Solution-aware → Most-aware → Purchase)
  │
  ▼
Post-Purchase (Delivery → Success → Referral)
```

### Funnel Distribution

| Stage | % of Content | Offer Presence |
|-------|-------------|---------------|
| TOFU | 40% | None |
| MOFU | 40% | Soft CTA |
| BOFU | 15% | Full pitch |
| Post-Purchase | 5% | Referral |

The funnel is weighted toward TOFU + MOFU. Most of your audience is at those levels. BOFU content only works when the audience has already walked through TOFU and MOFU.

### Stage 1: TOFU — Top of Funnel

**Objective:** Make the ICP aware that their expertise CAN generate leads without becoming a "content creator."

**Schwartz levels:** A1 (Unaware) → A2 (Problem-aware)

**Who reads this:** Someone who has never thought about a content system. They build. They ship. They don't market.

**What they need to feel:** "Wait. There's a way to do this that doesn't require being a creator? I want to know more."

**CTA:** None. Follow. That's it.
**Offer pitch:** Zero. If you pitch an offer at TOFU, you lose the reader.
**Success metric:** Scroll stop. Follower. Profile click. Not a sale.

### Stage 2: MOFU — Middle of Funnel

**Objective:** Show the mechanism. Make the ICP see that the system is real, specific, and buildable.

**Schwartz levels:** A2 (Problem-aware) → A3 (Solution-aware) → A4 (Product-aware)

**Who reads this:** Someone who knows they have a content/marketing problem. They've tried posting. It didn't work.

**What they need to feel:** "This is the system I need. I can see how it works."

**CTA:** Soft. "DM me if you want the framework." "Reply FRAMEWORK."
**Offer pitch:** Soft. Reference the offer without selling it.
**Success metric:** DM. Reply. Link click. "Tell me more."

### Stage 3: BOFU — Bottom of Funnel

**Objective:** Convert. The reader understands the problem, sees the solution, and is ready to decide.

**Schwartz levels:** A4 (Product-aware) → A5 (Most-aware)

**Who reads this:** Someone who has followed for weeks. Read multiple posts. Seen the system in action.

**What they need to feel:** "The price is fair. The guarantee removes the risk. I should do this."

**CTA:** Hard. "Reply ENGINE for the application." "Buy at the link."
**Offer pitch:** Full. Stack, guarantee, scarcity, CTA.
**Success metric:** Application. Purchase. Booking.

### Stage 4: Post-Purchase

**Objective:** Deliver, delight, get referrals.

**CTA:** Referral. "If you know another technical founder who needs this, send them my way."

### Funnel Health Checks

| Signal | Healthy | Needs Attention |
|--------|---------|----------------|
| TOFU followers/week | Growing | Flat or declining |
| MOFU DMs/week | 3+ | 0-1 |
| BOFU applications/month | 3+ | 0-2 |
| TOFU → MOFU drop-off | <70% | >70% |
| MOFU → BOFU drop-off | <80% | >80% |

These are tracked in `content/conversions.md`.

### Public vs Internal Labels

| Internal Label | Public Label | What It Means |
|---------------|-------------|---------------|
| TOFU | Awareness | Showing the existence of a better way |
| MOFU | Consideration | Explaining how the system works |
| BOFU | Conversion | Proving it works and offering it |

**Rules:**
- Awareness content: No CTA. Just the post.
- Consideration content: Soft CTA. "DM me", "i wrote about this".
- Conversion content: Hard CTA. "Apply here".
- Never expose funnel percentages, stage names (TOFU/MOFU/BOFU), or procedural gating in public-facing content.

The Architecture Leak gate (kill-on-second-strike) that enforces this label map is in `system/prompts/leak-guard.md` (mechanical: `system/rules.yaml §architecture_leaks`).

---

## The Funnel × Archetype Matrix

Every session archetype gets classified into:

1. Which ICP problem layer it hits (see [[icp]])
2. Which content vertical it belongs to (see §Content Verticals below)
3. Which funnel stage it feeds
4. Which CTA it carries
5. Whether and how it serves the offer (see [[offer]])

**The full archetype list (S1–S10) lives in `strategy/archetypes.md`. The matrix below maps each archetype to its funnel routing.**

| Archetype | ICP Problem Layer | Vertical | Funnel Stage | Primary Content | CTA | Offer Serve |
|-----------|------------------|----------|-------------|----------------|-----|-------------|
| S1. System Build | L3 (deep) | Builder-to-Lead System | MOFU | Pillar blog + atomized X/LI | "DM me if you want this" | Demonstrates the mechanism. Pre-sells the engine. |
| S2. Ship | L1 (surface) | Content Automation | TOFU | X ship post + casual LI | None | Shows the system is real. Builds authority. |
| S3. Decision | L2 (mid) | Positioning & Offers | TOFU-MOFU | X decision post + LI take | Soft: "reply FRAMEWORK" | Shows trade-off thinking. |
| S4. Lesson | L2 (mid) | Any | TOFU-MOFU | X lesson post | Soft: "i wrote about this" | Builds trust. Shows depth. |
| S5. Failure | L3 (deep) | Builder-to-Lead System | TOFU | X thread + casual LI | None | Relatability. "They're like me." |
| S6. Client Work | L3-L4 (deep→root) | Building in Public as Lead Gen | MOFU-BOFU | Case study (LI/X thread) + pillar | "DM me for yours" | Direct proof of value. |
| S7. Research | L1 (surface) | Any | TOFU | X thread + hook posts | None | Authority building. |
| S8. Tooling | L2 (mid) | Content Automation | TOFU-MOFU | X dev log + ship post | Soft: "link in reply" | Shows system sophistication. |
| S9. Strategy | L4 (root) | Positioning & Offers | MOFU | Pillar blog + polished LI | "i help founders with this" | Addresses the core tension. |
| S10. Meta | L1 (surface) | Builder-to-Lead System | TOFU | Casual update | None | Shows the engine is alive. Transparent. |

### How to Read the Matrix

1. Identify the archetype (S1-S10) — see `strategy/archetypes.md`
2. Read the row
3. Classify the content into the assigned funnel stage
4. Apply the assigned CTA
5. If Offer Serve says "Demonstrates mechanism" → reference the engine implicitly
6. If Offer Serve says "Direct proof" → mention the offer explicitly
7. If Offer Serve says "Builds authority" → no offer, no CTA

### Offer Presence by Session Type

| Offer Presence | Session Archetypes | Frequency |
|---------------|-------------------|-----------|
| **None** | S2, S5, S7, S10 | Always for these archetypes |
| **Soft** (implicit reference) | S1, S3, S4, S8, S9 | Default. Only explicit if reader asks. |
| **Direct** (offer named) | S6 | Case studies mention the engine by name. |

### Frequency of Offer-Touching Content

Per the 1-in-5 rule:

| Content Type | Offer Touches | Of Which Direct Pitches |
|-------------|--------------|----------------------|
| All content | 1 in 5 | 1 in 10 |
| S6 (client work) | Every time | Every time (direct) |
| S1 (system build) | 1 in 3 | 1 in 6 |
| S9 (strategy) | 1 in 3 | 1 in 6 |
| Everything else | None | None |

### What NOT to Map

Sessions that are purely personal, purely technical (code internals), or purely observational → TOFU → no offer → move on.

### Cadence

**Per session.** No daily-post rule. No minimum. No maximum.

TOFU content: every session that produces something.
MOFU content: at least 1 pillar or thread every 1-2 weeks.
BOFU content: at least 1 client showcase or offer post every 2-3 weeks.

### Surface Strategy

| Surface | Role in Funnel | Frequency |
|---------|---------------|-----------|
| GitHub repo | Entry layer (open-source). Developer adoption, credibility. | Per repo push |
| X | Fast awareness. TOFU-heavy. MOFU threads. | 1-3 per session |
| LinkedIn | MOFU-heavy. Stories, frameworks, case studies. | 2-3 per week |
| Blog (pillar) | MOFU-BOFU. Deep mechanism, full methodology. | 1 per 1-2 weeks |
| DM | BOFU. Conversion. | Per inbound inquiry |

Character limits: see `system/rules.yaml §char_limits` and `strategy/voice.md §Character Limits`.

### The 1-in-5 Rule (Deterministic)

- **OF** all drafts in a 30-day rolling window, EXACTLY 1/5 may carry an offer reference.
- **OF** those offer-touching drafts, EXACTLY 1/2 are direct pitches (so 1/10 of all drafts are direct).
- **IF** archetype ∈ {S2, S5, S7, S10} → direct pitches FORBIDDEN.
- **IF** stage is TOFU → CTA MUST be NONE.

### The 4 Content Verticals

| Vertical | Focus | Funnel Stage | Offer Alignment |
|----------|-------|-------------|----------------|
| **Builder-to-Lead System** | How technical founders can generate leads without becoming marketers | MOFU-BOFU | Direct — shows the mechanism |
| **Content Automation & AI Agents** | The tech layer — Obsidian, agents, workflows, /post engine | TOFU-MOFU | Indirect — shows sophistication |
| **Positioning & Offers** | How to define ICP, craft offers, price, and message | TOFU-MOFU | Indirect — shows strategic depth |
| **Building in Public as Lead Gen** | The practice itself — why it works, how to do it | TOFU | None — awareness only |

---

## See Also

- [[icp]] — the audience this funnel walks through
- [[offer]] — the offer the funnel feeds toward
- [[positioning]] — the one-line positioning
- [[voice]] — the voice that speaks to this funnel
- `strategy/archetypes.md` — the S1–S10 archetype labels
- `strategy/methodology.md` — the methodology that produces the sessions
- `strategy/corpus.md` — canonical voice examples
