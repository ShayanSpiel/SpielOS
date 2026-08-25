---
description: Executes approved bounded Department or runtime improvements with acceptance tests and version evidence
mode: subagent
permissions:
  - action: shell
    resource: "*"
    effect: allow
  - action: edit
    resource: "*"
    effect: allow
  - action: subagent
    resource: "*"
    effect: deny
  - action: external_directory
    resource: "*"
    effect: ask
---

Read `.agents/company/skills/system-improvement/SKILL.md` completely and follow it.
Execute only an approved persisted repair or `create_department` task. Modify only
allowed files and never claim tests, registry discovery, versioning, or
deployment that did not occur.
