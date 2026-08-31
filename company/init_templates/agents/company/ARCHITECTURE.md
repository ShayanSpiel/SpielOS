# SpielOS clean core

SpielOS is a Goal-driven adaptive system. A Goal chooses which outcome to move;
everything below it makes the chosen Intervention work.

```text
Goal tree + Goal support DAG
            │
           Goal
            │
           Run ── OBSERVE → DECIDE → ACT → EVALUATE
                                    │
                              Intervention
                                    │
                              Resolution Cycle
                    execute / create / fix / retry / validate
```

## Relationships

The Goal tree is the human hierarchy and uses `Goal.parent_id`. The support DAG
is causal and uses `GoalEdge(relation="supports")`. Both reject cycles. A Goal
is always the same record; primary, supporting, and system-improvement Goal
subclasses do not exist.

## Runs and Resolution

A Run is one adaptive iteration, regardless of elapsed time. ACT persists one
bounded Intervention. Resolution owns Workflow execution and may repair Agents,
Skills, Connections, Workflows, Departments, or SpielOS itself. Local work does
not create another Goal and does not wake the Goal after every Workflow step.

Resolution has four outcomes:

- `CONTINUE_LOCAL`: more local work is needed.
- `RETURN_TO_GOAL`: EVALUATE has enough information.
- `ESCALATE_TO_GOAL`: the Goal-level decision is materially invalid.
- `ASK_USER`: context, authority, approval, or Goal ownership is missing.

## Durable causality

One SQLite database holds explicit subsystem tables. Domain queries live in
their subsystem repositories; `state.Database` owns connection lifecycle only.
Every WorkOrder and execution Evidence record retains `goal_id`, `run_id`, and
`intervention_id`, plus WorkflowRun and WorkOrder references where applicable.
This makes every meaningful action traceable to the outcome it served.

## Responsibility boundaries

| Package | Responsibility |
|---|---|
| `goals` | Goal tree and support DAG |
| `runtime` | Run stages and scheduling |
| `resolution` | Intervention execution, repair, retry, validation |
| `workflows` | Reusable definitions and durable WorkflowRuns |
| `work_orders` | Claimable exact units of Agent work |
| `agents`, `hosts` | Replaceable execution identity and transport |
| `skills`, `connections`, `departments` | Portable capability definitions |
| `evidence` | Immutable facts about what happened |
| `memory` | Owner, workflow, and strategy learning |
| `context` | Bounded decision projection |
| `observability` | Read-only health and causal traces |
| `state` | SQLite connection and schema plumbing only |

Dependencies point inward through these contracts. Goals do not import
Workflows or Agents. Hosts do not own Goal semantics. Departments are packages,
not runtimes.

## Living observability

The Observatory is a read-only projection, not a second runtime. It combines a
static map derived from the source contracts with live rows from the one SQLite
database. Goal hierarchy and `supports` edges remain separately identifiable on
the same canvas; Runs, Interventions, WorkflowRuns, WorkOrders, Evidence, and
Memory retain their causal relations.

Clean-core tables are the sole live authority as soon as they contain Goals.
Until then, persisted historical state is shown behind an explicit compatibility
boundary and is never merged with clean-core records. Coherence checks report
cycles, disconnected entities, duplicate capability names, blocked work,
unused definitions, missing template parity, and compatibility-only state so
the organism exposes drift instead of concealing it.

## Memory

Owner Memory is explicit durable direction and needs no Evidence. Workflow
Memory captures reusable execution learning. Strategy Memory captures what
moved a Goal. Workflow and Strategy Memory must cite Evidence from their causal
Run.

## Compatibility

The historical `runtime.loop.Runtime` remains a compatibility facade for
existing commands and persisted homes during the bounded data migration.
`runtime.engine.GoalRuntime` is the canonical clean-core control path. New
architecture code must depend on the subsystem contracts above, not on the
compatibility facade.
