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
pipx upgrade spielos && spielos update --dir /your/chosen/folder
```

Update replaces only the harness spine and host adapters. It preserves the
home’s strategy, assets, installed Workgroups, configuration, and private
`.spielos/` state. `spielos refresh` remains a compatibility alias.

To test unreleased source changes locally, install the built wheel explicitly;
plain `pipx install spielos` installs the latest release published on PyPI:

```sh
pipx install --force /path/to/SpielOS/dist/spielos-VERSION-py3-none-any.whl
spielos update --dir /your/chosen/folder
```

## Workgroups and workers

A Workgroup is an installable, worker-owned capability. Its workers own narrowly-scoped workflows and can only produce their declared evidence. The Director routes work through durable work orders; workers never own the company loop or approve external actions.

```sh
spielos workgroup validate --file workgroup.json
spielos workgroup install --file workgroup.json --dir /your/chosen/folder
spielos workgroup list
```

Fresh homes deliberately start with no Workgroups. Install one package or all
six bundled capabilities only when they match a real company outcome:

```sh
spielos workgroup install --all --dir /your/chosen/folder
```

Owner-language aliases are translated at intake: Department means Workgroup;
Agent and Employee mean Worker. They are not additional runtime layers. Use one
orientation command instead of probing several catalogs:

```sh
spielos overview
```

## Artifacts, friction, and migration

Generated work has one lifecycle under
`.spielos/artifacts/<goal>/<run>/<workflow?>/{work,final}`. Agents prepare the
workspace, finalize verified deliverables, clean declared intermediates, and
automatically open the final folder only for owner-facing creative or content
deliverables such as videos, images, audio, copy, documents, and decks:

```sh
spielos artifact prepare --goal GOAL_ID --run RUN_ID
spielos artifact finalize --goal GOAL_ID --run RUN_ID --file PATH --open
```

Code, packages, archives, tests, logs, manifests, migration plans, and internal
evidence are reported with their paths but are not opened unless the owner asks.

Misleading tools, commands, instructions, contradictions, and fallbacks are
durable friction rather than silent retries. Inspect them with `spielos friction
list`.

Migrate into a fresh home, never by treating a foreign runtime as current code:

```sh
spielos migration inspect --from /old/home
spielos migration plan --from /old/home --out migration-plan.json
```

The plan archives foreign Goals by default, normalizes capability/executor
aliases, quarantines unknowns, and converts one Workgroup at a time.

## State, context, and memory

Goals, runs, approvals, work orders, evidence, typed company-profile overlays,
experiment learning, and reusable Workflow candidates are stored locally in
`.spielos/state/`. Strategy Markdown is the reviewed base profile; owner-explicit
profile overlays can supersede one typed claim without rewriting the source files.

Codex `SessionStart` and `UserPromptSubmit` hooks, plus OpenCode's model-request
hook, load a small read-only projection automatically. Initial context contains
the company profile, top Goal state, and urgent attention. Each user message adds
only prompt-relevant profile claims, experiment results, and Workflow instructions.
Chat history and tool traces remain host-owned and are not copied into SpielOS.

Memory writes have explicit triggers: the Goal loop records experiment learning
only after valid cited evidence; an owner-explicit strategy correction writes a
profile claim; and every user turn carries a typed memory-candidate contract.
The host model interprets semantic intent while deterministic runtime code owns
scope, authority, identity, deduplication, supersession, provenance, and
retrieval. Explicit owner Workflow corrections apply immediately, task-only
instructions stay temporary, and a canonical Workflow defect routes to a
bounded source repair instead of contradictory memory. Other procedural
candidates harden after two matching behavior keys in 14 days; stale one-offs
expire during consolidation. Hooks remain read-only.

## Development

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -B -m company status
PYTHONDONTWRITEBYTECODE=1 python3 -B -m unittest discover -s company/tests -v
```

The shipped home is built from `company/init_templates/`; runtime spine files must remain identical between source and template.

See [company/README.md](company/README.md) for the operating contract.
