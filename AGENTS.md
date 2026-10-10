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
requested. Previously relocated originals remain preserved in their home.
Publishing credentials may remain in an ignored local `.env` when explicitly
authorized; never commit them. Run `python3 -B tools/check_source_boundary.py`
to audit the working tree, including ignored owner directories.

This repository is the source product used to create and update SpielOS homes. It runs from source with:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -B -m company COMMAND
```

The public product uses one runtime-owned Goal loop and portable Agent-owned Departments. Do not reintroduce retired Workgroups, Workers, Workbooks, or Workkits into docs, commands, templates, or onboarding.

`company/init_templates/` is what `spielos init` ships. Keep executable spine files byte-identical between `company/` and `company/init_templates/agents/company/`. Private `.spielos/` runtime state is ignored by Git.

DECIDE is the reasoning seam of the one Goal loop: a Run the runtime cannot
decide for the owner parks a structured decision request (run DECIDE/waiting,
one owner notification, no Intervention and no WorkOrder) that the owner
answers with `company goal decide` — adopting a candidate Department workflow
or assigning bounded direct work whose instruction is mandatory. Stalled goals
(a metric flat across `stall_threshold` evaluated runs with no new evidence)
and `review_every` checkpoints park for `company goal resume`. Progressing
runs chain automatically: there are no per-run owner gates.

Owner voice is the default on every owner-facing surface: goals, evidence,
memory, and asks render as names, human progress, and outcome sentences
with named options. Raw goal/evidence ids, metric keys, stage or decision
enums, JSON dumps, and CLI answer syntax never enter owner-facing text;
they ride the payload machine fields and one `Machine reference` line at
the end of the context projection for the Director alone, quoted only when
the owner asks for technical detail. The owner answers in plain words; the
Director records the answer through the CLI itself.

Memory is causal and classified: WorkOrder briefs carry the bounded active
learning for the work they open (workflow-scope claims for workflow orders,
goal-relevant claims for direct ones — including the goal's own direct-work
lessons, which are goal-keyed and reach future direct orders of the same
Goal), so the next execution builds on the
last one's evidence-backed lesson. Owner preferences write owner scope
(`profile set`), operational lessons write workflow scope
(`tasks --complete --learning`, only when something reusable was learned),
and owner strategic direction writes strategy scope (`memory add --scope
strategy`). The deterministic runtime fabricates none of these; a stale
claim is retired with `company memory retire` (row and evidence preserved).

System changes require a bounded system-improvement Goal, exact allowed files, and actual acceptance evidence. External actions—including publishing or sending—remain approval-gated.
