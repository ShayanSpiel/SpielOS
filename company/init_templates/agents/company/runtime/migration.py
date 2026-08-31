"""Read-only inspection and normalization plans for foreign harness content."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any


NORMALIZATION = {
    "department": "department",
    "workgroup": "department",
    "agent": "agent",
    "employee": "agent",
    "worker": "agent",
    "playbook": "workflow",
    "workflow": "workflow",
    "prompt": "skill",
    "method": "skill",
    "workbook": "skill",
    "skill": "skill",
    "tool": "connection",
    "workkit": "connection",
    "connection": "connection",
    "output": "artifact",
    "evidence": "artifact",
}


POLICIES = {
    "foreign_runtime": "replace_with_current_spine; never import as capability code",
    "operational_goals": "archive_by_default; promote only owner-selected goals with explicit lineage",
    "history": "preserve immutable runs, evidence, approvals, decisions, and artifact references",
    "external_actions": "disable credentials and require explicit approval during migration tests",
    "unknown_files": "quarantine; never guess or silently discard",
    "installation": "convert, validate, test, and install one Department atomically at a time",
    "application": "migrate site code separately from the harness; preserve source history and verify build plus critical user flows",
}

APPLICATION_EXCLUDES = frozenset({
    ".agents", ".codex", ".git", ".github", ".opencode", ".spielos",
    ".astro", ".next", ".nuxt", ".output", ".pytest_cache", "__pycache__",
    "build", "coverage", "dist", "node_modules", "outbound",
})
APPLICATION_FILE_EXCLUDES = frozenset({
    "agents.md", "company.db", "company.sqlite", "opencode.json",
})


def _version(root: Path) -> str | None:
    candidates = [root / ".agents/company/runtime/config.py",
                  root / "company/runtime/config.py"]
    for path in candidates:
        if path.is_file():
            match = re.search(r'^VERSION\s*=\s*["\']([^"\']+)',
                              path.read_text(encoding="utf-8", errors="replace"), re.M)
            if match:
                return match.group(1)
    return None


def _known_files(root: Path) -> list[Path]:
    if root.is_file():
        return [root]
    candidates = []
    for relative in (".agents/company/departments", ".agents/company/workgroups",
                     ".agents/company/agents/installed", ".agents/company/skills",
                     ".agents/company/strategy", ".agents/company/assets",
                     "company/departments", "company/workgroups"):
        folder = root / relative
        if folder.is_dir():
            candidates.extend(path for path in folder.rglob("*") if path.is_file()
                              and "__pycache__" not in path.parts and path.suffix != ".pyc")
    for relative in ("AGENTS.md", ".spielos/state/company.sqlite"):
        path = root / relative
        if path.is_file():
            candidates.append(path)
    return sorted(set(candidates))


def _fingerprint(root: Path, files: list[Path]) -> str:
    digest = hashlib.sha256()
    for path in files:
        relative = path.name if root.is_file() else path.relative_to(root).as_posix()
        digest.update(relative.encode())
        digest.update(str(path.stat().st_size).encode())
    return digest.hexdigest()[:20]


def _application_inventory(root: Path) -> dict[str, Any]:
    """Summarize non-harness project files without traversing generated trees."""
    empty = {"detected": False, "files": 0, "bytes": 0, "roots": []}
    if root.is_file():
        return empty
    markers = ("package.json", "pyproject.toml", "index.html", "src", "app", "public")
    detected = any((root / marker).exists() for marker in markers)
    if not detected:
        return empty
    totals: dict[str, dict[str, int | str]] = {}
    file_count = 0
    byte_count = 0

    def visit(folder: Path) -> None:
        nonlocal file_count, byte_count
        for path in folder.iterdir():
            if (path.name in APPLICATION_EXCLUDES
                    or path.name.lower() in APPLICATION_FILE_EXCLUDES):
                continue
            if path.is_dir():
                visit(path)
                continue
            if not path.is_file() or path.suffix == ".pyc":
                continue
            relative = path.relative_to(root)
            top = relative.parts[0]
            size = path.stat().st_size
            summary = totals.setdefault(
                top, {"path": top, "files": 0, "bytes": 0})
            summary["files"] = int(summary["files"]) + 1
            summary["bytes"] = int(summary["bytes"]) + size
            file_count += 1
            byte_count += size

    visit(root)
    return {
        "detected": True,
        "files": file_count,
        "bytes": byte_count,
        "roots": sorted(totals.values(), key=lambda item: str(item["path"])),
    }


def _classify(path: Path) -> dict[str, str]:
    name = path.name.lower()
    parts = tuple(part.lower() for part in path.parts)

    def under(*segments: str) -> bool:
        width = len(segments)
        return any(parts[index:index + width] == segments
                   for index in range(len(parts) - width + 1))

    text = ""
    if path.stat().st_size <= 256_000 and path.suffix.lower() in {".json", ".md", ".py", ".yaml", ".yml", ".toml"}:
        text = path.read_text(encoding="utf-8", errors="replace")[:20_000].lower()
    if name == ".gitkeep":
        target, action = "directory_metadata", "regenerate_if_needed"
    elif name == "company.sqlite" and under(".spielos", "state"):
        target, action = "operational_state", "archive_then_selectively_promote"
    elif name == "agents.md":
        target, action = "host_instruction", "merge_current_policy_then_review"
    elif under("company", "runtime"):
        target, action = "foreign_runtime", "replace_not_import"
    elif "templates" in parts:
        target, action = "template_asset", "preserve_and_validate_with_owner"
    elif name == "skill.md" or "skills" in parts or "prompt" in name or "method" in name:
        target, action = "skill", "convert_and_review"
    elif "strategy" in parts:
        target, action = "strategy_context", "merge_current_kernel_then_review"
    elif "assets" in parts:
        target, action = "asset_or_artifact", "preserve_classify_and_hash_verify"
    elif "workflows" in parts:
        target, action = "workflow_component", "bundle_with_parent_workflow"
    elif "workflow" in name or "playbook" in name or "worksteps" in text:
        target, action = "workflow", "convert_and_validate"
    elif name in {"department.py", "workgroup.json"}:
        target, action = "department", "convert_and_validate"
    elif under("agents", "installed") or "workers" in parts or name == "worker.json":
        target, action = "agent", "normalize_identity"
    elif "worker" in name or "employee" in name:
        target, action = "agent", "normalize_identity"
    elif "workgroup" in name or "department" in name:
        target, action = "department", "convert_and_validate"
    elif any(token in name for token in ("connection", "integration", "permission", "tool")):
        target, action = "connection", "review_authority_and_credentials"
    elif any(token in name for token in ("artifact", "output", "evidence")):
        target, action = "artifact", "preserve_and_hash_verify"
    else:
        target, action = "unknown", "quarantine_for_owner_review"
    return {"path": str(path), "target_type": target, "action": action}


def inspect_source(source: str | Path) -> dict[str, Any]:
    root = Path(source).expanduser().resolve()
    if not root.exists():
        raise ValueError(f"migration source does not exist: {root}")
    files = _known_files(root)
    base = root.parent if root.is_file() else root
    department_root = base / ".agents/company/departments"
    if not department_root.is_dir():
        department_root = base / "company/departments"
    workgroup_root = base / ".agents/company/workgroups"
    if not workgroup_root.is_dir():
        workgroup_root = base / "company/workgroups"
    departments = sorted(path.name for path in department_root.iterdir()
                         if path.is_dir() and not path.name.startswith(("_", "."))) if department_root.is_dir() else []
    retired_workgroups = sorted(path.name for path in workgroup_root.iterdir()
                     if path.is_dir() and (path / "workgroup.json").is_file()) if workgroup_root.is_dir() else []
    state = base / ".spielos/state/company.sqlite"
    application = _application_inventory(base)
    return {
        "source": str(root),
        "source_kind": "file" if root.is_file() else "harness_or_folder",
        "detected_version": _version(base),
        "fingerprint": _fingerprint(root, files),
        "inventory": {
            "recognized_files": len(files),
            "departments": departments,
            "retired_workgroups": retired_workgroups,
            "has_operational_state": state.is_file(),
            "operational_state_bytes": state.stat().st_size if state.is_file() else 0,
            "application": application,
            "file_assessments": [_classify(path) for path in files],
        },
        "normalization": NORMALIZATION,
        "policies": POLICIES,
    }


def migration_plan(source: str | Path) -> dict[str, Any]:
    inspection = inspect_source(source)
    inventory = inspection["inventory"]
    units = [
        {"source_id": identifier, "source_type": "department",
         "target_type": "department", "target_id": identifier,
         "status": "needs_validation_and_acceptance"}
        for identifier in inventory["departments"]]
    units += [
        {"source_id": identifier, "source_type": "workgroup",
         "target_type": "department", "target_id": identifier,
         "status": "needs_conversion_and_acceptance"}
        for identifier in inventory["retired_workgroups"]]
    quarantined = [item for item in inventory["file_assessments"]
                   if item["target_type"] == "unknown"]
    application = inventory["application"]
    site_unit = ({
        "source_id": Path(inspection["source"]).name,
        "source_type": "website_application",
        "target_type": "website_application",
        "target_id": ".",
        "status": "needs_clean_snapshot_build_and_user_flow_acceptance",
        "files": application["files"],
        "bytes": application["bytes"],
    } if application["detected"] else None)
    return {
        "schema_version": 1,
        "inspection": inspection,
        "execution_policy": "one_department_at_a_time",
        "units": units,
        "site_unit": site_unit,
        "quarantined_files": quarantined,
        "state_action": ("archive_then_selectively_promote"
                         if inventory["has_operational_state"] else "none"),
        "required_gates": [
            "owner reviews source classification and quarantined unknowns",
            "runtime spine is installed fresh from the current release",
            "website source is migrated separately without copying the foreign harness",
            "website build, tests, and critical user flows pass in the destination",
            "each Department validates before installation",
            "external credentials remain disabled during acceptance",
            "artifacts and historical evidence are hash-verified",
            "only owner-selected Goals enter the new rooted Goal graph",
        ],
    }
