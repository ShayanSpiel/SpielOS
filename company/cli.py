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
    authority: dispatching ``init`` or ``update`` into the existing home
    would re-copy that home's own templates instead of the new release.
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
        return token in {"init", "update", "mcp"}
    return False


def main(argv: list[str] | None = None) -> int:
    """Run the local home's runtime, or the installed package outside a home."""
    argv = list(sys.argv[1:] if argv is None else argv)
    try:
        explicit_home = next((token.split('=',1)[1] for token in argv if token.startswith('--home=')),None)
        if '--home' in argv:
            index=argv.index('--home')
            explicit_home=argv[index+1] if index+1<len(argv) else None
        if explicit_home is not None:
            selected=Path(explicit_home).expanduser().resolve()
            home=selected if (selected/'.agents/company/__main__.py').is_file() else None
        else:home = _vendored_home()
    except FileNotFoundError:
        print(
            "SpielOS cannot continue because this shell's current folder was deleted.\n"
            "Change to an existing company home folder, then rerun SpielOS.",
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
        if os.name=='nt':
            import subprocess
            return subprocess.call([sys.executable,'-B','-m','company',*argv],env=environment)
        os.execve(
            sys.executable,
            [sys.executable, "-B", "-m", "company", *argv],
            environment,
        )
    from .__main__ import main as package_main

    return package_main(argv)


if __name__ == "__main__":
    sys.exit(main())
