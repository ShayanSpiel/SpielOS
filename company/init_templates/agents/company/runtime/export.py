"""Department portability: export one department as a portable ``.sdep``
bundle, and install a bundle (or a built-in example) into the current home.

A bundle is a directory (or a ``.tar.gz`` of one) containing::

    manifest.json          id, version, files[] with sha256, requires
    department/**          the whole departments/<id>/ folder
    skills/**              every Skill bound by its Workflows or Agents
    README.md              human summary

Bundles never contain strategy, assets, credentials, or run state — those
are user-layer. The receiving side re-validates everything through the
normal ``department install`` path.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import tarfile
from pathlib import Path
from typing import Any

COMPANY_ROOT = Path(__file__).resolve().parents[1]
DEPARTMENTS_ROOT = COMPANY_ROOT / "departments"

RETIRED_HOST_AGENTS = {
    "codex": ("workgroup-runner.toml",),
    "opencode": ("workgroup-runner.md",),
}

RETIRED_HARNESS_FILES = ("runtime/workgroup_install.py",)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _declared_dependencies(department, roster: dict) -> tuple[list[str], list[str]]:
    """Return dependencies from the loaded Department model, never source text.

    Workflow and graph declarations are both authoritative. Agent Skills are
    included as well because their exported specifications bind those Skills
    even when a Workflow does not repeat the declaration.
    """
    skills: set[str] = set()
    connections: set[str] = set()
    for workflow in department.workflows:
        skills.update(workflow.skill_ids)
        connections.update(workflow.connection_ids)
        for step in workflow.graph:
            skills.update(step.skill_ids)
            connections.update(step.connection_ids)
    for agent_id in department.agent_ids:
        agent = roster.get(agent_id)
        if agent is not None:
            skills.update(agent.skill_ids)
    return sorted(skills), sorted(connections)


def _known_skill_ids() -> set[str]:  # kept for external tooling/debugging
    from ..agents import known_skill_ids

    return known_skill_ids()


def export_department(department_id: str, out_dir: Path | None = None) -> dict:
    """Bundle departments/<id>/ + its company skills into a portable package."""
    dept_dir = DEPARTMENTS_ROOT / department_id
    if not dept_dir.is_dir():
        raise ValueError(f"no such department: {department_id}")

    from ..agents import agents as installed_agents
    from .registry import departments as installed_departments

    department = installed_departments()[department_id]
    roster = installed_agents()
    required_skills, connection_ids = _declared_dependencies(department, roster)

    out_root = (out_dir or Path.cwd()).resolve()
    stamp = out_root / f"{department_id}.sdep"
    staging = out_root / f".{department_id}.sdep.tmp"
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(parents=True)

    copied: list[str] = []
    files: list[dict[str, str]] = []

    def _emit(src: Path, rel: str) -> None:
        dest = staging / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)
        copied.append(rel)
        files.append({"path": rel, "sha256": _sha256(src)})

    def _emit_json(rel: str, payload: dict[str, Any]) -> None:
        dest = staging / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(json.dumps(payload, indent=2) + "\n")
        copied.append(rel)
        files.append({"path": rel, "sha256": _sha256(dest)})

    for path in sorted(dept_dir.rglob("*")):
        if path.is_file() and "__pycache__" not in path.parts:
            _emit(path, f"department/{path.relative_to(dept_dir)}")

    for skill_id in required_skills:
        skill_dir = _find_skill_dir(skill_id)
        if skill_dir is None:
            raise ValueError(
                f"department '{department_id}' binds skill '{skill_id}' "
                "which is not installed; install it first")
        for path in sorted(skill_dir.rglob("*")):
            if path.is_file() and "__pycache__" not in path.parts:
                _emit(path, f"skills/{skill_id}/{path.relative_to(skill_dir)}")

    for agent_id in department.agent_ids:
        if agent_id not in roster:
            raise ValueError(
                f"department '{department_id}' references unknown Agent '{agent_id}'")
        agent = roster[agent_id]
        _emit_json(f"agents/{agent_id.replace('-', '_')}.json", {
            "id": agent.id, "description": agent.description,
            "skill_ids": list(agent.skill_ids),
            "permissions": list(agent.permissions),
            "produces": list(agent.produces),
        })

    manifest = {
        "kind": "spielos-department",
        "manifest_version": 1,
        "id": department_id,
        "requires": {"agents": list(department.agent_ids),
                     "skills": required_skills, "connections": connection_ids},
        "files": files,
    }
    (staging / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")

    with tarfile.open(stamp, "w:gz") as tar:
        tar.add(staging, arcname=f"{department_id}.sdep")
    shutil.rmtree(staging)

    return {"bundle": str(stamp), "id": department_id,
            "files": len(files), "skills": required_skills,
            "connections": connection_ids}


def _find_skill_dir(skill_id: str) -> Path | None:
    from ..agents import find_skill_dir as _locate

    return _locate(skill_id)


def add_department(source: str, *, force: bool = False,
                   target: str | Path | None = None) -> dict:
    """Install a department into the current home from a .sdep file, a
    bundle directory, or a built-in example id shipped with the package."""
    source_path = Path(source)

    if source_path.suffix == ".sdep" and source_path.is_file():
        extract_dir = source_path.parent / f".{source_path.stem}.unpack"
        if extract_dir.exists():
            shutil.rmtree(extract_dir)
        extract_dir.mkdir(parents=True)
        with tarfile.open(source_path, "r:gz") as tar:
            tar.extractall(extract_dir, filter="data")
        inner = next(extract_dir.iterdir())
        receipt = _install_bundle_dir(inner, force=force, target=target)
        shutil.rmtree(extract_dir)
        return receipt

    if source_path.is_dir() and (source_path / "manifest.json").is_file():
        return _install_bundle_dir(source_path, force=force, target=target)

    # Built-in example: copy straight from the vendored/template tree.
    template_dept = _template_department(source, target=target)
    if template_dept is not None:
        return _install_plain_department(template_dept, force=force, target=target)

    raise ValueError(
        f"cannot add '{source}': not a .sdep file, bundle directory, "
        "or built-in department id")


def _home_agents_dir(target: str | Path | None = None) -> Path:
    from .paths import selected_project_root, validate_home_destination

    return validate_home_destination(selected_project_root(target)) / ".agents"


def _template_department(department_id: str,
                         target: str | Path | None = None) -> Path | None:
    candidates = [
        _home_agents_dir(target) / "company" / "departments" / department_id,
        Path(__file__).resolve().parents[1] / "init_templates" / "agents"
        / "company" / "departments" / department_id,
    ]
    for candidate in candidates:
        if candidate.is_dir():
            return candidate
    return None


def _verify_manifest(bundle: Path) -> dict:
    manifest = json.loads((bundle / "manifest.json").read_text())
    if manifest.get("kind") != "spielos-department":
        raise ValueError("not a spielos-department bundle")
    broken = [entry["path"] for entry in manifest.get("files", [])
              if not (bundle / entry["path"]).is_file()
              or _sha256(bundle / entry["path"]) != entry["sha256"]]
    if broken:
        raise ValueError(f"bundle integrity check failed: {broken[:5]}")
    return manifest


def _install_bundle_dir(bundle: Path, *, force: bool,
                        target: str | Path | None = None) -> dict:
    manifest = _verify_manifest(bundle)
    department_id = manifest["id"]
    home = _home_agents_dir(target)

    dept_src = bundle / "department"
    dept_dst = home / "company" / "departments" / department_id
    if dept_dst.exists() and not force:
        raise FileExistsError(
            f"department '{department_id}' already exists; pass --force to replace")
    if dept_dst.exists():
        shutil.rmtree(dept_dst)
    shutil.copytree(dept_src, dept_dst)

    # Every exported dependency travels with the Department. This keeps a
    # .sdep self-contained without creating a third, hidden shared-skill scope.
    skills_src = bundle / "skills"
    installed_skills: list[str] = []
    if skills_src.is_dir():
        skills_dst = dept_dst / "skills"
        for skill_dir in sorted(skills_src.iterdir()):
            if skill_dir.is_dir():
                shutil.copytree(skill_dir, skills_dst / skill_dir.name,
                                dirs_exist_ok=True)
                installed_skills.append(skill_dir.name)

    installed_agents: list[str] = []
    agents_src = bundle / "agents"
    if agents_src.is_dir():
        agents_dst = home / "company" / "agents" / "installed"
        agents_dst.mkdir(parents=True, exist_ok=True)
        for agent_file in sorted(agents_src.glob("*.json")):
            shutil.copy2(agent_file, agents_dst / agent_file.name)
            installed_agents.append(json.loads(agent_file.read_text())["id"])

    return {"added": department_id, "agents_installed": installed_agents,
            "skills_installed": installed_skills,
            "version": _department_version(dept_dst),
            "note": "run `python3 -m company departments` to confirm discovery"}


def _install_plain_department(template: Path, *, force: bool,
                              target: str | Path | None = None) -> dict:
    department_id = template.name
    dept_dst = _home_agents_dir(target) / "company" / "departments" / department_id
    if dept_dst.exists() and not force:
        raise FileExistsError(
            f"department '{department_id}' already exists; pass --force to replace")
    if dept_dst.exists():
        shutil.rmtree(dept_dst)
    shutil.copytree(template, dept_dst,
                    ignore=shutil.ignore_patterns("__pycache__"))
    return {"added": department_id, "source": str(template),
            "note": "run `python3 -m company departments` to confirm discovery"}


def _department_version(dept_dir: Path) -> str:
    import re

    init_py = dept_dir / "department.py"
    if init_py.is_file():
        match = re.search(r'version\s*=\s*"([^"]+)"', init_py.read_text())
        if match:
            return match.group(1)
    return "unknown"


def refresh_home(*, force: bool = True,
                 target: str | Path | None = None) -> dict:
    """Re-vendor the SPINE (runtime code + company skills + host adapters)
    into the current home from the newest templates. User layer is preserved:
    strategy/, assets/, departments/, agents/, config.user.json, .spielos/."""
    from .bootstrap import template_root

    templates = template_root()
    home = _home_agents_dir(target)
    if not (home / "company").is_dir():
        raise ValueError("no harness home here; run `spielos init` first")

    refreshed: list[str] = []

    def _sync(src: Path, dst: Path, preserve: set[str] = frozenset()) -> None:
        nonlocal refreshed
        for path in sorted(src.rglob("*")):
            if path.is_dir() or "__pycache__" in path.parts or path.suffix == ".pyc":
                continue
            rel = path.relative_to(src)
            if preserve & set(rel.parts):
                continue
            dest = dst / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, dest)
            refreshed.append(str(dest))

    spine = templates / "agents" / "company"
    _sync(spine / "runtime", home / "company" / "runtime")
    _sync(spine / "evals", home / "company" / "evals")
    _sync(spine / "connections", home / "company" / "connections")
    _sync(spine / "agents", home / "company" / "agents",
          preserve={"installed"})
    _sync(spine / "skills", home / "company" / "skills")
    # Note: the contract test suite deliberately does NOT ship to homes.
    # It validates this product repository's packaging layout and belongs
    # to the source checkout and CI. Homes verify through company status,
    # catalog, and their departments' own evals.
    for top_level in spine.glob("*.py"):
        shutil.copy2(top_level, home / "company" / top_level.name)
        refreshed.append(str(home / "company" / top_level.name))

    for name in ("opencode", "codex"):
        src = templates / "hosts" / name
        if src.is_dir():
            _sync(src, home.parent / ("." + name),
                  preserve=set())

    removed_host_agents: list[str] = []
    for host, filenames in RETIRED_HOST_AGENTS.items():
        agents = home.parent / ("." + host) / "agents"
        for filename in filenames:
            path = agents / filename
            if path.is_file():
                path.unlink()
                removed_host_agents.append(str(path))

    removed_harness_files: list[str] = []
    for relative in RETIRED_HARNESS_FILES:
        path = home / "company" / relative
        if path.is_file():
            path.unlink()
            removed_harness_files.append(str(path))

    return {"refreshed_files": len(refreshed),
            "removed_retired_host_agents": removed_host_agents,
            "removed_retired_harness_files": removed_harness_files,
            "preserved": ["strategy/", "assets/", "departments/",
                          "agents/installed/", "config.user.json",
                          ".spielos/"]}
