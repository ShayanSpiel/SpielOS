"""One human-readable catalog for the universal company vocabulary."""

from pathlib import Path

from . import config as runtime_config
from .registry import workgroups as installed_workgroups
from .strategy import strategy_kernel_summary

COMPANY_ROOT = Path(__file__).resolve().parents[1]


def _skills():
    from ..agents import skill_files

    values = []
    for path in sorted(skill_files()):
        name, description = path.parent.name, ""
        for line in path.read_text().splitlines()[1:20]:
            if line.startswith("name:"):
                name = line.split(":", 1)[1].strip().strip('"')
            elif line.startswith("description:"):
                description = line.split(":", 1)[1].strip().strip('"')
        values.append({"id": name, "description": description,
                       "path": str(path.relative_to(COMPANY_ROOT.parent))})
    return values


def catalog():
    workgroups = []
    for _, handler in sorted(installed_workgroups().items()):
        group = handler.workgroup
        workgroups.append({
            "id": group.id,
            "version": group.version,
            "description": group.description,
            "metrics": list(group.metrics),
            "workers": [{
                "id": worker.id,
                "description": worker.description,
                "workbook": list(worker.skill_ids),
                "workkit": list(worker.permissions),
                "produces": list(worker.produces),
                "workflows": [_workflow_summary(item) for item in worker.workflows],
            } for worker in group.workers],
        })
    return {
        "vocabulary": {
            "canonical": {"capability": "Workgroup", "executor": "Worker"},
            "input_aliases": {
                "department": "Workgroup",
                "agent": "Worker",
                "employee": "Worker",
            },
            "rule": "Aliases are translated at intake; they never create parallel runtime models.",
        },
        "runtime": {
            "version": runtime_config.VERSION,
            "loop": ["GOAL", "OBSERVE", "DECIDE", "ACT", "EVALUATE"],
            "controls": ["director", "system-improvement"],
            "execution_runtime": "worker-workflow-interpreter",
            "goal_authority": ".spielos/state/company.sqlite",
            "strategy_kernel": strategy_kernel_summary(),
        },
        "workgroups": workgroups,
        "artifact_authority": ".spielos/artifacts/",
    }


def company_overview(runtime, *, project_root: str | Path | None = None) -> dict:
    """One orientation read for Goals, capabilities, executors, and health."""
    from .artifacts import artifact_root
    from .friction import friction_summary

    root = Path(project_root or COMPANY_ROOT.parent).resolve()
    package = catalog()
    snapshot = runtime.company_snapshot(5)
    topology = runtime.topology_audit()
    workers = []
    for group in package["workgroups"]:
        for worker in group["workers"]:
            workers.append({
                "id": worker["id"],
                "workgroup_id": group["id"],
                "workflows": [item["id"] for item in worker["workflows"]],
                "produces": worker["produces"],
            })
    return {
        "schema_version": 1,
        "runtime": package["runtime"],
        "vocabulary": package["vocabulary"],
        "goals": {
            "counts": snapshot["counts"],
            "focus": snapshot.get("focus_goal"),
            "active": snapshot.get("active_goals") or [],
            "topology": {
                "canonical_root_goal_id": topology["canonical_root_goal_id"],
                "root_goal_ids": topology["root_goal_ids"],
                "defect_count": len(topology["defects"]),
                "defects": topology["defects"],
            },
        },
        "workgroups": package["workgroups"],
        "workers": workers,
        "work_orders": snapshot.get("work_orders") or [],
        "attention": snapshot.get("attention") or [],
        "friction": friction_summary(project_root=root),
        "artifacts": {
            "root": str(artifact_root(root)),
            "policy": "goal/run/workflow/{work,final,manifest.json}",
        },
        "migration": {
            "inspect": "company migration inspect --from PATH",
            "plan": "company migration plan --from PATH --out migration-plan.json",
        },
    }


def _workflow_summary(item):
    return {
        "id": item.id,
        "description": item.description,
        "steps": [node.id for node in item.graph] or list(item.steps),
        "workbook": list(item.skill_ids),
        "workkit": list(item.connection_ids),
    }
