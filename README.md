# SpielOS

SpielOS is a local clean-core runtime for durable Goals.

```sh
pipx install spielos
spielos init --dir my-company -y
cd my-company
spielos
```

`GoalRuntime` owns the persisted loop: observe, decide, act, and evaluate.
Departments are optional declarative packages; Agents complete bounded work
orders through declared Hosts, Skills, and Connections. Evidence, approvals,
notifications, and owner/workflow/strategy Memory are stored locally in the
canonical `core_*` schema.

Useful commands:

```sh
spielos status
spielos overview
spielos context
spielos memory summary
spielos profile list
spielos runner tick
spielos notifications list
```

Upgrade an existing home after `pipx upgrade spielos`:

```sh
spielos update --dir /path/to/home
```

For source development, run:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -B -m unittest company.tests.test_clean_core_acceptance
```

See [the architecture](company/ARCHITECTURE.md) for the clean-core contract.
