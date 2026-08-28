---
description: Approve one exact parked action
agent: director
---

Inspect the goal in `$ARGUMENTS` and show its exact parked action, artifact,
destination, scope, risk, and consequence. Map the owner's words to the runtime:
“approve this” is `per_action`, “approve this run” is `per_run`, and “everything
approved for this goal/until stopped” is `everything_approved` for the Goal and
its descendants. Record that exact scope and advance to the next real
suspension. Do not invent another confirmation inside an already approved scope.

When the pending notification includes `approval_interaction`, invoke the
native `question` tool with its separate Approve and Reject choices before
recording anything. Run its fallback command only after Approve. On Reject,
leave the action parked and confirm that nothing executed.
