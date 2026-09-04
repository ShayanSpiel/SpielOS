#!/usr/bin/env python3
"""Codex Stop hook: surface pending SpielOS attention when a turn ends.

The OpenCode plugin has session.idle; the Codex equivalent is this Stop
hook. Stays silent when nothing needs the owner, fails open on any error.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPORTABLE = {"owner_input_required"}


def _looks_like_home(candidate: Path) -> bool:
    return ((candidate / ".agents" / "company").is_dir()
            or (candidate / "company").is_dir())


def _root(request: dict) -> Path:
    candidates: list[Path] = []
    raw_cwd = str(request.get("cwd") or "")
    if raw_cwd:
        candidates.append(Path(raw_cwd).expanduser())
    candidates.append(Path(__file__).resolve().parents[2])
    candidates.append(Path.cwd())
    for candidate in candidates:
        try:
            probes = (candidate.resolve(), *candidate.resolve().parents)
        except OSError:
            continue
        for probe in probes:
            if _looks_like_home(probe):
                return probe
    return Path.cwd()


def main() -> int:
    try:
        try:
            request = json.load(sys.stdin)
        except json.JSONDecodeError:
            request = {}
        root = _root(request)
        vendored = root / ".agents"
        sys.path.insert(0, str(vendored if vendored.is_dir() else root))
        from company.commands import CleanCommandRuntime

        database = root / ".spielos" / "state" / "company.sqlite"
        if not database.is_file():
            return 0
        rows = CleanCommandRuntime(database, readonly=True).notifications(
            status="pending", limit=20)
        pending = [row for row in rows if row.get("kind") in REPORTABLE]
        if pending:
            summary = "; ".join(
                f"{row.get('payload', {}).get('message') or row.get('kind')}"
                for row in pending[:5])
            print(json.dumps({
                "systemMessage": (
                    f"SpielOS needs your input ({len(pending)} item(s)): {summary}. "
                    "Ask the Director or run: PYTHONDONTWRITEBYTECODE=1 "
                    "PYTHONPATH=.agents python3 -B -m company notifications list"),
            }, ensure_ascii=False))
    except Exception:
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
