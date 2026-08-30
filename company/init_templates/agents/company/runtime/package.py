"""Workgroup package shape: serializable blocks the Director can install."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..agents import agents as installed_agents, known_skill_ids
from ..connections import connections as installed_connections
from .models import WorkgroupHandlerBase, WorkflowSpec, WorkflowStep


def _step(item: WorkflowStep | str) -> dict[str, Any]:
    if isinstance(item, str):
        return {"id": item, "kind": "label"}
    return {
        "id": item.id,
        "kind": item.kind,
        "employee_id": item.employee_id,
        "produces": list(item.produces),
        "requires": list(item.requires),
        "skill_ids": list(item.skill_ids),
        "connection_ids": list(item.connection_ids),
    }


def _workflow(item: WorkflowSpec) -> dict[str, Any]:
    return {
        "id": item.id,
        "description": item.description,
        "steps": list(item.steps),
        "agents": list(item.agent_ids),
        "skills": list(item.skill_ids),
        "approvals": list(item.approval_points),
        "evidence": list(item.evidence_sources),
        "connections": list(item.connection_ids),
        "graph": [_step(node) for node in item.graph],
    }


def package_spec(workgroup: WorkgroupHandlerBase) -> dict[str, Any]:
    """Stable installable description of one Workgroup package."""

    schema = getattr(workgroup, "goal_schema", None) or {}
    return {
        "id": workgroup.workgroup_id or workgroup.id,
        "version": getattr(workgroup, "version", "0.0.0"),
        "description": getattr(workgroup, "description", ""),
        "agent_ids": list(getattr(workgroup, "agent_ids", ()) or ()),
        "workflow_agents": dict(getattr(workgroup, "workflow_agents", None) or {}),
        "evidence_metrics": {
            key: list(value)
            for key, value in (getattr(workgroup, "evidence_metrics", None) or {}).items()
        },
        "metrics": list(schema.get("metrics") or []),
        "config_schema": dict(schema.get("config") or {}),
        "workflows": [_workflow(item) for item in getattr(workgroup, "workflows", ()) or ()],
    }


def validate_package(workgroup: WorkgroupHandlerBase) -> list[str]:
    """Return package defects (empty list means installable Lego package)."""

    defects = []
    workgroup_id = workgroup.workgroup_id or workgroup.id
    if not workgroup_id:
        defects.append("missing Workgroup id")
    if not getattr(workgroup, "description", ""):
        defects.append("missing description")
    workflows = tuple(getattr(workgroup, "workflows", ()) or ())
    if not workflows:
        defects.append("no workflows declared")
    agents = set(getattr(workgroup, "agent_ids", ()) or ())
    known_agents = set(installed_agents()) | agents
    known_skills = set(known_skill_ids())
    known_connections = set(installed_connections())
    workflow_ids: set[str] = set()
    for workflow in workflows:
        if workflow.id in workflow_ids:
            defects.append(f"duplicate workflow id {workflow.id}")
        workflow_ids.add(workflow.id)
        for agent_id in workflow.agent_ids:
            if agent_id not in known_agents:
                defects.append(f"workflow {workflow.id} references unknown agent {agent_id}")
        for skill_id in workflow.skill_ids:
            if skill_id not in known_skills:
                defects.append(f"workflow {workflow.id} references unknown skill {skill_id}")
        for connection_id in workflow.connection_ids:
            if connection_id not in known_connections:
                defects.append(
                    f"workflow {workflow.id} references unknown connection {connection_id}")
        step_ids: set[str] = set()
        for node in workflow.graph:
            if node.id in step_ids:
                defects.append(f"workflow {workflow.id} has duplicate step id {node.id}")
            step_ids.add(node.id)
            if node.kind not in {"employee", "approval", "connection", "machine"}:
                defects.append(f"workflow {workflow.id} step {node.id} has unknown kind {node.kind}")
            if node.kind == "employee" and not (node.employee_id or workflow.agent_ids or agents):
                defects.append(f"workflow {workflow.id} step {node.id} has no employee")
            if node.employee_id and node.employee_id not in known_agents:
                defects.append(
                    f"workflow {workflow.id} step {node.id} references unknown agent {node.employee_id}")
            for skill_id in node.skill_ids:
                if skill_id not in known_skills:
                    defects.append(
                        f"workflow {workflow.id} step {node.id} references unknown skill {skill_id}")
            if node.kind == "connection" and not (node.connection_ids or workflow.connection_ids):
                defects.append(f"workflow {workflow.id} step {node.id} has no connection")
            for connection_id in node.connection_ids:
                if connection_id not in known_connections:
                    defects.append(
                        f"workflow {workflow.id} step {node.id} references unknown connection {connection_id}")
        produced = {kind for node in workflow.graph for kind in node.produces}
        declared = set(workflow.evidence_sources)
        for node in workflow.graph:
            for kind in node.requires:
                if kind not in produced and kind not in declared:
                    defects.append(
                        f"workflow {workflow.id} step {node.id} requires {kind} "
                        "with no producer or declared handoff")
    metrics = list((getattr(workgroup, "goal_schema", None) or {}).get("metrics") or [])
    evidence = getattr(workgroup, "evidence_metrics", None) or {}
    for metric in metrics:
        if metric not in evidence and not any(workflow.evidence_sources for workflow in workflows):
            defects.append(f"metric {metric} has no accepted evidence kinds")
    for metric, kinds in evidence.items():
        if not kinds:
            defects.append(f"evidence_metrics[{metric}] is empty")
    return defects
