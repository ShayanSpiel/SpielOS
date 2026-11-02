# SpielOS architecture

The runtime implements Company, Workflow, Run and Improvement. The new public CLI, host adapters and MCP interface share one bounded workflow core. They do not invoke the historical Goal controller. GODAE is a reviewed development process; a production invocation never starts another pursuit or self-repair cycle.

## State and ownership

CompanyHome owns the schema-2 visible layout, checked source/home boundary and hash-bound migration journal. `company/` holds owner definitions; `.spielos/runtime/company/` holds distribution code. `.agents/company` remains an internal compatibility alias. Private state, credentials and artifacts stay outside product source. Initialization is explicit; status and MCP selection never create a home.

WorkflowRuntime uses a single local SQLite authority, company identity binding and transactional records for immutable candidate manifests, releases, acceptances, invocations, evaluation evidence, actor audit, action decisions, effects, usage and export events. Opening an unsupported schema fails closed. Historical `core_*` records remain readable through a fresh read-only snapshot. Compatibility library modules are retained for historical fixtures; their retired Goal/runner commands are unavailable for new operation. Remove those internal modules only at a declared compatibility boundary.

CompanyAuthority validates signed expiring principals against private per-company policy. Roles separate build, execute, review, approval and configuration. Revocation invalidates already issued credentials. The local OS owner controls the trust root. This does not provide enterprise SSO or an untrusted-code isolation boundary. Multiple machines need one explicit team service authority; sharing SQLite through Git is unsupported.

## Release and invocation

Candidate validation pins actual implementation bytes, execution adapter revision, evaluation implementation revision, schemas, rubric/cases, documents, agent/skills, connection references and approved brand version. Supplied derived fields cannot spoof resolved context. Brand releases retain immutable approved snapshots and rendered-review evidence. Workflow and evaluation consume the same revision.

Release acceptance references actual exact-candidate executions for every representative, held-out and negative case. A separate authenticated reviewer is mandatory for consequential releases. Accepted evidence and actor identity are immutable. Production runs accept new schema-valid inputs and evaluate them against the pinned criteria; production inputs need not equal a sample.

The request identity and intent are committed before dispatch. Reuse with changed content fails. Adapters expose start, inspect and optional cancel; uncertain dispatch retains the original handle. Lease generation, exclusive claims, deadlines and actor/token checks reject stale callbacks. LocalAdapter uses a spawned trusted function process with a hard deadline. LocalFileAdapter invokes pinned trusted Python with a minimal environment and bounded JSON transport. Neither is a VM for hostile code. Host work returns the pinned assignment and requires explicit claim/deliver. SequentialAdapter maps earlier outputs to accepted component releases with durable parent/root links and a fixed step bound; no arbitrary DAG engine is present.

External-action approval is separate from quality review and bound to exact action/destination/content/scope. An effect intent is persisted before dispatch. Unknown results are reconciled rather than blindly retried. The shipped pilot enables no external-effect provider. Enabling an integration requires separately scoped authorization.

## Context and evaluation

WorkflowMemory retains explicit owner, strategy and evidence-backed workflow scopes, original provenance and retirement records. Each scope is selected before limiting, so owner preferences cannot starve operational learning. Pinned context is budgeted with mandatory constraints protected. Owner projection uses names and outcome sentences, with machine references separated from owner text.

Evaluation contracts distinguish pass, fail, missing, error and not-applicable, and reject empty or duplicate populations. Blocking failures survive aggregation. Mechanical rules apply to arbitrary new inputs. Human/model evidence includes artifact digest, criterion, evaluator and version. Independent calibration records cite actual delivered artifacts and disagreement policy. Self-judging cannot replace release authority. Review revisions enqueue immutable prior/new evidence. Deterministic release-only review is limited to pure checked workflows; default production policy requires review per run.

Business measurements separately declare metric definition, unit, population, sufficient sample, elapsed observation window, source and measured baseline or explicit unknown. Output quality cannot infer business impact.

## Telemetry and read models

A durable transactional outbox exports one logical run trace with child execution/evaluation/review observations. Composition propagates its root. Langfuse OTLP v4 uses stable observation IDs; score subjects and definition versions are read back. Dataset and score-definition creation has its own intent/readback journal. Uncertain creates are read back, not blindly repeated. Experiment verification checks dataset, exact item roots and scores after resource verification.

Export policy defaults to local retention. Explicit export or an approved project-scoped host-wake configuration flushes bounded batches. The approved reviewed-evidence policy exports selected inspectable inputs, outputs, supplied context and evaluation evidence. Credentials, hidden reasoning and unrestricted context stay local. New releases require this policy and confirmed Langfuse evidence; local-only drafts remain unqualified. Costs retain actual/estimated/unknown source, stage, attempts and currency; unsupported host billing stays unknown. SQL aggregates separate inventory, production roots, children and candidates, keeping large-history context bounded. Business observations have their own denominator.

## Installation and interfaces

Bootstrap copies only release-owned files, merges owned host hooks and preserves owner configuration. Generic content is created only if absent. A migration previews exact inventory, references, state and owner-memory scope before moves; journals and internal aliases preserve recoverability and references. Safe portable import is static and declarative: hashes, dependency closure, collision preview and journaled exclusive writes; no submitted import or hook execution. Imported definitions remain drafts.

Host hooks inject read-only company context on supported lifecycle events, with no attention polling daemon. A selected host/provider owns wakes and notifications. MCP stdio is a thin tool surface over the same authenticated core. Plugin cache holds no company state and selecting a company cannot initialize it.

See README.md for commands and ACCEPTANCE.md for scenarios and qualification limits. Local synthetic tests do not qualify a held remote provider, enterprise deployment or unmeasured business outcome.

## Declaring a company brand release

`brand candidate --version <version> --files <json-list> --home <home>` pins actual files; `brand release --candidate <json-file> --inspection <json-file>` requires an independent authenticated reviewer and a PNG example included in the pinned files. `brand show` resolves an immutable release. The same operations are `build_workflow` action `brand-candidate` and `review_output` action `brand-release` in MCP.

The starter convention uses voice.md, design-system/tokens.json and components.css, plus assets/templates/examples. It imposes no report-specific CSS classes. An actual company may instead declare brand/brand.json with schema 1 and roles: voice, tokens, components, assets, templates and examples. Each role is a nonempty list of contained brand-relative files included in the candidate; the contract is pinned automatically. Tokens can be JSON or CSS, and real assets can live within an existing design-system snapshot. CSS custom properties with valid fallbacks are allowed. Framework/rendering quality belongs to the paired harness and attributable rendered review, not a fixed component naming convention.

A workflow may declare execution.brand_context as a distinct nonempty list of text paths inside its approved brand release. Only those immutable bytes enter the assignment; unknown or binary paths fail. The full brand digest and file references remain pinned for both harnesses. Without an explicit subset, a declared brand contract contributes its voice/token/component/template roles, not unrelated manifests or examples. Critical-context and token-budget checks still apply; selecting a subset never silently trims a required constraint.

## Operational contract after migration

Company context is a read-only projection of explicit memory claims, production work, candidate evaluation, Improvements and telemetry readiness. It does not infer completion of direct chat work. Imported owner records keep their historical provenance and context-only authority; historical authorization is excluded from applicable memory. New classifications can carry explicit topic restrictions and mandatory constraints.

The release transaction requires a candidate-linked Improvement in evaluation and records its acceptance in the same transaction. Required telemetry is verified against the approved project before release. System changes use measured file and acceptance-artifact evidence and independent review rather than fake workflow executions. Historical implementation claims can be reconciled while remaining unresolved. These checks govern supported runtime APIs; host instructions also require direct tool/file work to remain draft until it enters the appropriate lifecycle. They are not operating-system filesystem permissions.

## Evaluation and activity standard

See [EVALUATION.md](EVALUATION.md). New candidates require `spielos-evaluation/2`: meaningful cases, observable criterion questions, explicit anchors and exact negative-failure expectations. Recorded activity distinguishes host sessions from Director/agent roles, retains supplied context changes, feedback targets and measured artifact lineage. Approved `reviewed_evidence` telemetry exports inspectable evidence into Langfuse. Local passes remain unqualified until exact remote readback; software tests never certify model or creative quality.

## Graph coordination

`company.graph` adds a bounded DAG coordinator and source explorer. Workflow nodes delegate accepted releases to WorkflowRuntime; graph journals do not grant release acceptance or external permission. Inspection nodes verify source references only. They do not execute a Director, prove model quality or benchmark business outcomes. The sequential workflow adapter remains a separate, simpler composition contract. See [GRAPH.md](GRAPH.md).

## Supported deployment boundary

The current implementation targets a trusted local POSIX host with Python 3.11+. File locking uses `fcntl`, company identity uses the OS user, and home layout uses symbolic links. Native Windows is not qualified. Process deadlines are operational controls for trusted code, not a security sandbox or proof that every descendant process is terminated. Team services, shared network SQLite and hostile local code are outside the current deployment claim.
