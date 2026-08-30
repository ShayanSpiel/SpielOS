"""Brief → multi-step WorkflowSpec graph templates for Workgroup install."""

from __future__ import annotations

from typing import Any

# Step-name hints map free-form brief steps onto Lego kinds.
_APPROVAL_NAMES = {"approve", "approval", "review", "signoff", "sign_off", "gate"}
_CONNECTION_NAMES = {
    "publish", "dispatch", "send", "post", "schedule", "deliver", "ship", "release",
}
_RESEARCH_NAMES = {"discover", "research", "qualify", "source", "scout"}
_PRODUCE_NAMES = {
    "produce", "draft", "write", "compose", "create", "build", "render", "package",
    "record", "capture", "brief", "outline",
}


def infer_template(spec: dict[str, Any]) -> str:
    """Pick a graph template from brief fields when template is omitted."""

    explicit = str(spec.get("template") or "").strip().lower()
    if explicit in {"artifact", "publish", "research", "pipeline", "minimal"}:
        return explicit
    connections = list(spec.get("connection_ids") or [])
    external = [str(item).lower() for item in (spec.get("external_actions") or [])]
    approvals = list(spec.get("approval_points") or [])
    steps = [str(item).lower() for item in (spec.get("steps") or [])]
    if connections or any(name in _CONNECTION_NAMES for name in external + steps):
        if approvals or any(name in _APPROVAL_NAMES for name in steps):
            return "publish"
    if any(name in _RESEARCH_NAMES for name in steps) or str(
        spec.get("default_workflow") or ""
    ).lower() in {"research", "lead-research", "discovery"}:
        return "research"
    if steps and len(steps) >= 2:
        return "pipeline"
    return "artifact"


def _node(step_id: str, kind: str, *, employee_id: str | None = None,
          produces: list[str] | None = None, requires: list[str] | None = None,
          skill_ids: list[str] | None = None,
          connection_ids: list[str] | None = None) -> dict[str, Any]:
    return {
        "id": step_id,
        "kind": kind,
        "employee_id": employee_id,
        "produces": list(produces or []),
        "requires": list(requires or []),
        "skill_ids": list(skill_ids or []),
        "connection_ids": list(connection_ids or []),
    }


def _kind_for_step_name(name: str) -> str:
    key = name.lower().replace("-", "_")
    if key in _APPROVAL_NAMES:
        return "approval"
    if key in _CONNECTION_NAMES:
        return "connection"
    return "employee"


def _artifact_for(step_id: str, produces_fallback: list[str], index: int,
                  total: int) -> list[str]:
    if index == total - 1:
        return list(produces_fallback)
    return [f"{step_id}_artifact"]


def build_graph_from_brief(
    *,
    template: str,
    employee: str,
    agents: list[str],
    produces: list[str],
    skill_ids: list[str],
    connection_ids: list[str],
    approval_points: list[str],
    steps: list[str] | None = None,
    external_actions: list[str] | None = None,
) -> tuple[list[str], list[dict[str, Any]]]:
    """Return (step_labels, graph_nodes) for a short Workgroup brief."""

    template = (template or "artifact").lower()
    steps = [str(item) for item in (steps or []) if str(item).strip()]
    external_actions = [str(item) for item in (external_actions or [])]
    skill_ids = list(skill_ids or [])
    connection_ids = list(connection_ids or [])
    produces = list(produces or ["artifact"])
    secondary = agents[1] if len(agents) > 1 else employee

    if template == "minimal":
        labels = steps or ["produce"]
        return labels, [
            _node("produce", "employee", employee_id=employee, produces=produces,
                  skill_ids=skill_ids, connection_ids=connection_ids),
        ]

    if template == "publish":
        package_kind = produces[0] if produces else "content_package"
        receipt_kind = produces[-1] if len(produces) > 1 else "publication_receipt"
        if receipt_kind == package_kind:
            receipt_kind = "publication_receipt"
        labels = steps or ["select", "approve", "dispatch", "verify"]
        graph = [
            _node("select", "employee", employee_id=employee,
                  produces=[package_kind], skill_ids=skill_ids),
            _node(approval_points[0] if approval_points else "approve", "approval",
                  requires=[package_kind]),
            _node("dispatch", "connection", requires=[package_kind],
                  produces=[receipt_kind], connection_ids=connection_ids or ["website"]),
        ]
        return labels, graph

    if template == "research":
        labels = steps or ["discover", "qualify", "research", "record"]
        mid = f"{labels[1]}_artifact" if len(labels) > 1 else "qualified_lead"
        final = produces[0]
        graph = [
            _node("discover", "employee", employee_id=employee,
                  produces=["candidate_lead"], skill_ids=skill_ids,
                  connection_ids=connection_ids),
            _node("qualify", "employee", employee_id=employee,
                  produces=[mid], requires=["candidate_lead"], skill_ids=skill_ids),
            _node("record", "employee", employee_id=secondary,
                  produces=[final], requires=[mid], skill_ids=skill_ids),
        ]
        if approval_points:
            graph.insert(-1, _node(approval_points[0], "approval", requires=[mid]))
            graph[-1]["requires"] = [mid]
        return labels, graph

    if template == "pipeline" or (template == "artifact" and steps):
        labels = steps or ["research", "draft", "review", "record"]
        # Drop pure labels that we still want as approval/connection nodes.
        graph: list[dict[str, Any]] = []
        prior_produces: list[str] = []
        employee_nodes = [name for name in labels if _kind_for_step_name(name) == "employee"]
        employee_count = max(1, len(employee_nodes))
        employee_index = 0
        for name in labels:
            kind = _kind_for_step_name(name)
            if kind == "approval":
                graph.append(_node(name, "approval", requires=list(prior_produces)))
                continue
            if kind == "connection":
                out = [produces[-1]] if produces else ["publication_receipt"]
                graph.append(_node(
                    name, "connection",
                    requires=list(prior_produces) or None,
                    produces=out,
                    connection_ids=connection_ids or ["website"],
                ))
                prior_produces = out
                continue
            out = _artifact_for(name, produces, employee_index, employee_count)
            who = agents[min(employee_index, len(agents) - 1)] if agents else employee
            graph.append(_node(
                name, "employee", employee_id=who, produces=out,
                requires=list(prior_produces) if prior_produces else [],
                skill_ids=skill_ids,
                connection_ids=connection_ids if employee_index == 0 else [],
            ))
            prior_produces = out
            employee_index += 1
        if approval_points and not any(node["kind"] == "approval" for node in graph):
            # Insert approval before final produce/connection when brief asked for a gate.
            insert_at = max(0, len(graph) - 1)
            requires = list(graph[insert_at - 1]["produces"]) if insert_at else []
            graph.insert(insert_at, _node(
                approval_points[0], "approval", requires=requires))
            if insert_at + 1 < len(graph) and graph[insert_at + 1]["kind"] == "employee":
                graph[insert_at + 1]["requires"] = requires
        # Ensure last employee/connection emits the package primary produces.
        for node in reversed(graph):
            if node["kind"] in {"employee", "connection"}:
                node["produces"] = list(produces)
                break
        return labels, graph

    # Default multi-step artifact pipeline.
    labels = steps or ["research", "produce", "review", "record"]
    research_out = "research_note"
    draft_out = produces[0] if produces else "artifact"
    graph = [
        _node("research", "employee", employee_id=employee,
              produces=[research_out], skill_ids=skill_ids,
              connection_ids=connection_ids),
        _node("produce", "employee", employee_id=secondary,
              produces=[draft_out], requires=[research_out], skill_ids=skill_ids),
        _node("record", "employee", employee_id=secondary,
              produces=list(produces), requires=[draft_out], skill_ids=skill_ids),
    ]
    if approval_points:
        graph.insert(2, _node(approval_points[0], "approval", requires=[draft_out]))
        graph[-1]["requires"] = [draft_out]
    return labels, graph


def expand_brief_workflows(spec: dict[str, Any], *, folder: str, agent_ids: list[str],
                           metrics: list[str], evidence_metrics: dict[str, list[str]],
                           skill_ids: list[str], connection_ids: list[str],
                           approval_points: list[str], description: str) -> list[dict[str, Any]]:
    """Build one or more workflows from a short brief."""

    template = infer_template(spec)
    produces = []
    for metric in metrics:
        produces.extend(evidence_metrics.get(metric) or [])
    if not produces:
        produces = [str(item) for item in (spec.get("evidence_sources") or [])] or ["artifact"]
    # De-dupe preserving order.
    seen = set()
    ordered_produces = []
    for item in produces:
        if item not in seen:
            seen.add(item)
            ordered_produces.append(item)

    employee = agent_ids[0]
    workflow_id = str(spec.get("default_workflow") or "primary")
    labels, graph = build_graph_from_brief(
        template=template,
        employee=employee,
        agents=agent_ids,
        produces=ordered_produces,
        skill_ids=skill_ids,
        connection_ids=connection_ids,
        approval_points=approval_points,
        steps=list(spec.get("steps") or []),
        external_actions=list(spec.get("external_actions") or []),
    )
    return [{
        "id": workflow_id,
        "description": description,
        "steps": labels,
        "agents": agent_ids,
        "skills": skill_ids,
        "approvals": approval_points,
        "evidence": ordered_produces,
        "connections": connection_ids,
        "graph": graph,
        "template": template,
    }]
