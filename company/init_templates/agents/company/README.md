# SpielOS operating guide

A Company owns its profile, strategy, responsibilities, boundaries and brand. A Workflow is a versioned business capability. A Run is one bounded invocation. An Improvement records a bounded GODAE change with its business need, exact file scope, observations, architecture and acceptance evidence.

Company content lives in `company/`; runtime code is pinned under `.spielos/runtime/company/`. Private state and generated work live under `.spielos/state/` and `.spielos/artifacts/`. `.agents/company` is a compatibility alias, not the editable content home. Optional Departments group ownership; they do not run a control loop.

## Working through the Director

Use the main company chat in Codex, the Director in OpenCode, or `claude --agent director`. Review hooks with your host's supported controls. Context injection is read-only and restores pending work after a restart or compaction. If absent, read `status` once and explain the injection failure. A status read never initializes a missing company or dispatches work.

Speak in names, outcomes and clear next decisions. Keep raw identifiers, enum values and JSON in tool payloads; the final Machine reference line is for the Director. The owner answers in plain language and the Director records the decision. No periodic runner, Goal tick, autonomous pursuit or repair process is part of new operation. A selected host or provider owns scheduling and notifications. Without a wake/callback, unattended reconciliation is not promised.

## Definitions and development

`company/profile.md` is the canonical typed identity document. `profile set --fields <json-file> --source <owner-direction>` records explicit facts and audit hashes while preserving notes. Unknowns remain unknown. Put strategic positioning in `strategy/`; operational tokens, real components, approved assets, voice, examples and templates belong in `brand/`. Avoid copying contradictory policy into both places.

A workflow package contains `workflow.json`, a readable `brief.md`, `execution/`, `evaluation/rubric.json`, `evaluation/cases/` and example input/output. The manifest references the canonical rubric and case files. The shipped sales-report is a neutral draft demonstrating actual computation, held-out inputs and a negative refund case; it is not an approved company process.

The Improvement sequence is `create`, `observe`, `agree-architecture`, `attach-candidate`, `decide`. Agree the acceptance brief and architecture in proportion to the change; the runtime does not force five owner interruptions. Independent accept/revise/reject uses real candidate execution evidence. Structural changes need exact allowed files and actual checks. Never silently change a production release, permissions or rubric.

## CLI

The installed `spielos` launcher and `python3 -B -m company` use the same core. Use an explicit installed `--home /absolute/path` on company operations. In a vendored home use `PYTHONPATH=.agents python3 -B -m company`. `--json` is machine output; ordinary output is owner language. See each command's `--help` for required file arguments.

| Command family | Purpose |
| --- | --- |
| `status`, `context`, `overview`, `catalog`, `layout` | Inspect company, definitions and unfinished work without dispatch |
| `profile show/set`, `memory summary/add/retire` | Record explicit facts, direction and causal operational learning |
| `improvement create/observe/agree-architecture/attach-candidate/decide` | Bounded GODAE development |
| `workflow candidate`, `experiment`, `experiment-show`, `release` | Pin harnesses, run real case evidence, independently qualify a release |
| `workflow run/show/claim/deliver/evaluate/review` | Invoke, execute host work, evaluate and review a bounded run |
| `workflow reconcile/cancel/wake` | Recover a named run or handle one host wake |
| `workflow approve-action` | Record the separately authorized exact action; does not publish |
| `workflow calibrate-judge/measure/scorecard/export` | Independent judge ratings, explicit business observations and telemetry |
| `export`, `import` | Preview and transfer a hashed declarative workflow closure |
| `migrate`, `history` | Review an exact legacy move plan and inspect preserved history |
| `mcp` | Serve the same core over local standard input/output |

To try the generic draft in a disposable installed home:

```sh
spielos workflow candidate --home /absolute/path/my-company   --manifest /absolute/path/my-company/company/workflows/sales-report/workflow.json --json
```

The candidate pins implementation bytes and context. Use the returned release in `workflow experiment --release ... --name ... --request-key ...` to execute its real cases. An experiment does not release a workflow. Release requires the exact case-to-run map and a separate authenticated reviewer; changing a reviewer string cannot impersonate that reviewer. Do not provision a second identity just to self-approve.

## Evaluation and approvals

Criteria have stable identities, sources, observable anchors, severity and justified thresholds. Cases include representative, held-out and negative splits. Check actual new inputs with deterministic rules; subjective criteria use pinned model/human verdicts with artifact evidence. Missing, error and not-applicable are distinct; an empty population or absent blocking criterion cannot pass. A hard failure cannot disappear into an average. Media review inspects rendered output at relevant sizes, with the actual artifact digest.

Model judge calibration requires independent human ratings of actual delivered run artifacts. A producer cannot supply fake reviewer labels. Reviewer revisions preserve the prior evaluation events. Execution completion, output quality, policy permission, operational performance and business outcome remain separate. An elapsed observation window, sample population and source are necessary for a business measurement; a quality score does not prove revenue impact.

Exact-action approval binds action, destination, accepted content digest and scope. Changed content requires a new decision. The effect ledger records intent before dispatch and will not blindly replay an unknown external result. Only a qualified configured adapter can dispatch; this release enables no Activepieces flow.

## Memory and context

Owner preferences are explicit owner-scope memory; strategic direction is explicit strategy scope. Workflow lessons cite evaluated runs of that workflow. Runtime code invents none of them. Retire stale claims without erasing their provenance. Summaries report actual scope counts plus a bounded sample. Host work receives the release's pinned declared documents, agent, skills, brand and selected causal lessons within a context budget. Critical constraints cannot be silently trimmed.

Legacy direct-work and strategy lessons remain in the historical database and migration review inventory until their exact workflow context is agreed. Only explicitly classified active owner preferences migrate automatically, with original lineage. Old approvals remain historical; they do not authorize new content or destinations.

## Recovery, portability and updates

Requests commit a stable identity before dispatch. Duplicate identities with changed content fail. Current claim tokens, lease generation and deadlines fence late results. Local code has a hard deadline; remote uncertainty requires inspection of the original provider handle rather than blind redispatch. A host assignment requires an actual claim and output delivery; no agent is silently started. Sequential composition uses explicit earlier-step JSON mappings and durable child runs; it is not a general DAG engine.

A migration plan inventories legacy state and hashes exact owner moves before applying. Recoverable journals handle interruption; integrity and collision checks refuse ambiguous state. Existing owner files are never silently replaced. Rollback must not replay an external action. Snapshot/restore is explicit and includes committed WAL records. A copied company database cannot be used under another company's identity.

Updates refresh only shipped runtime/host files, preserve untracked owner content and merge only the selected home's owned hooks. Use `--keep-stale` when deletion was not authorized. Owner documents are additive templates, never overwritten by product updates. Portable imports inspect static declarations and hashes, refuse secret/hidden/escape paths, and preview collisions. Imports execute no submitted code and inherit no production approvals.

## Telemetry and local plugin

Langfuse is the observation and evaluation record; local state journals execution and approvals for recovery. Configure the exact project and approved reviewed-evidence policy before qualification. Credentials stay in environment/private connection settings. The outbox uses stable event IDs, bounded retry and exact remote readback. A transport response alone does not mark verification. Under reviewed evidence, dataset items carry approved inspectable inputs and expected results; historical digest-only datasets remain historical. Experiments link actual case root observations and score definitions. Usage is actual, estimated or unknown with source and currency; unknown is never zero.

The optional local plugin exposes select_company, inspect_company, build_workflow, run_workflow, review_output and approve_action. It stores no home in the plugin cache, has no lifecycle hooks and never initializes a company during selection. The local OS owner is its trust root unless a scoped revocable bearer principal is supplied. This is not a hosted multitenant service or enterprise certification. Activepieces preparation stays offline until the owner explicitly authorizes live work.

## Declaring a company brand release

`brand candidate --version <version> --files <json-list> --home <home>` pins actual files; `brand release --candidate <json-file> --inspection <json-file>` requires an independent authenticated reviewer and a PNG example included in the pinned files. `brand show` resolves an immutable release. The same operations are `build_workflow` action `brand-candidate` and `review_output` action `brand-release` in MCP.

The starter convention uses voice.md, design-system/tokens.json and components.css, plus assets/templates/examples. It imposes no report-specific CSS classes. An actual company may instead declare brand/brand.json with schema 1 and roles: voice, tokens, components, assets, templates and examples. Each role is a nonempty list of contained brand-relative files included in the candidate; the contract is pinned automatically. Tokens can be JSON or CSS, and real assets can live within an existing design-system snapshot. CSS custom properties with valid fallbacks are allowed. Framework/rendering quality belongs to the paired harness and attributable rendered review, not a fixed component naming convention.

A workflow may declare execution.brand_context as a distinct nonempty list of text paths inside its approved brand release. Only those immutable bytes enter the assignment; unknown or binary paths fail. The full brand digest and file references remain pinned for both harnesses. Without an explicit subset, a declared brand contract contributes its voice/token/component/template roles, not unrelated manifests or examples. Critical-context and token-budget checks still apply; selecting a subset never silently trims a required constraint.

## Operational readiness

Context includes scoped memory claim text and provenance, unfinished Improvements, candidate reviews, expected negative-case rejection and telemetry state. The selected host passes the current prompt for relevant retrieval. Mandatory constraints survive topic filtering and cannot be silently omitted to fit a budget. Canonical strategy files are distinct from strategy-memory claims. Historical permissions never grant a new external action. Use memory classify to specify topics, category and mandatory constraints; critical claims cannot silently disappear under a budget.

Workflow candidates are drafts. Release requires an Improvement with that exact candidate attached, actual evaluated cases and independent review. The release and Improvement acceptance commit together. Preserved Department ready flags do not qualify a workflow. Direct file/tool work remains draft and cannot be reported as a qualified production run.

For product or system changes, improvement attach-change records actual file hashes and acceptance evidence under the agreed file boundary; improvement decide requires an independent reviewer and refuses changed evidence. improvement reconcile attaches historical evidence without granting acceptance. No reviewer identity should be invented to self-approve.

workflow configure-telemetry accepts an explicit enabled Langfuse destination, reviewed_evidence policy, mandatory require_verified_release=true and optional private credential_ref inside .spielos. The credential file must be owner-private and contain authorization or public_key/secret_key; credentials never enter workflow definitions or export events. A required release remains blocked until every candidate event is verified in that exact project. Status makes disabled or unsynchronized telemetry visible.

## Evaluation and activity standard

See [EVALUATION.md](EVALUATION.md). New candidates require `spielos-evaluation/2`: meaningful cases, observable criterion questions, explicit anchors and exact negative-failure expectations. Recorded activity distinguishes host sessions from Director/agent roles, retains supplied context changes, feedback targets and measured artifact lineage. Approved `reviewed_evidence` telemetry exports inspectable evidence into Langfuse. Local passes remain unqualified until exact remote readback; software tests never certify model or creative quality.

Continuous evaluation uses the selected host model. `evaluation pending --home <home> --session <session> --json` reads frozen reviews; `evaluation judge --home <home> --payload <verdict-file> --json` records actual criterion verdicts and model provenance. The Stop hook requests one bounded review pass. Tool wakes batch and reconcile telemetry, and every delivered workflow output runs its executable rubric automatically. Native Langfuse rules and workflow/agent definitions are mandatory for qualified releases. See EVALUATION.md for limits, human review and hook trust.

## Live company reports and chat receipts

`report --home /explicit/home --json` opens or reuses an authenticated loopback dashboard. `--no-open` returns the URL without opening a browser; `--snapshot` reads the structured company report; `--serve --port 0` serves on an assigned loopback port. `/report` in configured Codex/Claude company context runs the same operation. Do not use a source checkout as a company home.

The report exposes current workflow/run counts, scoped usage subtotals, categorized memory, actual supplied-context receipts, telemetry confirmations and current profile/strategy files. Unknown tokens, costs and active execution time stay unknown. Observed turn/run elapsed time includes waiting. Host and workflow charges are not silently combined. Existing candidate/release gates require the actual paired evaluation, independently reviewed release and configured telemetry; a dashboard or same-host diagnostic cannot qualify a workflow.

The generic UI ships with the runtime. A home may explicitly declare `.spielos/report.json` with `schema:1`, `ui_root:".spielos/artifacts/<custom-ui>"`, `custom_name` and `port`. Company visuals and reference galleries remain owner content; source contains generic renderer and synthetic tests only. The server rejects traversal, private state, secret roots and symlinks; native file reveal is an authenticated same-origin explicit action. No arbitrary command endpoint exists.

Codex/Claude hooks capture scoped context and supply concise owner-message instructions. At Stop, one bounded same-host review requests a Markdown tracking receipt with real report/trace links and pending/confirmed status. This is assistant-rendered chat delivery, not a claim that the host implements arbitrary rich cards. No hook trust record is edited. Restart or review host hook configuration when required by that host.


Codex usage can be imported from an explicitly bound current-chat log through `activity import-usage --session <session> --payload <private JSON containing path> --home <home>`. Hooks use only their supplied path or that registered source; no directory discovery occurs. Session identity and company cwd must match. The adapter stores model/turn/time/token metadata, never messages or reasoning bodies. Cached input and reasoning output remain included in their parent totals. `/report` shows actual tokens, actual bill unknown, and separately labelled current Standard-rate reference credits/API equivalents with official sources and verification dates.
