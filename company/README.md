# SpielOS

SpielOS is a clean, durable Goal runtime.

`GoalRuntime` owns the control loop. Departments are declarative packages;
Agents, Skills, Connections, Capabilities, and Hosts provide replaceable
execution declarations. Every material result is recorded as Evidence and can
inform owner, workflow, or strategy Memory.

## Quick start

```sh
spielos init --dir my-company -y
cd my-company
spielos
spielos status
spielos overview
spielos context
spielos memory summary
spielos profile list
spielos runner tick
spielos notifications list
```

## Upgrade an existing home

```sh
pipx upgrade spielos
spielos update --dir /path/to/home
```

`update` overwrites only the vendored `.agents/` spine and host adapters;
private `.spielos/` state and user Departments under
`.agents/company/departments/` are always preserved.

A new home starts with no bundled Departments. Add clean declarative packages
only when their Goal, Workflow, Agent, Evidence, and approval contracts are
ready.
