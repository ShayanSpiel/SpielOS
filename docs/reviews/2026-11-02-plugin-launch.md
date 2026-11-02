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

## Installed-host MCP correction (10.3.7)

The actual public Git marketplace install exposed a Codex 0.146.1 path-resolution failure: the MCP cwd variable was treated as a literal subfolder. Use plugin-relative cwd `.` and launcher `./scripts/launch.sh` in portable and compatibility MCP configuration. Verify the effective Codex configuration and an actual tool call through its app-server, not only direct server tests. Versioned account/public packages are updated together.

Corrective acceptance: the real Codex app-server successfully called `select_company` through the installed 10.3.7 plugin and discovered all six MCP tools. The regression now executes the actual manifest command, args and working directory, so it catches this packaging failure. No model turn or paid provider call was used.

## Tester onboarding across hosts

The selected company used by the website has an existing reviewed-evidence/export policy, automatic review, both host hook configurations and a company-specific dashboard. These are private company setup, not reusable product assets. Generic installs must provide the same product capabilities through explicit setup without copying company identity, custom artifacts, credentials or external connections.

Additional allowed files for tester readiness: company/init_templates/hosts/claude/settings-fragment.json; company/init_templates/hosts/claude/hooks/spielos-observe.py; company/init_templates/hosts/codex/hooks/spielos-observe.py; docs/tester-guide.md. Existing bootstrap, plugin setup/help/Director/dashboard skills, manifests, exporter, tests, READMEs and runtime twins remain in scope. Add Claude's own marketplace catalog to the generated distribution, use its supported plugin-root expansion only in its compatibility MCP file, and keep Codex's verified relative cwd launch separate. Test real host loaders and actual installed hook commands for both hosts. No production home or credentials are copied or changed.

Also allowed: company/tests/test_import_bundle.py. Its pristine-home comparison must normalize both hosts' installed absolute hook paths while continuing to verify that bundle import leaves host settings byte-identical.

Production qualification was checked against operations.require_release_telemetry: local tracking/drafts/experiments require no provider, but production release requires exact verified Langfuse evidence and independent review. Tester guidance now states that distinction explicitly; governance was not weakened to make setup appear complete. The final coherent tester package is 10.3.9.

## Native Windows and tester positioning

Scope extends to native Windows because the requested tester distribution must work across supported desktop devices. Exact additional files: company/platform.py and runtime twin; company/security.py and twin; company/home.py and twin; company/__main__.py and twin; company/workflows/runs.py and twin; company/graph/runtime.py and twin; company/observability/automatic.py and twin; company/observability/evaluators.py and twin; company/observability/usage.py and twin; company/tests/test_platform.py; .github/workflows/check.yml; .github/workflows/publish.yml; tools/smoke_distribution.py. Existing reporting/bootstrap/plugin/build/tests/docs files remain in scope. Replace POSIX-only locking/identity assumptions with explicit platform adapters; Windows authority requires private ACLs and its actual user SID, never fabricated UID/chmod acceptance. Runtime directory aliases use owner-created junctions on local Windows volumes without Developer Mode; preserve canonical company data and refuse escapes. MCP uses a supported cross-platform Python entrypoint rather than /bin/sh. Verify native Windows fresh installation, both hook contracts, dashboard authentication, context/review/usage receipts, workflow experiments, permissions and update preservation in Windows CI. Do not infer Windows qualification from a mocked os.name or from POSIX tests.

User-facing listing examples now target real company jobs: outbound email workflow for an explicit ICP, evidence-backed lead research agent, and quality-tested recurring work. These are guided builds with selected sources and criteria, not fictitious preinstalled integrations or permission to send email. Public install links must distinguish a Git marketplace from private account visibility and public-directory approval. The website company's custom dashboard is an extension; reusable presentation may be generalized only without copying its private data or artifacts.

Reference dashboard adoption: the supplied evaluation-lab URL is the intended product interface. Additional exact files: company/report_ui/index.html, company/report_ui/workspace.js, company/report_ui/workspace.css, company/report_ui/logo.png and runtime twins. Generalize its sidebar, subject selection, Home/History/Quality/Activity structure, memory/context/delivery inspection and visual language against the live report API. Do not ship its private fixture files, company role labels, historical claims, film gallery, planning notices or owner-only links. Empty states show absence of evidence. The generic interface and explicit custom extensions share the same renderer and data contracts.

First-use onboarding extension: new users must be asked whether to connect Langfuse now or continue locally, and receive their own dashboard and a short reading guide after the first meaningful chat. Additional exact files: company/onboarding.py and runtime twin; company/tests/test_onboarding.py; company/observability/langfuse.py and runtime twin. Existing plugin entry/setup/Director/help/dashboard instructions, host context/Stop adapters, shared receipts, report API/shell and tester docs remain in scope. Store only onboarding choices and verified connection metadata in the selected home; keys stay in a private authority-controlled local file and are never echoed into chat, report JSON, logs or public files. A local connection form must name the exact destination and evidence exported, require the user's submit, enforce same-origin authenticated POST, and verify the selected project before enabling export. Synthetic tests must not contact a real project. Mark the dashboard tour delivered only after actually presenting it; never infer a user's connection consent from installation or time elapsed.
