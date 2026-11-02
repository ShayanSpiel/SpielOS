# SpielOS source checkout

This tree owns reusable product code, generic installation templates,
packaging, documentation, and synthetic test fixtures only. It is not an
installed company home. Do not install owner Departments, Skills, bundles,
workflows, host configuration, private state, credentials, or generated media
here. Generic core modules and synthetic fixture schemas are product code;
they must contain no owner's production instructions, identity, or data.
Generic host adapter templates ship under `company/init_templates/hosts/`.

`.spielos-boundary.json` declares this tree as source. Runtime state writes
and home installation inside it are refused. Run owner commands from an
explicit, separately installed home. Never delete or relocate existing files
without owner authorization, and never create preservation copies unless
requested. Publishing credentials may remain in an ignored local `.env` when explicitly
authorized; never commit them. Run `python3 -B tools/check_source_boundary.py`
to audit the working tree, including ignored owner directories.

This repository is the source product used to create and update SpielOS homes. It runs from source with:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -B -m company COMMAND
```

The public product uses Company, Workflow, Run and Improvement. GODAE is bounded development, not an autonomous pursuit loop. New execution uses company.workflows.runs.WorkflowRuntime and requires no Goal tables or product scheduler. Historical Goal code is a compatibility library only; do not reintroduce its commands, polling, repair or pursuit into new operation. Departments are optional ownership groupings; Agents and Skills are workflow implementation choices.

`company/init_templates/` is what `spielos init` ships. Keep runtime files byte-identical between `company/` and `company/init_templates/agents/company/` using `tools/sync_runtime_templates.py`. Private `.spielos/` runtime state is ignored by Git.

Owner voice is the default: names, human progress and outcome sentences. Raw identifiers, metric keys, enums, JSON dumps and CLI answer syntax belong in payloads and the final Machine reference for the Director. The owner answers in plain words; the Director records the answer.

Memory is explicit and classified. Owner preferences use owner scope; owner strategic direction uses strategy scope; operational workflow lessons cite evaluated runs of that same workflow. Never fabricate a baseline, strategy, learning or business impact. Retire stale claims without erasing evidence. Historical direct-work lessons stay scoped and require reviewed mapping before reuse.

System changes require a bounded Improvement, exact allowed files and actual acceptance evidence. External actions—including publishing or sending—remain separately approval-gated for the exact action, destination, content and scope. A quality pass grants no external permission.

Activepieces remains inactive under the owner's current instruction. Offline MCP preparation and local contract tests are allowed; live connection, execution, publishing and enabling are held.

Public documentation and screenshots use neutral synthetic companies unless the owner explicitly requests a supplied reference image. Do not ship machine paths, customer names, private chat transcripts, historical owner approvals or instructions copied from a development conversation. Public repository URLs and author/license attribution are product metadata, not company context. Generated diagnostic evidence stays outside source; reviewed synthetic documentation images may live in `docs/images/`.

For reviews, record a bounded source Improvement with exact allowed files and inspectable acceptance evidence. Preserve unrelated working-tree edits. Run boundary/parity checks, behavior tests, scenario acceptance and an isolated installed-wheel smoke journey before claiming release readiness. Do not invoke retired commands even in release CI. `docs/reviews/` records review findings and limits; a passing suite does not establish independent acceptance or remote qualification.
