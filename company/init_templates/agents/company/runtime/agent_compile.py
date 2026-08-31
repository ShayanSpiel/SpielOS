"""Compile a Department Workflow into a first-class Agent.

Given a Department and one of its Workflows, generates the three host
adapter artifacts from the single WorkflowSpec catalog:

    .opencode/agents/<name>.md            OpenCode agent definition
    .codex/agents/<name>.toml             Codex agent definition
    .agents/company/agents/installed/<name>.json   Agent roster entry

The compiled Agent is scoped to exactly that Department + Workflow: it may
only produce the workflow's declared evidence kinds, only uses its declared
skills and connections, never edits repository files, and has no Director
routing. Approvals still park through the runtime.

This is the general form of the hand-built lead-researcher repo.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from .registry import departments


def _workflow(department_id: str, workflow_id: str):
    dept = departments().get(department_id)
    if dept is None:
        raise ValueError(f"no such Department: {department_id}")
    for spec in dept.workflows:
        if spec.id == workflow_id:
            return dept, spec
    raise ValueError(f"Department '{department_id}' has no Workflow '{workflow_id}'; "
                     f"known: {', '.join(w.id for w in dept.workflows)}")


def _clean(value) -> str:
    return str(value or "").strip()


def compile_agent(department_id: str, workflow_id: str, name: str | None = None,
                  *, force: bool = False,
                  home: str | Path | None = None) -> dict:
    from .paths import selected_project_root, validate_home_destination

    root = validate_home_destination(selected_project_root(home))
    dept, spec = _workflow(department_id, workflow_id)
    agent_name = name or f"{department_id}-{_slug(spec.id)}"

    skills = [_clean(s) for s in (spec.skill_ids or ())]
    connections = [_clean(c) for c in (spec.connection_ids or ())]
    evidence_kinds = [_clean(e) for e in (spec.evidence_sources or ())]
    stages = [_clean(s) for s in (spec.steps or ())]

    purpose = _clean(getattr(spec, "description", "") or spec.id)

    opencode_path = _render_opencode(root, agent_name, department_id,
                                     workflow_id, purpose, skills,
                                     evidence_kinds, stages, force)
    codex_path = _render_codex(root, agent_name, department_id, workflow_id,
                               purpose, skills, evidence_kinds, stages, force)
    roster_path = _render_roster(root, agent_name, department_id,
                                 workflow_id, skills, connections,
                                 evidence_kinds, force)

    return {
        "agent": agent_name,
        "scope": {"department": department_id, "workflow": workflow_id},
        "files": [opencode_path, codex_path, roster_path],
        "note": ("first-class Agent: runs only this Workflow; approvals still "
                 "park; no Director routing"),
    }


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")


def _render_opencode(root: Path, name: str, department_id: str, workflow_id: str,
                     purpose: str, skills: list[str], kinds: list[str],
                     stages: list[str], force: bool) -> str:
    path = root / ".opencode" / "agents" / f"{name}.md"
    if path.exists() and not force:
        raise FileExistsError(f"{path} exists; pass --force to overwrite")
    path.parent.mkdir(parents=True, exist_ok=True)
    skill_list = ", ".join(f"`{s}`" for s in skills) or "none"
    kind_list = ", ".join(f"`{k}`" for k in kinds) or "the workflow's declared kinds"
    stage_list = " → ".join(stages) or spec_stages_fallback(workflow_id)
    path.write_text(f"""---
description: First-class {name} Agent ({department_id}/{workflow_id}). Runs only this Department's Workflow.
mode: primary
temperature: 0.2
permissions:
  edit: deny
  webfetch: allow
---

You are **{name}** — the first-class executor of the `{workflow_id}`
Workflow inside the `{department_id}` Department of this SpielOS company.
You are NOT the Director. You do not route goals, create companies, or touch
other Departments.

## Scope (hard boundary)

- Department: `{department_id}` · Workflow: `{workflow_id}`
- Stages: {stage_list}
- Evidence kinds you may produce: {kind_list}
- Skills to follow: {skill_list}

## Operating contract

1. Work only toward this workflow's steps via `python3 -m company` CLI tasks
   (`company tasks`, claim/complete work orders) or as instructed by the operator.
2. Record real evidence for every step. Never invent provider results,
   receipts, or metrics. Invalid or technical-only evidence cannot support a
   business conclusion.
3. Live external actions park for explicit approval. Never auto-approve.
4. Never edit repository files; the bounded Resolution agent owns repairs.
5. Report outcomes plainly: what ran, what was produced, what is blocked.
""")
    return str(path)


def spec_stages_fallback(workflow_id: str) -> str:
    return workflow_id


def _render_codex(root: Path, name: str, department_id: str, workflow_id: str,
                  purpose: str, skills: list[str], kinds: list[str],
                  stages: list[str], force: bool) -> str:
    path = root / ".codex" / "agents" / f"{name}.toml"
    if path.exists() and not force:
        raise FileExistsError(f"{path} exists; pass --force to overwrite")
    path.parent.mkdir(parents=True, exist_ok=True)
    skill_list = ", ".join(skills) or ""
    kind_list = ", ".join(kinds)
    path.write_text(f"""# First-class {name} Agent — scope: {department_id}/{workflow_id}
# Generated by `spielos agent compile`. Do not hand-edit scope fields.
name = "{name}"
description = "First-class executor of the {workflow_id} Workflow in the {department_id} Department."
developer_instructions = '''
You operate as {name}: execute only the {workflow_id} workflow of the
{department_id} Department. Follow the persisted company work-order contract,
record honest evidence, park live external actions for approval, never edit
repository files, and never touch other Departments' Goals.
'''
# Hard scope: department={department_id} workflow={workflow_id}
# Evidence kinds: {kind_list}
# Skills: {skill_list}
# This Agent never edits repository files and never approves its own live actions;
# approvals park in the runtime regardless of host.
""")
    return str(path)


def _render_roster(root: Path, name: str, department_id: str, workflow_id: str,
                   skills: list[str], connections: list[str],
                   kinds: list[str], force: bool) -> str:
    roster_dir = root / ".agents" / "company" / "agents" / "installed"
    path = roster_dir / f"{name}.json"
    if path.exists() and not force:
        raise FileExistsError(f"{path} exists; pass --force to overwrite")
    roster_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "id": name,
        "first_class": True,
        "department_id": department_id,
        "workflow_ids": [workflow_id],
        "skill_ids": skills,
        "permissions": ["read_strategy", "write_evidence", *(
            f"use_connection:{connection}" for connection in connections)],
        "produces": kinds,
        "generated_by": "spielos agent compile",
    }
    path.write_text(json.dumps(payload, indent=2) + "\n")
    return str(path)
