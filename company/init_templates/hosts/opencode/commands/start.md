---
description: Start or resume a SpielOS goal
agent: director
---

Enable company automation first by running the runner start command — there is
no plugin hook that does it for you:

    PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=.agents python3 -B -m company runner start

This re-enables deterministic Runner advancement. Then treat `$ARGUMENTS` as either a Goal ID to resume or
a business outcome to create. Inspect persisted state, start exactly one
appropriate Goal or proposed next run, and advance only to its next real
approval, evidence wait, blocker, or completion.
