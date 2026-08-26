# SpielOS — AI Company Operating System (Open Source)

**SpielOS is an open-source AI company operating system**: a local harness for
running your company with AI agents — durable goals, supervised runs, evidence,
approvals, and **AI departments** that do real business work under one Director
loop:

```text
GOAL -> OBSERVE -> DECIDE -> ACT -> EVALUATE
          ^                            |
          +----------------------------+
```

The runtime owns every Goal, Run, approval, evidence record, and notification.
Departments are **Lego packages**: self-contained folders that supply business
behavior and never create another loop. Codex, OpenCode, Claude Code, and
humans are all clients of the same persisted state. Nothing lives in chat
memory — close the session, the company keeps its state on disk.

## Install (one line)

```sh
pipx install spielos && spielos init
```

`spielos init` scaffolds a verified, self-contained harness home into your
current folder — with OpenCode-style progress, an optional starter-department
picker, host detection, and a runtime verification before it
reports success.

## Update (one line)

```sh
pipx upgrade spielos && spielos refresh
```

`pipx upgrade` fetches the newest release; `spielos refresh` re-vendors the
runtime spine and host adapters into every home on this machine while keeping
your strategy, assets, departments, installed agents, and `.spielos/` state.

No pipx yet? The bootstrap installer sets everything up (Python check,
pipx, spielos) and runs init in an empty folder automatically:

```sh
curl -fsSL https://raw.githubusercontent.com/ShayanSpiel/SpielOS/main/install.sh | sh
```

`spielos init` scaffolds a **fresh** home into your current folder — with
OpenCode-style progress, an optional starter-department picker, host detection,
and a runtime verification before it reports success.

**Fresh means:** the spine only — runtime, company skills, OpenCode/Codex
adapters, empty `.spielos/` state, `opencode.json`, `AGENTS.md`. **Zero
departments, zero strategy content.** Your company starts empty; the Director
onboards you and capabilities are added when goals need them:

```sh
spielos add outbound                 # install a built-in department
spielos add ./team.sdep              # or your own exported bundle
spielos init --department seo        # or vendor starters at scaffold time
```

Scripted and CI runs stay deterministic: add `-y/--yes` to skip prompts,
`--json` for a machine-readable receipt; exit code 0 means verified, 1 means
failed with an actionable message.

## Departments as products

Every department is one extractable folder: behavior (`department.py`),
workflows, evals, skills, templates, and tooling live together.

```sh
spielos department export outbound --out ./dist   # portable .sdep bundle
spielos add ./outbound.sdep                        # install into a home
spielos add ./outbound.sdep --force                # upgrade in place
spielos init --department outbound                  # scaffold with one starter department
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

## Extracted workers you can run today

The same worker pattern is published standalone — install once into
[Claude Code](https://claude.com/claude-code),
[OpenCode](https://opencode.ai), or [Codex CLI](https://github.com/openai/codex)
with one pasted command, and it works immediately:

| Worker | Keyword it owns | Repo | Guide |
|---|---|---|---|
| Lead Researcher | AI lead research agent | [Lead-Researcher](https://github.com/ShayanSpiel/Lead-Researcher) | [Guide](https://spielos.xyz/landing/lead-researcher/) |
| AI Keyword Research Agent | AI keyword research automation skill | [AI-Keyword-Research-Agent](https://github.com/ShayanSpiel/AI-Keyword-Research-Agent) | [Guide](https://spielos.xyz/landing/ai-keyword-research-agent/) |
| Social Lead Researcher | LinkedIn lead research agent | [Social-Lead-Researcher](https://github.com/ShayanSpiel/Social-Lead-Researcher) | [Guide](https://spielos.xyz/landing/social-lead-researcher/) |
| Email Outreach Agent | Cold email automation agent | [Email-Outreach-Agent](https://github.com/ShayanSpiel/Email-Outreach-Agent) | Guide: see repo |
| SEO Audit Agent | Technical SEO audit agent | [SEO-Audit-Agent](https://github.com/ShayanSpiel/SEO-Audit-Agent) | Guide: see repo |
| SpielOS Workers | 22 automation playbook recipes | [SpielOS-Workers](https://github.com/ShayanSpiel/SpielOS-Workers) | [Catalog](https://spielos.xyz/solutions/) |

More workers and agent skills: [Skills library](https://github.com/ShayanSpiel/Skills) ·
[Prompt-cache audit tool](https://github.com/ShayanSpiel/CacheCatch) ·
[full ecosystem on the profile hub](https://github.com/ShayanSpiel).

## How a SpielOS-run company is organized

| Concept | Meaning | Docs |
|---|---|---|
| Director | One loop that owns goals, routing, approvals, evidence | [How it works](https://spielos.xyz/features/director/) |
| Departments | Outbound, Content, Design, Analytics, SEO — Lego packages | [Departments](https://spielos.xyz/features/departments/) |
| Workflows | Repeatable playbooks inside a department | [Workflows](https://spielos.xyz/features/workflows/) |
| Agents | Bounded executors — one job each | [Agents](https://spielos.xyz/features/agents/) |
| Skills | Reusable methods an agent follows | [Skills](https://spielos.xyz/features/skills/) |
| Evals | Deterministic rubric evaluation of produced work | [Evals](https://spielos.xyz/features/evals/) |
| Artifacts | Evidence-backed outputs of every run | [Artifacts](https://spielos.xyz/features/artifacts/) |
| Connections | Access to external systems (Buffer, PostHog, Search Console…) | [Connections](https://spielos.xyz/features/connections/) |

See it running live — the public record of a company operated by this system:
**[spielos.xyz/live](https://spielos.xyz/live/)**

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

---

**SpielOS is built in the open by [Shayan Spiel](https://github.com/ShayanSpiel).**
Want these AI departments built, supervised, and measured *for* your business?
[Apply — free review](https://spielos.xyz/apply/) · free review · no required call.
