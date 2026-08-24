"""Single derivation of the SpielOS project root.

The harness historically assumed it always lived at `<repo>/.agents/company/`.
That holds for repository-vendored installs but breaks for a pip-installed
console script. Resolution order:

1. ``SPIELOS_HOME`` environment variable (explicit override);
2. nearest ancestor of the current working directory that looks like a
   SpielOS home (contains ``.spielos/state`` or ``.agents/company``);
3. the vendored repository layout this package file lives in
   (``<repo>/.agents/company/runtime/paths.py`` -> ``<repo>``), so an
   uninstalled checkout behaves exactly as before.
"""

from __future__ import annotations

import os
from pathlib import Path


def package_vendored_root() -> Path | None:
    """Project root implied by this file's location, when vendored."""
    candidate = Path(__file__).resolve().parents[3]
    if (candidate / ".agents" / "company").is_dir():
        return candidate
    return None


def find_project_root() -> Path:
    """Resolve the active SpielOS project root (see module docstring)."""
    env_home = os.environ.get("SPIELOS_HOME")
    if env_home:
        return Path(env_home).expanduser().resolve()

    cwd = Path.cwd().resolve()
    for candidate in (cwd, *cwd.parents):
        if ((candidate / ".spielos" / "state").is_dir()
                or (candidate / ".agents" / "company").is_dir()):
            return candidate

    vendored = package_vendored_root()
    if vendored is not None:
        return vendored

    # Last resort: treat the cwd as the project root (fresh `spielos init`
    # runs before any state exists).
    return cwd


def skills_root(project_root: Path | None = None) -> Path:
    """The skills namespace root: ``<project_root>/.agents/skills``."""
    root = project_root or find_project_root()
    candidate = root / ".agents" / "skills"
    if candidate.is_dir():
        return candidate
    # Vendored fallback for tooling that runs before init scaffolds skills.
    return Path(__file__).resolve().parents[2] / "skills"
