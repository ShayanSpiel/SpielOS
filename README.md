# SpielOS — the company harness

One durable loop for operating AI work as a company system:

```text
GOAL -> OBSERVE -> DECIDE -> ACT -> EVALUATE
          ^                            |
          +----------------------------+
```

The runtime owns every Goal, Run, approval, evidence record, and notification.
Departments are **Lego packages**: self-contained folders that supply business
behavior and never create another loop. Codex, OpenCode, and humans are all
clients of the same persisted state.

## Install (one line)

```sh
curl -fsSL https://raw.githubusercontent.com/ShayanSpiel/SpielOS1/main/install.sh | sh
```

The installer checks Python 3.11+, installs `pipx` for you when it is missing
(brew or pip — no manual steps), installs `spielos`, and offers to run the
first-run init right away. Re-running it upgrades an existing install.

Prefer to do it by hand?

```sh
pipx install "spielos @ git+https://github.com/ShayanSpiel/SpielOS1.git" && spielos init
```

`spielos init` vendors a complete, self-contained harness home into the current
directory — `.agents/company/` spine, `.spielos/` private state, OpenCode/Codex
host adapters, `opencode.json`, `AGENTS.md`, gitignore — with zero runtime
dependency on the installed package afterward. It verifies the new home runs
before it reports success, and detects which host (OpenCode / Codex) you have.

Interactive on a terminal: pick **full harness** (everything) or a
**minimal appliance** (spine + one department). Scripted and CI runs stay
deterministic: add `-y/--yes` to skip prompts, `--json` for a machine-readable
receipt; exit code 0 means verified, 1 means failed with an actionable message.

## Departments as products

Every department is one extractable folder: behavior (`department.py`),
workflows, evals, skills, templates, and tooling live together.

```sh
spielos department export outbound --out ./dist   # portable .sdep bundle
spielos add ./outbound.sdep                        # install into a home
spielos add ./outbound.sdep --force                # upgrade in place
spielos init --minimal --department outbound       # single-department appliance
```

Bundles carry a checksummed manifest plus the department's skills. They never
carry strategy, assets, credentials, or run state.

## First-class workers

Any workflow compiles into a bounded agent worker (no Director, no routing):

```sh
spielos agent compile outbound --workflow social-lead-research --name lead-researcher
```

Emits the OpenCode agent, Codex TOML, and roster entry from one WorkflowSpec.
The worker runs only that workflow, produces only its declared evidence kinds,
never edits files; approvals still park in the runtime.

## Updating

```sh
pipx upgrade spielos   # new CLI
spielos refresh        # re-vendor spine + hosts into an existing home;
                       # preserves strategy/, assets/, departments/, .spielos/
```

## Layout

```text
company/            Python package: runtime spine, evals, connections, CLI
  skills/           operator methods (director, department-runner, …)
  departments/      LEGO SHELF — each folder is an extractable product
    _shared/        cross-department contract + shared methods
    <id>/skills/    department-owned methods
    design/tools/   render/TTS tooling · design/tokens/ brand tokens
hosts/              adapter sources vendored into homes by init
tests/              → company/tests/ (in-package)
docs/               architecture notes
.spielos/           private runtime state (gitignored; exists only when this
                    checkout itself operates as a live company home)
```

Authority for architecture, vocabulary, pursuit semantics, safety rules, and
the owner doctrine: `company/README.md`.
