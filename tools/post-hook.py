#!/usr/bin/env python3
"""post-hook.py — Deterministic hook script for the /post command.

Fires on UserPromptSubmit (Claude Code) and beforeSubmitPrompt (Cursor).
Reads JSON from stdin (the hook context), captures the session, writes:

    1. <vault>/content/sessions/current.md  — the session artifact
    2. <vault>/content/current.md          — the routing context

Output: JSON with additionalContext telling the LLM to dispatch to @director.

CLI:
    python3 tools/post-hook.py --vault <path>

Reads hook JSON from stdin.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _vault import resolve_vault  # noqa: E402

MAX_TRANSCRIPT_BYTES = 1_000_000  # 1 MB hard cap


def read_hook_context() -> dict:
    """Read JSON from stdin. Handle both Claude Code and Cursor formats."""
    try:
        data = json.load(sys.stdin)
        if not isinstance(data, dict):
            return {}
        return data
    except (json.JSONDecodeError, EOFError, ValueError):
        return {}


def parse_post_command(prompt: str) -> tuple[str, str]:
    """Parse /post command. Returns (args, mode).

    mode = "topic" if args present, else "session"
    Returns ("", "none") if not a /post command.
    """
    if not prompt:
        return "", "none"
    prompt = prompt.strip()
    match = re.match(r"^/post\b\s*(.*)", prompt, re.DOTALL)
    if not match:
        return "", "none"
    args = match.group(1).strip()
    return (args, "topic") if args else ("", "session")


def extract_text_content(message) -> str:
    """Extract text from a message field. Handles string, list of blocks."""
    if isinstance(message, str):
        return message
    content = message.get("content", "") if isinstance(message, dict) else ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if not isinstance(block, dict):
                continue
            btype = block.get("type", "")
            if btype == "text":
                parts.append(block.get("text", ""))
            elif btype == "tool_use":
                name = block.get("name", "?")
                parts.append(f"[Tool call: {name}]")
            elif btype == "tool_result":
                result = block.get("content", "")
                if isinstance(result, str):
                    parts.append(f"[Result: {result[:300]}]")
                else:
                    parts.append(f"[Result: {str(result)[:300]}]")
            elif btype == "thinking":
                thinking = block.get("thinking", "")
                if thinking:
                    parts.append(f"[Thinking: {thinking[:300]}...]")
        return "\n".join(parts)
    return str(content)


def parse_transcript(transcript_path: str) -> dict:
    """Parse a JSONL transcript file. Returns structured session data.

    Handles both Claude Code and Cursor JSONL formats:
    - Claude Code: {"type": "user|assistant", "message": {...}}
    - Cursor: {"role": "user|assistant", "message": {...}}
    """
    result = {
        "user_messages": [],
        "assistant_messages": [],
        "tool_calls": 0,
        "tool_results": 0,
        "total_lines": 0,
    }
    if not transcript_path:
        return result
    p = Path(transcript_path).expanduser()
    if not p.is_file():
        return result
    try:
        text = p.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return result
    if len(text.encode("utf-8")) > MAX_TRANSCRIPT_BYTES:
        text = text.encode("utf-8")[:MAX_TRANSCRIPT_BYTES].decode("utf-8", errors="ignore")
        if "\n" in text[-200:]:
            text = text.rsplit("\n", 1)[0]
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        result["total_lines"] += 1
        entry_type = entry.get("type") or entry.get("role", "")
        message = entry.get("message", {})
        if entry_type == "user":
            text_content = extract_text_content(message)
            if text_content.strip():
                result["user_messages"].append(text_content)
        elif entry_type == "assistant":
            text_content = extract_text_content(message)
            if text_content.strip():
                result["assistant_messages"].append(text_content)
            if isinstance(message, dict):
                content = message.get("content", [])
                if isinstance(content, list):
                    for block in content:
                        if isinstance(block, dict) and block.get("type") == "tool_use":
                            result["tool_calls"] += 1
        elif entry_type in ("tool_use",):
            result["tool_calls"] += 1
        elif entry_type in ("tool_result",):
            result["tool_results"] += 1
    return result


def generate_run_id(date_str: str, vault: Path) -> str:
    """Generate a unique run_id for today. YYYY-MM-DD-NNN."""
    marker = vault / "content" / ".run-counter"
    n = 1
    if marker.is_file():
        try:
            stored = json.loads(marker.read_text(encoding="utf-8"))
            if stored.get("date") == date_str:
                n = int(stored.get("n", 0)) + 1
        except (json.JSONDecodeError, ValueError, OSError):
            n = 1
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text(json.dumps({"date": date_str, "n": n}), encoding="utf-8")
    return f"{date_str}-{n:03d}"


def write_session_file(vault: Path, mode: str, input_text: str, transcript_data: dict, date_str: str) -> Path:
    """Write content/sessions/current.md with the session artifact."""
    sessions_dir = vault / "content" / "sessions"
    sessions_dir.mkdir(parents=True, exist_ok=True)
    session_path = sessions_dir / "current.md"

    lines = [
        "---",
        f"date: {date_str}",
        f"mode: {mode}",
        f"captured_at: {datetime.now().isoformat(timespec='seconds')}",
        "captured_by: post-hook.py",
        f"transcript_lines: {transcript_data.get('total_lines', 0)}",
        f"user_messages: {len(transcript_data.get('user_messages', []))}",
        f"assistant_messages: {len(transcript_data.get('assistant_messages', []))}",
        f"tool_calls: {transcript_data.get('tool_calls', 0)}",
        "---",
        "",
        "# Session Capture",
        "",
    ]
    if mode == "topic":
        lines.extend(["## Input (topic)", "", input_text, ""])
    else:
        lines.extend(["## User Messages", ""])
        for i, msg in enumerate(transcript_data.get("user_messages", []), 1):
            lines.append(f"### {i}")
            lines.append("")
            lines.append(msg)
            lines.append("")
        lines.extend(["## Assistant Messages", ""])
        for i, msg in enumerate(transcript_data.get("assistant_messages", []), 1):
            lines.append(f"### {i}")
            lines.append("")
            lines.append(msg)
            lines.append("")
        lines.extend([
            "## Tool Activity",
            "",
            f"- Tool calls: {transcript_data.get('tool_calls', 0)}",
            f"- Tool results: {transcript_data.get('tool_results', 0)}",
            "",
        ])

    content = "\n".join(lines)
    atomic_write(session_path, content)
    return session_path


def write_current_md(vault: Path, mode: str, input_text: str, run_id: str) -> Path:
    """Write content/current.md with the routing context."""
    current_path = vault / "content" / "current.md"
    current_path.parent.mkdir(parents=True, exist_ok=True)
    session_rel = "content/sessions/current.md"
    if mode == "topic":
        input_yaml = f'"{input_text}"'
    else:
        input_yaml = '""'
    content = (
        "---\n"
        f"mode: {mode}\n"
        f"input: {input_yaml}\n"
        f"session: {session_rel}\n"
        "status: routing\n"
        f"run_id: {run_id}\n"
        f"created_at: {datetime.now().isoformat(timespec='seconds')}\n"
        "captured_by: post-hook.py\n"
        "---\n"
    )
    atomic_write(current_path, content)
    return current_path


def atomic_write(path: Path, content: str) -> None:
    """Write to tmp, fsync, rename. Survives crashes mid-write."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", dir=path.parent, prefix=".post-hook-", suffix=".tmp", delete=False, encoding="utf-8"
    ) as f:
        tmp = Path(f.name)
        f.write(content)
        f.flush()
        os.fsync(f.fileno())
    tmp.replace(path)


def build_additional_context(current_path: Path, session_path: Path, mode: str) -> str:
    """Build the explicit additionalContext for the LLM."""
    return (
        "Execution context prepared.\n"
        "\n"
        "NEXT ACTION REQUIRED:\n"
        "Invoke @director.\n"
        "\n"
        "Source of truth:\n"
        f"  - {current_path}\n"
        f"  - {session_path}\n"
        "\n"
        "Do not interpret, modify, or explain. Dispatch @director immediately."
    )


def main() -> int:
    ap = argparse.ArgumentParser(description="Hook script for /post command")
    ap.add_argument("--vault", help="Path to vault root")
    ap.add_argument("--ide", choices=["claude", "cursor", "opencode"], default="claude",
                    help="Which IDE hook is calling (affects output format)")
    args = ap.parse_args()

    vault = resolve_vault(args.vault)
    if not vault:
        print("ERROR: could not locate vault", file=sys.stderr)
        sys.exit(1)

    context = read_hook_context()
    prompt = context.get("prompt", "")
    transcript_path = context.get("transcript_path", "")

    post_args, mode = parse_post_command(prompt)
    if mode == "none":
        sys.exit(0)

    transcript_data = parse_transcript(transcript_path) if mode == "session" else {"total_lines": 0}

    date_str = datetime.now().strftime("%Y-%m-%d")
    run_id = generate_run_id(date_str, vault)
    session_path = write_session_file(vault, mode, post_args, transcript_data, date_str)
    current_path = write_current_md(vault, mode, post_args, run_id)

    additional_context = build_additional_context(current_path, session_path, mode)

    if args.ide == "cursor":
        output = {"continue": True}
    else:
        output = {
            "hookSpecificOutput": {
                "hookEventName": "UserPromptSubmit",
                "additionalContext": additional_context,
            }
        }
    print(json.dumps(output))
    return 0


if __name__ == "__main__":
    sys.exit(main())
