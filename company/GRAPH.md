# Executable architecture graph

## Bounded source Improvement

Name: Inspectable and testable architecture, version 1.
Scope: reusable source architecture and synthetic qualification. This source brief is not an installed-home runtime record or production acceptance. Changes to an installed company or plugin require their own explicit scope.

Baseline: no general DAG engine or explorer; bounded workflow execution and evaluations already exist. Performance and model-quality improvement are unknown.
Target: a typed, executable, file-based DAG with actual runtime delegation, protected comparisons, recovery tests and an interactive explorer.
Users: maintainers and workflow builders. Window: this bounded implementation and its acceptance run.
Constraints: no new dependencies, agents, live providers, production changes, capability deletion, external publication, autonomous promotion or owner state in source. Existing uncommitted work is preserved.

Exact allowed files are `company/graph/__init__.py`, `company/graph/schema.json`, `company/graph/architecture.json`, `company/graph/model.py`, `company/graph/runtime.py`, `company/graph/experiments.py`, `company/graph/__main__.py`, `company/graph/explorer.html`, their eight counterparts under `company/init_templates/agents/company/graph/`, `company/tests/test_graph_architecture.py`, `company/tests/test_graph_runtime.py`, `company/tests/test_graph_experiments.py`, `company/tests/fixtures/graph/benchmarks.json`, this document and `company/init_templates/agents/company/GRAPH.md`.

Execution design: a small graph coordinator delegates accepted workflow releases to WorkflowRuntime. Architecture inspection nodes check actual source references and do not pretend to execute Director/model tasks. All generated state is external to source. File traces supplement, never replace, runtime authority.
Evaluation design: deterministic structural tests plus actual execution, failure/restart, protected-benchmark and browser interaction tests. Test passes do not qualify creative output, model quality, business outcomes or unavailable remote providers. Acceptance evidence records observed outcomes and measured files; independent production acceptance remains separate.
Alternatives: replace the runtime (rejected: duplicates working safety/recovery); add React/graph services (rejected: no existing frontend and unnecessary dependencies). Cost envelope: bounded local tests, with unavailable host/model usage explicitly unknown.

Implementation and measured acceptance details follow below when available.
