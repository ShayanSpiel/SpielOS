"""Canonical artifact workspaces and final-outcome presentation."""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .paths import find_project_root


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _slug(value: str, label: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9._-]+", "-", str(value).strip()).strip("-.")
    if not cleaned or cleaned in {".", ".."}:
        raise ValueError(f"{label} must contain a safe identifier")
    return cleaned


def artifact_root(project_root: str | Path | None = None) -> Path:
    return Path(project_root or find_project_root()).resolve() / ".spielos" / "artifacts"


def workspace_path(*, goal_id: str, run_id: str, workflow_id: str | None = None,
                   project_root: str | Path | None = None) -> Path:
    path = artifact_root(project_root) / _slug(goal_id, "goal") / _slug(run_id, "run")
    if workflow_id:
        path /= _slug(workflow_id, "workflow")
    return path


def prepare_workspace(*, goal_id: str, run_id: str,
                      workflow_id: str | None = None,
                      project_root: str | Path | None = None) -> dict[str, Any]:
    workspace = workspace_path(goal_id=goal_id, run_id=run_id,
                               workflow_id=workflow_id, project_root=project_root)
    work, final = workspace / "work", workspace / "final"
    work.mkdir(parents=True, exist_ok=True)
    final.mkdir(parents=True, exist_ok=True)
    manifest = workspace / "manifest.json"
    if not manifest.exists():
        manifest.write_text(json.dumps({
            "schema_version": 1,
            "goal_id": goal_id,
            "run_id": run_id,
            "workflow_id": workflow_id,
            "status": "working",
            "created_at": _now(),
            "final_files": [],
        }, indent=2) + "\n", encoding="utf-8")
    return {"workspace": str(workspace), "work": str(work),
            "final": str(final), "manifest": str(manifest)}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def finalize_workspace(*, goal_id: str, run_id: str, files: list[str | Path],
                       workflow_id: str | None = None, label: str = "",
                       move: bool = True, cleanup_work: bool = True,
                       project_root: str | Path | None = None) -> dict[str, Any]:
    if not files:
        raise ValueError("at least one final file is required")
    paths = prepare_workspace(goal_id=goal_id, run_id=run_id,
                              workflow_id=workflow_id, project_root=project_root)
    workspace, work, final = (Path(paths[key]) for key in ("workspace", "work", "final"))
    emitted = []
    for raw in files:
        source = Path(raw).expanduser().resolve()
        if not source.is_file():
            raise ValueError(f"final artifact does not exist or is not a file: {source}")
        destination = final / source.name
        if destination.exists() and destination.resolve() != source:
            stem, suffix, index = destination.stem, destination.suffix, 2
            while destination.exists():
                destination = final / f"{stem}-{index}{suffix}"
                index += 1
        if source != destination.resolve():
            if move:
                shutil.move(str(source), str(destination))
            else:
                shutil.copy2(source, destination)
        emitted.append({"path": str(destination), "name": destination.name,
                        "bytes": destination.stat().st_size,
                        "sha256": _sha256(destination)})
    if cleanup_work and work.is_dir():
        shutil.rmtree(work)
    manifest_path = workspace / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest.update({"status": "final", "label": label.strip(),
                     "finalized_at": _now(), "final_files": emitted,
                     "work_cleaned": cleanup_work})
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return {"workspace": str(workspace), "final": str(final),
            "manifest": str(manifest_path), "files": emitted,
            "work_cleaned": cleanup_work}


def list_artifacts(*, goal_id: str | None = None,
                   project_root: str | Path | None = None) -> list[dict[str, Any]]:
    root = artifact_root(project_root)
    search = root / _slug(goal_id, "goal") if goal_id else root
    if not search.is_dir():
        return []
    values = []
    for manifest in sorted(search.rglob("manifest.json"), reverse=True):
        try:
            value = json.loads(manifest.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        value["manifest"] = str(manifest)
        value["workspace"] = str(manifest.parent)
        values.append(value)
    return values


def present_artifact(path: str | Path, *, open_folder: bool = False,
                     project_root: str | Path | None = None) -> dict[str, Any]:
    target = Path(path).expanduser().resolve()
    root = artifact_root(project_root).resolve()
    if not target.exists() or not target.is_relative_to(root):
        raise ValueError(f"presentation target must exist inside {root}")
    folder = target if target.is_dir() else target.parent
    opened, command, error = False, [], None
    if open_folder:
        if sys.platform == "darwin":
            command = ["open", "-a", "Finder", str(folder)]
        elif sys.platform.startswith("win"):
            command = ["explorer", str(folder)]
        else:
            command = ["xdg-open", str(folder)]
        try:
            completed = subprocess.run(command, check=False, capture_output=True, text=True)
            opened = completed.returncode == 0
            if not opened:
                error = (completed.stderr or completed.stdout or "open command failed").strip()
        except OSError as exc:
            error = str(exc)
    return {"path": str(target), "folder": str(folder), "opened": opened,
            "open_requested": open_folder, "open_command": command, "error": error}
