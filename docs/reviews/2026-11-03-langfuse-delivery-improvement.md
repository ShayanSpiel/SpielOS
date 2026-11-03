# Langfuse backlog delivery Improvement

Need: make bounded host wakes progress on both newly queued and unconfirmed records while resource setup is slow or mismatched. Preserve stable identities, immutable evidence, project checks, privacy policies, and exact readback; never blindly resend an uncertain event or overwrite a conflicting remote resource.

Exact source scope: `company/observability/automatic.py`, `company/observability/experiments.py`, `company/observability/evaluators.py`, their runtime template twins, `company/tests/test_report_receipts.py`, `company/tests/test_evaluation_experiments.py` if present, and this record. The selected company update is limited to the installed versions of those three runtime modules, preserving other owner files. External delivery is restricted to the configured project and existing queued approved evidence. Record local and remote outcomes separately; no model quality or release acceptance is inferred.

Acceptance: tests exercise queue fairness and slow/unavailable resource setup, preserving readback semantics; source boundary and runtime parity pass. Verify delivery against actual queue state where safely possible and explicitly report unresolved remote conflicts.

## Local verification

The focused delivery, evaluation and reporting tests passed (42 tests); the scenario suite passed (66 verified scenarios); an isolated installed wheel passed its 14-check local journey. Runtime template parity, source boundary and patch whitespace checks passed. These checks do not establish remote qualification or independent acceptance. Queue progress requires later host-triggered wakes; no polling daemon or scheduler is installed. Uncertain sends are read back without blind re-ingestion, and malformed historical records remain preserved and unqualified.
