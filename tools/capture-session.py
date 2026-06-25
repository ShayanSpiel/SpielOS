#!/usr/bin/env python3
"""capture-session.py — Capture the CURRENT session and save it as the canonical log.

The Researcher subagent runs this on every /post (no args). The LLM is the only
thing that has the live transcript of the conversation it is in, so it builds a
clean transcript (drop tool noise, keep user/assistant text) and hands it to
this tool. The tool writes it to a single canonical file:

    <vault>/content/sessions/YYYY-MM-DD-session-current.md

Always overwrites. There is exactly one "current" session log per day. No NN
numbering, no per-message subdirs, no fallback to older logs.

The Researcher must NEVER scan content/sessions/ for any existing log, NEVER
call tools/researcher.py synthesize-session, and NEVER read a log other than
the one this tool just wrote. That is by design (see team/researcher.md).

CLI:
    python3 tools/capture-session.py \
        --vault <path> \
        (--transcript-stdin | --transcript-file <path> | --transcript-string "<md>") \
        [--title "..."] [--status complete|in-progress] \
        [--tags "s1,build"] [--summary "..."] \
        [--structured-json <path>]

Output: JSON to stdout, human summary to stderr.
Exit codes: 0 = ok, 2 = bad input, 3 = vault not found.
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

# Shared vault resolver
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
from _vault import resolve_vault  # noqa: E402

# ─── Vault resolution ─────────────────────────────────────────────────────

def find_vault(cli_vault: str | None) -> Path:
    v = resolve_vault(cli_vault)
    if v is None:
        return Path.cwd()
    return v


# ─── Transcript input ─────────────────────────────────────────────────────

MAX_TRANSCRIPT_BYTES = 1_000_000  # 1 MB hard cap


def read_transcript(args: argparse.Namespace) -> str:
    """Read the transcript from whichever source the user picked."""
    sources = [bool(args.transcript_stdin), bool(args.transcript_file), bool(args.transcript_string)]
    if sum(sources) != 1:
        raise ValueError(
            "Specify exactly one of --transcript-stdin, --transcript-file, --transcript-string"
        )
    if args.transcript_stdin:
        data = sys.stdin.read()
    elif args.transcript_file:
        p = Path(args.transcript_file).expanduser()
        if not p.is_file():
            raise ValueError(f"--transcript-file not found: {p}")
        data = p.read_text(encoding="utf-8")
    else:
        data = args.transcript_string
    if not data or not data.strip():
        raise ValueError("transcript is empty")
    if len(data.encode("utf-8")) > MAX_TRANSCRIPT_BYTES:
        # Truncate at a clean line boundary if possible, then mark it.
        data = data.encode("utf-8")[:MAX_TRANSCRIPT_BYTES].decode("utf-8", errors="ignore")
        if "\n" in data[-200:]:
            data = data.rsplit("\n", 1)[0]
        data += "\n\n[truncated at 1MB]\n"
    return data


# ─── Structured input ─────────────────────────────────────────────────────

def read_structured(args: argparse.Namespace) -> dict | None:
    """Optional. LLM can pass a JSON file with the 6 canonical sections
    pre-extracted. If present, we render those into the body. If absent,
    the body holds only the raw transcript (status: in-progress) and the
    Researcher fills the sections itself in markdown after."""
    if not args.structured_json:
        return None
    p = Path(args.structured_json).expanduser()
    if not p.is_file():
        raise ValueError(f"--structured-json not found: {p}")
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise ValueError(f"--structured-json is not valid JSON: {e}")
    if not isinstance(data, dict):
        raise ValueError("--structured-json must be a JSON object")
    return data


# ─── Frontmatter / log rendering ─────────────────────────────────────────

def _yaml_quote(s: str) -> str:
    """Quote a string for YAML if it contains special chars."""
    if not s:
        return '""'
    if re.match(r"^[a-zA-Z0-9_\-./@ ]+$", s):
        return s
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _render_frontmatter(args: argparse.Namespace, date_str: str, message_count: int) -> str:
    status = args.status or "in-progress"
    if status not in ("complete", "in-progress"):
        raise ValueError(f"--status must be 'complete' or 'in-progress', got: {status!r}")
    title = (args.title or "Current session").strip()[:120]
    tags = [t.strip() for t in (args.tags or "").split(",") if t.strip()]
    if not tags:
        tags = ["captured", "current"]
    tags_yaml = "[" + ", ".join(_yaml_quote(t) for t in tags) + "]"
    summary = (args.summary or "").strip().replace('"', '\\"')
    summary_line = f"summary: \"{summary}\"" if summary else "summary: \"\""
    parts = [
        "---",
        f"title: {_yaml_quote(title)}",
        f"date: {date_str}",
        "session_id: current",
        f"tags: {tags_yaml}",
        "produces_pillar: no",
        "pillar_outline: none",
        "drafts: []",
        f"status: {status}",
        summary_line,
        f"captured_by: capture-session.py",
        f"captured_at: {datetime.now().isoformat(timespec='seconds')}",
        f"message_count: {message_count}",
        "---",
        "",
    ]
    return "\n".join(parts)


def _render_body(transcript: str, structured: dict | None, status: str) -> str:
    lines: list[str] = []
    lines.append("# Current Session")
    lines.append("")
    lines.append(
        "> Auto-captured by the Researcher from the live conversation. "
        "Edits are fine; the file is overwritten on the next `/post`."
    )
    lines.append("")
    if structured:
        # Render the 6 canonical sections from the structured JSON.
        section_titles = [
            ("patterns", "Patterns recognized"),
            ("decisions", "Decisions made"),
            ("what_we_did", "What we did"),
            ("shipped", "Shipped"),
            ("numbers", "Numbers"),
            ("lesson", "Lesson"),
        ]
        for key, title in section_titles:
            items = structured.get(key)
            lines.append(f"## {title}")
            lines.append("")
            if isinstance(items, list) and items:
                for it in items:
                    s = str(it).strip()
                    if s:
                        lines.append(f"- {s}")
            elif isinstance(items, str) and items.strip():
                for line in items.strip().splitlines():
                    lines.append(f"- {line.strip()}" if line.strip() else "")
            else:
                lines.append("- (none captured)")
            lines.append("")
        # Optional summary
        if structured.get("summary"):
            lines.append("## Summary")
            lines.append("")
            lines.append(str(structured["summary"]).strip())
            lines.append("")
    else:
        # No structured input — body is a stub; Researcher fills it after.
        for title in ("Patterns recognized", "Decisions made", "What we did", "Shipped", "Numbers", "Lesson"):
            lines.append(f"## {title}")
            lines.append("")
            lines.append("- (to be filled in by the Researcher)")
            lines.append("")
    # Transcript appendix (always)
    lines.append("## Transcript")
    lines.append("")
    lines.append("```")
    lines.append(transcript.rstrip())
    lines.append("```")
    lines.append("")
    if status == "in-progress":
        lines.append("---")
        lines.append("")
        lines.append(
            "**Status: in-progress.** The Researcher captures mid-flight and "
            "fills the structured sections in this same file before handing off "
            "to the Strategist. If you ran this manually, edit the sections "
            "above and set `status: complete` in the frontmatter."
        )
        lines.append("")
    return "\n".join(lines)


# ─── Atomic write ──────────────────────────────────────────────────────────

def atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    # Write to tmp, fsync, rename. Survives crashes mid-write.
    with tempfile.NamedTemporaryFile(
        "w", dir=path.parent, prefix=".capture-", suffix=".tmp", delete=False, encoding="utf-8"
    ) as f:
        tmp = Path(f.name)
        f.write(content)
        f.flush()
        os.fsync(f.fileno())
    tmp.replace(path)


# ─── Count messages (best-effort) ─────────────────────────────────────────

def count_messages(transcript: str) -> int:
    """Best-effort message count. The LLM may pass a clean transcript with
    'User:' / 'Assistant:' / '## User' markers, or a raw JSON array, or just
    prose. We count separator lines if present, else count paragraphs."""
    if not transcript.strip():
        return 0
    # Try structured markers first.
    for marker in (r"(?m)^#+\s*User\b", r"(?m)^#+\s*Assistant\b", r"(?m)^#+\s*Human\b",
                   r"(?m)^User:", r"(?m)^Assistant:", r"(?m)^Human:"):
        pass  # not a count, just check format
    # Heuristic: count non-empty paragraph blocks.
    blocks = [b for b in re.split(r"\n\s*\n", transcript.strip()) if b.strip()]
    return max(1, len(blocks))


# ─── CLI ──────────────────────────────────────────────────────────────────

def main() -> int:
    ap = argparse.ArgumentParser(
        description="Capture the CURRENT session transcript and save it as the canonical log.",
    )
    ap.add_argument("--vault", help="Path to the vault root. Default: $VAULT_DIR → walk up from cwd")
    src = ap.add_mutually_exclusive_group(required=False)  # enforced manually for better error
    src.add_argument("--transcript-stdin", action="store_true",
                     help="Read the transcript from stdin")
    src.add_argument("--transcript-file", help="Read the transcript from a file path")
    src.add_argument("--transcript-string", help="Pass the transcript as a string (small only)")
    ap.add_argument("--title", help="Title for the session log (default: 'Current session')")
    ap.add_argument("--status", choices=["complete", "in-progress"],
                    help="Status flag (default: in-progress)")
    ap.add_argument("--tags", help="Comma-separated tags, e.g. 's2,build,refactor'")
    ap.add_argument("--summary", help="One-line summary the LLM extracted")
    ap.add_argument("--structured-json",
                    help="Optional JSON with pre-extracted Patterns/Decisions/etc. sections")
    ap.add_argument("--out", help="Override output path (default: <vault>/content/sessions/<date>-session-current.md)")
    args = ap.parse_args()

    # Vault
    vault = find_vault(args.vault)
    if not vault:
        sys.stderr.write("ERROR: could not locate SpielOS vault.\n")
        sys.stderr.write("  Tried --vault, $VAULT_DIR, walk up for .spiel-vault / team/md.md\n")
        sys.stderr.write("  Fix: pass --vault /path/to/SpielOS or export VAULT_DIR=...\n")
        return 3

    # Transcript
    try:
        transcript = read_transcript(args)
    except ValueError as e:
        sys.stderr.write(f"ERROR: {e}\n")
        return 2

    # Structured
    try:
        structured = read_structured(args)
    except ValueError as e:
        sys.stderr.write(f"ERROR: {e}\n")
        return 2

    # Output path
    date_str = datetime.now().strftime("%Y-%m-%d")
    if args.out:
        out_path = Path(args.out).expanduser()
        if not out_path.is_absolute():
            out_path = vault / out_path
    else:
        out_path = vault / "content" / "sessions" / f"{date_str}-session-current.md"

    overwrote = out_path.exists()
    msg_count = count_messages(transcript)

    # Render
    try:
        frontmatter = _render_frontmatter(args, date_str, msg_count)
    except ValueError as e:
        sys.stderr.write(f"ERROR: {e}\n")
        return 2
    body = _render_body(transcript, structured, args.status or "in-progress")
    content = frontmatter + body

    # Write
    try:
        atomic_write(out_path, content)
    except OSError as e:
        sys.stderr.write(f"ERROR: could not write {out_path}: {e}\n")
        return 3

    result = {
        "ok": True,
        "path": str(out_path),
        "session_id": "current",
        "date": date_str,
        "message_count": msg_count,
        "bytes": out_path.stat().st_size,
        "overwrote": overwrote,
        "status": args.status or "in-progress",
    }
    print(json.dumps(result, indent=2))
    sys.stderr.write(
        f"  ✓ Captured session → {out_path}  ({msg_count} messages, "
        f"{result['bytes']} bytes, overwrote={overwrote})\n"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
