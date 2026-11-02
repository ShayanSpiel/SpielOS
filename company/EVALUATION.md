# Evaluation and observability standard

Version: `spielos-evaluation/2`.

A file existing, a command returning zero, a JSON schema validating, or a trace arriving proves only that particular fact. None establishes that the Director made the right decision or that an artifact satisfies its brief. Every quality claim must state the question, expected behavior or result, observed behavior or result, evaluator, evidence and applicable version.

## Identity and authority

Codex, Claude and OpenCode are execution hosts. Director is a SpielOS role performed within a selected host session. An agent is a declared responsibility with scoped skills, context and permissions; declaring one does not execute it. A workflow defines a paired execution/evaluation contract. A run invokes one immutable candidate or accepted release. An Improvement bounds a change, including a change made while an order is being produced.

One host session can contain Director, builder, agent and evaluator activity. Those roles have separate session records linked by explicit causal events and targets. An activity record is evidence of captured activity, not independent approval. The main owner conversation remains the Director; this standard does not create another hidden Director or a pursuit daemon.

## The two harnesses

The execution harness specifies input, actual implementation, scoped context, output, permissions, deadlines and cost envelope. The evaluation harness specifies observable objectives, criterion questions, anchored pass/fail judgments, severity, evaluator versions, representative cases, unseen cases and negative controls. Both are versioned and pinned together. New candidates must declare the standard; old releases and evidence remain historical and are never rewritten to appear compliant.

Keep workflow definitions under `company/workflows/<name>/`: `workflow.json`, `brief.md`, `execution/`, `evaluation/rubric.json`, `evaluation/cases/` and examples. Shared Director/build/system/agent suites are generated with `evaluation template`, reviewed and registered through the evaluation harness. Store company-authored suites in the selected company's visible content; generated observations and acceptance reports belong under its private `.spielos/` tree. Product source contains generic standards and explicitly synthetic tests only.

A case contains actual inspectable input, an expected result or behavior, its purpose and its split. Artifact references may accompany those values; a filename is not their substitute. Creative references describe acceptable alternatives, dimensions and failure examples; exact text equality is appropriate only when exact equality is the task. Subjective judgments need artifact-specific observations, not generic praise.

Each criterion has an identity, question, source, dimension (`output`, `behavior`, `safety`, `operational`), severity, explicit pass/fail anchors and evaluator. Mechanical checks inspect actual output or captured events. Event checks can test content, counts, forbidden actions and ordering. A schema or presence check is supporting evidence, never the only output-quality assessment. Semantic quality uses an attributed human reviewer or a versioned model judge with independent human calibration on accepted and rejected artifacts. Producer self-ratings cannot grant independent acceptance.

A negative control must fail its named criteria. Failure for a different reason does not qualify it. Missing, errored and inapplicable judgments remain distinct. Blocking failures cannot be averaged away. Quality, external permission, runtime reliability, cost and measured business outcomes remain separate.

## Required behavioral review

| Subject | Required review coverage |
| --- | --- |
| Director | Correct routing and role; feedback target; context provenance; permission boundaries; interruption/recovery; honest reporting |
| Building | Input/output contract; paired harness design; representative/unseen cases; judge calibration; actual candidate execution; release/regression decision |
| System improvement | Exact scope; behavioral acceptance; regressions; actual changed bytes; evidence integrity; independent acceptance |
| Workflow | Correctness; constraints; artifact usability; new-input generalization; failure handling; cost/latency provenance |
| Agent | Assigned responsibility; tool/context use; handoff; feedback application; permissions; output quality |

The generated subject templates are starting exercises, explicitly unqualified. They do not certify all coverage obligations or replace a domain's reviewed golden dataset. Deterministic infrastructure tests do not qualify a Director model, motion design quality, or business impact. Do not call a visible example a protected holdout: use independently maintained cases and record which dataset/judge version was used before tuning.

## Session and feedback evidence

Start an activity session with explicit host, host session and SpielOS role. Supply its identity through `--session`, `SPIELOS_SESSION_ID`, or the MCP payload `session_id` when operating the runtime. Registered mutations then append a causal operation record transactionally. Workflow invocations retain the originating session. A resumed host session reuses its identity; changed content requires a new event identity, never rewriting an old event.

Context events contain the actual supplied text, hashes and added/changed/removed documents with a reason. They describe the context SpielOS supplied, not the model's entire hidden context. Compaction/resume are new snapshots. Tool capture is limited to events the selected host exposes. If a hook is not installed, reviewed or invoked, report that coverage gap. Never claim hidden reasoning or unavailable token counts were captured. Usage is actual, estimated or unknown with its source; unknown never means zero. Provider-reported generation usage uses Langfuse's native token fields.

Feedback records contain the owner's message, interpretation, target, scope and effect. Supported scopes are order/run, project, owner preference, workflow, evaluation and build. An order correction changes an order revision. A reusable workflow change starts or updates a bounded Improvement and a new candidate. A judge correction revises the evaluator and rechecks affected evidence. Do not mutate an executing release or silently turn one order's preference into global policy. Record the before/after boundary and what continues under each version.

Artifact records measure actual bytes and retain path, type, size, producer session, target and causal event. Register input assets, intermediate previews, final artifacts and revisions. File hashes establish provenance; quality still needs rendered/behavioral inspection. A local path is not a remote media preview. Binary uploads require a separately implemented/authorized media path; never imply Langfuse can play a local-only asset. Files remain in the selected home; credentials and authority files cannot be registered as artifacts.

## Langfuse is the observation and evaluation record

The configured project is the authoritative place to inspect activity, datasets, experiments and scores. SQLite remains the transactional journal for invocation identity, approval enforcement and recovery; it is not a substitute for remote observability. Without confirmed remote evidence, report `awaiting_telemetry`, never fully qualified.

The approved `reviewed_evidence` policy exports selected inspectable inputs, outputs, supplied context, criterion questions/anchors, evaluator evidence, artifact lineage and feedback. Credentials and hidden reasoning are excluded; obvious secrets are redacted. Avoid placing secrets in task payloads. The old `digests_only` policy remains readable for historical integrations but cannot qualify this new standard. Required Langfuse verification cannot be disabled under reviewed-evidence policy.

Use native Langfuse sessions to group role traces; agent/tool/generation/evaluator observations identify the work. Categorical criterion scores preserve pass/fail/missing/error/not-applicable. Numeric ratings preserve the anchored value separately, together with rationale and evaluator version. Human annotations in Langfuse are review evidence; they do not grant external-action approval or silently change local release authority.

Datasets contain actual approved input and expected output plus purpose, split, expected failure criteria and the pinned rubric. Dataset identity is based on the evaluation contract, not execution version, so candidate code/prompt variants can be compared on the same cases. A changed dataset or judge starts a different comparison population. Experiment items point to the actual invocation/evaluation observation. Verify dataset/resource content, exact observations, scores, experiment membership and case roots by readback; HTTP acceptance alone is incomplete.

Exports are journaled before sending. An ambiguous observation creation is read back using its stable identity rather than blindly resent. Missing visibility, rejected payloads and exhausted budgets remain visible. Each host wake flushes bounded batches; an explicit activity export flushes additional pending evidence. No product polling loop is introduced. Offline work remains journaled and visibly unqualified until synchronization succeeds.

## Bounded experiments while building or running

Run baseline and candidate against the same immutable evaluation contract. Preserve task revision, actual output, criterion-level result, failures, cost source and case coverage. Compare paired cases and reject regressions. A failed trial is evidence, not a workflow update. Production order revisions and candidate trials remain linked but distinct. Experiments do not automatically promote a release or authorize publishing.

The evaluation harness runs importable trusted Python tasks with deadlines and case limits. Host-agent work uses recorded host output or normal candidate assignments; it must not be replaced with invented transcripts. If execution crashes after dispatch, the committed invocation remains unresolved and is not silently rerun. Resolve it explicitly or start a separately identified trial. This implementation provides bounded execution/comparison, not an autonomous hypothesis-generating research controller.

## Operating surface

- `activity start/show/record/context/artifact/export --home <home>` records and inspects activity.
- `evaluation template --subject director|build|system_improvement|workflow|agent --home <home>` produces an unqualified suite for review.
- `evaluation register/evaluate-event/show/compare --payload <json-file> --home <home>` uses the same shared harness.
- `workflow experiment/experiment-show` executes actual pinned candidate cases and exposes local versus remote evidence.
- MCP `build_workflow` has corresponding `activity-*` and `evaluation-*` actions; existing run/review tools retain their authority checks.

System-change acceptance under reviewed evidence requires behavioral questions, expected and actual observations, passing evidence and a linked activity session. Exact files and test artifacts are measured, and the session's remote evidence must be confirmed before independent acceptance. A successful source test suite is software evidence; model/creative quality remains unqualified until its actual executions and independent judgments exist.

Sources used for integration: [Langfuse evaluation concepts](https://langfuse.com/docs/evaluation/core-concepts), [experiments via OpenTelemetry](https://langfuse.com/docs/evaluation/experiments/experiments-via-opentelemetry), and [official Codex hooks](https://learn.chatgpt.com/docs/hooks).

A pending Improvement can be explicitly withdrawn for another draft with `improvement revise --reason ...`. The previous evidence and reason remain in immutable revision history; fresh evidence and independent acceptance are required. Accepted releases cannot be withdrawn through this draft operation.

## Continuous operation and selected-host judging

With `automatic.enabled`, each owner turn has its own stable trace title under the host session. Context, requests, tool calls, answer, lifecycle checks and host judgment are separate observations. The lifecycle checks distinguish captured evidence from semantic quality. They never infer that an answer is good merely because a file, tool result or trace exists.

At Stop, the answer and rubric are frozen. The synchronous Stop hook requests at most one continuation of the same host model to inspect up to three pending results. `evaluation pending` exposes the actual input/output and anchored criteria; `evaluation judge` records criterion state, reason, artifact-specific evidence and an optional justified numeric rating. The second Stop cannot request another continuation. Pending work stays pending rather than starting a pursuit loop. The host model identity exposed by the hook is enforced; unavailable model identity is explicitly unknown. A human-required judgment is not impersonated by a model.

Langfuse is not given a separate provider credential to run Codex. Native code evaluators validate and record the host-model verdicts, preserve model provenance, and expose readable categorical results and numeric ratings. The semantic reasoning is performed in the selected Codex/other model runtime. Same-host judgments are diagnostic; independent release acceptance remains separate.

Every delivered workflow output is evaluated automatically against its pinned executable rubric. Human/model evidence that is absent remains missing, with a frozen host-review request where applicable. New candidates register a versioned native evaluator/rule definition for the workflow and its bound agent, including purpose, rubric and execution binding. Release is refused until its exact native definition and candidate evidence are verified. New workflow/agent definitions must declare the intended execution and judging model when known; actual observed judging identity is retained for each run.

Native observation rules sample every matching result, filter to the exact company and result category, and distinguish Director turn checks, Codex/host quality judgments, workflow output evaluations and experiment outcomes. Experiments are controlled comparisons, not a label applied to ordinary production traffic. Existing historical events and judgments remain preserved.

Each tool lifecycle wake uses a nonblocking delivery lock, a record limit, a byte limit and a wall-clock budget. Pending observations are sent in OTLP batches, and later wakes read back exact observations and scores. Current work and older backlog both receive capacity. A local telemetry-health projection exposes waiting or failed delivery. No resident worker, product scheduler or polling daemon is created. Ambiguous old sends can be explicitly reopened for readback without blindly resending them. Host hooks must receive the platform's normal trust review; modifying trust records is never part of installation.
