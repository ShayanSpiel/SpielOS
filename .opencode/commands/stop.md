---
description: Stop SpielOS automation and optionally pause a goal
agent: director
---

Disable company automation first by running the runner stop command — there is
no plugin hook that does it for you:

    PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=.agents python3 -B -m company runner stop

This persistently disables durable company automation (no idle hooks, ticker,
or background supervision will start more work) until `/start` enables it
again. If `$ARGUMENTS` identifies a goal, pause that goal too. Do not advance,
retry, or start any work. Report what is stopped and explain that `/start`
resumes it.
