"""Console entry point that defers to the selected SpielOS home's runtime."""

from __future__ import annotations

import os
import sys
from pathlib import Path


def _vendored_home(start: Path | None = None) -> Path | None:
    """Return the nearest initialized home containing a vendored runtime."""
    current = (start or Path.cwd()).resolve()
    for candidate in (current, *current.parents):
        if (candidate / ".agents" / "company" / "__main__.py").is_file():
            return candidate
    return None


def _uses_installed_package(argv: list[str]) -> bool:
    """Return whether this invocation must bypass a vendored home.

    Home lifecycle commands need the just-installed distribution as their
    authority.  Dispatching ``update`` into the existing home would run the
    old runtime and can only re-copy old templates.
    """
    index = 0
    while index < len(argv):
        token = argv[index]
        if token in {"--version", "-V"}:
            return True
        if token == "--db":
            index += 2
            continue
        if token.startswith("--db="):
            index += 1
            continue
        if token.startswith("-"):
            return False
        return token in {"init", "update", "refresh"}
    return False


def main(argv: list[str] | None = None) -> int:
    """Run the local home's runtime, or the installed package outside a home."""
    argv = list(sys.argv[1:] if argv is None else argv)
    try:
        home = _vendored_home()
    except FileNotFoundError:
        print(
            "SpielOS cannot continue because this shell's current folder was deleted.\n"
            "Run `cd ~/Desktop/Projects`, then rerun SpielOS from that existing folder.",
            file=sys.stderr,
        )
        return 2
    if home is not None and not _uses_installed_package(argv):
        environment = os.environ.copy()
        agents_root = str(home / ".agents")
        existing_path = environment.get("PYTHONPATH")
        environment["PYTHONPATH"] = (
            agents_root + (os.pathsep + existing_path if existing_path else "")
        )
        os.execve(
            sys.executable,
            [sys.executable, "-B", "-m", "company", *argv],
            environment,
        )
    from .__main__ import main as package_main

    return package_main(argv)


if __name__ == "__main__":
    sys.exit(main())
