# SpielOS source checkout

This repository is the source product used to create and update SpielOS homes. It runs from source with:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -B -m company COMMAND
```

The public product uses one runtime-owned Goal loop and portable Agent-owned Departments. Do not reintroduce retired Workgroups, Workers, Workbooks, or Workkits into docs, commands, templates, or onboarding.

`company/init_templates/` is what `spielos init` ships. Keep executable spine files byte-identical between `company/` and `company/init_templates/agents/company/`. Private `.spielos/` runtime state is ignored by Git.

System changes require a bounded system-improvement Goal, exact allowed files, and actual acceptance evidence. External actions—including publishing or sending—remain approval-gated.
