# AGENTS.md — operating rules for hosts in this repository

This checkout IS the SpielOS harness product. When working here you may be the
operating Director, a Department executor, or a bounded system-improvement
agent. Authority for architecture and doctrine: `company/README.md` below.

## Working in this checkout (dev mode)

This repo runs the harness **from source**, not from a vendored home:

- Runtime commands: `PYTHONDONTWRITEBYTECODE=1 python3 -B -m company …`
  (no `PYTHONPATH=.agents` — that form is only for scaffolded user homes).
- The Director skill lives at `company/skills/director/SKILL.md` here
  (in vendored homes it is `.agents/company/skills/director/SKILL.md`).
- Everything under `company/init_templates/` is what `spielos init` ships to
  users. Executable spine files must stay byte-identical between
  `company/` and `company/init_templates/agents/company/`
  (`company/tests/test_template_parity.py` enforces this).
- `.spielos/` here is private local runtime state; it is gitignored.


---
# SpielOS Company Harness

## Install (one line)

```sh
pipx install spielos && spielos init
```

## Update (one line)

```sh
pipx upgrade spielos && spielos refresh
```

No pipx yet? The bootstrap installer sets up Python/pipx/spielos and runs
first-run init in an empty folder automatically:

```sh
curl -fsSL https://raw.githubusercontent.com/ShayanSpiel/SpielOS/main/install.sh | sh
# or, from a checkout of this repository:
pipx install . && spielos init
```

`spielos init` vendors a complete, self-contained harness into the current
directory — `.agents/` spine, `.spielos/` private state, OpenCode/Codex host
adapters, `opencode.json`, `AGENTS.md`, and a gitignore — with zero runtime
dependency on the installed package afterward.

## Departments as products (lego extraction)

```sh
spielos department export outbound --out ./dist   # portable outbound.sdep bundle
spielos add ./outbound.sdep                        # customer side: install/upgrade
spielos add outbound                               # or install a built-in example
spielos add ./outbound.sdep --force                # replace an existing department
```

A bundle carries the department folder plus its company-namespace skills and a
checksummed manifest. It never carries strategy, assets, credentials, or run
state — those are user-layer.

Single-department appliance (no company scaffolding beyond one department):

```sh
spielos init --minimal --department outbound
```

First-class agent worker (the lead-researcher pattern, generated):

```sh
spielos agent compile outbound --workflow social-lead-research --name lead-researcher
```

Emits the OpenCode agent, Codex TOML, and roster entry from one WorkflowSpec.
The worker runs only that workflow, produces only its declared evidence kinds,
never edits files, never routes goals; approvals still park in the runtime.

Updating:

```sh
pipx upgrade spielos    # new CLI
spielos refresh         # re-vendor spine + host adapters into this home;
                        # preserves strategy/, assets/, departments/,
                        # agents/, config.user.json, and .spielos/
```

## Owner operating doctrine

These directives come from the owner. They bind every Department, Agent,
Skill, and piece of site copy. The website-facing restatement lives in the
repository root `agents.md`; this section is the authority.

### Company operating runtime

When the selected role is Director, it is the SpielOS operating Director, not a
generic coding or website agent. It owns business-goal intake, Department
routing, durable run supervision, evidence judgment, approvals, and outcome reporting.
It must identify itself accordingly and route unrelated implementation to
Build/default mode unless the user attaches that work to a company goal.

For business goals and company orchestration, use `.agents/company/` as the
durable authority and `.agents/skills/company/director/SKILL.md` as the operating
procedure. The public loop is only GOAL → OBSERVE → DECIDE → ACT → EVALUATE.
Stage, internal step, run status, and goal status are independent. The runtime
owns every goal. Departments supply domain behavior through colocated
`department.py` handlers and may run directly or as child goals of the Director. Workflows and
agents never own another loop. Never bypass runtime approvals or infer
live-execution permission from a chat request.

Runs are first-class and typed: business experiment, execution, diagnostic,
system improvement, evaluation, or controlled system test. Preserve hypothesis,
owner version, config snapshot, controlled/changed variables, evidence
validity, decisions, evaluation, and resume links. Never learn business lessons
from technical-only, contaminated, or invalid evidence. Department or runtime code changes
must be separate bounded system-improvement goals with allowed files and actual
acceptance-test evidence.

The universal company vocabulary is exactly Goal, Department, Workflow, Agent,
Skill, Connection, and Artifact. Do not introduce Engine, Tool, Port, or
ContentPackage as an additional public layer. `ContentPackage` is only an
Artifact manifest. This document is the complete authority, layout, and
OpenCode command surface; other READMEs link to it instead of restating the
architecture.

### Apply-first conversion funnel

The commercial funnel is Apply-first (owner directive 2026-08-22): every primary
conversion CTA links to `/apply/` — **Apply — Free Review** — with the microcopy
"Free review · No required call · See the scope before you pay". Contextual CTAs:
"Show Us What Keeps Breaking" (DeSlopping contexts: codex/claude-code/opencode
pages) and "Show Us the Work" (AI Workers contexts: software/use-case pages).
Applying comes before payment; pricing supports the decision and never leads.
Booking stays optional and secondary (owner directive 2026-08-23, supersedes
the 2026-08-22 Cal retirement): a small icon-only call CTA (`data-cal-link`
opening Cal's native embed popup) is allowed on the Contact page and in the
Apply "Not sure?" section beside "Start a Review" — never as a primary CTA,
never a required-call step. Do not expand booking CTAs to other pages without
a new owner directive. The two services are AI DeSlopping (fix broken AI-built
software) and AI Workers (hand repetitive work to AI), sold at $2,990/month
with one active build at a time. The Live page is proof ("WE RUN ON AI
OURSELVES"), framed as credibility, not a conversion destination. The legacy
waitlist route no longer exists.

### Strategy — single source of truth

`.agents/company/strategy/icp.md` is the canonical Ideal Customer Profile (buyer, exclusions,
positioning idea). Every skill, outbound rule, lead score, and piece of site copy
follows it. Never restate or redefine the ICP in another file — reference it.
The Outbound Department implements it via
`.agents/company/departments/outbound/strategy.md` (execution details only); the campaign data
(master xlsx, `.env`) stays local under `.spielos/data/outbound/` and
`.spielos/.env`; both are gitignored.

Company-wide positioning, voice, and measurement rules live beside the ICP in
`.agents/company/strategy/`. Approved reusable facts and proof live in
`.agents/company/assets/`; channel-specific templates live with their Department.
Skills contain methods, never company truth. Generated drafts and run evidence
belong under `.spielos/artifacts/`, not strategy, assets, or skills.

SpielOS runs the company through one durable loop:

```text
GOAL -> OBSERVE -> DECIDE -> ACT -> EVALUATE
          ^                            |
          +----------------------------+
```

The runtime owns every Goal, transition, approval, run, status, and evidence
record. A Department supplies business behavior; it never creates another loop.
Codex, OpenCode, and humans are clients of the same persisted state.

## Universal vocabulary

| Word | Meaning | Example |
|---|---|---|
| Goal | Measurable outcome owned by the runtime | Reach 30% qualified reply rate |
| Department | Durable business capability | Outbound, Content, Design, Analytics, SEO |
| Workflow | Repeatable playbook inside a Department | Email outreach, article, keyword research |
| Agent | Bounded executor for Workflow steps | Lead Researcher, Publisher |
| Skill | Reusable method an Agent follows | Copywriting, SEO, video creation |
| Connection | Access to an external or local system | Buffer, PostHog, Search Console, website |
| Artifact | Output or evidence produced by a run | Draft, report, graphic, video, receipt |

`ContentPackage` is an Artifact manifest that groups one brief with its related
post, article, graphic, video, evidence, and publication receipts. It is not a
new architectural layer. It lives at
`.spielos/artifacts/{goal}/{run}/content-package.json`.

## Structure

```text
.agents/company/
  runtime/                 one loop, persistence, supervision, controls
  strategy/                ICP, positioning, voice, measurement
  assets/                  approved reusable facts, proof, brand references
  departments/
    outbound/              lead research, email, social research, DMs
    content/               packages, posts, articles, publishing
    design/                graphics, renditions, video, templates
    analytics/             scorecards, funnels, CRO
    seo/                   keywords, briefs, audits, improvements
  connections/             host-first Connection declarations
  agents/                  bounded executor identities

.agents/skills/            reusable methods
  company/                 harness operation (director, department-runner,
                           system-improvement, outbound, outbound-email,
                           copywriting-en/fa)
  website/                 site-bound methods (spielos-ui, seo, analytics,
                           translation-fa, video-creation)
.spielos/.env              private credentials (ignored)
.spielos/data/             private operational inputs (ignored)
.spielos/state/            durable runtime state (ignored)
.spielos/artifacts/        generated run outputs (ignored)
public/                    intentionally published website assets
```

Each Department keeps its runtime implementation in `department.py`, its
Workflows beside it, and its channel templates inside its own folder. There is
no separate public adapter or Tool layer.

## Five OpenCode commands

| Command | Meaning |
|---|---|
| `/start [request or goal]` | Create, resume, or continue one Goal |
| `/stop [goal]` | Persistently stop automation; optionally pause one Goal |
| `/status [goal]` | Show the compact Company Snapshot or one Goal |
| `/approve <goal>` | Approve exactly one displayed parked action |
| `/help` | Explain this vocabulary and command surface |

Escape cancels the current OpenCode response. `/stop` and `/start` are
different from the rest: the V2 plugin has no command interception hook, so the
Director disables durable company automation itself by running `company runner
stop` (`/start` runs `company runner start`). While automation is disabled, idle
hooks, the HUD ticker, and background supervision will not start more work.

## Connections

Workflows declare logical Connections. Interactive work uses the active Codex
app/plugin or OpenCode MCP first. A direct API implementation is added only when
the Workflow must run unattended without a chat host. Today direct email
delivery is retained for unattended Outbound; Buffer, PostHog, Search Console,
and website publishing are host-resolved.

Connection credentials use the single example contract at
`.agents/company/.env.example`. Real values live only in `.spielos/.env`.
Outbound lead data lives only in `.spielos/data/outbound/`.

Buffer is a direct unattended Connection for approved content packages. Its
GraphQL API takes stable public HTTPS URLs for image and video assets; it does
not accept binary uploads. `python3 -B -m company.connections.buffer --check`
lists connected channels without printing credentials. `--probe-draft` creates,
verifies, and deletes one Threads draft only; it never schedules or publishes.

## Runtime commands

The Director and OpenCode commands call one portable internal CLI:

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=.agents python3 -B -m company departments
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=.agents python3 -B -m company catalog
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=.agents python3 -B -m company status
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=.agents python3 -B -m company status GOAL_ID
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=.agents python3 -B -m company status --history --limit 10
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=.agents python3 -B -m company tasks
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=.agents python3 -B -m company runner status
```

Open employee assignments are durable **work orders** in SQLite. When a run
blocks on `request_agent` (or a known capability handoff), the runtime writes
one open work order any Codex/OpenCode/host client can pick up. Matching
evidence closes it; `company retry GOAL_ID` continues the goal.

Installed employees execute through this one portable contract—no generated
host adapter per employee:

```sh
python3 -B -m company tasks --status active
python3 -B -m company tasks WORK_ORDER_ID --claim HOST_WORKER_ID
python3 -B -m company tasks WORK_ORDER_ID --complete HOST_WORKER_ID \
  --evidence '[{"kind":"accepted_kind","payload":{"artifact":"…"}}]'
```

Claiming is atomic, evidence is linked to the exact assignment, and successful
completion closes the work order and advances the Goal to its next real
suspension. This is also the concurrency boundary for multiple hosts and
cross-Department execution.

Work-order fields (employee, accepted evidence kinds, skills, connections) are
resolved from the Department `WorkflowSpec` catalog via
`runtime/contracts.py`. `goal create` validates metric and workflow against
that catalog and fills a default workflow when omitted.

### Department Lego packages

Growth Departments are declarative packages:

- `WorkflowSpec` — playbook labels + optional executable `graph` of `WorkflowStep`
- `WorkflowStep` kinds — `employee` | `approval` | `connection` | `machine`
- `runtime/interpreter.py` — shared OBSERVE→DECIDE→ACT→EVALUATE for packages
- `runtime/package.py` — `package_spec` / `validate_package` for install checks

A Department folder only needs package data (workflows, agents, metrics,
evidence_metrics). Custom stage code is reserved for special paths (live email).
`company catalog` marks packages with `"lego": true` when validation passes.

The shared Lego boundary is frozen at runtime catalog version `5.3.1`. Integrity
6.4 proved that freeze behaviorally, not only as serializable metadata:

- Content, Analytics, and Outbound execute representative flows through
  `runtime/interpreter.py`.
- A step's `requires` list is an AND: every declared kind must be present
  before the step advances.
- A required kind must be produced by a graph node or declared in that
  Workflow's evidence sources as a cross-Department handoff.
- `lego: true` therefore means the package both validates and runs the shared
  OBSERVE→DECIDE→ACT→EVALUATE interpreter.

Expanding that contract requires fresh evidence of a recurring business need
that cannot be expressed through these primitives and a separately bounded
system-improvement Goal. A Department-specific algorithm, prompt, channel bug,
or quality issue is not an abstraction leak.

Outbound's direct email Workflow remains the **only** documented stage
exception (`email-outreach`). It uses bespoke stage behavior for guarded
unattended delivery, provider observation, and evidence-window polling while
still exposing the same Goal, Workflow, Agent, Skill, Connection, approval,
metric, and evidence contract in the catalog. Social research and DM drafts
use the shared interpreter. Email does not own another lifecycle or justify
widening the common Lego primitives.

The current campaign Artifact authority is
`departments/campaign_contract.py` at schema `1.1`. Schema `1.0` remains
readable when the artifact already satisfies the current fields. Retired
`batch_items` / live-journey packages are rejected and must be migrated.

### Install path

```sh
# Validate a package JSON (short brief or full package_spec)
python3 -B -m company department validate --spec '{"id":"partnerships","purpose":"…","metrics":["meetings"]}'

# Write departments/{id}/ and reload via discovery
python3 -B -m company department install --spec '…' [--force]
python3 -B -m company department list
```

`system-improvement` goals with `change_kind: create_department` and a
`department_spec` install the package automatically after approval (no separate
coding executor for pure Lego packages).

Briefs expand through templates (`artifact`, `research`, `publish`, `pipeline`)
into multi-step graphs. Install also writes employee roster entries under
`.agents/company/agents/installed/*.json` (merged into `company.agents`).
Install stages and validates the whole package before swapping it into the live
catalog; failure restores the previous Department and employee records.

One approval authorizes the ordinary actions in its run. The runtime pauses
again only for an explicit `approval` Workflow node. Separate explicit nodes
remain independently auditable; employee and machine steps never invent extra
approval prompts.

The default status is a bounded Company Snapshot: automation, genuine active
attention, active and paused Goals, unread results, recent terminal results,
and counts. It never embeds configurations, observations, evidence bodies, or
historical task payloads. `status GOAL_ID` is a compact single-Goal projection.
`status --raw` is the explicit full-audit escape hatch. Terminal Goals are
closed transactionally, so they cannot remain operationally blocked or awaiting
approval even though their complete audit history remains in SQLite.

Create a Department goal with `--owner`, for example:

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=.agents python3 -B -m company goal create \
  --name "Research 10 qualified prospects" --owner outbound \
  --metric qualified_social_leads --operator ge --target 10 \
  --config '{"workflow":"social-lead-research","required_count":10}'
```

Internal CLI operations such as `runner tick`, `change complete`, evidence
recording, and notification acknowledgement are runtime plumbing. They are not
additional user-facing concepts or slash commands.

## Pursuit semantics and alignment

These are operating meanings, not new public vocabulary and not new tables.

| Kind | Meaning | Explicitly not |
|---|---|---|
| Primary Goal | Durable measurable business outcome | A slogan, task list, batch, or readiness proxy |
| Supporting Goal | Active bottleneck promoted to autonomous pursuit | Every metric in the causal model |
| System Improvement Goal | Bounded repair or capability that enables pursuit | Proof the parent business outcome happened |
| Run | One controlled attempt toward a Goal | The Goal itself |
| Batch | Bounded exposure inside one Run | A new Goal by default |
| Task | Known bounded work | An autonomous pursuit |
| Guardrail | Quality, risk, evidence, or authority constraint | A Goal by default |

The runtime accepts an optional `config.pursuit_kind` only to make one of the
three Goal roles explicit: `primary_goal`, `supporting_goal`, or
`system_improvement_goal`. It rejects `run`, `batch`, `task`, and `guardrail`
as Goal kinds. A bounded Batch lives at `run.config_snapshot.batch` with an ID
and positive size. This is a projection over existing Goal and Run records;
there is no causal-graph table or second scheduler.

A requested System Improvement is judged before it consumes company attention:

1. supports an active company outcome,
2. enables one,
3. protects a required invariant, or
4. is a justified bounded exploration.

If none apply, the Goal is created as `proposed` and the Director recommends
deferral with the opportunity cost. The owner may override (`company approve`
or `company resume`). The audit keeps `judgment: defer_recommended` and stamps
`owner_override`. Override is not strategic justification and does not approve
sending, publishing, spending, or code changes.

Do not invent causal lineage from filenames or test counts. Missing material
fields stay `unknown` and block or defer the repair.

When a child Goal changes material state, a waiting parent returns to OBSERVE
and re-measures its own outcome. Child success does not achieve the parent.
Pausing or closing an ancestor pauses descendants and cancels their open or
claimed work orders.

An active unmet Goal with a valid next experiment continues automatically.
That is permission to keep pursuing, not permission to send, publish, spend,
or change code. Automatic continuation stops when the Goal is terminal, the
evaluation is invalid, the next experiment is missing or is a system-improvement
blocker, a declared run limit is reached, an ancestor is not active, or another
Goal already holds the same channel or file scope. `company next` remains a
manual escape hatch.

Every persisted decision may link the exact Evidence IDs that justified its
selected branch. The shared interpreter links only the metric, prerequisite,
or package evidence it inspected; Director system-intervention decisions link
only invalid or contaminated evidence from the child's latest evaluated Run.
The runtime accepts links only from the current Run, evaluated children, or the
ancestor lineage. Unrelated visible records and obsolete child attempts are not
attached, and no provenance schema or graph store is added.

A Run hypothesis begins `active` and may move once to `supported`, `rejected`,
or `inconclusive`. Resolution requires an evaluation to explicitly name the
hypothesis attached to that same Run and state that its prediction was tested.
Goal achievement alone never resolves a hypothesis. Invalid or contaminated
tests can resolve only as inconclusive, while technical-only acceptance may
resolve a technical Run's hypothesis but never a business hypothesis. An
adjacent child or repair therefore cannot settle its parent's prediction.

Memory is narrower than a Run event or evaluation: it is an evidence-backed
reusable claim likely to change or better justify a future decision. A handler
must explicitly mark the claim reusable, state its decision relevance and
applicability, and cite valid Evidence IDs from the current Run. Routine
completion and shortfall summaries, invalid support, and unscoped claims stay
out of Memory. Retrieval is bounded to the current Goal and its ancestor Goals
owned by the same Department. When the shared interpreter uses a claim, the
persisted decision names the Memory ID and includes the claim in its rationale.

Cross-Department retrieval is opt-in and bounded. A reusable claim must set
`share_scope: company`, name its `audience_departments`, and declare `topics`.
The receiving Goal must request matching `config.memory_topics`. The runtime
returns at most ten newest matching claims from other Departments; unshared,
wrong-audience, wrong-topic, and invalid claims never enter the Goal context.
The same explicit Memory-ID decision audit applies. This uses the existing
Memory table and deterministic metadata filters—no embeddings, vector store,
or implicit company-wide context.

Strategic escalation is deliberately harder than tactical continuation. The
Director may propose a Policy or Model experiment only after three consecutive
valid business experiments on one Supporting Goal reject their own exact
hypotheses while reporting competent execution and a trustworthy system. Each
proposal names its scope, changed strategic variable, stop condition,
confidence, contradiction assessment, and the exact Run, hypothesis, and
Evidence IDs that justify it. Technical-only, invalid, unresolved, or
operationally untrustworthy attempts cannot trigger escalation. The proposal
parks for explicit owner approval; approval authorizes the discriminating
experiment only and never mutates strategy automatically.

The Strategy Kernel is a read-only logical graph over existing authority, not a
second strategy store. `strategy/kernel.json` maps exact authoritative Markdown
sections into Intent, Model, Policy, and Constitution and exposes ICP,
positioning, voice, and measurement as named views. Every Goal context contains
its current measurable Intent plus at most eight sections selected by explicit
`config.strategy_context.topics`, scopes, and layers; required safety rules
still apply. Each section carries its source path and hash. Evidence and Memory
remain separate, and neither an experiment proposal nor its approval can edit a
strategy source. `company strategy` shows the reference-only state; topic/scope
options show the same bounded context selector used by the runtime.

## Safety and system improvement

Live external actions always park for approval. Generated material is not
business evidence. Technical-only, contaminated, or invalid evidence cannot
support a market conclusion.

Every `approval_required` notification carries one typed
`approval_interaction`: question, action, artifact, destination, scope, risk,
consequence, separate Approve/Reject choices, and the exact fallback command.
Host adapters must render it through their native question control (`question`
in OpenCode and `request_user_input` in Codex when exposed). They never combine
parked actions or auto-approve. Hosts without that control must show the same
fields as a prominent blocking question; Reject leaves the action parked.

Runtime or Department changes use one bounded `system_improvement` Goal with:

- `owner_id`, current and target version;
- problem and allowed files;
- exact acceptance commands;
- `change_kind: repair` or `create_department`;
- a `department_spec` when creating a Department;
- an alignment judgment, or an explicit owner override.

The executor edits only approved files, records actual test evidence, and never
marks deployment unless deployment happened. A failed acceptance opens a fresh
task on the same Goal and allowed files. Same-scope retries do not ask for
approval again. Expanding files, diagnosis, or side effects needs a new
approval or a new Goal. The local evaluation never satisfies a parent business
metric.

The `/live` snapshot sync and push are strictly best-effort and bounded:
`sync-live-timeline.py` runs with a 15-second hard bound and every git
subprocess with a 20-second hard bound (`LIVE_SYNC_TIMEOUT_S` and
`LIVE_PUSH_GIT_TIMEOUT_S` in `runtime/loop.py`). A hung network, remote lock,
or filesystem logs a warning and never blocks a goal transition. A cycle left
mid-flight in `running` state by a killed client resumes on the next tick once
its lease expires — the pull worker treats a `running` cycle without a live
lease as runnable (`store.live_lease`).

## OpenCode permission policy

Company agents run with free-run shell permissions in OpenCode (V2
`permissions` rules in `.opencode/agents/*.md`). The Director and Department
executors never edit repository files; `system-improvement` is the only editing
agent and is bounded by its persisted goal. OpenCode-level prompting is thereby
limited to OpenCode defaults (`.env` reads, external directories); the runtime's
parked approvals are the single gate for live external and customer-facing
actions. Do not reintroduce per-command `ask` rules for company agents.
