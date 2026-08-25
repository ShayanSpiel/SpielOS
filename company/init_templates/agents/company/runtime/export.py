"""Department portability: export one department as a portable ``.sdep``
bundle, and install a bundle (or a built-in example) into the current home.

A bundle is a directory (or a ``.tar.gz`` of one) containing::

    manifest.json          id, version, files[] with sha256, requires
    department/**          the whole departments/<id>/ folder
    skills/company/**      every skill the workflows bind (flat skills/<id>/)
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


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _required_skills(dept_dir: Path) -> list[str]:
    """Skill ids referenced by the department's workflow declarations."""
    import re

    source = "\n".join(
        p.read_text() for p in dept_dir.rglob("*.py") if "__pycache__" not in p.parts)
    referenced: set[str] = set()
    for group in re.findall(r'skill_ids=\(([^)]*)\)', source):
        for token in group.split(","):
            token = token.strip().strip("\"' ")
            if token:
                referenced.add(token)
    return sorted(referenced)


def _known_skill_ids() -> set[str]:  # kept for external tooling/debugging
    from .paths import skills_root

    root = skills_root()
    known: set[str] = set()
    if root.is_dir():
        for namespace in root.iterdir():
            if namespace.is_dir():
                known |= {p.name for p in namespace.iterdir() if p.is_dir()}
    return known


def export_department(department_id: str, out_dir: Path | None = None) -> dict:
    """Bundle departments/<id>/ + its company skills into a portable package."""
    dept_dir = DEPARTMENTS_ROOT / department_id
    if not dept_dir.is_dir():
        raise ValueError(f"no such department: {department_id}")

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

    for path in sorted(dept_dir.rglob("*")):
        if path.is_file() and "__pycache__" not in path.parts:
            _emit(path, f"department/{path.relative_to(dept_dir)}")

    required_skills = _required_skills(dept_dir)
    for skill_id in required_skills:
        skill_dir = _find_skill_dir(skill_id)
        if skill_dir is None:
            raise ValueError(
                f"department '{department_id}' binds skill '{skill_id}' "
                "which is not installed; install it first")
        for path in sorted(skill_dir.rglob("*")):
            if path.is_file() and "__pycache__" not in path.parts:
                _emit(path, f"skills/{skill_id}/{path.relative_to(skill_dir)}")

    # Connections this department declares (names only; credentials stay local).
    connections = sorted(set(__import__("re").findall(
        r'connection_ids?=\(([^)]*)\)',
        "\n".join(p.read_text() for p in dept_dir.rglob("*.py")))))
    connection_ids = sorted({c.strip("\"' ") for group in connections
                             for c in group.split(",") if c.strip("\"' ")})

    manifest = {
        "kind": "spielos-department",
        "manifest_version": 1,
        "id": department_id,
        "requires": {"skills": required_skills, "connections": connection_ids},
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


def add_department(source: str, *, force: bool = False) -> dict:
    """Install a department into the current home from a .sdep file, a
    bundle directory, or a built-in example id shipped with the package."""
    target = Path(source)

    if target.suffix == ".sdep" and target.is_file():
        extract_dir = target.parent / f".{target.stem}.unpack"
        if extract_dir.exists():
            shutil.rmtree(extract_dir)
        extract_dir.mkdir(parents=True)
        with tarfile.open(target, "r:gz") as tar:
            tar.extractall(extract_dir, filter="data")
        inner = next(extract_dir.iterdir())
        receipt = _install_bundle_dir(inner, force=force)
        shutil.rmtree(extract_dir)
        return receipt

    if target.is_dir() and (target / "manifest.json").is_file():
        return _install_bundle_dir(target, force=force)

    # Built-in example: copy straight from the vendored/template tree.
    template_dept = _template_department(source)
    if template_dept is not None:
        return _install_plain_department(template_dept, force=force)

    raise ValueError(
        f"cannot add '{source}': not a .sdep file, bundle directory, "
        "or built-in department id")


def _home_agents_dir() -> Path:
    from .paths import find_project_root

    return find_project_root() / ".agents"


def _template_department(department_id: str) -> Path | None:
    candidates = [
        _home_agents_dir() / "company" / "departments" / department_id,
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


def _install_bundle_dir(bundle: Path, *, force: bool) -> dict:
    manifest = _verify_manifest(bundle)
    department_id = manifest["id"]
    home = _home_agents_dir()

    # Skills first so validation sees them. Bundled skills install into the
    # shared department-skills shelf (methods used across departments).
    skills_src = bundle / "skills"
    installed_skills: list[str] = []
    if skills_src.is_dir():
        skills_dst = home / "company" / "departments" / "_shared" / "skills"
        for skill_dir in sorted(skills_src.iterdir()):
            if skill_dir.is_dir():
                shutil.copytree(skills_src / skill_dir.name,
                                skills_dst / skill_dir.name, dirs_exist_ok=True)
                installed_skills.append(skill_dir.name)

    dept_src = bundle / "department"
    dept_dst = home / "company" / "departments" / department_id
    if dept_dst.exists() and not force:
        raise FileExistsError(
            f"department '{department_id}' already exists; pass --force to replace")
    if dept_dst.exists():
        shutil.rmtree(dept_dst)
    shutil.copytree(dept_src, dept_dst)

    return {"added": department_id, "skills_installed": installed_skills,
            "version": _department_version(dept_dst),
            "note": "run `python3 -m company departments` to confirm discovery"}


def _install_plain_department(template: Path, *, force: bool) -> dict:
    department_id = template.name
    dept_dst = _home_agents_dir() / "company" / "departments" / department_id
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


def refresh_home(*, force: bool = True) -> dict:
    """Re-vendor the SPINE (runtime code + company skills + host adapters)
    into the current home from the newest templates. User layer is preserved:
    strategy/, assets/, departments/, agents/, config.user.json, .spielos/."""
    from .bootstrap import template_root

    templates = template_root()
    home = _home_agents_dir()
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

    return {"refreshed_files": len(refreshed),
            "preserved": ["strategy/", "assets/", "departments/",
                          "agents/installed/", "config.user.json",
                          ".spielos/"]}
