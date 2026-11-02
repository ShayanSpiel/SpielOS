# Bounded Improvement: plugin-first SpielOS

Scope: plugin-first desktop distribution, official branding, GitHub/plugin presentation and new-user acceptance. Public-directory approval and legal attestations remain platform gates; no provider activation is included.
Need: replace separate CLI setup with a desktop plugin that carries its runtime and guides company selection/creation in conversation.
Baseline: the local plugin calls an externally installed `spielos mcp`, has no logo/onboarding and no account publication. Public source has verified POSIX behavior; before/after dashboard improvement remains incomplete.
Target: self-contained desktop package, verified fresh-home operation, supplied branding, clear outcome-led listing/README and actual install links with truthful distribution state.
Users: founders and operators using supported local coding-agent hosts. Window: this plugin release and acceptance.
Constraints: no owner state in source or plugin cache; no hidden installs/downloads, telemetry connections, permission grants or self-acceptance. Retain the existing six-tool workflow core. Do not equate private publication or a repo marketplace with universal-directory approval.

Exact source files allowed:

- docs/reviews/2026-11-02-plugin-launch.md
- docs/plugin-privacy.md
- docs/plugin-terms.md
- README.md
- company/init_templates/integrations/spielos/plugin.json
- company/init_templates/integrations/spielos/mcp.json
- company/init_templates/integrations/spielos/README.md
- company/init_templates/integrations/spielos/assets/logo.png
- company/init_templates/integrations/spielos/scripts/launch.sh
- company/init_templates/integrations/spielos/scripts/entry.py
- company/init_templates/integrations/spielos/skills/setup/SKILL.md
- company/init_templates/integrations/spielos/skills/spielos-company/SKILL.md
- company/init_templates/integrations/spielos/skills/spielos-build-workflow/SKILL.md
- company/init_templates/integrations/spielos/skills/spielos-run-workflow/SKILL.md
- company/init_templates/integrations/spielos/skills/spielos-review-output/SKILL.md
- tools/build_plugin.py
- company/tests/test_plugin_distribution.py

Design: build a standalone plugin archive outside source from reusable runtime and installation templates. A POSIX launcher locates supported Python and runs isolated bundled code; no global SpielOS installation is used. Guided setup handles explicit company creation/selection through bundled commands. Company data stays in the user-selected home. Bundle no lifecycle hooks; normal company hooks retain normal host review.
Evaluation: archive inventory and icon checks, isolated MCP startup/tool discovery, missing/source-home refusal, actual setup/status/report/candidate journey, source boundaries, existing regression/scenario/wheel checks and supported host installation. Record unavailable public review separately.
Distribution: publish a public Git-backed Codex marketplace/package and eligible account plugin without claiming universal listing. Preserve account identity if found. New public marketplace source exports and package archives are build outputs outside this checkout. Only reusable product files are included, from the explicit build inventory.
Cost envelope: local checks and normal hosting; no paid model calls or live provider execution.


Canonical product boundary: this distribution contains the SpielOS company runtime, dashboard, context capture, evaluation and usage receipts. No alternative implementation or owner company belongs in the package. Replaced package files are explicitly removed rather than retained by upload overlay. Account identity is preserved; unrelated plugins and company folders are outside scope.

Additional exact files allowed: company/init_templates/integrations/spielos/.codex-plugin/plugin.json, company/init_templates/integrations/spielos/.mcp.json, company/init_templates/integrations/spielos/.claude-plugin/plugin.json, tools/export_plugin_marketplace.py. Generated public marketplace and archives stay outside source. Verify that bundled runtime files are byte-identical to company/; verify actual dashboard HTTP authentication, supplied-context recording, Stop evaluation request and token receipt through the packaged home. Retain normal host hook trust; do not fabricate native rich-card support or remote acceptance.

Also allowed: tools/smoke_distribution.py, replacing its retired-command invocation with CLI help inspection, as required by source instructions. No retired operation is invoked by the release smoke journey.

Also allowed: company/tests/scenarios/test_reporting.py. Its clean-install journey must execute the real bundled plugin launcher, replacing the old assertion that a separately installed global SpielOS command is the plugin. Preserve all actual workflow execution, evaluation, independent review and authorization assertions.

New-user acceptance extension covering Director, commands, hooks, dashboard, evaluations and chat receipts. Exact additional files: company/observability/receipts.py and its runtime twin; company/runtime/config.py and its runtime twin; package.json; company/init_templates/integrations/spielos/skills/director/SKILL.md; company/init_templates/integrations/spielos/skills/dashboard/SKILL.md; company/init_templates/integrations/spielos/skills/help/SKILL.md. Existing allowed entry.py, setup skill, READMEs, privacy notice and plugin tests cover local-only capture setup and discovery. New version 10.3.6 keeps product/package identity coherent. Setup records local context, exposed activity and bounded self-review only in the explicitly selected company; it creates a disabled-export policy only if none exists, preserving all existing policies. No Langfuse connection or live provider is enabled. Verify a zero-configuration new company, local-only receipt, actual pending review and judgment, no repeated Stop continuation, dashboard readback, visible skill discovery and ordinary hook trust. A rendered native card and independent quality acceptance must not be claimed from a Markdown receipt or scripted event replay.

Also allowed: company/reporting.py, company/report_ui/report.js and their runtime twins. A local-only dashboard must not fabricate a Langfuse project/trace URL or call unexported local records a broken cloud connection.

Also allowed: company/runtime/bootstrap.py and its runtime twin; company/tests/test_update_preservation.py. Fresh Codex hook commands must use the supported interpreter selected during setup, rather than an unrelated older `python3` on PATH. Recognize only exact owned hook paths when refreshing, and preserve unrelated owner hooks.

Dashboard review found the existing evaluations renderer was absent from navigation. The release adds the Evaluations tab, frozen pending requests, anchored criteria, recorded judgments and their evidence; no synthetic quality rating is inferred.


## Acceptance evidence for 10.3.6

- Source boundary audit: clean; runtime twins: zero differences.
- Full regression: 507 tests passed. Dedicated plugin journey: eight tests passed, including the actual installed hook command/interpreter, context capture, local-only policy, preserved existing policy, Stop continuation guard, exposed token receipt, pending rubric and recorded diagnostic judgment.
- Scenario acceptance: all 66 scenario contracts verified across 57 journeys. The acceptance runner retains its separate overall-qualification limits; local passing evidence is not independent or remote acceptance.
- Isolated built-wheel journey: 14 checks passed at 10.3.6, including company setup, update preservation and actual representative/held-out/negative workflow experiment runs. Retired operations are absent from the smoke journey.
- Codex app-server discovery from an isolated plugin installation: all eight namespaced skills enabled, with no discovery errors. Includes setup, director, dashboard, help and the four workflow/company skills.
- Actual browser inspection of a synthetic installed company: authenticated dashboard; captured context documents; exposed 123 input / 21 output test tokens; local-only activity; visible Evaluations navigation, pending Director review and all six anchored criteria. The test metadata is synthetic and is not a model quality or performance benchmark.
- Account package updated in place to 10.3.6; the wrong implementation's 35 obsolete paths were deleted in the corrective release. Public GitHub marketplace is a generated distribution of this same source, with a file-hash inventory.

Limits: hooks still require normal host trust and an explicitly selected company workspace. No trust bypass, production company activation, paid model test, live Langfuse delivery, independent acceptance, native-card guarantee or universal-directory approval was performed. End-of-chat receipts are rendered Markdown driven by actual host-exposed events. A full before/after workflow improvement scorecard remains outside this release.
