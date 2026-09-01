"""One human-readable catalog for the universal company vocabulary."""

from pathlib import Path

from . import config as runtime_config
from ..agents import agents as installed_agents
from ..connections import connections as installed_connections
from ..evals import suite_spec as eval_suite_spec, suites as installed_eval_suites
from .package import package_spec, validate_package
from .registry import departments as installed_departments
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
    departments = []
    for _, department in sorted(installed_departments().items()):
        package = package_spec(department)
        package["package_defects"] = validate_package(department)
        package["lego"] = not package["package_defects"]
        departments.append(package)
    return {
        "vocabulary": {
            "canonical": ["Goal", "Department", "Workflow", "Agent",
                          "Skill", "Connection", "Artifact"],
            "rule": "These are the only public company building blocks.",
        },
        "runtime": {
            "version": runtime_config.VERSION,
            "loop": ["GOAL", "OBSERVE", "DECIDE", "ACT", "EVALUATE"],
            "owner_agent": "director",
            "department_runtime": "declarative manifests executed by GoalRuntime",
            "goal_authority": ".spielos/state/company.sqlite",
            "strategy_kernel": strategy_kernel_summary(),
        },
        "departments": departments,
        "agents": [vars(item) for _, item in sorted(installed_agents().items())],
        "skills": _skills(),
        "connections": [vars(item) for _, item in sorted(installed_connections().items())],
        "evals": [eval_suite_spec(item) for _, item in sorted(installed_eval_suites().items())],
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
        "departments": package["departments"],
        "agents": package["agents"],
        "skills": package["skills"],
        "connections": package["connections"],
        "evals": package["evals"],
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
