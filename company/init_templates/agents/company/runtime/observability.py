"""Live, read-only architecture observability for a SpielOS home.

The observatory deliberately projects existing authorities instead of creating a
second state model: SQLite owns operations, Strategy owns intent/policy, package
registries own capabilities, and the artifact tree owns deliverables.
"""

from __future__ import annotations

import ast
import hashlib
import json
import mimetypes
import os
import threading
import webbrowser
from collections import Counter, defaultdict
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "1.0"
LAYERS = (
    ("input", "Inputs & adapters", "Host entrypoints, hooks, and owner input."),
    ("strategy", "Strategy", "Intent, model, policy, and constitutional constraints."),
    ("control", "Goals & control", "Goal tree, causal support DAG, runs, and approvals."),
    ("runtime", "Runtime loop", "The single GOAL → OBSERVE → DECIDE → ACT → EVALUATE loop."),
    ("capability", "Departments", "Portable installable company capabilities."),
    ("execution", "Agents", "Bounded executors and current durable assignments."),
    ("workflow", "Workflows", "Agent-owned playbooks and their ordered steps."),
    ("method", "Skills & connections", "Reusable methods and authorized system access."),
    ("knowledge", "Evidence & memory", "Evidence, decisions, evaluations, and durable memory."),
    ("state", "State & artifacts", "SQLite tables, notifications, friction, and artifact manifests."),
    ("code", "Code architecture", "Source modules and their local import relations."),
)
LOOP_STAGES = ("GOAL", "OBSERVE", "DECIDE", "ACT", "EVALUATE")
TERMINAL_GOALS = {"achieved", "abandoned", "expired"}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json(value: Any, fallback: Any) -> Any:
    if isinstance(value, (dict, list, tuple, int, float, bool)) or value is None:
        return value
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return fallback


def _slug(value: Any) -> str:
    return str(value or "unknown").replace(" ", "-").replace("/", "-")


class Graph:
    def __init__(self) -> None:
        self.nodes: dict[str, dict] = {}
        self.edges: dict[str, dict] = {}
        self.findings: list[dict] = []

    def node(self, identifier: str, *, kind: str, label: str, layer: str,
             subtitle: str = "", status: str = "neutral", live: bool = False,
             source: str | None = None, meta: dict | None = None) -> str:
        item = {
            "id": identifier, "kind": kind, "label": label,
            "subtitle": subtitle, "layer": layer, "status": status,
            "live": bool(live), "source": source, "meta": meta or {},
        }
        item["search"] = " ".join(str(value) for value in (
            identifier, kind, label, subtitle, source or "",
            json.dumps(item["meta"], ensure_ascii=False, default=str),
        )).lower()
        self.nodes[identifier] = item
        return identifier

    def edge(self, source: str, target: str, relation: str, *,
             label: str = "", status: str = "neutral", meta: dict | None = None) -> None:
        if source not in self.nodes or target not in self.nodes:
            return
        raw = f"{source}|{target}|{relation}|{label}"
        identifier = "edge-" + hashlib.sha1(raw.encode()).hexdigest()[:12]
        self.edges[identifier] = {
            "id": identifier, "source": source, "target": target,
            "relation": relation, "label": label or relation,
            "status": status, "meta": meta or {},
        }

    def finding(self, severity: str, kind: str, title: str, detail: str, *,
                node_ids: list[str] | tuple[str, ...] = (), suggestion: str = "") -> None:
        raw = f"{severity}|{kind}|{title}|{detail}"
        self.findings.append({
            "id": "finding-" + hashlib.sha1(raw.encode()).hexdigest()[:12],
            "severity": severity, "kind": kind, "title": title,
            "detail": detail, "node_ids": list(node_ids),
            "suggestion": suggestion,
        })


def _table_snapshot(store) -> tuple[list[dict], dict[str, int]]:
    tables: list[dict] = []
    counts: dict[str, int] = {}
    with store.connect() as con:
        names = [row[0] for row in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' "
            "ORDER BY name").fetchall()]
        for name in names:
            # Names originate from sqlite_master, not user input.
            count = int(con.execute(f'SELECT COUNT(*) FROM "{name}"').fetchone()[0])
            counts[name] = count
            columns = [row[1] for row in con.execute(f'PRAGMA table_info("{name}")')]
            updated = None
            for timestamp_column in ("updated_at", "created_at", "observed_at"):
                if timestamp_column in columns:
                    updated = con.execute(
                        f'SELECT MAX("{timestamp_column}") FROM "{name}"').fetchone()[0]
                    break
            tables.append({"name": name, "count": count, "updated_at": updated})
    return tables, counts


def _rows(store, sql: str, parameters: tuple = ()) -> list[dict]:
    with store.connect() as con:
        return [dict(row) for row in con.execute(sql, parameters).fetchall()]


def _goal_projection(runtime) -> list[dict]:
    summaries = {item["id"]: item for item in runtime.store.goal_summaries(limit=100)}
    values: list[dict] = []
    for goal in runtime.store.goals():
        current = summaries.get(goal["id"])
        if current is None:
            try:
                cycle = runtime.store.cycle(goal["id"])
                run = runtime.store.run(cycle["id"])
            except KeyError:
                cycle, run = {}, {}
            config = goal.get("config") or {}
            current = {
                **goal, "run_id": cycle.get("id"), "sequence": cycle.get("sequence"),
                "stage": cycle.get("stage"), "step": cycle.get("step"),
                "run_status": cycle.get("run_status"), "resume_at": cycle.get("resume_at"),
                "runtime_updated_at": cycle.get("updated_at"),
                "run_type": run.get("run_type"),
                "evidence_validity": run.get("evidence_validity"),
                "pursuit_kind": config.get("pursuit_kind") or (
                    "system_improvement_goal" if goal.get("owner_id") == "system-improvement"
                    else "supporting_goal" if goal.get("parent_id") else "primary_goal"),
                "supports_goal_ids": list(config.get("supports_goal_ids") or ()),
                "priority": config.get("priority"), "causal_lineage": config.get("causal_lineage") or {},
            }
        values.append(current)
    return values


def _add_strategy(graph: Graph, project_root: Path) -> dict:
    from .strategy import strategy_kernel_summary

    summary = strategy_kernel_summary()
    root_id = graph.node(
        "strategy:kernel", kind="strategy_kernel", label="Strategy Kernel",
        layer="strategy", subtitle=summary.get("state_hash", "")[:12],
        status="healthy", source=str(summary.get("authority") or ""), meta={
            "mutation": summary.get("mutation"), "state_hash": summary.get("state_hash"),
        })
    for layer, sections in (summary.get("layers") or {}).items():
        layer_id = graph.node(
            f"strategy-layer:{layer}", kind="strategy_layer", label=layer.title(),
            layer="strategy", subtitle=f"{len(sections)} sections", status="healthy",
            meta={"section_count": len(sections)})
        graph.edge(root_id, layer_id, "contains")
        for section in sections:
            identifier = f"strategy:{section['id']}"
            graph.node(identifier, kind="strategy_section", label=section.get("heading") or section["id"],
                       layer="strategy", subtitle=section.get("source", ""),
                       status="healthy" if section.get("required") else "neutral",
                       source=section.get("source"), meta=section)
            graph.edge(layer_id, identifier, "defines")
    return summary


def _add_hosts(graph: Graph, project_root: Path) -> list[dict]:
    host_root = project_root / "company" / "init_templates" / "hosts"
    hosts: list[dict] = []
    if not host_root.is_dir():
        return hosts
    for folder in sorted(path for path in host_root.iterdir() if path.is_dir()):
        host_id = graph.node(
            f"host:{folder.name}", kind="host_adapter", label=folder.name.title(),
            layer="input", subtitle="adaptor host", status="healthy", source=str(folder))
        files = [path for path in sorted(folder.rglob("*")) if path.is_file()]
        hosts.append({"id": folder.name, "files": len(files), "path": str(folder)})
        for path in files:
            relative = path.relative_to(project_root).as_posix()
            kind = "host_hook" if "hook" in relative else (
                "host_agent" if "/agents/" in relative else "host_command")
            child_id = graph.node(
                f"host-file:{relative}", kind=kind, label=path.stem,
                layer="input", subtitle=relative, status="healthy", source=relative)
            graph.edge(host_id, child_id, "provides")
    return hosts


def _add_departments(graph: Graph) -> dict:
    from .registry import departments

    installed = departments()
    workflow_ids: dict[str, list[str]] = defaultdict(list)
    skill_ids: set[str] = set()
    connection_ids: set[str] = set()
    agent_ids: set[str] = set()
    for department_id, department in sorted(installed.items()):
        node_id = graph.node(
            f"department:{department_id}", kind="department", label=department_id,
            layer="capability", subtitle=department.description, status="healthy",
            source=f"company/departments/{department_id}", meta={
                "version": department.version,
                "agent_ids": list(department.agent_ids),
                "evidence_metrics": {
                    key: list(value) for key, value in department.evidence_metrics.items()
                },
            })
        for agent_id in department.agent_ids:
            agent_ids.add(agent_id)
            agent_node = graph.node(
                f"agent:{agent_id}", kind="agent", label=agent_id,
                layer="execution", subtitle="Department Agent", status="idle",
                meta={"departments": [department_id]})
            graph.edge(node_id, agent_node, "includes")
        for workflow in department.workflows:
            workflow_ids[workflow.id].append(department_id)
            workflow_node = graph.node(
                f"workflow:{department_id}:{workflow.id}", kind="workflow",
                label=workflow.id, layer="workflow", subtitle=workflow.description,
                status="idle", source=f"company/departments/{department_id}", meta={
                    "department_id": department_id,
                    "agent_ids": list(workflow.agent_ids),
                    "evidence": list(workflow.evidence_sources),
                })
            graph.edge(node_id, workflow_node, "owns")
            for agent_id in workflow.agent_ids:
                if f"agent:{agent_id}" in graph.nodes:
                    graph.edge(workflow_node, f"agent:{agent_id}", "executed_by")
            previous = None
            for index, step in enumerate(workflow.graph):
                step_node = graph.node(
                    f"step:{department_id}:{workflow.id}:{step.id}", kind="workflow_step",
                    label=step.id, layer="workflow", subtitle=f"step {index + 1} · {step.kind}",
                    status="neutral", meta={
                        "agent_id": step.agent_id, "produces": list(step.produces),
                        "requires": list(step.requires),
                    })
                graph.edge(workflow_node, step_node, "contains", label=f"step {index + 1}")
                if previous:
                    graph.edge(previous, step_node, "precedes")
                previous = step_node
                assigned = step.agent_id or (workflow.agent_ids[0] if workflow.agent_ids else None)
                if assigned and f"agent:{assigned}" in graph.nodes:
                    graph.edge(step_node, f"agent:{assigned}", "executed_by")
                for produced in step.produces:
                    evidence_node = graph.node(
                        f"evidence-kind:{produced}", kind="evidence_kind", label=produced,
                        layer="knowledge", subtitle="declared evidence", status="neutral")
                    graph.edge(step_node, evidence_node, "produces")
                for required in step.requires:
                    evidence_node = graph.node(
                        f"evidence-kind:{required}", kind="evidence_kind", label=required,
                        layer="knowledge", subtitle="required evidence", status="neutral")
                    graph.edge(evidence_node, step_node, "required_by")
                for skill in step.skill_ids:
                    skill_ids.add(skill)
                    skill_node = graph.node(
                        f"skill:{skill}", kind="skill", label=skill, layer="method",
                        subtitle="reusable method", status="neutral")
                    graph.edge(step_node, skill_node, "uses")
                for connection in step.connection_ids:
                    connection_ids.add(connection)
                    connection_node = graph.node(
                        f"connection:{connection}", kind="connection", label=connection,
                        layer="method", subtitle="authorized access", status="neutral")
                    graph.edge(step_node, connection_node, "uses")
    return {
        "departments": installed, "workflow_ids": workflow_ids, "skills": skill_ids,
        "connections": connection_ids, "agents": agent_ids,
    }



def _add_catalog_methods(graph: Graph, graph_inventory: dict) -> dict:
    from ..agents import agents, skill_files
    from ..connections import connections

    installed_agents = agents()
    installed_connections = connections()
    installed_skills: dict[str, Path] = {}
    for path in skill_files():
        installed_skills.setdefault(path.parent.name, path)
        identifier = f"skill:{path.parent.name}"
        if identifier not in graph.nodes:
            graph.node(identifier, kind="skill", label=path.parent.name, layer="method",
                       subtitle="installed skill", status="ignored", source=str(path))
    for connection_id, connection in sorted(installed_connections.items()):
        identifier = f"connection:{connection_id}"
        graph.node(identifier, kind="connection", label=connection_id, layer="method",
                   subtitle=connection.description,
                   status="neutral" if connection_id in graph_inventory["connections"] else "ignored",
                   meta={"capabilities": list(connection.capabilities),
                         "hosts": list(connection.hosts), "unattended": connection.unattended,
                         "required_environment": list(connection.required_environment)})
    for agent_id, agent in sorted(installed_agents.items()):
        identifier = f"agent:{agent_id}"
        if identifier not in graph.nodes:
            graph.node(identifier, kind="agent", label=agent_id, layer="execution",
                       subtitle=agent.description, status="ignored", meta={
                           "skills": list(agent.skill_ids), "permissions": list(agent.permissions),
                           "produces": list(agent.produces), "catalog_only": True,
                       })
        for skill in agent.skill_ids:
            if f"skill:{skill}" in graph.nodes:
                graph.edge(identifier, f"skill:{skill}", "uses")
    unused_skills = sorted(set(installed_skills) - graph_inventory["skills"])
    unused_connections = sorted(set(installed_connections) - graph_inventory["connections"])
    if unused_skills:
        graph.finding(
            "info", "unused_capability", f"{len(unused_skills)} installed skills are unreferenced",
            "No canonical Department step currently declares these Skills: " + ", ".join(unused_skills),
            node_ids=[f"skill:{item}" for item in unused_skills],
            suggestion="Remove true dead weight or bind each method to one explicit Workflow step.")
    if unused_connections:
        graph.finding(
            "info", "unused_connection", f"{len(unused_connections)} connections are unreferenced",
            "No canonical Department step currently declares these Connections: "
            + ", ".join(unused_connections),
            node_ids=[f"connection:{item}" for item in unused_connections],
            suggestion="Keep only intentional platform capabilities or declare their owning workflow.")
    return {
        "installed_agents": len(installed_agents), "installed_skills": len(installed_skills),
        "installed_connections": len(installed_connections),
        "unused_skills": unused_skills, "unused_connections": unused_connections,
    }


def _add_runtime_state(graph: Graph, runtime, goals: list[dict], tables: list[dict],
                       project_root: Path) -> dict:
    db_id = graph.node(
        "state:sqlite", kind="state_authority", label="company.sqlite",
        layer="state", subtitle="operational authority", status="healthy",
        source=str(runtime.store.path), meta={"readonly": runtime.readonly})
    for table in tables:
        table_id = graph.node(
            f"table:{table['name']}", kind="state_table", label=table["name"],
            layer="state", subtitle=f"{table['count']} rows", status="healthy",
            meta=table)
        graph.edge(db_id, table_id, "stores")

    stage_nodes: dict[str, str] = {}
    for index, stage in enumerate(LOOP_STAGES):
        stage_nodes[stage] = graph.node(
            f"loop:{stage.lower()}", kind="loop_stage", label=stage,
            layer="runtime", subtitle=f"stage {index + 1} of {len(LOOP_STAGES)}",
            status="neutral", meta={"order": index})
        if index:
            graph.edge(stage_nodes[LOOP_STAGES[index - 1]], stage_nodes[stage], "advances_to")
    graph.edge(stage_nodes["EVALUATE"], stage_nodes["GOAL"], "continues", status="active")

    goal_ids = {goal["id"] for goal in goals}
    owner_counts = Counter(goal.get("owner_id") for goal in goals)
    for owner, count in owner_counts.items():
        if owner in {"director", "system-improvement"}:
            owner_id = graph.node(
                f"control:{owner}", kind="control", label=owner,
                layer="control", subtitle=f"owns {count} goals", status="healthy")
            graph.edge(owner_id, stage_nodes["GOAL"], "governs")
        elif f"department:{owner}" in graph.nodes:
            owner_id = f"department:{owner}"
        else:
            owner_id = graph.node(
                f"missing-owner:{owner}", kind="missing_reference", label=str(owner),
                layer="capability", subtitle="goal owner not installed", status="critical")
            graph.finding(
                "error", "missing_owner", f"Goal owner '{owner}' is not installed",
                f"{count} goal(s) point to an owner absent from the active capability registry.",
                node_ids=[owner_id], suggestion="Install or migrate the owner before advancing these Goals.")

    active_by_stage = Counter()
    for goal in goals:
        status = goal.get("goal_status") or "unknown"
        live = status not in TERMINAL_GOALS
        stage = str(goal.get("stage") or "GOAL").upper()
        if live:
            active_by_stage[stage] += 1
        pursuit = goal.get("pursuit_kind") or "goal"
        goal_node = graph.node(
            f"goal:{goal['id']}", kind="goal", label=goal.get("name") or goal["id"],
            layer="control", subtitle=(f"{goal.get('metric')} {goal.get('operator')} "
                                       f"{goal.get('target')}"), status=status, live=live,
            meta={key: goal.get(key) for key in (
                "id", "owner_id", "goal_status", "priority", "pursuit_kind", "metric",
                "operator", "target", "deadline", "parent_id", "supports_goal_ids",
                "run_id", "run_type", "run_status", "stage", "step", "why_next",
                "evidence_count", "verdict", "goal_met", "created_at", "updated_at",
                "runtime_updated_at", "causal_lineage")})
        owner = goal.get("owner_id")
        owner_node = (f"control:{owner}" if owner in {"director", "system-improvement"}
                      else f"department:{owner}" if f"department:{owner}" in graph.nodes
                      else f"missing-owner:{owner}")
        graph.edge(owner_node, goal_node, "owns")
        if goal.get("parent_id") in goal_ids:
            graph.edge(f"goal:{goal['parent_id']}", goal_node, "parent_of")
        for target in goal.get("supports_goal_ids") or ():
            if target in goal_ids:
                graph.edge(goal_node, f"goal:{target}", "supports", status="active")
        run_id = goal.get("run_id")
        if run_id:
            run_status = goal.get("run_status") or "unknown"
            run_node = graph.node(
                f"run:{run_id}", kind="run", label=run_id,
                layer="control", subtitle=f"{goal.get('run_type')} · {run_status}",
                status=run_status, live=live, meta={
                    "goal_id": goal["id"], "sequence": goal.get("sequence"),
                    "stage": stage, "step": goal.get("step"),
                    "run_type": goal.get("run_type"), "status": run_status,
                    "resume_at": goal.get("resume_at"),
                })
            graph.edge(goal_node, run_node, "current_run")
            if stage in stage_nodes:
                graph.edge(run_node, stage_nodes[stage], "currently_at", status="active")

    work_orders = runtime.store.work_orders(status=None, limit=100)
    for order in work_orders:
        order_id = graph.node(
            f"work-order:{order['id']}", kind="work_order", label=order["id"],
            layer="execution", subtitle=f"{order.get('workflow_id') or 'workflow'} · {order['status']}",
            status=order["status"], live=order["status"] in {"open", "claimed"}, meta=order)
        graph.edge(f"goal:{order['goal_id']}", order_id, "dispatches")
        graph.edge(f"run:{order['run_id']}", order_id, "creates")
        agent_node = f"agent:{order.get('agent_id')}"
        if agent_node in graph.nodes:
            graph.edge(order_id, agent_node, "assigned_to")
            graph.nodes[agent_node]["status"] = "active" if order["status"] in {"open", "claimed"} else graph.nodes[agent_node]["status"]
            graph.nodes[agent_node]["live"] = order["status"] in {"open", "claimed"}
        elif order["status"] in {"open", "claimed"}:
            graph.finding(
                "error", "missing_agent", f"Work order {order['id']} has no installed Agent",
                f"Assignment references '{order.get('agent_id')}' but no matching Agent exists.",
                node_ids=[order_id], suggestion="Install the Agent or reissue the bounded assignment.")
        workflow_id = order.get("workflow_id")
        matches = [node["id"] for node in graph.nodes.values()
                   if node["kind"] == "workflow" and node["label"] == workflow_id]
        for match in matches:
            graph.edge(order_id, match, "executes")

    return {"work_orders": work_orders, "active_by_stage": dict(active_by_stage)}


def _add_memory_and_evidence(graph: Graph, runtime) -> dict:
    stores = {
        "company_profile": list(runtime.store.profile_claims(limit=200)),
        "operating_directives": list(runtime.store.directives(limit=100)),
        "experiment_learning": list(runtime.store.experiment_memories(limit=200)),
        "workflow_memory": list(runtime.store.workflow_memories(limit=200)),
        "legacy_learning": list(runtime.store.recent_memories(50)),
    }
    memory_root = graph.node(
        "memory:durable", kind="memory_layer", label="Durable memory",
        layer="knowledge", subtitle=f"{sum(map(len, stores.values()))} records",
        status="healthy")
    for category, items in stores.items():
        category_node = graph.node(
            f"memory-category:{category}", kind="memory_category",
            label=category.replace("_", " "), layer="knowledge",
            subtitle=f"{len(items)} records", status="healthy" if items else "empty",
            meta={"count": len(items)})
        graph.edge(memory_root, category_node, "contains")
        for index, item in enumerate(items[:60]):
            raw_id = item.get("id") or f"{category}-{index}"
            item_node = graph.node(
                f"memory-item:{category}:{raw_id}", kind="memory_item",
                label=str(item.get("title") or item.get("claim") or item.get("text") or raw_id)[:100],
                layer="knowledge", subtitle=str(item.get("status") or category),
                status=str(item.get("status") or "neutral"), meta=item)
            graph.edge(category_node, item_node, "contains")
            if item.get("goal_id") and f"goal:{item['goal_id']}" in graph.nodes:
                graph.edge(item_node, f"goal:{item['goal_id']}", "learned_from")
            if item.get("workflow_id"):
                matches = [node["id"] for node in graph.nodes.values()
                           if node["kind"] == "workflow" and node["label"] == item["workflow_id"]]
                for match in matches:
                    graph.edge(item_node, match, "applies_to")

    evidence_rows = _rows(runtime.store, """SELECT id,goal_id,run_id,kind,source,validity,observed_at
        FROM evidence ORDER BY observed_at DESC LIMIT 200""")
    for item in evidence_rows:
        evidence_node = graph.node(
            f"evidence:{item['id']}", kind="evidence", label=item["kind"],
            layer="knowledge", subtitle=f"{item['source']} · {item['validity']}",
            status="healthy" if item["validity"] in {"business", "technical_only"} else "warning",
            meta=item)
        graph.edge(f"goal:{item['goal_id']}", evidence_node, "has_evidence")
        graph.edge(f"run:{item['run_id']}", evidence_node, "produced")
    return {"categories": {key: len(value) for key, value in stores.items()},
            "evidence_visible": len(evidence_rows)}


def _add_artifacts(graph: Graph, project_root: Path) -> list[dict]:
    root = project_root / ".spielos" / "artifacts"
    root_node = graph.node(
        "artifacts:root", kind="artifact_authority", label="Artifact lifecycle",
        layer="state", subtitle=str(root), status="healthy" if root.exists() else "empty",
        source=str(root))
    manifests: list[dict] = []
    if not root.is_dir():
        return manifests
    for path in sorted(root.rglob("manifest.json"), key=lambda item: item.stat().st_mtime, reverse=True)[:200]:
        payload = _json(path.read_text(encoding="utf-8"), {})
        relative = path.relative_to(root)
        parts = relative.parts
        goal_id = payload.get("goal_id") or (parts[0] if parts else None)
        run_id = payload.get("run_id") or (parts[1] if len(parts) > 1 else None)
        workflow_id = payload.get("workflow_id") or (parts[2] if len(parts) > 2 else None)
        artifact_id = "artifact:" + hashlib.sha1(str(path).encode()).hexdigest()[:12]
        files = payload.get("files") or payload.get("artifacts") or []
        item = {"id": artifact_id, "path": str(path), "goal_id": goal_id,
                "run_id": run_id, "workflow_id": workflow_id, "files": files}
        manifests.append(item)
        graph.node(artifact_id, kind="artifact_manifest", label=workflow_id or run_id or path.parent.name,
                   layer="state", subtitle=f"{len(files)} final files", status="healthy",
                   source=str(path), meta=item)
        graph.edge(root_node, artifact_id, "contains")
        if goal_id:
            graph.edge(f"goal:{goal_id}", artifact_id, "produces")
        if run_id:
            graph.edge(f"run:{run_id}", artifact_id, "produces")
    return manifests


def _local_imports(path: Path, project_root: Path) -> list[str]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, SyntaxError):
        return []
    module = path.relative_to(project_root).with_suffix("").as_posix().replace("/", ".")
    package = module.rsplit(".", 1)[0] if "." in module else module
    imports: list[str] = []
    for item in ast.walk(tree):
        if isinstance(item, ast.Import):
            imports.extend(alias.name for alias in item.names if alias.name.startswith("company"))
        elif isinstance(item, ast.ImportFrom):
            if item.level:
                base = package.split(".")
                prefix = base[:max(1, len(base) - item.level + 1)]
                name = ".".join((*prefix, *(item.module or "").split("."))).strip(".")
            else:
                name = item.module or ""
            if name.startswith("company"):
                imports.append(name)
    return sorted(set(imports))


def _add_code_architecture(graph: Graph, project_root: Path) -> dict:
    company_root = project_root / "company"
    paths = [path for path in company_root.rglob("*.py")
             if "__pycache__" not in path.parts and "init_templates" not in path.parts]
    modules: dict[str, str] = {}
    for path in sorted(paths):
        relative = path.relative_to(project_root).as_posix()
        module = relative[:-3].replace("/", ".")
        if module.endswith(".__init__"):
            module = module[:-9]
        modules[module] = graph.node(
            f"module:{module}", kind="code_module", label=module.split(".")[-1] or module,
            layer="code", subtitle=module, status="neutral", source=relative,
            meta={"bytes": path.stat().st_size, "module": module})
    import_count = 0
    for path in sorted(paths):
        relative = path.relative_to(project_root).as_posix()
        source_module = relative[:-3].replace("/", ".")
        if source_module.endswith(".__init__"):
            source_module = source_module[:-9]
        source = modules.get(source_module)
        for imported in _local_imports(path, project_root):
            target = modules.get(imported)
            if target is None:
                candidates = [key for key in modules if key.startswith(imported + ".")]
                target = modules.get(sorted(candidates)[0]) if candidates else None
            if source and target and source != target:
                graph.edge(source, target, "imports")
                import_count += 1
    return {"modules": len(modules), "local_imports": import_count}


def _activity(runtime) -> list[dict]:
    rows = _rows(runtime.store, """SELECT e.id,e.goal_id,e.cycle_id,e.kind,e.payload_json,e.created_at,
               g.name AS goal_name
        FROM events e LEFT JOIN goals g ON g.id=e.goal_id
        ORDER BY e.created_at DESC,e.id DESC LIMIT 200""")
    values = []
    for row in rows:
        payload = _json(row.pop("payload_json", "{}"), {})
        values.append({**row, "payload": payload})
    return values


def _coherence(graph: Graph, runtime, goals: list[dict], project_root: Path,
               graph_inventory: dict, runtime_state: dict) -> dict:
    audit = runtime.topology_audit()
    for defect in audit.get("defects") or ():
        goal_id = defect.get("goal_id")
        graph.finding(
            "error", "goal_topology", defect.get("kind", "topology defect").replace("_", " ").title(),
            f"{goal_id} violates the Goal control-tree or causal-support contract.",
            node_ids=[f"goal:{goal_id}"],
            suggestion="Use the owner-reviewed topology migration plan; never infer parentage from timestamps.")
    if goals and not audit.get("canonical_root_goal_id"):
        graph.finding(
            "error", "missing_canonical_root", "No canonical primary Goal",
            f"{len(audit.get('root_goal_ids') or ())} roots exist and none is canonical.",
            node_ids=[f"goal:{item}" for item in audit.get("root_goal_ids") or ()],
            suggestion="Choose exactly one primary outcome and map every active supporting Goal to it.")

    duplicates = {key: value for key, value in graph_inventory["workflow_ids"].items()
                  if len(set(value)) > 1}
    for workflow_id, owners in duplicates.items():
        graph.finding(
            "warning", "duplicate_workflow", f"Workflow id '{workflow_id}' is duplicated",
            "The same workflow id is declared by: " + ", ".join(sorted(set(owners))),
            node_ids=[node["id"] for node in graph.nodes.values()
                      if node["kind"] == "workflow" and node["label"] == workflow_id],
            suggestion="Keep one canonical owner or qualify the workflows so routing is unambiguous.")

    active_goals = [goal for goal in goals if goal.get("goal_status") == "active"]
    blocked = [goal for goal in active_goals if goal.get("run_status") in {"blocked", "failed"}]
    if blocked:
        graph.finding(
            "warning", "blocked_work", f"{len(blocked)} active Goals are blocked or failed",
            "Blocked work is visible but not advancing: " + ", ".join(item["id"] for item in blocked),
            node_ids=[f"goal:{item['id']}" for item in blocked],
            suggestion="Resolve the named assignment, approval, or same-scope repair before adding work.")
    if active_goals and not runtime_state["work_orders"]:
        graph.finding(
            "warning", "no_agent_activity", "Active Goals have no durable Agent assignments",
            f"{len(active_goals)} active Goals exist but there are no recorded work orders.",
            node_ids=[f"goal:{item['id']}" for item in active_goals],
            suggestion="Route executable work through an Agent-owned Workflow and persist its work order.")

    source = project_root / "company" / "__main__.py"
    template = project_root / "company" / "init_templates" / "agents" / "company" / "__main__.py"
    if source.is_file() and template.is_file() and source.read_bytes() != template.read_bytes():
        graph.finding(
            "error", "template_parity", "CLI spine differs from the shipped template",
            "company/__main__.py is not byte-identical to the initialized-home copy.",
            suggestion="Mirror the source CLI into init_templates before completing this change.")

    ignore_file = project_root / ".gitignore"
    ignored = []
    if ignore_file.is_file():
        ignored = [line.strip() for line in ignore_file.read_text(encoding="utf-8").splitlines()
                   if line.strip() and not line.lstrip().startswith("#")]
        ignored_node = graph.node(
            "policy:gitignore", kind="ignored_paths", label="Ignored paths",
            layer="state", subtitle=f"{len(ignored)} patterns", status="neutral",
            source=".gitignore", meta={"patterns": ignored})
        graph.edge("state:sqlite", ignored_node, "excluded_from_source")
    return {"topology": audit, "duplicate_workflows": duplicates, "ignored_patterns": ignored}


def collect_snapshot(runtime, *, project_root: str | Path) -> dict:
    """Build a complete, JSON-safe, read-only snapshot of the living system."""

    root = Path(project_root).resolve()
    graph = Graph()
    tables, table_counts = _table_snapshot(runtime.store)
    goals = _goal_projection(runtime)

    strategy = _add_strategy(graph, root)
    hosts = _add_hosts(graph, root)
    graph_inventory = _add_departments(graph)
    methods = _add_catalog_methods(graph, graph_inventory)
    runtime_state = _add_runtime_state(graph, runtime, goals, tables, root)
    memory = _add_memory_and_evidence(graph, runtime)
    artifacts = _add_artifacts(graph, root)
    code = _add_code_architecture(graph, root)
    coherence = _coherence(graph, runtime, goals, root, graph_inventory, runtime_state)
    activity = _activity(runtime)

    severity_counts = Counter(item["severity"] for item in graph.findings)
    score = max(0, 100 - severity_counts["error"] * 9
                - severity_counts["warning"] * 3 - severity_counts["critical"] * 15)
    active_goals = [item for item in goals if item.get("goal_status") == "active"]
    running_goals = [item for item in active_goals if item.get("run_status") == "running"]
    blocked_goals = [item for item in active_goals if item.get("run_status") in {"blocked", "failed"}]
    pending_notifications = runtime.store.notifications("pending", 100)
    attention = runtime.store.attention(100)
    work_orders = runtime_state["work_orders"]
    open_orders = [item for item in work_orders if item.get("status") in {"open", "claimed"}]
    layer_counts = Counter(item["layer"] for item in graph.nodes.values())
    kind_counts = Counter(item["kind"] for item in graph.nodes.values())

    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": _utc_now(),
        "source": {
            "project_root": str(root), "database": str(runtime.store.path.resolve()),
            "authority": "live read-only projection", "refresh_seconds": 2,
            "strategy_hash": strategy.get("state_hash"),
        },
        "health": {
            "score": score,
            "status": "critical" if severity_counts["critical"] or severity_counts["error"] >= 5
                      else "degraded" if severity_counts["error"] or severity_counts["warning"]
                      else "healthy",
            "findings": dict(severity_counts),
        },
        "metrics": {
            "goals_total": len(goals), "goals_active": len(active_goals),
            "goals_running": len(running_goals), "goals_blocked": len(blocked_goals),
            "attention": len(attention), "pending_notifications": len(pending_notifications),
            "work_orders_open": len(open_orders), "departments": len(graph_inventory["departments"]),
            "agents": len(graph_inventory["agents"]),
            "workflows": sum(len(value) for value in graph_inventory["workflow_ids"].values()),
            "memory_records": sum(memory["categories"].values()), "artifacts": len(artifacts),
            "architecture_nodes": len(graph.nodes), "relations": len(graph.edges),
            "code_modules": code["modules"], "state_rows": sum(table_counts.values()),
        },
        "loop": {"stages": list(LOOP_STAGES), "active_by_stage": runtime_state["active_by_stage"]},
        "layers": [{"id": key, "label": label, "description": description,
                    "order": index, "count": layer_counts[key]}
                   for index, (key, label, description) in enumerate(LAYERS)],
        "nodes": list(graph.nodes.values()), "edges": list(graph.edges.values()),
        "findings": graph.findings, "activity": activity,
        "inventory": {
            "node_kinds": dict(kind_counts), "state_tables": tables,
            "hosts": hosts, "memory": memory, "methods": methods,
            "departments": {"count": len(graph_inventory["departments"]),
                            "agents": sorted(graph_inventory["agents"])},
            "artifacts": artifacts, "code": code, "coherence": coherence,
            "attention": attention, "pending_notifications": pending_notifications,
        },
    }


def _ui_path() -> Path:
    return Path(__file__).with_name("observability_ui.html")


def serve_observatory(runtime, *, project_root: str | Path,
                      host: str = "127.0.0.1", port: int = 8765,
                      open_browser: bool = True) -> dict:
    """Serve the live observatory until interrupted."""

    root = Path(project_root).resolve()
    ui = _ui_path()
    if not ui.is_file():
        raise FileNotFoundError(f"observatory UI missing: {ui}")

    class Handler(BaseHTTPRequestHandler):
        def _send(self, status: int, body: bytes, content_type: str) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:  # noqa: N802 - stdlib handler contract
            route = self.path.split("?", 1)[0]
            if route == "/api/snapshot":
                try:
                    body = json.dumps(collect_snapshot(runtime, project_root=root),
                                      ensure_ascii=False, default=str).encode("utf-8")
                    self._send(200, body, "application/json; charset=utf-8")
                except Exception as error:  # keep the UI alive and make failure visible
                    body = json.dumps({"error": type(error).__name__, "detail": str(error),
                                       "generated_at": _utc_now()}).encode("utf-8")
                    self._send(500, body, "application/json; charset=utf-8")
            elif route in {"/", "/index.html"}:
                self._send(200, ui.read_bytes(), "text/html; charset=utf-8")
            elif route == "/favicon.ico":
                self._send(204, b"", "image/x-icon")
            else:
                self._send(404, b"not found", mimetypes.guess_type(route)[0] or "text/plain")

        def log_message(self, _format: str, *_args: Any) -> None:
            return

    server = ThreadingHTTPServer((host, int(port)), Handler)
    url = f"http://{host}:{server.server_address[1]}/"
    if open_browser:
        threading.Timer(0.25, lambda: webbrowser.open(url)).start()
    print(f"SpielOS Observatory live at {url}", flush=True)
    try:
        server.serve_forever(poll_interval=0.35)
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return {"url": url, "stopped": True}
