---
name: system-improvement
description: Execute a bounded SpielOS runtime repair or new-Department build created by the Director, with allowed-file scope, acceptance tests, versioning, and return to the originating goal. Use when a persisted system-improvement goal is approved and waiting for a coding executor.
---

# System Improvement

Read the persisted goal, run, and change task before editing anything. The task
must specify `change_kind`, owner, problem or capability, allowed files,
acceptance commands, version before, and target version.

1. Refuse an unbounded or incomplete task.
2. Modify only `allowed_files`. Do not opportunistically refactor.
3. Preserve the originating business hypothesis and controlled variables.
4. Run every acceptance command exactly as recorded.
5. Record failure honestly if any acceptance command fails. A failed
   acceptance stays failed; the next try is a new task on the same Goal
   and allowed files, not a rewrite of the failed task.
6. On success, call `company change complete` with the actual test evidence.
7. Mark deployed only after deployment actually happened.
8. Return control to the originating run. Never convert machinery evidence into
   a market or positioning conclusion.

The business run remains suspended or contaminated during this work. Never
silently resume it with different business variables.

For `change_kind: create_department`, also require `department_spec` with purpose,
supported metrics, configuration contract, external actions, approval points,
evidence sources, and acceptance behavior. Use `from_version: new`, implement
the shared four-stage Department contract, add contract tests, and prove catalog
discovery before recording version `1.0.0` or later. A new Department is a durable
business capability, not a renamed prompt or subagent.
