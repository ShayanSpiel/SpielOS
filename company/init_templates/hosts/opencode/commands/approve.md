---
description: Approve one exact parked action
agent: director
---

Inspect the goal in `$ARGUMENTS` and show its exact parked action, artifact,
destination, scope, risk, and consequence. This command is approval only for
that displayed action. Record it, advance to the next real suspension, and do
not approve later actions automatically.

When the pending notification includes `approval_interaction`, invoke the
native `question` tool with its separate Approve and Reject choices before
recording anything. Run its fallback command only after Approve. On Reject,
leave the action parked and confirm that nothing executed.
