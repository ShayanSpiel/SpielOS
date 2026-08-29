---
name: system-improvement
description: Execute a bounded SpielOS runtime or Workgroup repair created by the Director, with allowed-file scope, acceptance tests, versioning, and return to the originating Goal.
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

For a new Workgroup package, require its purpose, metrics, Workers, Worker-owned
Workflows, declared evidence, and exact allowed paths. Validate the package
before editing and prove catalog discovery plus a clean-home install before
recording version `1.0.0` or later.
