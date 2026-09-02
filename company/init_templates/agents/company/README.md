# SpielOS

SpielOS is a local clean-core runtime for durable Goals.

[spielos.xyz](https://spielos.xyz) · `GoalRuntime` owns the persisted loop:
observe, decide, act, and evaluate. Departments are declarative packages;
Agents, Skills, Connections, Capabilities, and Hosts provide replaceable
execution declarations. Every material result is recorded as Evidence and can
inform owner, workflow, or strategy Memory.

## Talk to your Director

```sh
opencode    # or: codex
```

In **OpenCode**: run `/agents`, select the **Director** agent, and talk to
it — it already sees your company state.

In **Codex**: talk to the **Director** agent — it already sees your company
state.

The host injects a fresh, read-only company projection into every model
request; do not begin with a manual status probe.

## Commands

```sh
spielos status            # one Goal or the company snapshot
spielos overview          # the full company projection
spielos context           # the same context your host injects
spielos memory summary    # owner, workflow, and strategy memory
spielos profile list      # owner profile claims
spielos notifications list
spielos runner tick       # advance every ready Run once
spielos goal create --name "..." --owner director --metric ... --target ...
spielos approve <goal_id> --note "..." [--key legal]
spielos tasks             # open work orders
spielos update --dir .    # refresh this home (global CLI, after pipx upgrade)
```

Always run `update` through the global `spielos` command — it refreshes the
home from the installed release's templates. Running
`PYTHONPATH=.agents python3 -m company update` inside the home would try to
copy the home's own files onto themselves. `update` overwrites only the
vendored `.agents/` spine and host adapters; private `.spielos/` state and
user Departments under `.agents/company/departments/` are always preserved,
and stale files from older releases are pruned.

## Vocabulary

| Concept | What it is |
|---|---|
| **GoalRuntime** | The one durable control loop |
| **Goal** | A measurable outcome with an owner, metric, and target |
| **Department** | A declarative, Agent-owned capability package |
| **Workflow** | Ordered steps with declared evidence and approval keys |
| **Agent** | Performs claimed work orders through a Host |
| **Evidence** | Immutable proof attached to Goals and Runs |
| **Memory** | owner / workflow / strategy scopes only |
| **Approval** | Explicit owner keys; external actions park first |

A new home starts with no bundled Departments. Add clean declarative packages
only when their Goal, Workflow, Agent, Evidence, and approval contracts are
ready.
