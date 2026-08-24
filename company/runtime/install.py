"""Install declarative Department Lego packages from a department_spec.

Director / system-improvement / CLI turn JSON into a discoverable
departments/{id}/department.py that the interpreter can run.
"""

from __future__ import annotations

import importlib
import json
import os
import re
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any

from .package import package_spec, validate_package
from .templates import expand_brief_workflows, infer_template

COMPANY_ROOT = Path(__file__).resolve().parents[1]
DEPARTMENTS_ROOT = COMPANY_ROOT / "departments"
AGENTS_INSTALLED_ROOT = COMPANY_ROOT / "agents" / "installed"
REPO_ROOT = COMPANY_ROOT.parent

_ID_RE = re.compile(r"^[a-z][a-z0-9_]*$")
_AGENT_ID_RE = re.compile(r"^[a-z][a-z0-9_-]*$")
_RESERVED = {"director", "system_improvement", "system-improvement", "email", "base"}


def module_folder(department_id: str) -> str:
    return department_id.replace("-", "_")


def class_name(department_id: str) -> str:
    parts = re.split(r"[_-]+", department_id)
    return "".join(part[:1].upper() + part[1:] for part in parts if part) + "Department"


def agent_file_stem(agent_id: str) -> str:
    return agent_id.replace("-", "_")


def synthesize_agents(normalized: dict[str, Any],
                      explicit: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    """Build AgentSpec dicts for every agent_id referenced by the package."""

    by_id: dict[str, dict[str, Any]] = {}
    for item in explicit or []:
        agent_id = str(item.get("id") or "").strip()
        if not agent_id:
            continue
        by_id[agent_id] = {
            "id": agent_id,
            "description": str(item.get("description") or f"{agent_id} employee"),
            "skill_ids": [str(value) for value in (item.get("skill_ids") or [])],
            "permissions": [str(value) for value in (
                item.get("permissions") or ("read_strategy", "write_evidence"))],
            "produces": [str(value) for value in (item.get("produces") or [])],
        }

    for agent_id in normalized["agent_ids"]:
        produces: list[str] = []
        skills: list[str] = []
        for workflow in normalized["workflows"]:
            for node in workflow.get("graph") or []:
                if node.get("employee_id") == agent_id:
                    produces.extend(str(value) for value in (node.get("produces") or []))
                    skills.extend(str(value) for value in (node.get("skill_ids") or []))
            skills.extend(str(value) for value in (workflow.get("skills") or []))
        # unique preserve order
        def uniq(values: list[str]) -> list[str]:
            seen: set[str] = set()
            out: list[str] = []
            for value in values:
                if value and value not in seen:
                    seen.add(value)
                    out.append(value)
            return out

        current = by_id.get(agent_id, {
            "id": agent_id,
            "description": f"{agent_id} for {normalized['id']}",
            "skill_ids": [],
            "permissions": ["read_strategy", "write_evidence"],
            "produces": [],
        })
        current["produces"] = uniq(list(current.get("produces") or []) + produces) or ["artifact"]
        current["skill_ids"] = uniq(list(current.get("skill_ids") or []) + skills)
        current["permissions"] = uniq(list(current.get("permissions") or [
            "read_strategy", "write_evidence"]))
        by_id[agent_id] = current

    # Preserve package agent_ids order, then any extras.
    ordered = []
    seen_ids = set()
    for agent_id in list(normalized["agent_ids"]) + list(by_id):
        if agent_id in seen_ids or agent_id not in by_id:
            continue
        seen_ids.add(agent_id)
        ordered.append(by_id[agent_id])
    return ordered


def normalize_department_spec(raw: dict[str, Any], *,
                              default_id: str | None = None,
                              default_version: str | None = None) -> dict[str, Any]:
    """Accept package_spec shape or a short create_department brief."""

    if not isinstance(raw, dict):
        raise ValueError("department_spec must be a JSON object")
    spec = dict(raw)
    dept_id = str(spec.get("id") or default_id or "").strip()
    if not dept_id:
        raise ValueError("department_spec.id is required")
    folder = module_folder(dept_id)
    if not _ID_RE.match(folder):
        raise ValueError(
            f"department id '{dept_id}' is invalid; use lowercase letters, digits, underscore")
    if folder in _RESERVED or dept_id in _RESERVED:
        raise ValueError(f"department id '{dept_id}' is reserved")

    description = str(
        spec.get("description") or spec.get("purpose") or f"{dept_id} department"
    ).strip()
    version = str(spec.get("version") or default_version or "1.0.0").strip()
    metrics = [str(item) for item in (spec.get("metrics") or []) if str(item).strip()]
    agent_ids = [str(item) for item in (spec.get("agent_ids") or []) if str(item).strip()]
    explicit_agents = list(spec.get("agents") or [])
    for item in explicit_agents:
        agent_id = str((item or {}).get("id") or "").strip()
        if agent_id and agent_id not in agent_ids:
            agent_ids.append(agent_id)
    if not agent_ids:
        prefix = folder.replace("_", "-")
        agent_ids = [f"{prefix}-operator", f"{prefix}-specialist"]

    for agent_id in agent_ids:
        if not _AGENT_ID_RE.match(agent_id):
            raise ValueError(f"agent id '{agent_id}' is invalid")

    evidence_metrics = {
        str(key): [str(kind) for kind in (value or [])]
        for key, value in (spec.get("evidence_metrics") or {}).items()
    }
    workflow_agents = {
        str(key): str(value)
        for key, value in (spec.get("workflow_agents") or {}).items()
    }
    skill_ids = [str(item) for item in (spec.get("skill_ids") or []) if str(item).strip()]
    connection_ids = [str(item) for item in (spec.get("connection_ids") or []) if str(item).strip()]
    approval_points = [str(item) for item in (spec.get("approval_points") or []) if str(item).strip()]

    workflows = list(spec.get("workflows") or [])
    if not workflows:
        evidence_sources = [str(item) for item in (spec.get("evidence_sources") or [])]
        produces = evidence_sources or ([f"{metrics[0]}_record"] if metrics else ["artifact"])
        if not metrics:
            metrics = ["artifacts"]
        for metric in metrics:
            evidence_metrics.setdefault(metric, list(produces))
        workflows = expand_brief_workflows(
            spec, folder=folder, agent_ids=agent_ids, metrics=metrics,
            evidence_metrics=evidence_metrics, skill_ids=skill_ids,
            connection_ids=connection_ids, approval_points=approval_points,
            description=description,
        )
        for workflow in workflows:
            workflow_agents.setdefault(
                workflow["id"], (workflow.get("agents") or agent_ids)[0])

    if not metrics:
        metrics = list(evidence_metrics) or ["artifacts"]
        if metrics == ["artifacts"] and not evidence_metrics:
            evidence_metrics["artifacts"] = ["artifact"]

    for workflow in workflows:
        workflow.setdefault("steps", ["produce"])
        workflow.setdefault("agents", agent_ids)
        workflow.setdefault("skills", skill_ids)
        workflow.setdefault("approvals", approval_points)
        workflow.setdefault("evidence", [])
        workflow.setdefault("connections", connection_ids)
        workflow.setdefault("graph", [])
        workflow.setdefault("description", description)
        if not workflow.get("id"):
            raise ValueError("each workflow needs an id")
        if not workflow_agents.get(workflow["id"]) and workflow.get("agents"):
            workflow_agents[workflow["id"]] = workflow["agents"][0]
        for node in workflow["graph"]:
            node.setdefault("kind", "employee")
            node.setdefault("produces", [])
            node.setdefault("requires", [])
            node.setdefault("skill_ids", [])
            node.setdefault("connection_ids", [])
            if node["kind"] == "employee" and not node.get("employee_id"):
                node["employee_id"] = workflow_agents.get(workflow["id"]) or agent_ids[0]
            if node["kind"] == "employee" and not node["produces"]:
                node["produces"] = list(
                    workflow.get("evidence") or evidence_metrics.get(metrics[0], ["artifact"]))
            if node.get("employee_id") and node["employee_id"] not in agent_ids:
                agent_ids.append(node["employee_id"])

    for metric in metrics:
        evidence_metrics.setdefault(
            metric, list(next(iter(evidence_metrics.values()), ["artifact"])))

    config_schema = dict(spec.get("config_schema") or {})
    config_schema.setdefault(
        "workflow", {"enum": [workflow["id"] for workflow in workflows]})
    config_schema.setdefault("required_count", {"type": "integer"})

    normalized = {
        "id": folder,
        "department_id": folder,
        "version": version,
        "description": description,
        "agent_ids": agent_ids,
        "workflow_agents": workflow_agents,
        "evidence_metrics": evidence_metrics,
        "metrics": metrics,
        "config_schema": config_schema,
        "workflows": workflows,
        "template": infer_template(spec) if not spec.get("workflows") else spec.get("template"),
    }
    normalized["agents"] = synthesize_agents(normalized, explicit_agents)
    return normalized


def validate_department_spec(spec: dict[str, Any]) -> list[str]:
    try:
        normalized = normalize_department_spec(spec)
    except ValueError as error:
        return [str(error)]
    defects = []
    if not normalized["workflows"]:
        defects.append("no workflows")
    if not normalized["metrics"]:
        defects.append("no metrics")
    if not normalized["agent_ids"]:
        defects.append("no agent_ids")
    from ..agents import AGENTS, agents as installed_agents
    from ..agents import known_skill_ids
    from ..connections import connections as installed_connections
    known_agents = set(installed_agents()) | {
        item["id"] for item in normalized.get("agents") or []
    }
    # Skills live inside the departments that use them (plus operator skills
    # under company/skills/); every discovered skill is department-bindable.
    known_skills = known_skill_ids()
    known_connections = set(installed_connections())
    explicit_agent_ids = {
        str(item.get("id") or "") for item in (spec.get("agents") or [])
    }
    for agent_id in sorted(explicit_agent_ids & set(AGENTS)):
        defects.append(f"agent {agent_id} is built-in and cannot be redefined")

    def skill_defect(owner: str, skill_id: str) -> str | None:
        if skill_id not in known_skills:
            return f"{owner} references unknown skill {skill_id}"
        return None

    for agent in normalized.get("agents") or []:
        for skill_id in agent.get("skill_ids") or []:
            defect = skill_defect(f"agent {agent['id']}", skill_id)
            if defect:
                defects.append(defect)
    stems: dict[str, str] = {}
    for agent_id in normalized["agent_ids"]:
        stem = agent_file_stem(agent_id)
        if stem in stems and stems[stem] != agent_id:
            defects.append(
                f"agent ids {stems[stem]} and {agent_id} share installed filename {stem}.json")
        stems[stem] = agent_id
    workflow_ids: set[str] = set()
    for workflow in normalized["workflows"]:
        workflow_id = str(workflow.get("id") or "")
        if workflow_id in workflow_ids:
            defects.append(f"duplicate workflow id {workflow_id}")
        workflow_ids.add(workflow_id)
        for agent_id in workflow.get("agents") or []:
            if agent_id not in known_agents:
                defects.append(f"workflow {workflow_id} references unknown agent {agent_id}")
        for skill_id in workflow.get("skills") or []:
            defect = skill_defect(f"workflow {workflow_id}", skill_id)
            if defect:
                defects.append(defect)
        for connection_id in workflow.get("connections") or []:
            if connection_id not in known_connections:
                defects.append(
                    f"workflow {workflow_id} references unknown connection {connection_id}")
        step_ids: set[str] = set()
        for node in workflow.get("graph") or []:
            step_id = str(node.get("id") or "")
            if not step_id:
                defects.append(f"workflow {workflow_id} has a step without id")
            elif step_id in step_ids:
                defects.append(f"workflow {workflow_id} has duplicate step id {step_id}")
            step_ids.add(step_id)
            kind = node.get("kind")
            if kind not in {"employee", "approval", "connection", "machine"}:
                defects.append(f"workflow {workflow_id} unknown step kind {kind}")
            if kind == "employee" and not node.get("employee_id"):
                defects.append(f"workflow {workflow_id} employee step needs employee_id")
            if node.get("employee_id") and node["employee_id"] not in known_agents:
                defects.append(
                    f"workflow {workflow_id} step {step_id} references unknown agent "
                    f"{node['employee_id']}")
            for skill_id in node.get("skill_ids") or []:
                defect = skill_defect(
                    f"workflow {workflow_id} step {step_id}", skill_id)
                if defect:
                    defects.append(defect)
            if kind == "connection" and not (
                node.get("connection_ids") or workflow.get("connections")
            ):
                defects.append(f"workflow {workflow_id} connection step needs connections")
            for connection_id in node.get("connection_ids") or []:
                if connection_id not in known_connections:
                    defects.append(
                        f"workflow {workflow_id} step {step_id} references unknown connection "
                        f"{connection_id}")
    for metric in normalized["metrics"]:
        if not normalized["evidence_metrics"].get(metric):
            defects.append(f"metric {metric} has no accepted evidence kinds")
    for metric, kinds in normalized["evidence_metrics"].items():
        if not kinds:
            defects.append(f"evidence_metrics[{metric}] is empty")
    return list(dict.fromkeys(defects))


def _py_tuple(values: list | tuple) -> str:
    items = list(values)
    if not items:
        return "()"
    body = ", ".join(repr(item) for item in items)
    return f"({body},)" if len(items) == 1 else f"({body})"


def _py_step(node: dict[str, Any]) -> str:
    return (
        f"WorkflowStep({node.get('id')!r}, {node.get('kind', 'employee')!r}, "
        f"{node.get('employee_id')!r}, produces={_py_tuple(node.get('produces') or [])}, "
        f"requires={_py_tuple(node.get('requires') or [])}, "
        f"skill_ids={_py_tuple(node.get('skill_ids') or [])}, "
        f"connection_ids={_py_tuple(node.get('connection_ids') or [])})"
    )


def _py_workflow(workflow: dict[str, Any]) -> str:
    graph = workflow.get("graph") or []
    if graph:
        graph_src = "(\n" + ",\n".join(
            f"                {_py_step(node)}" for node in graph
        ) + ",\n            )"
    else:
        graph_src = "()"
    return (
        f"WorkflowSpec(\n"
        f"            {workflow['id']!r},\n"
        f"            {workflow.get('description', '')!r},\n"
        f"            {_py_tuple(workflow.get('steps') or ['produce'])},\n"
        f"            {_py_tuple(workflow.get('agents') or [])},\n"
        f"            {_py_tuple(workflow.get('skills') or [])},\n"
        f"            {_py_tuple(workflow.get('approvals') or [])},\n"
        f"            {_py_tuple(workflow.get('evidence') or [])},\n"
        f"            {_py_tuple(workflow.get('connections') or [])},\n"
        f"            graph={graph_src},\n"
        f"        )"
    )


def render_department_module(spec: dict[str, Any]) -> str:
    normalized = normalize_department_spec(spec)
    name = class_name(normalized["id"])
    workflows_src = ",\n        ".join(_py_workflow(item) for item in normalized["workflows"])
    evidence_lines = ",\n        ".join(
        f"{key!r}: {_py_tuple(value)}"
        for key, value in normalized["evidence_metrics"].items()
    )
    workflow_agents_src = ",\n        ".join(
        f"{key!r}: {value!r}" for key, value in normalized["workflow_agents"].items()
    )
    return f'''"""Auto-installed Department Lego package: {normalized["id"]}."""

from .._evidence import EvidenceDepartment
from ...runtime.models import Department, WorkflowSpec, WorkflowStep


class {name}(EvidenceDepartment, Department):
    id = department_id = {normalized["id"]!r}
    version = {normalized["version"]!r}
    description = {normalized["description"]!r}
    agent_ids = {_py_tuple(normalized["agent_ids"])}
    workflows = (
        {workflows_src},
    )
    goal_schema = {{
        "metrics": {json.dumps(normalized["metrics"])},
        "config": {json.dumps(normalized["config_schema"])},
    }}
    evidence_metrics = {{
        {evidence_lines},
    }}
    workflow_agents = {{
        {workflow_agents_src}
    }}
'''


def department_paths(department_id: str, *, root: Path | None = None) -> dict[str, Path]:
    root = root or DEPARTMENTS_ROOT
    folder = root / module_folder(department_id)
    return {
        "folder": folder,
        "init": folder / "__init__.py",
        "department": folder / "department.py",
        "spec": folder / "package.json",
    }


def allowed_install_files(department_id: str, agent_ids: list[str] | None = None) -> list[str]:
    folder = module_folder(department_id)
    base = f".agents/company/departments/{folder}"
    files = [f"{base}/__init__.py", f"{base}/department.py", f"{base}/package.json"]
    for agent_id in agent_ids or []:
        stem = agent_file_stem(agent_id)
        files.append(f".agents/company/agents/installed/{stem}.json")
    return files


def _purge_module_cache(department_id: str) -> None:
    folder = module_folder(department_id)
    prefix = f"company.departments.{folder}"
    for key in list(sys.modules):
        if key == prefix or key.startswith(prefix + "."):
            del sys.modules[key]
    # Agents roster may also change during install.
    for key in list(sys.modules):
        if key == "company.agents" or key.startswith("company.agents."):
            del sys.modules[key]
    importlib.invalidate_caches()


def _assert_allowed(written: list[str], allowed_files: list[str] | None) -> None:
    if allowed_files is None:
        return
    allowed = {item.replace("\\", "/") for item in allowed_files}
    for path in written:
        normalized = path.replace("\\", "/")
        if normalized in allowed:
            continue
        if any(normalized.endswith(item) or item.endswith(normalized) for item in allowed):
            continue
        raise PermissionError(
            f"install would write {normalized} which is outside allowed_files")


def load_installed_department(department_id: str):
    """Import the installed department instance from the live company tree."""

    folder = module_folder(department_id)
    _purge_module_cache(department_id)
    module = importlib.import_module(f"company.departments.{folder}.department")
    from .models import Department
    candidates = [value for value in vars(module).values()
                  if isinstance(value, type) and issubclass(value, Department)
                  and value is not Department and value.__module__ == module.__name__]
    if len(candidates) != 1:
        raise ValueError(
            f"installed module must export exactly one Department, found {len(candidates)}")
    return candidates[0]()


def install_agents(agents: list[dict[str, Any]], *,
                   root: Path | None = None,
                   force: bool = False,
                   allowed_files: list[str] | None = None) -> list[str]:
    """Write AgentSpec JSON files under agents/installed/ and return paths written."""

    root = Path(root) if root else AGENTS_INSTALLED_ROOT
    live = root.resolve() == AGENTS_INSTALLED_ROOT.resolve()
    written: list[str] = []
    root.mkdir(parents=True, exist_ok=True)
    from ..agents import AGENTS
    for agent in agents:
        agent_id = str(agent.get("id") or "").strip()
        if not agent_id or not _AGENT_ID_RE.match(agent_id):
            raise ValueError(f"invalid agent id in roster: {agent_id!r}")
        if agent_id in AGENTS:
            # Packages may reuse a built-in employee but never shadow it.
            continue
        stem = agent_file_stem(agent_id)
        path = root / f"{stem}.json"
        rel = f".agents/company/agents/installed/{stem}.json"
        payload = {
            "id": agent_id,
            "description": str(agent.get("description") or f"{agent_id} employee"),
            "skill_ids": list(agent.get("skill_ids") or []),
            "permissions": list(agent.get("permissions") or ("read_strategy", "write_evidence")),
            "produces": list(agent.get("produces") or ["artifact"]),
        }
        target = rel if live else str(path)
        _assert_allowed([rel if live else str(path)], allowed_files)
        if path.exists() and not force:
            # Same id already installed — overwrite only when force, else refresh description/produces.
            existing = json.loads(path.read_text(encoding="utf-8"))
            if existing.get("id") == agent_id:
                # Merge produces/skills upward for evolving packages.
                def merge(key):
                    values = list(existing.get(key) or [])
                    for item in payload[key]:
                        if item not in values:
                            values.append(item)
                    payload[key] = values
                merge("skill_ids")
                merge("permissions")
                merge("produces")
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        written.append(target)
    return written


def _write_package_files(paths: dict[str, Path], normalized: dict[str, Any]) -> None:
    """Write a complete package tree after syntax-checking generated source."""

    source = render_department_module(normalized)
    compile(source, str(paths["department"]), "exec")
    paths["folder"].mkdir(parents=True, exist_ok=True)
    paths["init"].write_text('"""Installed Department package."""\n', encoding="utf-8")
    paths["department"].write_text(source, encoding="utf-8")
    paths["spec"].write_text(
        json.dumps(normalized, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _install_live_transaction(normalized: dict[str, Any], *, force: bool,
                              allowed_files: list[str] | None) -> tuple[list[str], Any]:
    """Stage, swap, discover, and roll back a live package as one transaction."""

    target_paths = department_paths(normalized["id"])
    if target_paths["department"].exists() and not force:
        raise FileExistsError(
            f"department '{normalized['id']}' already exists; pass force=True to overwrite")
    if target_paths["folder"].exists() and not target_paths["spec"].exists():
        raise ValueError(
            f"department '{normalized['id']}' is built-in and cannot be overwritten")

    from ..agents import AGENTS
    target_owned: set[str] = set()
    if target_paths["spec"].is_file():
        try:
            target_owned = set(json.loads(
                target_paths["spec"].read_text(encoding="utf-8")).get("agent_ids") or [])
        except (OSError, json.JSONDecodeError):
            raise ValueError(
                f"department '{normalized['id']}' has an unreadable installed package.json")
    installed_files: dict[str, str] = {}
    for path in AGENTS_INSTALLED_ROOT.glob("*.json"):
        try:
            existing_id = str(json.loads(path.read_text(encoding="utf-8")).get("id") or "")
        except (OSError, json.JSONDecodeError):
            raise ValueError(f"installed agent record is unreadable: {path.name}")
        if existing_id:
            installed_files[path.stem] = existing_id
    for agent_id in normalized["agent_ids"]:
        stem = agent_file_stem(agent_id)
        existing_id = installed_files.get(stem)
        if existing_id and (existing_id != agent_id or agent_id not in target_owned):
            raise ValueError(
                f"agent '{agent_id}' conflicts with installed employee '{existing_id}'")
    installable_agents = [
        item for item in normalized.get("agents") or [] if item["id"] not in AGENTS
    ]
    planned = allowed_install_files(
        normalized["id"], [item["id"] for item in installable_agents])
    _assert_allowed(planned, allowed_files)

    with tempfile.TemporaryDirectory(
            prefix=".department-install-", dir=str(DEPARTMENTS_ROOT.parent)) as tmp:
        temporary = Path(tmp)
        staged_paths = department_paths(
            normalized["id"], root=temporary / "departments")
        _write_package_files(staged_paths, normalized)
        staged_agents = temporary / "agents"
        install_agents(installable_agents, root=staged_agents, force=True)

        backup = temporary / "backup"
        backup.mkdir()
        backup_department = backup / "department"
        backup_agents = backup / "agents"
        backup_agents.mkdir()
        moved_agents: list[tuple[Path, Path | None]] = []
        department_had_backup = False
        try:
            if target_paths["folder"].exists():
                os.replace(target_paths["folder"], backup_department)
                department_had_backup = True
            target_paths["folder"].parent.mkdir(parents=True, exist_ok=True)
            os.replace(staged_paths["folder"], target_paths["folder"])

            AGENTS_INSTALLED_ROOT.mkdir(parents=True, exist_ok=True)
            for staged in sorted(staged_agents.glob("*.json")):
                target = AGENTS_INSTALLED_ROOT / staged.name
                previous = None
                if target.exists():
                    previous = backup_agents / staged.name
                    os.replace(target, previous)
                moved_agents.append((target, previous))
                os.replace(staged, target)

            instance = load_installed_department(normalized["id"])
            defects = validate_package(instance)
            if defects:
                raise ValueError(
                    "installed package failed validation: " + "; ".join(defects))
            from ..agents import agents as installed_agents
            roster = installed_agents()
            missing = [agent_id for agent_id in normalized["agent_ids"]
                       if agent_id not in roster]
            if missing:
                raise ValueError(f"installed agents missing from roster: {', '.join(missing)}")
            return planned, instance
        except Exception:
            if target_paths["folder"].exists():
                shutil.rmtree(target_paths["folder"])
            if department_had_backup:
                os.replace(backup_department, target_paths["folder"])
            for target, previous in reversed(moved_agents):
                target.unlink(missing_ok=True)
                if previous and previous.exists():
                    os.replace(previous, target)
            _purge_module_cache(normalized["id"])
            raise


def install_department(spec: dict[str, Any], *,
                       root: Path | None = None,
                       agents_root: Path | None = None,
                       default_id: str | None = None,
                       default_version: str | None = None,
                       force: bool = False,
                       allowed_files: list[str] | None = None) -> dict[str, Any]:
    """Write a Department package + agent roster entries and validate discovery."""

    normalized = normalize_department_spec(
        spec, default_id=default_id, default_version=default_version)
    defects = validate_department_spec(normalized)
    if defects:
        raise ValueError("invalid department_spec: " + "; ".join(defects))

    root = Path(root) if root else DEPARTMENTS_ROOT
    live = root.resolve() == DEPARTMENTS_ROOT.resolve()
    paths = department_paths(normalized["id"], root=root)
    if live:
        written, instance = _install_live_transaction(
            normalized, force=force, allowed_files=allowed_files)
        package = package_spec(instance)
        from ..agents import agents as installed_agents
        roster = installed_agents()
        agents_loaded = [roster[agent_id].id for agent_id in normalized["agent_ids"]]
        agent_paths = [path for path in written if "/agents/installed/" in path]
        package_defects: list[str] = []
    else:
        if paths["department"].exists() and not force:
            raise FileExistsError(
                f"department '{normalized['id']}' already exists; pass force=True to overwrite")
        local_agents_root = Path(agents_root) if agents_root else root.parent / "agents"
        agent_paths = install_agents(
            normalized.get("agents") or [], root=local_agents_root,
            force=force, allowed_files=allowed_files)
        _write_package_files(paths, normalized)
        written = [str(paths["init"]), str(paths["department"]), str(paths["spec"]), *agent_paths]
        package = normalized
        package_defects = []
        agents_loaded = [item["id"] for item in normalized.get("agents") or []]

    return {
        "id": normalized["id"],
        "version": normalized["version"],
        "written": written,
        "agents_written": agent_paths,
        "agents": agents_loaded,
        "template": normalized.get("template"),
        "package": package,
        "defects": package_defects,
        "checks": {
            "normalized": True,
            "references_resolved": True,
            "generated_source_compiles": True,
            "catalog_discovery": bool(live),
            "agent_roster_loaded": bool(live),
        },
        "ok": True,
    }
