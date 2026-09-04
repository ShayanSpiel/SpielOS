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
spielos memory add --scope workflow --claim "..." --evidence <id> --goal <id> --run <id>
spielos profile list      # owner profile claims
spielos notifications list
spielos runner tick       # advance every ready Run once
spielos goal create --name "..." --owner director --metric ... --target ...
spielos approve <goal_id> --note "..." [--key legal] [--scope run]
spielos tasks             # open work orders
spielos tasks <id> --complete <agent> --evidence '[...]' [--learning "claim"]
spielos layout            # audit the canonical layout for drift
spielos update --dir .    # refresh this home (global CLI, after pipx upgrade)
```

Always run `update` through the global `spielos` command — it refreshes the
home from the installed release's templates. Running
`PYTHONPATH=.agents python3 -m company update` inside the home would try to
copy the home's own files onto themselves. `update` overwrites only the
vendored `.agents/` spine and host adapters; private `.spielos/` state,
`opencode.json`/`AGENTS.md` owner edits, and every owner-created file in the
user layers (Departments, Skills, Capabilities, Connections, Strategy,
installed Agents, host agents/commands/plugins) are always preserved, while
stale files from older releases are pruned.

## Canonical layout

Company content lives in exactly these layers under `.agents/company/`:

| Layer | Contents |
|---|---|
| `departments/<id>/department.py` | one Department declaration per folder |
| `skills/<id>/SKILL.md` | one reusable Skill per folder |
| `capabilities/<id>/` | capability packages |
| `connections/` | connection registry and client modules |
| `strategy/` | canonical strategy documents |
| `agents/installed/` | installed worker Agents |

Never invent folders or files outside these layers; the Director is the host
agent prompt, not a Skill. Run `spielos layout` to audit drift.

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
