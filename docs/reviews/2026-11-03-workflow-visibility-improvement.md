# Workflow visibility and delivery Improvement

Need: show recorded candidate workflow histories when their source definition is absent, and prevent a large activity backlog from starving workflow delivery. Baseline: the selected company has recorded candidate runs with no current definition and pending workflow events; remote qualification is not established.

Allowed files: `company/reporting.py`, `company/observability/automatic.py`, `company/tests/test_report_workspace.py`, `company/tests/test_report_receipts.py`, their corresponding runtime templates under `company/init_templates/agents/company/`, and this review. Preserve unrelated edits. No company data or credentials belong in source. No remote telemetry export is authorized by this source change.

Acceptance: synthetic tests demonstrate historical candidates are visible without being represented as accepted, existing definitions are not duplicated, and workflow queue records get an opportunity despite activity backlog. Run runtime parity and source-boundary checks. Independent acceptance and live Langfuse delivery remain separate.

Evidence: the synthetic reporting, receipt and continuous-evaluation suites passed (28 tests); source boundary and runtime-template parity passed. The queue change gives both types an opportunity in a bounded wake and avoids repeating experiment resource synchronization for every selected event. A pending experiment still requires successful remote resource setup and readback. No live delivery, independent acceptance or release qualification was performed.
