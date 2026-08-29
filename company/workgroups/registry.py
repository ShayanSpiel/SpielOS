"""Discover fresh Workgroup packages without executable Departments."""

from __future__ import annotations

import json
from pathlib import Path

from ..runtime.interpreter import InterpretedDepartment
from ..runtime.models import Department, WorkgroupSpec, WorkerSpec, WorkflowSpec, WorkflowStep

ROOT = Path(__file__).resolve().parent


def _workflow(path: Path) -> WorkflowSpec:
    value = json.loads(path.read_text())
    graph = tuple(WorkflowStep(
        id=item["id"], kind=item.get("kind", "employee"),
        employee_id=item.get("worker_id"),
        produces=tuple(item.get("produces") or ()),
        requires=tuple(item.get("requires") or ()),
        skill_ids=tuple(item.get("workbook") or ()),
        connection_ids=tuple(item.get("workkit") or ()),
    ) for item in value.get("worksteps") or ())
    return WorkflowSpec(value["id"], value["description"],
                        tuple(item.id for item in graph), (),
                        tuple(value.get("workbook") or ()),
                        tuple(item.id for item in graph if item.kind == "approval"),
                        tuple(value.get("evidence") or ()),
                        tuple(value.get("workkit") or ()), graph)


def _group(folder: Path) -> WorkgroupSpec:
    value = json.loads((folder / "workgroup.json").read_text())
    workers = []
    for worker_file in sorted((folder / "workers").glob("*/worker.json")):
        worker = json.loads(worker_file.read_text())
        workflows = tuple(_workflow(path) for path in sorted(worker_file.parent.glob("workflows/*.json")))
        workers.append(WorkerSpec(worker["id"], worker["description"],
                                  tuple(worker.get("workbook") or ()),
                                  tuple(worker.get("workkit") or ()),
                                  tuple(worker.get("produces") or ()),
                                  value["id"], workflows))
    return WorkgroupSpec(value["id"], value.get("version", "1.0.0"),
                         value["description"], tuple(workers),
                         tuple(value.get("metrics") or ()),
                         dict(value.get("config_schema") or {}),
                         {key: tuple(items) for key, items in (value.get("evidence_metrics") or {}).items()})


class WorkgroupHandler(InterpretedDepartment, Department):
    """Loop adapter: a Workgroup routes execution to its Worker workflows."""

    def __init__(self, workgroup: WorkgroupSpec):
        self.workgroup = workgroup
        self.id = self.department_id = workgroup.id
        self.version = workgroup.version
        self.description = workgroup.description
        self.agent_ids = tuple(worker.id for worker in workgroup.workers)
        self.workflows = tuple(flow for worker in workgroup.workers for flow in worker.workflows)
        self.workflow_agents = {flow.id: worker.id for worker in workgroup.workers for flow in worker.workflows}
        self.evidence_metrics = dict(workgroup.evidence_metrics)
        self.goal_schema = {"metrics": list(workgroup.metrics), "config": dict(workgroup.config_schema)}


def workgroups() -> dict[str, WorkgroupHandler]:
    return {group.id: WorkgroupHandler(group) for folder in sorted(ROOT.iterdir())
            if folder.is_dir() and (folder / "workgroup.json").is_file()
            for group in (_group(folder),)}
