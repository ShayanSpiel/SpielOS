#!/usr/bin/env python3
"""Read-only Codex adapter for SpielOS context v2."""

from __future__ import annotations

import json
import sys
from pathlib import Path


def _root(start: Path) -> Path:
    for candidate in (start, *start.parents):
        if (candidate / ".agents" / "company").is_dir() or (candidate / "company").is_dir():
            return candidate
    return start


def main() -> int:
    try:
        request = json.load(sys.stdin)
        root = _root(Path.cwd().resolve())
        vendored = root / ".agents"
        sys.path.insert(0, str(vendored if vendored.is_dir() else root))
        from company.commands import CleanCommandRuntime, goal_authority
        from company.runtime.context import ContextAssembler, codex_hook_output
        from company.runtime.store import Store

        database = root / ".spielos" / "state" / "company.sqlite"
        if not database.is_file():
            return 0
        event_name = str(request.get("hook_event_name") or request.get("hookEventName") or
                         "UserPromptSubmit")
        if goal_authority(database) == "clean-core":
            projection = CleanCommandRuntime(database, readonly=True).assemble_context(
                prompt=str(request.get("prompt") or ""),
                boot=event_name == "SessionStart", owner_id="director")
        else:
            projection = ContextAssembler(
                Store(database, readonly=True), project_root=root).assemble(
                    prompt=str(request.get("prompt") or ""),
                    boot=event_name == "SessionStart", owner_id="director")
        print(json.dumps(codex_hook_output(projection, event_name), ensure_ascii=False))
    except Exception:
        # Host startup must remain available if state is absent or outdated.
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
