---
title: Session archetypes (S1–S10)
audience: engine + LLM
status: canonical
---

# Session archetypes (S1–S10)

The 10 archetypes the engine uses to classify sessions and route content. **Banned in public posts** (`system/prompts/leak-guard.md`).

| # | Archetype | Description | Example |
|---|-----------|-------------|---------|
| S1 | System Build | Building a system, architecture, or workflow | "Built the session classifier" |
| S2 | Ship | Shipping a feature, product, or release | "Shipped /post v2" |
| S3 | Decision | Choosing X over Y, documented trade-offs | "Chose Obsidian over Notion" |
| S4 | Lesson | Something learned, abstracted into insight | "What 19 rejected drafts taught me" |
| S5 | Failure | Something broke, went wrong, got fixed | "I broke the engine. Here's how." |
| S6 | Client Work | Work done for/with someone else | "Installed the engine for a founder" |
| S7 | Research | Learning, reading, analyzing | "Analyzed 100 viral posts" |
| S8 | Tooling | Building tools, scripts, automations | "Wrote the session capture script" |
| S9 | Strategy | Planning, positioning, thinking | "Defined the new ICP" |
| S10 | Meta | Working on the engine, the system itself | "Refactored the engine" |

## The matrix (archetype × ICP layer × vertical × funnel)

| Archetype | ICP Layer | Vertical | Funnel | Primary Content | CTA | Offer Serve |
|-----------|-----------|----------|--------|-----------------|-----|-------------|
| S1 System Build | L3 (deep) | Builder-to-Lead | MOFU | Pillar + atomized | "DM me if you want this" | Demonstrates mechanism |
| S2 Ship | L1 (surface) | Content Automation | TOFU | X ship + casual LI | None | Shows the system is real |
| S3 Decision | L2 (mid) | Positioning & Offers | TOFU-MOFU | X decision + LI take | Soft: "reply FRAMEWORK" | Shows trade-off thinking |
| S4 Lesson | L2 (mid) | Any | TOFU-MOFU | X lesson post | Soft: "i wrote about this" | Builds trust |
| S5 Failure | L3 (deep) | Builder-to-Lead | TOFU | X thread + casual LI | None | Relatability |
| S6 Client Work | L3-L4 (deep→root) | Building in Public | MOFU-BOFU | Case study + pillar | "DM me for yours" | Direct proof of value |
| S7 Research | L1 (surface) | Any | TOFU | X thread + hook posts | None | Authority building |
| S8 Tooling | L2 (mid) | Content Automation | TOFU-MOFU | X dev log + ship post | Soft: "link in reply" | Shows sophistication |
| S9 Strategy | L4 (root) | Positioning & Offers | MOFU | Pillar + polished LI | "i help founders with this" | Addresses core tension |
| S10 Meta | L1 (surface) | Builder-to-Lead | TOFU | Casual update | None | Shows engine is alive |

## Offer presence by archetype

| Offer | Archetypes | Frequency |
|-------|-----------|-----------|
| **None** | S2, S5, S7, S10 | Always |
| **Soft** (implicit) | S1, S3, S4, S8, S9 | Default |
| **Direct** (named) | S6 | Case studies |

## Keyword index (used by `engine/selectors/classifier.py`)

See `system/rules.yaml §classifier.archetypes` for the keyword-to-archetype mapping.

## Reference

Original spec: `strategy/funnel.md` § Session Archetypes. This file is the **canonical summary** for the engine and LLM context injection.