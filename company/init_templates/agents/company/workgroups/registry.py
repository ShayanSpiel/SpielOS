"""Discover fresh Workgroup packages without executable Departments."""

from __future__ import annotations

import json
from pathlib import Path

from ..runtime.interpreter import InterpretedDepartment
from ..runtime.models import Department, WorkgroupSpec, WorkerSpec, WorkflowSpec, WorkflowStep

ROOT = Path(__file__).resolve().parent


def builtin_specs() -> tuple[dict, ...]:
    """The operational starter catalog shipped with the source product."""
    values = (
        ("product-reliability", "Protect installation, upgrades, and regressions", "reliability-worker", "release_verification"),
        ("ux-experience", "Improve onboarding, commands, delegation, and hand-offs", "ux-worker", "ux_finding"),
        ("real-world-validation", "Collect repeatable real-home validation evidence", "validation-worker", "validation_receipt"),
        ("user-feedback", "Turn user reports into verified problem records", "feedback-worker", "feedback_record"),
        ("release-operations", "Prepare verified releases and upgrade receipts", "release-worker", "release_receipt"),
        ("growth-community", "Measure discoverability and community feedback", "growth-worker", "growth_signal"),
    )
    specs = [{
        "id": group_id, "version": "1.0.0", "description": description,
        "metrics": [evidence], "evidence_metrics": {evidence: [evidence]},
        "workers": [{
            "id": worker_id, "description": description,
            "workbook": [], "workkit": [], "produces": [evidence],
            "workflows": [{
                "id": f"{group_id}-workflow", "description": description,
                "evidence": [evidence],
                "worksteps": [{"id": "execute", "kind": "employee", "produces": [evidence]}],
            }],
        }],
    } for group_id, description, worker_id, evidence in values]
    specs[1] = {
        "id": "ux-experience", "version": "1.0.0",
        "description": "Improve onboarding, commands, delegation, and worker hand-offs.",
        "metrics": ["handoff_validation"],
        "evidence_metrics": {"handoff_validation": ["handoff_validation"]},
        "workers": [
            {"id": "journey-researcher", "description": "Maps a real operator journey and its friction.",
             "workbook": ["journey-analysis"], "workkit": [], "produces": ["journey_observation"],
             "workflows": [{"id": "onboarding-journey-audit", "description": "Observe setup, first command, and first outcome.",
                            "evidence": ["journey_observation"], "worksteps": [
                                {"id": "map-onboarding", "kind": "employee", "produces": ["journey_observation"]}]}]},
            {"id": "interaction-designer", "description": "Turns journey evidence into a bounded UX recommendation.",
             "workbook": ["interaction-design"], "workkit": [], "produces": ["ux_recommendation"],
             "workflows": [{"id": "command-and-delegation-review", "description": "Improve command clarity and delegation feedback.",
                            "evidence": ["ux_recommendation"], "worksteps": [
                                {"id": "review-commands", "kind": "employee", "requires": ["journey_observation"], "produces": ["ux_recommendation"]}]}]},
            {"id": "handoff-validator", "description": "Validates a worker hand-off is clear, bounded, and recoverable.",
             "workbook": ["handoff-validation"], "workkit": [], "produces": ["handoff_validation"],
             "workflows": [{"id": "worker-handoff-validation", "description": "Validate assignment, evidence return, and Director resumption.",
                            "evidence": ["handoff_validation"], "worksteps": [
                                {"id": "validate-handoff", "kind": "employee", "requires": ["ux_recommendation"], "produces": ["handoff_validation"]}]}]},
        ],
    }
    return tuple(specs)


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
    discovered = {group.id: WorkgroupHandler(group) for folder in sorted(ROOT.iterdir())
            if folder.is_dir() and (folder / "workgroup.json").is_file()
            for group in (_group(folder),)}
    for spec in builtin_specs():
        if spec["id"] in discovered:
            continue
        workers = []
        for worker in spec["workers"]:
            flows = []
            for flow in worker["workflows"]:
                graph = tuple(WorkflowStep(
                    id=step["id"], kind=step.get("kind", "employee"),
                    employee_id=worker["id"], produces=tuple(step.get("produces") or ()),
                    requires=tuple(step.get("requires") or ()))
                    for step in flow["worksteps"])
                flows.append(WorkflowSpec(
                    flow["id"], flow["description"], (), (),
                    tuple(flow.get("workbook") or ()), (), tuple(flow["evidence"]),
                    tuple(flow.get("workkit") or ()), graph))
            workers.append(WorkerSpec(
                worker["id"], worker["description"], tuple(worker.get("workbook") or ()),
                tuple(worker.get("workkit") or ()), tuple(worker["produces"]), spec["id"], tuple(flows)))
        discovered[spec["id"]] = WorkgroupHandler(WorkgroupSpec(
            spec["id"], spec["version"], spec["description"], tuple(workers),
            tuple(spec["metrics"]), {}, {key: tuple(value) for key, value in spec["evidence_metrics"].items()}))
    return discovered
