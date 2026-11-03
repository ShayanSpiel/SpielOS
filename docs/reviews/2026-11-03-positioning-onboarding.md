# Positioning and onboarding Improvement

Stage: bounded implementation and local evaluation. Independent acceptance and publication are pending.

Need: help a new user understand SpielOS, install it in their chosen host, and reach a useful first workflow without chasing another page. Existing conversion and business impact are unknown. Preserve the supported installation behavior and unrelated working-tree changes; do not connect providers or publish.

Exact allowed files: `README.md`, `docs/tester-guide.md`, `company/init_templates/integrations/spielos/README.md`, `company/init_templates/integrations/spielos/plugin.json`, `company/init_templates/integrations/spielos/skills/setup/SKILL.md`, `pyproject.toml`, `company/runtime/onboard.py`, `company/init_templates/agents/company/runtime/onboard.py`, `docs/architecture/README.md`, `docs/architecture/*.svg`, `company/tests/test_cli_onboarding_journey.py`, and this record. The source and shipped runtime must remain byte-identical.

Acceptance: installation instructions identify prerequisites and supported hosts, give actionable installation and setup steps in place, distinguish installation from creating a company, and lead to an example first job. Positioning must reflect implemented capabilities and retain consequential release and authorization limits. Verify runtime parity, boundary, relevant onboarding and installation tests. GitHub descriptions and profile bio are proposed below; changing remote public profiles or repositories requires separate exact-action approval.

## Evidence and limits

- `python3 -B tools/check_source_boundary.py`: passed.
- `python3 -B tools/sync_runtime_templates.py`: zero diverged runtime files.
- `PYTHONDONTWRITEBYTECODE=1 python3 -B -m unittest company.tests.test_onboarding company.tests.scenarios.test_installation company.tests.test_plugin_distribution`: 19 tests passed. The first run exposed the plugin short-description length limit; the revised description passed on rerun.
- `git diff --check`: passed. Unrelated existing changes were preserved.
- This is local acceptance evidence, not independent acceptance, a release-readiness claim, or proof of improved conversion. The actual Codex marketplace install and native Windows journey were not exercised. Claude Code's documented marketplace flow still requires separate marketplace and install commands; no unsupported combined command is claimed.

## Proposed GitHub copy for separate approval

- `ShayanSpiel/SpielOS` description: “Turn recurring business work into reusable AI workflows with company context, evaluation and review. For Codex and Claude Code.”
- `ShayanSpiel/SpielOS-Plugin` description: “Build reusable AI workflows for your company in Codex and Claude Code. Keep context, decisions and results together.”
- `ShayanSpiel` profile bio: “Building SpielOS: reusable AI workflows that know your company and improve with evidence.”

These are proposals only. No remote profile, repository, release or marketplace has been changed.
