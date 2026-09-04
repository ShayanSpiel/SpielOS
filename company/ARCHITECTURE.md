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
