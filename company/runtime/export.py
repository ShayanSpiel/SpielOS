"""Refresh an installed SpielOS home while preserving its user layer."""

from __future__ import annotations

import shutil
from pathlib import Path


RETIRED_HOST_AGENTS = {
    "codex": (
        "department-runner.toml", "lead-researcher.toml",
        "outreach-writer.toml", "social-researcher.toml",
    ),
    "opencode": (
        "department-runner.md", "lead-researcher.md",
        "outreach-writer.md", "social-researcher.md",
    ),
}

RETIRED_HARNESS_FILES = (
    "runtime/campaign_contract.py",
    "connections/buffer.py",
)


def _home_agents_dir(target: str | Path | None = None) -> Path:
    from .paths import selected_project_root, validate_home_destination

    root = validate_home_destination(selected_project_root(target))
    return root / ".agents"


def refresh_home(*, force: bool = True,
                 target: str | Path | None = None) -> dict:
    """Re-vendor the runtime spine and host adapters from current templates."""
    from .bootstrap import template_root

    templates = template_root()
    home = _home_agents_dir(target)
    if not (home / "company").is_dir():
        raise ValueError("no harness home here; run spielos init first")
    refreshed: list[str] = []

    def sync(src: Path, dst: Path, preserve: set[str] = frozenset()) -> None:
        for path in sorted(src.rglob("*")):
            if path.is_dir() or "__pycache__" in path.parts or path.suffix == ".pyc":
                continue
            rel = path.relative_to(src)
            if preserve & set(rel.parts):
                continue
            destination = dst / rel
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, destination)
            refreshed.append(str(destination))

    spine = templates / "agents" / "company"
    sync(spine / "runtime", home / "company" / "runtime")
    sync(spine / "evals", home / "company" / "evals")
    sync(spine / "connections", home / "company" / "connections")
    sync(spine / "agents", home / "company" / "agents", preserve={"installed"})
    sync(spine / "skills", home / "company" / "skills")
    for top_level in spine.glob("*.py"):
        shutil.copy2(top_level, home / "company" / top_level.name)
        refreshed.append(str(home / "company" / top_level.name))
    for name in ("opencode", "codex"):
        source = templates / "hosts" / name
        if source.is_dir():
            sync(source, home.parent / ("." + name))
    removed = []
    for host, filenames in RETIRED_HOST_AGENTS.items():
        agents = home.parent / ("." + host) / "agents"
        for filename in filenames:
            path = agents / filename
            if path.is_file():
                path.unlink()
                removed.append(str(path))
    removed_harness = []
    for relative in RETIRED_HARNESS_FILES:
        path = home / "company" / relative
        if path.is_file():
            path.unlink()
            removed_harness.append(str(path))
    return {"refreshed_files": len(refreshed),
            "removed_retired_host_agents": removed,
            "removed_retired_harness_files": removed_harness,
            "preserved": ["strategy/", "assets/", "workgroups/",
                          "agents/installed/", "config.user.json", ".spielos/"]}
