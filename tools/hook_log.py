#!/usr/bin/env python3
"""tools/hook_log.py — Append/read the Codex UserPromptSubmit hook log.

The Codex plugin hook (plugins/spielos/scripts/post-hook.sh) calls this
helper to record every invocation. Output is append-only JSONL at
`content/runs/_hooks/hook.jsonl`. The dashboard reads this file via
`spiel hook-log` or directly.

Why a dedicated log? The hook is deterministic but invisible — without
a log, you can't tell whether the hook fired, what decision it made,
or why `spiel post` failed. This log is the audit trail.

Usage from the bash hook:
    python3 tools/hook_log.py \\
        --vault <vault> \\
        --event user_prompt_submit \\
        --prompt "<raw prompt>" \\
        --decision topic|file|session|skip \\
        --result ok|guard_failed|cli_error|no_match|missing_spiel \\
        --run-id <id|null> \\
        --duration-ms <int> \\
        --detail "<one-line>"

Usage from the dashboard / CLI:
    python3 tools/hook_log.py --vault <vault>            # print last 20
    python3 tools/hook_log.py --vault <vault> --tail N   # print last N
    python3 tools/hook_log.py --vault <vault> --json     # print as JSON
    python3 tools/hook_log.py --vault <vault> --clear    # truncate (rare)
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _vault import resolve_vault  # noqa: E402


HOOK_LOG_REL = Path("content") / "runs" / "_hooks" / "hook.jsonl"
MAX_LOG_BYTES = 5 * 1024 * 1024  # 5 MB
MAX_LOG_LINES = 5000


def now_iso() -> str:
    return datetime.now().isoformat(timespec="milliseconds")


def hook_log_path(vault: Path) -> Path:
    p = vault / HOOK_LOG_REL
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def append_event(vault: Path, **fields) -> None:
    """Append a single JSON line. No-op if vault is None.

    POSIX `O_APPEND` guarantees atomic append for writes up to PIPE_BUF
    (4096 bytes on Linux/macOS). Our lines are well under that, so a
    simple open(..., "a") + write + flush is atomic across processes.

    The log is rotated at MAX_LOG_BYTES (default 5 MB) by keeping the
    last MAX_LOG_LINES (default 5000) lines. This prevents the dashboard's
    audit trail from growing without bound.
    """
    if vault is None:
        return
    row = {"at": now_iso(), **fields}
    path = hook_log_path(vault)
    line = json.dumps(row, ensure_ascii=False)
    with path.open("a", encoding="utf-8") as f:
        f.write(line + "\n")
        f.flush()
        os.fsync(f.fileno())
    _maybe_rotate(path)


def _maybe_rotate(path: Path) -> None:
    """Rotate the hook log if it exceeds the size cap. Keep the last
    MAX_LOG_LINES so the dashboard always has the most recent activity.
    """
    try:
        if path.stat().st_size < MAX_LOG_BYTES:
            return
    except OSError:
        return
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return
    lines = text.splitlines()
    if len(lines) <= MAX_LOG_LINES:
        return
    keep = lines[-MAX_LOG_LINES:]
    path.write_text("\n".join(keep) + "\n", encoding="utf-8")


def read_events(vault: Path, limit: int = 50) -> list[dict]:
    path = hook_log_path(vault)
    if not path.is_file():
        return []
    out: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    if limit and len(out) > limit:
        out = out[-limit:]
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="SpielOS hook activity log")
    ap.add_argument("--vault", help="Vault root")
    ap.add_argument("--event", help="Append: event name (e.g. user_prompt_submit)")
    ap.add_argument("--prompt", help="Append: raw user prompt text")
    ap.add_argument("--decision", help="Append: topic|file|session|skip")
    ap.add_argument("--result", help="Append: ok|guard_failed|cli_error|no_match|missing_spiel")
    ap.add_argument("--run-id", help="Append: resulting run_id (or empty)")
    ap.add_argument("--duration-ms", type=int, default=0, help="Append: hook duration")
    ap.add_argument("--detail", help="Append: one-line reason / error")
    ap.add_argument("--tail", type=int, default=20, help="Read: last N events")
    ap.add_argument("--json", action="store_true", help="Read: emit JSON array")
    ap.add_argument("--clear", action="store_true", help="Truncate the log")
    args = ap.parse_args()

    vault = resolve_vault(args.vault)
    if vault is None:
        sys.stderr.write("ERROR: could not locate SpielOS vault\n")
        return 2

    if args.clear:
        path = hook_log_path(vault)
        if path.is_file():
            path.unlink()
        print(f"cleared {path}")
        return 0

    if args.event:
        fields = {
            "event": args.event,
            "prompt": args.prompt or "",
            "decision": args.decision or "skip",
            "result": args.result or "no_match",
            "run_id": args.run_id or None,
            "duration_ms": args.duration_ms,
            "detail": args.detail or "",
        }
        append_event(vault, **fields)
        return 0

    events = read_events(vault, limit=args.tail)
    if args.json:
        print(json.dumps({"vault": str(vault), "count": len(events), "events": events}, indent=2, ensure_ascii=False))
        return 0

    if not events:
        print("no hook activity yet")
        return 0
    for ev in events:
        at = ev.get("at", "?")
        ev_name = ev.get("event", "?")
        decision = ev.get("decision", "skip")
        result = ev.get("result", "no_match")
        run_id = ev.get("run_id") or "-"
        dur = ev.get("duration_ms", 0)
        detail = ev.get("detail", "")
        prompt = ev.get("prompt", "")
        if len(prompt) > 60:
            prompt = prompt[:57] + "..."
        print(f"  {at}  {ev_name:20s}  decision={decision:8s} result={result:14s} run={run_id:18s} {dur:5d}ms  {detail}")
        if prompt:
            print(f"      prompt: {prompt}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
