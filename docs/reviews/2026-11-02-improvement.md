# Release health and public onboarding Improvement

Stage: implementation and evaluation; independent acceptance not granted.
Authorization: repository owner's request to review architecture, health, privacy and onboarding in this chat. This is a bounded source-development brief, not a production workflow or installed company record.

Need: make the current workflow architecture understandable and verify the release journey before technical review.
Baseline: source boundary and runtime parity pass; publishing smoke tests still invoke retired commands. Broader readiness is under investigation, not presumed.
Target: actionable source-backed findings, current install/update examples, reproducible local acceptance, privacy-safe screenshots and regression fixes for demonstrated defects.
Users: adopters and technical reviewers. Window: this source review and local validation.
Constraints: preserve existing uncommitted work; no deletion/relocation, live providers, personal home changes or self-approval; Git commit/push subsequently authorized by the owner. Synthetic homes and generated evidence live outside source. Only reviewed synthetic documentation screenshots are source assets.

Exact allowed files:

- docs/reviews/2026-11-02-improvement.md
- docs/reviews/2026-11-02-technical-review.md
- docs/images/spielos-in-codex.png
- docs/images/company-overview.png
- docs/images/company-memory.png
- docs/images/commands-and-context.png
- README.md
- AGENTS.md
- .github/workflows/publish.yml
- .github/workflows/check.yml
- tools/smoke_distribution.py
- tools/capture_docs.py
- tools/sync_runtime_templates.py
- company/reporting.py
- company/init_templates/agents/company/reporting.py
- company/__main__.py
- company/init_templates/agents/company/__main__.py
- company/context/workflow.py
- company/init_templates/agents/company/context/workflow.py
- company/tests/test_operational_contract.py
- company/report_ui/report.js
- company/init_templates/agents/company/report_ui/report.js
- company/tests/test_report_workspace.py
- company/README.md
- company/init_templates/agents/company/README.md
- company/ARCHITECTURE.md
- company/init_templates/agents/company/ARCHITECTURE.md
- company/GRAPH.md
- company/init_templates/agents/company/GRAPH.md
- homebrew/spielos.rb
- install.sh
- company/runtime/onboard.py
- company/init_templates/agents/company/runtime/onboard.py
- company/runtime/bootstrap.py
- company/init_templates/agents/company/runtime/bootstrap.py
- company/init_templates/hosts/codex/agents/director.toml
- company/init_templates/hosts/claude/agents/director.md
- company/init_templates/hosts/opencode/agents/director.md
- company/ACCEPTANCE.md
- company/init_templates/agents/company/ACCEPTANCE.md

Observe: inspect execution, approval, memory/retrieval, hook, report, graph and packaging code; run existing suites and actual clean-wheel commands. Record failing behavior before fixing it.
Design: retain the shared workflow authority. Repair narrow contract defects; replace obsolete release smoke checks with an isolated installed-wheel journey; add pre-release checks; document real limitations rather than assert certification. Keep compatibility libraries until an authorized compatibility boundary.
Alternative: a large rewrite would invalidate existing evidence and is outside this bounded review.
Execution contract: local source edits only in this list, mirrored runtime changes, no owner data in public assets.
Evaluation contract: targeted regressions, full unit suite, scenario acceptance, boundary/parity audits, built-wheel isolated smoke and browser inspection of the actual report. Missing remote/host/OS coverage remains explicit.
Cost envelope: local computation; no paid provider/model calls. Independent quality/business impact unknown.
Acceptance evidence: final technical review links actual observed results and local evidence. No independent reviewer identity will be fabricated.

Owner refinement: use the supplied reference screenshot as the single README visual and emphasize Langfuse evaluations and experiments. The owner explicitly authorized that supplied image and pushing all current changes to the configured GitHub remote; this does not authorize package-registry publication or live integrations.
