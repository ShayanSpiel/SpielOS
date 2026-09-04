---
description: Approve one exact parked action
agent: director
---

Inspect the goal in `$ARGUMENTS` and show its exact parked action and what
the runtime is waiting for. When the owner approves, record it exactly:

    PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=.agents python3 -B -m company approve <goal_id> --note "<owner intent>"

If the parked Workflow step declares named approval keys, grant exactly those
keys with `--key <name>` (repeatable). One approval command grants the keys of
the current step; never invent another confirmation inside an already
approved step. For a multi-gate run the owner may instead grant the key for
the whole run with `--scope run` — the same key then satisfies every
remaining step of this run (a new run always asks again). On reject, leave
the action parked and confirm that nothing executed.
