"""Outbound deterministic policy veto boundary.

The Department enforces policy but never defines it — the workflow owns
the rules (workflows/email/policy_rules.py). Two enforcement points:

  soft — OBSERVE includes the gate verdict in the snapshot; DECIDE never
         plans past a hard breach (it holds instead)
  hard — ACT/GATE re-runs the check on FRESH observation right before
         EXECUTE, because hours can pass between OBSERVE and ACT
"""


class Policy:
    def __init__(self, workflow):
        self.workflow = workflow

    def check(self, ctx, snapshot: dict) -> dict:
        """{ok, breaches, problems} — the single gate authority."""
        return self.workflow.policy(ctx, snapshot)
