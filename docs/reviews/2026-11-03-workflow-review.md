# Workflow, evidence and installation review — 3 November 2026

This review covers revision `a487bee` plus the existing uncommitted graph
documentation changes. It is a bounded source review, not independent acceptance
or a release qualification. The companion Improvement records the exact scope.

## Findings

1. **P1 — Historical digest-only exports disclose rubric text.**
   `company/observability/experiments.py:69` uses the objective as a dataset
   description and includes criterion questions and anchors in score-config
   descriptions even when `payload_policy` is `digests_only`. A local call with
   synthetic private strings reproduced their inclusion without any network
   request. This affects historical integrations using that policy; current
   reviewed-evidence exports deliberately include approved inspectable material.
   Make the resource projection respect the selected privacy policy and test
   every emitted field before qualifying remote delivery.
2. **P1 — Concurrent system reviews can overwrite a decision.**
   `company/improvements.py:160` reads the pending state and evidence before an
   unconditional update at line 178. Two real threads with synthetic SQLite
   state both returned success: rejection was overwritten by acceptance. A
   withdrawal or new evidence can similarly race. Bind the decision atomically
   to the pending stage and exact evidence version; add concurrency regression.
3. **P1 — The 51st experiment can be starved indefinitely.**
   `company/observability/experiments.py:164` repeatedly selects the oldest 50,
   including already synchronized entries. In an in-memory reproduction with
   51 synthetic experiments and mocked successful resource creation, two syncs
   left the last experiment unsynchronized. The confirmation query at line 206
   can similarly starve newer records behind 50 unresolved entries. Use fair,
   resumable selection and verify remote changes with a qualified test project.
4. **P2 — Fresh CLI installation silently lacks chat capture.** A synthetic
   installed-home Codex prompt hook injected context successfully, but observe
   and Stop hooks returned empty responses and recorded no activity after plain
   `spielos init`: `capture_hook` returns early without the reviewed-evidence
   configuration (`company/observability/sessions.py:321`). The CLI hands setup
   to Director and does not itself ask for Langfuse. The plugin has a separate
   capture setup path. Clearly expose setup and missing capture in the CLI/host
   journey, without silently enabling content export or connecting a provider.
5. **P2 — Dashboard agent history is incomplete without a count warning.**
   `company/reporting.py:89,154` computes agent run counts and workflow
   associations from the latest 300 runs. Older associations disappear and
   counts understate history; per-workflow counts use a full SQL count. Aggregate
   over the complete population or label the bounded window explicitly.
6. **P2 — Acceptance loses the reviewer's reason.**
   `company/improvements.py:108` requires a reason, but the normal accepted
   release writes a fixed reason in `company/workflows/runs.py:650`. Preserve
   the actual reason in the same transaction as the release.
7. **P2 — Verify reviewer independence from authorship.** Candidate creation
   records a builder (`company/workflows/runs.py:608`); release checks the
   reviewer against case-run actors, not that builder (lines 634–635). A builder
   with review authority may therefore accept after another actor runs cases.
   This is a source-level concern requiring an end-to-end regression and a clear
   policy on independence from the candidate author.
8. **P2 — Workflow change scope is a declaration, not a measured diff.**
   `company/improvements.py:93` checks the caller's `changed_files` list against
   the allowed list; it does not establish that no other file changed. Treat it
   as declared scope until a measured comparison is added. System changes have a
   separate measured-file path, which also needs to establish completeness.

## GODAE and architecture

GODAE records an agreed need and scope, observations and criteria, architecture,
a candidate, and evaluated acceptance or revision. A release requires actual
candidate case results and a separate review under configured authority. Runs
pin releases, context and evaluation. Evidence, explicit feedback and classified
memory can inform a subsequent bounded Improvement. These are useful controls;
they do not automatically define or run a new experiment after each turn, edit
the workflow, promote a winner, or demonstrate quality gains after ten iterations.
Automatic same-host evaluations are diagnostics, not independent acceptance.
The graph experiment is limited to a protected ordering-edge comparison, not a
general autoresearch optimizer. Tokens, cost and time cannot be optimized without
measured comparable populations, actual host usage and independent quality gates.

Memory supports owner, strategy and workflow scopes, retirement and provenance;
operational lessons require evaluated same-workflow evidence. Retrieval is
bounded and lexical. These constraints do not establish relevance or causal
improvement in real usage. The dashboard displays observed records and partial
usage; unavailable host tokens and costs remain unknown. Evals have explicit
criteria, anchors, coverage and blocking gates, but synthetic passes do not
establish calibrated real-world quality. Langfuse's remote readback, datasets,
experiments and scores were not tested against a live service in this review.

The inspected non-test Python source is approximately 15,498 lines in 80 files,
plus a byte-identical shipped runtime template. Historical Goal modules remain
compatibility code, not the current operational loop; old tests are not proof of
new workflow improvement. Runtime duplication serves packaging, so line count
alone does not justify deletion. First inventory compatibility consumers; then
separate legacy entry points and split the large workflow runtime along state,
evaluation and export boundaries with behavior tests. Generating the template
at build time could reduce maintenance duplication if installed update parity is
preserved. Each change needs a separately bounded Improvement.

## Executed checks and limits

- Source boundary audit and runtime-template parity passed. Existing graph
  documentation edits were preserved.
- Full local unit discovery: 523 tests passed in 129 seconds.
- Isolated built wheel, Python 3.14, synthetic home: distribution smoke passed
  14 checks, including fresh install, context, catalog, dashboard snapshot,
  candidate, a real local three-case experiment and update preservation.
- Scenario acceptance: 57 tests passed; the runner reported 66 locally verified
  scenarios. These are synthetic scenario assertions, not independent acceptance.
- Forty-two targeted evaluation, observability, dashboard, export and graph
  experiment tests passed with offline or mocked providers.
- Synthetic installed hook payload: context injection succeeded; activity and
  Stop capture remained empty before separately configuring capture.
- The race, experiment starvation and privacy projection were reproduced with
  local synthetic data; the remaining findings are source inspection unless
  otherwise stated.

The installed-wheel journey used the following sequence with an empty temporary
directory outside the checkout. The regular wheel build installed its build
dependencies; an initial no-build-isolation attempt failed because setuptools
was absent from that interpreter.

```sh
python3 -m pip wheel --no-deps --wheel-dir "$REVIEW_DIR/wheels" .
python3 -m venv "$REVIEW_DIR/venv"
"$REVIEW_DIR/venv/bin/python" -m pip install "$REVIEW_DIR/wheels/spielos-10.3.12-py3-none-any.whl"
python3 -B tools/smoke_distribution.py --python "$REVIEW_DIR/venv/bin/python" --expected 10.3.12
"$REVIEW_DIR/venv/bin/spielos" init --dir "$REVIEW_DIR/company"
```

The last command created a verified synthetic home. A synthetic Codex
`UserPromptSubmit` JSON payload sent to its context hook returned the company
projection; a `Stop` payload sent to its observe hook returned `{}` before
capture setup. This directly calls installed scripts and does not prove the host
loaded, trusted or executed them. Reproduce the broader local checks with
`python3 -B tools/test_acceptance.py --out "$REVIEW_DIR/acceptance.json"`,
`python3 -B tools/check_source_boundary.py`, and
`python3 -B tools/sync_runtime_templates.py`.

No actual interactive model conversation, GUI-host trust flow, live Langfuse
project, real customer workflow, ten-iteration comparison, external action or
independent review was performed. The wheel smoke exercises multiple case types
for one synthetic workflow, not multiple real business workflows. Dashboard
browser interaction and all host/OS combinations remain unqualified in this
review. Logs and synthetic generated evidence are retained outside source.
