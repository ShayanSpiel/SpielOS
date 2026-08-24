---
name: department-runner
description: Run one SpielOS Department independently against a durable runtime-owned goal. Use when the user wants outbound or another production-ready Department without company-level Director orchestration.
---

# Department Runner

Use the shared runtime in `.agents/company/`; do not create channel-specific
state machines. Inspect the Department/workflow/agent catalog with
`python3 -B -m company catalog`
using `PYTHONPATH=.agents` and `PYTHONDONTWRITEBYTECODE=1`.

Create or select one measurable Department goal, then use `once`, `status`,
`approve`, `pause`, `resume`, and `report`. Preserve the four-stage contract and
surface every suspension. A completed unmet run with a valid next experiment
continues automatically; the next guarded action still parks. A Department supplies domain observation, diagnosis,
artifacts, guardrails, execution and measurement; the runtime owns transitions,
all goals, state, leases, approvals and events.

Every execution must preserve a typed run, hypothesis, Department version, config
snapshot, controlled and changed variables, evidence validity, decision, and
evaluation. A technical system test can validate machinery but cannot establish
market or positioning truth.

## Generic work-order execution

Do not require a host-specific agent file for an installed employee. The durable
work order is the complete portable execution contract.

1. List available assignments with `company tasks --status active`.
2. Claim exactly one with `company tasks WORK_ORDER_ID --claim HOST_WORKER_ID`.
   A claim is exclusive; never perform an order claimed by another host.
3. Read that order's `brief`, resolve its employee from `company catalog`, and
   load only the listed `skill_ids` and `connection_ids` needed for the step.
4. Produce only the requested evidence kinds. Preserve the Goal, Workflow, step,
   quantity, and completion conditions from the brief.
5. Complete atomically with
   `company tasks WORK_ORDER_ID --complete HOST_WORKER_ID --evidence JSON_ARRAY`.
   Completion links evidence to that exact order, closes it, and advances the
   Goal to its next real suspension.

One run-level approval covers ordinary actions in that run. Pause again only at
an explicit `approval` Workflow node or when the approved run scope materially
changes. Never invent approval points for employee or machine steps.

Never select `execution_mode: live` on the user's behalf. Never treat generated
copy or an executed action as evidence that the business goal was achieved.
