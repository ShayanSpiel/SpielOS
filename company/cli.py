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


def main() -> int:
    """Run the local home's runtime, or the installed package outside a home."""
    try:
        home = _vendored_home()
    except FileNotFoundError:
        print(
            "SpielOS cannot continue because this shell's current folder was deleted.\n"
            "Run `cd ~/Desktop/Projects`, then rerun SpielOS from that existing folder.",
            file=sys.stderr,
        )
        return 2
    if home is not None:
        environment = os.environ.copy()
        agents_root = str(home / ".agents")
        existing_path = environment.get("PYTHONPATH")
        environment["PYTHONPATH"] = (
            agents_root + (os.pathsep + existing_path if existing_path else "")
        )
        os.execve(
            sys.executable,
            [sys.executable, "-B", "-m", "company", *sys.argv[1:]],
            environment,
        )
    from .__main__ import main as package_main

    return package_main()


if __name__ == "__main__":
    sys.exit(main())
