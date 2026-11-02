---
name: spielos-build-workflow
description: Create or improve a reusable SpielOS workflow through a bounded GODAE record and actual candidate execution evidence.
---

Select the company and inspect its existing workflows before creating another.
Create an Improvement for the business need, accountable owner, baseline or
explicit unknown, target, constraints, intended users, outcome window and exact
allowed files. Observe examples, counterexamples, failures and real process
sources. Agree the acceptance brief and architecture for both harnesses, the
permissions and cost envelope. GODAE is development, never a production pursuit loop.

Write `company/workflows/<id>/workflow.json`, `brief.md`, `execution/`,
`evaluation/rubric.json`, `evaluation/cases/` and example input/output. Keep the
rubric in its referenced file. Use criterion identities shared by the brief,
examples and checks. Pin actual agent, skill, strategy and brand content.
Draft brand assets require review; do not invent company brand approval.

Call `build_workflow` with `action=candidate` and `payload.workflow_id`. Run each
pinned representative, held-out and negative case through `run_workflow` using
`candidate_case`. Evaluate the actual outputs through `review_output`.
A supplied example is a reference, not evidence that implementation executed.

Release requires an independently authenticated reviewer and the exact case-to-run
mapping in `payload.candidate_runs`. Do not impersonate a reviewer or provision a
second identity merely to self-approve. Explain missing review as an unresolved
requirement. A negative case must fail its stated quality criterion.

The bundled runtime’s `workflow experiment` runs the pinned case set and journals Langfuse dataset/score-definition resources when approved export is configured. Inspect experiment-show for local case evidence versus remote verification; neither an HTTP success nor the experiment itself creates a production release. Unknown service/model usage stays unknown.

For a company brand version, use `build_workflow` action `brand-candidate` with the version and actual files. Use the company's existing tokens/components; no report CSS class names are required. A brand/brand.json may explicitly declare contained voice/tokens/components/assets/templates/examples roles. The contract and actual bytes are pinned. Never replace an existing brand with the neutral starter just to satisfy validation.


Evaluation and observability are governed by `EVALUATION.md` and `spielos-evaluation/2`. Codex/Claude/OpenCode is the host; Director is a recorded SpielOS role in that host. Start or reuse the activity session supplied by the context hook; pass its session identity with runtime operations. If capture is missing, say what is unobserved and start explicit activity recording before claiming observable work. Log actual supplied/changed context, tool outcomes, measured artifacts and feedback targets. Classify each correction as run/project/owner/workflow/evaluation/build scope and state its recorded consequence. During an order, keep artifact revisions and bounded candidate Improvements distinct; never silently mutate the active release. Evals must judge actual behavior/output against explicit questions and anchored criteria. A filename, schema pass or successful command is only supporting evidence. Inspectable Langfuse inputs/outputs, datasets, experiment items, ratings and rationale must be confirmed remotely before qualification. Local passing evidence remains awaiting telemetry. Templates, synthetic tests and self-ratings never certify Director/model/creative quality. Record exposed usage with its source; hidden context/reasoning and unavailable host tokens stay unknown.


Use the selected company's live `/report` record for workflow/run counts, memory, supplied context, artifacts, evaluations and telemetry status. Read `company/evaluation-and-learning-contract.md` when present. Every new or changed workflow needs the executable evaluation pair and regression cases before qualification. Record actual host token metadata and separately sourced reference prices; never invent usage, billed cost, memory retention or independent acceptance. End meaningful work with a concise human tracking receipt and report/trace links. Keep company content in the selected home and reusable product code in source; no publication, hidden pursuit or cross-company routing is implied.

For setup or a missing company, use the bundled setup skill. Resolve the launcher at scripts/launch.sh relative to the installed plugin root. Use it for report and experiment operations that are not exposed by the six MCP tools; never require a separate global SpielOS installation. The runtime operating guide is bundled at runtime/company/README.md. Keep those commands internal and give the user names, findings and next decisions.
