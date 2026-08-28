# SpielOS — Worker-owned AI Company Operating System

SpielOS is an open-source local harness for running durable company work with AI: one Director owns the Goal loop, workers complete bounded workflows, and every approval, hand-off, and result is persisted on disk.

```
GOAL → OBSERVE → DECIDE → ACT → EVALUATE
```

## Install

```sh
pipx install spielos && spielos init --dir /your/chosen/folder
```

The chosen folder becomes a self-contained SpielOS home. It receives the runtime, worker host adapters for Codex and OpenCode, empty private state, and no pre-installed workgroups.

## Update

```sh
pipx upgrade spielos && spielos refresh --dir /your/chosen/folder
```

Refresh replaces only the harness spine and adapters. It preserves the home’s strategy, assets, installed workgroups, and private `.spielos/` state.

## Workgroups and workers

A Workgroup is an installable, worker-owned capability. Its workers own narrowly-scoped workflows and can only produce their declared evidence. The Director routes work through durable work orders; workers never own the company loop or approve external actions.

```sh
spielos workgroup validate --file workgroup.json
spielos workgroup install --file workgroup.json --dir /your/chosen/folder
spielos workgroup list
```

The first release after the worker-owned reset deliberately ships with no starter Workgroups. Add only validated capabilities that match a real company outcome.

## What is persisted

Goals, runs, approvals, work orders, evidence, explicit directives, and evidence-backed reusable Memory are stored locally in `.spielos/state/`. Chat history is not product state. Strategy is source-controlled Markdown; it is changed deliberately, never inferred from a conversation.

## Development

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -B -m company status
PYTHONDONTWRITEBYTECODE=1 python3 -B -m unittest discover -s company/tests -v
```

The shipped home is built from `company/init_templates/`; runtime spine files must remain identical between source and template.

See [company/README.md](company/README.md) for the operating contract.
