---
name: workgroup-runner
description: Run one SpielOS Workgroup independently against a durable runtime-owned Goal.
---

# Workgroup Runner

Use the shared runtime in `.agents/company/`. A Workgroup supplies Worker-owned
workflows; it never owns Goal routing, approvals, or another control loop.

1. Start from the exact persisted Goal, Workgroup, Workflow, and work-order
   assignment supplied by the Director/runtime. Never load the full company
   catalog at startup and never select a Goal from it. If any assignment field
   is missing, surface that bounded contract gap instead of exploring unrelated
   Workgroups.
2. Advance only that persisted runnable work with `company runner tick GOAL_ID`.
3. List assignments with `company tasks --status active` and claim exactly one
   durable work order with the declared Worker identity.
4. Load only its declared skills and connections, produce only accepted
   evidence kinds, and complete the exact work order atomically.
5. Surface every approval, owner question, failure, and evidence gap. Never
   infer permission for external actions.

Preserve the typed run, hypothesis, config snapshot, controlled and changed
variables, evidence validity, decision, and evaluation. Technical validation
proves machinery only; it cannot establish a market conclusion.
