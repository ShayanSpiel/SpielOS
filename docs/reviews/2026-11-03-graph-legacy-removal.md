# Retire architecture graph and legacy Goal observer

Bounded source Improvement; stage: implementation and evaluation.

Need: remove the standalone source graph feature and retired Goal-based observer while preserving the current company dashboard. Users: product maintainers. Window: this source cleanup. Baseline: the two retired surfaces exist; current reporting has its own UI and bounded workflow read model. Runtime performance and business impact are not measured.

Constraints: preserve unrelated edits, current reporting/UI, workflow scorecard and outcome recording, usage, evaluation and Langfuse behavior. No installed company, plugin, credentials or remote service changes. Remove generated graph-only diagnostics outside source; do not create preservation copies. Historical mixed-purpose review records remain historical evidence, not current feature documentation.

Exact allowed source files (deletion or scoped edit):

- `company/ARCHITECTURE.md`
- `company/GRAPH.md`
- `company/commands/goal_runtime.py`
- `company/graph/__init__.py`
- `company/graph/__main__.py`
- `company/graph/architecture.json`
- `company/graph/experiments.py`
- `company/graph/explorer.html`
- `company/graph/model.py`
- `company/graph/runtime.py`
- `company/graph/schema.json`
- `company/init_templates/agents/company/ARCHITECTURE.md`
- `company/init_templates/agents/company/GRAPH.md`
- `company/init_templates/agents/company/commands/goal_runtime.py`
- `company/init_templates/agents/company/graph/__init__.py`
- `company/init_templates/agents/company/graph/__main__.py`
- `company/init_templates/agents/company/graph/architecture.json`
- `company/init_templates/agents/company/graph/experiments.py`
- `company/init_templates/agents/company/graph/explorer.html`
- `company/init_templates/agents/company/graph/model.py`
- `company/init_templates/agents/company/graph/runtime.py`
- `company/init_templates/agents/company/graph/schema.json`
- `company/init_templates/agents/company/observability/__init__.py`
- `company/init_templates/agents/company/observability/read_model.py`
- `company/observability/__init__.py`
- `company/observability/read_model.py`
- `company/tests/fixtures/graph/benchmarks.json`
- `company/tests/test_architecture_stabilization.py`
- `company/tests/test_graph_architecture.py`
- `company/tests/test_graph_experiments.py`
- `company/tests/test_graph_runtime.py`
- `company/tests/test_learning_loop.py`
- `company/tests/test_observability_dashboard.py`
- `company/tests/test_spine_identity.py`
- `docs/reviews/2026-11-03-graph-legacy-removal.md`

Execution: remove graph modules/templates/tests/fixture/documentation; remove the legacy Observer class, package export, compatibility observe wrapper and tests dedicated to that removed projection. Preserve the shared bounded reporting functions exactly. Remove the current architecture-documentation entry.

Evaluation: compare pre/post hashes for dashboard/UI/support modules and the shared reporting-function bytes; search for executable references to removed features; run boundary/parity checks, the full behavior suite and scenario acceptance. Generated diagnostic records remain outside source. Existing dashboard behavior tests are the acceptance criteria; passing local tests do not grant independent or remote qualification. No release-readiness claim without an isolated installed-wheel smoke journey.

## Observed acceptance

- Removed 23 source/template/test/document files and 188 generated graph-only diagnostic files outside source.
- Removed the legacy Observer class, package export, compatibility wrapper and tests dedicated to that projection. Current workflow scorecard and outcome-recording function bytes are unchanged.
- All 36 protected dashboard/UI/support file hashes are unchanged. No dashboard code, assets, routes, tests or behavior were edited.
- No executable graph/Observer references remain in company code, tools or current product documentation. Mixed-purpose historical review scopes remain evidence of their original revision.
- Full regression: 481 tests passed. Focused dashboard/package/compatibility regression: 64 tests passed. Scenario acceptance: all 66 declared scenarios verified by 57 passing scenario tests.
- Source boundary and runtime parity checks passed; source syntax parses and the patch has no whitespace errors. Unrelated pre-existing review documents were preserved.

Inspectable diagnostic evidence is outside source: scope-and-baseline.json, preservation-check.json, removal.json, regression.log, scenario-acceptance.json, scenarios.log and acceptance.json. Independent acceptance and remote qualification are not claimed. No new isolated installed-wheel journey was run for this cleanup, so it makes no release-readiness claim. No installed company, live dashboard, plugin or remote provider was changed.
