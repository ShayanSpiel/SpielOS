# SpielOS architecture

SpielOS has one durable control loop: `GoalRuntime`.

Goals are stored with their Runs, interventions, work orders, evidence,
approvals, notifications, workflows, and memory in the clean `core_*` SQLite
schema. The runtime advances one persisted stage at a time:

1. Observe evidence and applicable Memory.
2. Decide the next bounded intervention.
3. Resolve it through a Workflow and Agent work orders.
4. Evaluate the evidence and either complete the Goal or create its next Run.

Departments are declarations, never loops. A Department may declare clean
Workflows; Workflows declare ordered `WorkflowStep` values; Agents perform
claimed work orders through a Host. Connections and Skills are declarations
selected by those workflows.

Memory has exactly three scopes: owner, workflow, and strategy. Non-owner
Memory is evidence-backed and retains Goal and Run lineage.

The command surface always opens `CleanCommandRuntime`, which projects the
clean repositories for humans and host hooks; `company observe` renders the
read-only `observability` dashboard (health, goal progress, causal traces). A new home starts with zero
Departments and only the canonical clean schema.

Hosts are adapters, never a runtime dependency: OpenCode (plugin), Codex
(hooks), and Claude Code (hooks plus a one-line `CLAUDE.md` bridge to
`AGENTS.md`) each inject the same read-only projection on every request,
restore it after compaction, and surface pending attention in owner words.
Host adapter files ship in `.opencode/`, `.codex/`, and `.claude/`; every
path the release does not ship there is owner content preserved by
`spielos update`.

Evals are a Department-facing rail, not a runtime dependency: Departments
ship suites as `departments/<id>/evals.py` and their own workflow steps
consume the reports as evidence (e.g. a quality gate before a campaign
advances). The runtime core (engine, resolution, commands) never invokes
the eval subsystem — a home with no Departments ships and runs without
it.

Department portability is a repository import, not an archive: `company
export` writes a complete bundle-repository folder (manifest with spine
pin and closure file list, department package, dependency closure,
onboarding README with per-adopter paste-prompt blocks), and `company
import` validates (manifest, spine pin, closure, declaration against
the live contracts) before installing into the six owner layers only —
never the vendored spine, host trees, or settings, idempotent, with
owner files outside the bundle list untouched.
