---
description: Show the compact company snapshot or one goal
agent: director
---

Run this visible command exactly once:

`PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=.agents python3 -B -m company status $ARGUMENTS`

Treat its compact projection as authoritative. Report the company state, what
needs attention, active work, recent results, and any required user action in
plain business language. Do not rediscover routine state through `--help`, goal
lists, saved shell output, repository search, or conversation history. If the
snapshot exposes a genuine inconsistency or the user explicitly requests audit
detail, retain full autonomy to drill down with one goal ID, bounded history,
or `--raw`. Do not mutate state.
