"""Validate and install a fresh Workgroup package.

The package is deliberately small: a Workgroup only groups Workers; every
Worker owns its workflows, workbook methods, and workkit declarations.
"""

from __future__ import annotations

import json
import shutil
import tempfile
from pathlib import Path
from typing import Any


def load_workgroup_spec(folder: Path) -> dict[str, Any]:
    """Read one inspectable Workgroup package directory into install shape."""
    group = json.loads((folder / "workgroup.json").read_text())
    workers = []
    for worker_file in sorted((folder / "workers").glob("*/worker.json")):
        worker = json.loads(worker_file.read_text())
        worker["workflows"] = [
            json.loads(path.read_text())
            for path in sorted(worker_file.parent.glob("workflows/*.json"))]
        workers.append(worker)
    return {**group, "workers": workers}


def bundled_workgroup_specs() -> tuple[dict[str, Any], ...]:
    """Load the real package folders shipped in init_templates."""
    from .bootstrap import template_root

    root = template_root() / "agents" / "company" / "workgroups"
    return tuple(load_workgroup_spec(folder) for folder in sorted(root.iterdir())
                 if folder.is_dir() and (folder / "workgroup.json").is_file())


def validate_workgroup_spec(spec: dict[str, Any]) -> list[str]:
    defects: list[str] = []
    identifier = spec.get("id")
    if not isinstance(identifier, str) or not identifier.replace("-", "").replace("_", "").isalnum():
        defects.append("id must be a non-empty slug")
    if not isinstance(spec.get("description"), str) or not spec["description"].strip():
        defects.append("description is required")
    if not isinstance(spec.get("metrics"), list) or not spec["metrics"]:
        defects.append("metrics must name at least one measurable outcome")
    workers = spec.get("workers")
    if not isinstance(workers, list) or not workers:
        return defects + ["workers must contain at least one Worker"]
    worker_ids: set[str] = set()
    workflow_ids: set[str] = set()
    produced_by_group: set[str] = set()
    for worker in workers:
        if not isinstance(worker, dict):
            defects.append("each Worker must be an object")
            continue
        worker_id = worker.get("id")
        if not isinstance(worker_id, str) or not worker_id:
            defects.append("each Worker needs an id")
            continue
        if worker_id in worker_ids:
            defects.append(f"duplicate Worker id: {worker_id}")
        worker_ids.add(worker_id)
        if not isinstance(worker.get("description"), str) or not worker["description"].strip():
            defects.append(f"Worker '{worker_id}' needs a description")
        if not isinstance(worker.get("produces"), list) or not worker["produces"]:
            defects.append(f"Worker '{worker_id}' must declare evidence it produces")
        else:
            produced_by_group.update(worker["produces"])
        flows = worker.get("workflows")
        if not isinstance(flows, list) or not flows:
            defects.append(f"Worker '{worker_id}' must own at least one Workflow")
            continue
        for flow in flows:
            if not isinstance(flow, dict) or not isinstance(flow.get("id"), str) or not flow["id"]:
                defects.append(f"Worker '{worker_id}' has a Workflow without an id")
                continue
            flow_id = flow["id"]
            if flow_id in workflow_ids:
                defects.append(f"duplicate Workflow id: {flow_id}")
            workflow_ids.add(flow_id)
            if not isinstance(flow.get("description"), str) or not flow["description"].strip():
                defects.append(f"Workflow '{flow_id}' needs a description")
            evidence = flow.get("evidence")
            if not isinstance(evidence, list) or not evidence:
                defects.append(f"Workflow '{flow_id}' must declare evidence")
            steps = flow.get("worksteps")
            if not isinstance(steps, list) or not steps:
                defects.append(f"Workflow '{flow_id}' must contain worksteps")
                continue
            seen_step_ids: set[str] = set()
            for step in steps:
                if not isinstance(step, dict) or not isinstance(step.get("id"), str):
                    defects.append(f"Workflow '{flow_id}' has a workstep without an id")
                    continue
                if step["id"] in seen_step_ids:
                    defects.append(f"Workflow '{flow_id}' has duplicate workstep '{step['id']}'")
                seen_step_ids.add(step["id"])
                if not isinstance(step.get("produces"), list) or not step["produces"]:
                    defects.append(f"Workstep '{step['id']}' must produce evidence")
                else:
                    produced_by_group.update(step["produces"])
                assigned = step.get("worker_id", worker_id)
                if assigned not in worker_ids and assigned not in {
                        item.get("id") for item in workers if isinstance(item, dict)}:
                    defects.append(
                        f"Workstep '{step['id']}' names unknown Worker '{assigned}'")
    for worker in workers:
        if not isinstance(worker, dict):
            continue
        for flow in worker.get("workflows") or []:
            if not isinstance(flow, dict):
                continue
            for step in flow.get("worksteps") or []:
                if not isinstance(step, dict):
                    continue
                for required in step.get("requires") or []:
                    if required not in produced_by_group:
                        defects.append(
                            f"Workstep '{step.get('id')}' requires unknown evidence '{required}'")
            for expected in flow.get("evidence") or []:
                if expected not in produced_by_group:
                    defects.append(
                        f"Workflow '{flow.get('id')}' declares unproduced evidence '{expected}'")
    return defects


def install_workgroup(spec: dict[str, Any], *, root: Path, force: bool = False) -> dict[str, Any]:
    defects = validate_workgroup_spec(spec)
    if defects:
        raise ValueError("invalid Workgroup package: " + "; ".join(defects))
    target = root / spec["id"]
    if target.exists() and not force:
        raise FileExistsError(f"Workgroup '{spec['id']}' already exists; pass --force to replace")
    root.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{spec['id']}-", dir=root))
    try:
        group = {key: spec[key] for key in ("id", "description", "metrics")}
        for key in ("version", "config_schema", "evidence_metrics"):
            if key in spec:
                group[key] = spec[key]
        (staging / "workgroup.json").write_text(json.dumps(group, indent=2) + "\n")
        for worker in spec["workers"]:
            worker_dir = staging / "workers" / worker["id"]
            (worker_dir / "workflows").mkdir(parents=True)
            identity = {key: worker.get(key, []) for key in ("id", "description", "workbook", "workkit", "produces")}
            (worker_dir / "worker.json").write_text(json.dumps(identity, indent=2) + "\n")
            for flow in worker["workflows"]:
                flow = dict(flow)
                flow.setdefault("workbook", worker.get("workbook", []))
                flow.setdefault("workkit", worker.get("workkit", []))
                for step in flow.get("worksteps") or []:
                    if step.get("kind", "employee") == "employee":
                        step.setdefault("worker_id", worker["id"])
                (worker_dir / "workflows" / f"{flow['id']}.json").write_text(
                    json.dumps(flow, indent=2) + "\n")
        if target.exists():
            shutil.rmtree(target)
        staging.replace(target)
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    return {"id": spec["id"], "workers": [item["id"] for item in spec["workers"]],
            "workflows": [flow["id"] for item in spec["workers"] for flow in item["workflows"]],
            "path": str(target)}
