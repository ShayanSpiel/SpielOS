#!/usr/bin/env python3
"""Deterministic /post runtime for SpielOS.

This tool owns the mechanical start of a run:

- resolve vault
- create a run_id
- normalize topic/file/session input
- write content/current.md
- initialize and advance content/.state.json
- write content/runs/<run_id>/events.jsonl

It deliberately does not write strategy or copy. The IDE/Codex layer can still
provide fuzzy session extraction, but this tool owns all durable files and state.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _vault import resolve_vault  # noqa: E402
from guard import check as guard_check  # noqa: E402


RUN_COUNTER_REL = Path("content") / ".run-counter"
CURRENT_REL = Path("content") / "current.md"
ICP_WORLD_REL = Path("content") / ".icp-world.json"


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def today_str() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def find_vault(cli_vault: str | None) -> Path:
    vault = resolve_vault(cli_vault)
    if not vault:
        raise RuntimeError("could not locate SpielOS vault")
    return vault


def atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", dir=path.parent, prefix=f".{path.name}-", suffix=".tmp", delete=False, encoding="utf-8"
    ) as f:
        tmp = Path(f.name)
        f.write(text)
        f.flush()
        os.fsync(f.fileno())
    tmp.replace(path)


def atomic_write_json(path: Path, data: dict) -> None:
    atomic_write(path, json.dumps(data, indent=2, ensure_ascii=False) + "\n")


def next_run_id(vault: Path) -> str:
    """Return a unique run_id for today, incrementing the counter and
    self-healing any collision (counter reset, leftover dir, etc.).

    The counter file is the primary source of truth. The filesystem is the
    uniqueness check. If the counter says N but `runs/<date>-<N>/` already
    exists with events from a different run, we bump N until we find a free
    slot. This guarantees that two runs on the same day never share a
    run_id, even if the counter is reset manually or by a crash.
    """
    path = vault / RUN_COUNTER_REL
    date = today_str()
    counter = {"date": date, "n": 0}
    if path.is_file():
        try:
            existing = json.loads(path.read_text(encoding="utf-8"))
            if existing.get("date") == date:
                counter["n"] = int(existing.get("n", 0))
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            counter = {"date": date, "n": 0}
    counter["n"] += 1
    runs_dir = vault / "content" / "runs"
    # Bump until we find a free run_id. The first iteration uses the counter
    # value; subsequent iterations only fire if the dir is already taken.
    while (runs_dir / f"{date}-{counter['n']:03d}").is_dir():
        counter["n"] += 1
    atomic_write_json(path, counter)
    return f"{date}-{counter['n']:03d}"


def run_dir(vault: Path, run_id: str) -> Path:
    return vault / "content" / "runs" / run_id


def log_event(vault: Path, run_id: str, event: str, **fields) -> None:
    path = run_dir(vault, run_id) / "events.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    row = {"at": now_iso(), "event": event, **fields}
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")
        f.flush()
        os.fsync(f.fileno())


def rel_to_vault(vault: Path, path: Path) -> str:
    return str(path.resolve().relative_to(vault.resolve()))


def read_file_input(vault: Path, refs: list[str]) -> tuple[str, list[str]]:
    chunks: list[str] = []
    sources: list[str] = []
    for raw in refs:
        ref = raw.removeprefix("@file:")
        p = Path(ref).expanduser()
        if not p.is_absolute():
            p = (Path.cwd() / p).resolve()
        if not p.is_file():
            raise RuntimeError(f"input file not found: {raw}")
        chunks.append(p.read_text(encoding="utf-8"))
        try:
            sources.append(rel_to_vault(vault, p))
        except ValueError:
            sources.append(str(p))
    return "\n\n".join(chunks).strip(), sources


def load_structured_json(path: str | None) -> dict | None:
    if not path:
        return None
    p = Path(path).expanduser()
    if not p.is_file():
        raise RuntimeError(f"structured JSON not found: {path}")
    data = json.loads(p.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise RuntimeError("structured JSON must be an object")
    return data


def capture_session(
    vault: Path,
    run_id: str,
    transcript: str,
    structured_json: str | None,
    title: str | None,
    tags: str | None,
) -> str:
    if not transcript.strip():
        raise RuntimeError("session transcript is empty")
    cmd = [
        sys.executable,
        str(vault / "tools" / "capture-session.py"),
        "--vault",
        str(vault),
        "--transcript-stdin",
        "--status",
        "complete",
        "--title",
        title or f"Session {run_id}",
    ]
    if tags:
        cmd.extend(["--tags", tags])
    if structured_json:
        cmd.extend(["--structured-json", structured_json])
    result = subprocess.run(cmd, input=transcript, text=True, capture_output=True)
    if result.returncode != 0:
        raise RuntimeError(f"capture-session.py failed: {result.stderr.strip()}")
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"capture-session.py returned invalid JSON: {e}") from e
    path = Path(payload["path"])
    return rel_to_vault(vault, path)


def yaml_scalar(value: str | None) -> str:
    if value is None:
        return "null"
    return json.dumps(value, ensure_ascii=False)


def write_current(vault: Path, *, mode: str, run_id: str, source: str | None, session: str | None, input_text: str | None) -> None:
    lines = [
        "---",
        f"mode: {mode}",
    ]
    if session:
        lines.append(f"session: {session}")
    if input_text is not None:
        lines.append(f"input: {yaml_scalar(input_text)}")
    lines.extend([
        f"run_id: {run_id}",
        f"created_at: {now_iso()}",
        f"source: {yaml_scalar(source)}",
        "---",
        "",
    ])
    atomic_write(vault / CURRENT_REL, "\n".join(lines))


def advance(vault: Path, args: list[str]) -> None:
    cmd = [sys.executable, str(vault / "tools" / "advance.py"), *args, "--vault", str(vault), "--quiet"]
    result = subprocess.run(cmd, text=True, capture_output=True)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip() or f"advance.py failed: {args}")


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description="Start a deterministic SpielOS post run")
    ap.add_argument("input", nargs="*", help="Topic text, or @file:<path> references")
    ap.add_argument("--vault", help="SpielOS vault root")
    ap.add_argument("--mode", choices=("auto", "topic", "session"), default="auto")
    ap.add_argument("--transcript-file", help="Session transcript markdown/text file")
    ap.add_argument("--transcript-string", help="Session transcript string")
    ap.add_argument("--structured-json", help="Structured session signal JSON from the agent")
    ap.add_argument("--title", help="Session title")
    ap.add_argument("--tags", help="Comma-separated session tags")
    ap.add_argument("--json", action="store_true", help="Print machine-readable result")
    ap.add_argument("--ignore-guard", action="store_true", help="Start even if guard detects untracked content")
    return ap


def main() -> int:
    args = build_parser().parse_args()
    try:
        vault = find_vault(args.vault)
        # Auto-reset: every /post starts a fresh run. tools/advance.py --reset
        # only deletes content/.state.json and content/current.md; user content
        # (content/drafts/, content/ready/, content/posted/, content/rejected/,
        # content/sessions/) is preserved. This is unconditional — there is no
        # resume from a prior run. The LLM adapter cannot opt out.
        state_file = vault / "content" / ".state.json"
        if state_file.exists():
            advance(vault, ["--reset"])
        # Also delete content/.icp-world.json so the simulator starts fresh.
        # The simulator is a per-run artifact; a stale one would let a previous
        # run's ICP world ground a new run's brief.
        icp_world_file = vault / ICP_WORLD_REL
        if icp_world_file.exists():
            try:
                icp_world_file.unlink()
            except OSError as e:
                # Non-fatal; the simulator's check will fail and the Editor
                # will set the error if .icp-world.json is malformed.
                sys.stderr.write(f"WARNING: could not delete {ICP_WORLD_REL}: {e}\n")
        guard = guard_check(vault)
        if not args.ignore_guard and not guard.get("ok", False):
            raise RuntimeError(
                "pipeline guard failed. Run `spiel guard` and repair or archive untracked content "
                "before starting a new post run. Use --ignore-guard only for explicit recovery."
            )
        run_id = next_run_id(vault)
        log_event(vault, run_id, "run_started", command="post")

        transcript = ""
        if args.transcript_file:
            transcript = Path(args.transcript_file).expanduser().read_text(encoding="utf-8")
        elif args.transcript_string:
            transcript = args.transcript_string

        mode = args.mode
        if mode == "auto":
            mode = "session" if transcript else "topic"

        if mode == "session":
            if not transcript.strip():
                raise RuntimeError(
                    "session mode needs --transcript-file or --transcript-string. "
                    "The Codex plugin should pass the clean transcript to spiel post."
                )
            load_structured_json(args.structured_json)
            session_rel = capture_session(vault, run_id, transcript, args.structured_json, args.title, args.tags)
            source_abs = str((vault / session_rel).resolve())
            write_current(vault, mode="session", run_id=run_id, source=source_abs, session=session_rel, input_text=None)
            log_event(vault, run_id, "artifact_written", path=str(CURRENT_REL), mode="session", session=session_rel)
            advance(vault, ["--init", "--run-id", run_id, "--mode", "session", "--session", session_rel])
        else:
            file_refs = [x for x in args.input if x.startswith("@file:")]
            literal = " ".join(x for x in args.input if not x.startswith("@file:")).strip()
            file_text = ""
            sources: list[str] = []
            if file_refs:
                file_text, sources = read_file_input(vault, file_refs)
            input_text = "\n\n".join(x for x in (literal, file_text) if x).strip()
            if not input_text:
                raise RuntimeError("topic mode needs text or @file:<path>")
            source = ", ".join(sources) if sources else None
            write_current(vault, mode="topic", run_id=run_id, source=source, session=None, input_text=input_text)
            log_event(vault, run_id, "artifact_written", path=str(CURRENT_REL), mode="topic", source=source)
            advance(vault, ["--init", "--run-id", run_id, "--mode", "topic"])

        advance(vault, ["--to", "capture", "--by", "post"])
        log_event(vault, run_id, "step_completed", step="capture")
        advance(vault, ["--to", "strategy", "--by", "post"])
        log_event(vault, run_id, "step_started", step="strategy")

        result = {
            "ok": True,
            "run_id": run_id,
            "mode": mode,
            "step": "strategy",
            "current": str(CURRENT_REL),
            "events": str(Path("content") / "runs" / run_id / "events.jsonl"),
        }
        if args.json:
            print(json.dumps(result, indent=2, ensure_ascii=False))
        else:
            print(f"  ✓ post run started: {run_id}")
            print("  step: strategy")
            print(f"  handoff: {CURRENT_REL}")
            print(f"  events: {result['events']}")
        return 0
    except Exception as e:
        try:
            vault = resolve_vault(args.vault)
            if vault:
                fallback_run_id = locals().get("run_id", "unknown")
                log_event(vault, fallback_run_id, "run_failed", error=str(e))
        except Exception:
            pass
        sys.stderr.write(f"ERROR: {e}\n")
        return 1


if __name__ == "__main__":
    sys.exit(main())
