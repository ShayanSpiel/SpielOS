"""One human-readable catalog for the universal company vocabulary."""

from pathlib import Path

from ..agents import agents as installed_agents
from ..connections import connections as installed_connections
from ..evals import suite_spec as eval_suite_spec, suites as installed_eval_suites
from .package import package_spec, validate_package
from . import config as runtime_config
from .registry import departments as installed_departments, workgroups as installed_workgroups
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
    departments = []
    for _, item in sorted(installed_departments().items()):
        package = package_spec(item)
        package["package_defects"] = validate_package(item)
        package["lego"] = not package["package_defects"]
        departments.append(package)
    return {
        "runtime": {
            "version": runtime_config.VERSION,
            "loop": ["GOAL", "OBSERVE", "DECIDE", "ACT", "EVALUATE"],
            "controls": ["director", "system-improvement"],
            "department_runtime": "interpreter",  # compatibility field
            "execution_runtime": "worker-workflow-interpreter",
            "goal_authority": ".spielos/state/company.sqlite",
            "strategy_kernel": strategy_kernel_summary(),
        },
        "workgroups": workgroups,
        "departments": departments,  # compatibility projection; remove after v7 migration
        "agents": [vars(item) for _, item in sorted(installed_agents().items())],
        "skills": _skills(),
        "connections": [vars(item) for _, item in sorted(installed_connections().items())],
        "evals": [eval_suite_spec(item) for _, item in sorted(installed_eval_suites().items())],
        "artifact_authority": ".spielos/artifacts/",
    }


def _workflow_summary(item):
    return {
        "id": item.id,
        "description": item.description,
        "steps": [node.id for node in item.graph] or list(item.steps),
        "workbook": list(item.skill_ids),
        "workkit": list(item.connection_ids),
    }
