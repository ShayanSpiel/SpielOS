---
description: Start or resume a SpielOS goal
agent: director
---

Enable company automation first by running the runner start command — there is
no plugin hook that does it for you:

    PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=.agents python3 -B -m company runner start

This re-enables durable automation and restarts the background supervisor if it
is not already running. Then treat `$ARGUMENTS` as either a goal ID to resume or
a business outcome to create. Inspect persisted state, start exactly one
appropriate goal or proposed next run, and advance only to its next real
approval, evidence wait, blocker, or completion.
