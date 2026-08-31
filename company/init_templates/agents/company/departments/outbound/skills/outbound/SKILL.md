---
name: outbound
description: Operate SpielOS Outbound Department workflows across discovery, qualification, research, email, social DM drafting, permitted channel actions, replies, and metrics through the single company runtime.
---

# Outbound Department Operations

Use the shared runtime in `.agents/company/` as the only goal, loop, status,
approval, memory, and reporting authority. The `outbound` Department contains
email, social-prospect research, and DM-drafting workflows under
`.agents/company/departments/outbound/`. Private campaign inputs live in
`.spielos/data/outbound/`, credentials in `.spielos/.env`, and runtime ledgers
in `.spielos/state/outbound/`.

## Workflow

1. Discover candidates from permitted sources.
2. Deduplicate and create a `discovered` lead.
3. Qualify against `.agents/company/strategy/icp.md`.
4. Research one operative fact and its operational consequence.
5. Draft channel-specific content and validate it.
6. Place the lead in the channel queue only when ready.
7. Ask the channel adapter whether the action is permitted.
8. Execute the allowed action through the provider's supported surface.
9. Record the result, reply, opt-out, warning, or block.
10. Return evidence to EVALUATE; the persisted goal decides whether another
    cycle is required.

## Separation of responsibilities

- Discovery adds and enriches leads. It never sends.
- Qualification decides whether the lead is eligible. It never sends.
- Drafting creates content. It never sends.
- Adapters execute only actions supported by the channel and current policy.
- Metrics reports progress and safety signals.

Never use this skill to scrape platforms, bypass rate limits, disguise
automation, or bulk-send unsolicited social DMs. LinkedIn and X require
platform-specific policy checks; a browser surface is not permission to bypass
those rules.

Every outbound action must run through a persisted Department goal. Live email
requires both `execution_mode: live` in that goal and approval of the prepared
batch. The default is no execution mode, which blocks execution safely.

## Goal configuration

Use a rolling queue rather than a fixed research limit. A campaign may target
30 sends while maintaining 100 ready leads and a larger discovery pool. If the
queue falls below its threshold, discovery replenishes it. If no qualified
lead remains, the loop stops honestly instead of lowering the ICP standard.
