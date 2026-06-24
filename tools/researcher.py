#!/usr/bin/env python3
"""researcher.py — Researcher role tool. Synthesizes a session log from the opencode DB.

The Researcher subagent uses this when `/post` (no args) finds no session log
for today. The tool:

1. Reads the opencode SQLite DB at `~/.local/share/opencode/opencode.db`.
2. Finds the most recent parent session in the current cwd.
3. Summarizes the session into a session log file.
4. Optionally classifies it (archetype / funnel / icp_layer / vertical).

CLI:
    python3 tools/researcher.py synthesize-session --out <path> [--cwd <path>]
    python3 tools/researcher.py classify --input <text> --kind session|topic
    python3 tools/researcher.py classify --input <file> --kind session|topic
    python3 tools/researcher.py session-list

Output: JSON to stdout, human summary to stderr.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

# Shared vault resolver
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
from _vault import resolve_vault  # noqa: E402

# ─── Vault detection ─────────────────────────────────────────────────────

def find_vault() -> Path:
    v = resolve_vault()
    if v is None:
        return Path.cwd()
    return v


VAULT = find_vault()
RULES_FILE = VAULT / "system" / "rules.yaml"


# ─── Rules loader ────────────────────────────────────────────────────────

def load_rules() -> dict:
    if not RULES_FILE.exists():
        return {}
    try:
        import yaml
        return yaml.safe_load(RULES_FILE.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}


# ─── Opencode DB read ────────────────────────────────────────────────────

OPENCODE_DB = Path.home() / ".local" / "share" / "opencode" / "opencode.db"


def find_recent_session(cwd: Path) -> dict | None:
    """Find the most recent parent session in cwd from the opencode DB."""
    if not OPENCODE_DB.exists():
        return None
    try:
        conn = sqlite3.connect(str(OPENCODE_DB))
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        # Try several schema variants
        candidates = []
        for query in [
            "SELECT id, parent_id, time_created, time_updated, title, directory FROM session ORDER BY time_created DESC LIMIT 50",
            "SELECT id, parent_id, created_at as time_created, updated_at as time_updated, title, cwd as directory FROM session ORDER BY created_at DESC LIMIT 50",
            "SELECT id, parent_id, time_created, time_updated, title, workspace as directory FROM session ORDER BY time_created DESC LIMIT 50",
        ]:
            try:
                cur.execute(query)
                rows = cur.fetchall()
                if rows:
                    for r in rows:
                        d = dict(r)
                        # Best-effort: match cwd substring
                        if not d.get("directory") or str(cwd) in str(d["directory"]) or str(d["directory"]).endswith(str(cwd.name)):
                            candidates.append(d)
                    if candidates:
                        break
            except sqlite3.OperationalError:
                continue
        conn.close()
        if not candidates:
            return None
        return candidates[0]
    except Exception as e:
        print(f"WARN: opencode DB read failed: {e}", file=sys.stderr)
        return None


def read_session_messages(session_id: str, max_chars: int = 12000) -> list[dict]:
    """Read messages for a session from the opencode DB. Best-effort across schemas."""
    if not OPENCODE_DB.exists():
        return []
    try:
        conn = sqlite3.connect(str(OPENCODE_DB))
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        for query in [
            "SELECT role, content, time_created FROM message WHERE session_id = ? ORDER BY time_created ASC",
            "SELECT role, parts as content, created_at as time_created FROM message WHERE session_id = ? ORDER BY created_at ASC",
        ]:
            try:
                cur.execute(query, (session_id,))
                rows = cur.fetchall()
                if rows:
                    out = []
                    for r in rows:
                        d = dict(r)
                        # Truncate per-message
                        c = d.get("content") or ""
                        if isinstance(c, str) and len(c) > 2000:
                            c = c[:2000] + "..."
                        d["content"] = c
                        out.append(d)
                    return out
            except sqlite3.OperationalError:
                continue
        conn.close()
    except Exception as e:
        print(f"WARN: opencode message read failed: {e}", file=sys.stderr)
    return []


# ─── Classification (keyword-based) ──────────────────────────────────────

def classify(text: str, kind: str, rules: dict) -> dict:
    """Mechanical classification via keyword matching. Returns a dict."""
    text_lower = text.lower()
    strategy = rules.get("strategy", {}) if isinstance(rules, dict) else {}

    # Archetype
    archetype = "S10"  # default
    archetype_score = 0
    archetypes = strategy.get("archetypes", {})
    for arch, keywords in archetypes.items():
        if not isinstance(keywords, list):
            continue
        score = sum(1 for kw in keywords if kw.lower() in text_lower)
        if score > archetype_score:
            archetype_score = score
            archetype = arch.split("_")[0].upper()  # S1, S2, ...

    # Funnel
    funnel = "TOFU"  # default
    funnel_score = 0
    funnel_stages = strategy.get("funnel_stages", {})
    for stage, keywords in funnel_stages.items():
        if not isinstance(keywords, list):
            continue
        score = sum(1 for kw in keywords if kw.lower() in text_lower)
        if score > funnel_score:
            funnel_score = score
            funnel = stage

    # ICP layer
    icp_layer = "L2"  # default
    icp_score = 0
    icp_layers = strategy.get("icp_layers", {})
    for layer, keywords in icp_layers.items():
        if not isinstance(keywords, list):
            continue
        score = sum(1 for kw in keywords if kw.lower() in text_lower)
        if score > icp_score:
            icp_score = score
            icp_layer = layer.split("_")[0].upper()

    # Vertical
    vertical = "builder-to-lead-system"  # default
    vert_score = 0
    verticals = strategy.get("verticals", {})
    for v, keywords in verticals.items():
        if not isinstance(keywords, list):
            continue
        score = sum(1 for kw in keywords if kw.lower() in text_lower)
        if score > vert_score:
            vert_score = score
            vertical = v

    return {
        "archetype": archetype,
        "funnel": funnel,
        "icp_layer": icp_layer,
        "vertical": vertical,
        "topic_type": "" if kind == "session" else "announcement",
        "scores": {
            "archetype": archetype_score,
            "funnel": funnel_score,
            "icp_layer": icp_score,
            "vertical": vert_score,
        },
    }


# ─── Session log synthesis ──────────────────────────────────────────────

SESSION_LOG_TEMPLATE = """---
title: {title}
date: {date}
session_id: {session_id}
tags: [{tags}]
produces_pillar: no
pillar_outline: none
drafts: []
status: complete
---

# {title}

> Auto-synthesized from opencode session {session_id}. Edit this log to refine before running `/post`.

## Patterns recognized

{patterns}

## Decisions made

{decisions}

## What we did

- (3-7 bullets from the session — edit to reflect what actually happened)
- (e.g., "Refactored the engine into role-based .md files.")
- (e.g., "Removed 5,000 LOC of Python state machine.")

## Shipped

{shipped}

## Numbers

- 0 (placeholder — edit)

## Lesson

{lesson}
"""


def synthesize_session(cwd: Path, out_path: Path) -> dict:
    """Read opencode session for cwd, summarize into a session log file."""
    session = find_recent_session(cwd)
    if not session:
        return {"ok": False, "reason": "no recent session found in opencode DB for cwd"}
    session_id = session.get("id", "unknown")
    session_id_short = session_id.split("_")[-1] if "_" in session_id else session_id[:8]
    created = session.get("time_created")
    if isinstance(created, (int, float)):
        date_str = datetime.fromtimestamp(created).strftime("%Y-%m-%d")
    else:
        date_str = datetime.now().strftime("%Y-%m-%d")
    title = session.get("title") or f"Session {session_id_short}"

    messages = read_session_messages(session_id, max_chars=12000)

    # Naive extraction: pick user messages, find patterns/decisions/lesson keywords
    user_msgs = [m for m in messages if m.get("role") in ("user", "human")]
    assistant_msgs = [m for m in messages if m.get("role") in ("assistant", "ai")]
    all_text = "\n".join((m.get("content") or "") for m in messages if isinstance(m.get("content"), str))

    patterns: list[str] = []
    decisions: list[str] = []
    shipped: list[str] = []
    lesson: list[str] = []
    for line in all_text.splitlines():
        s = line.strip()
        if not s or len(s) < 8 or len(s) > 200:
            continue
        sl = s.lower()
        if any(kw in sl for kw in ["decided", "chose", "picked"]):
            decisions.append(s)
        elif any(kw in sl for kw in ["shipped", "released", "merged", "deployed"]):
            shipped.append(s)
        elif any(kw in sl for kw in ["learned", "lesson", "realized", "taught me"]):
            lesson.append(s)
        elif any(kw in sl for kw in ["pattern", "noticed", "always", "tendency"]):
            patterns.append(s)

    def fmt(items: list[str], n: int = 5) -> str:
        if not items:
            return "- (none detected — fill in)"
        seen = set()
        out = []
        for it in items:
            if it in seen:
                continue
            seen.add(it)
            out.append(f"- {it}")
            if len(out) >= n:
                break
        return "\n".join(out)

    text = SESSION_LOG_TEMPLATE.format(
        title=title[:80],
        date=date_str,
        session_id=session_id_short,
        tags="synthesized, auto",
        patterns=fmt(patterns, 5),
        decisions=fmt(decisions, 5),
        shipped=fmt(shipped, 5),
        lesson=fmt(lesson, 3) if lesson else "- (fill in after reading the session)",
    )

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(text, encoding="utf-8")

    # Classify
    rules = load_rules()
    classification = classify(all_text[:4000], kind="session", rules=rules)

    return {
        "ok": True,
        "session_id": session_id,
        "session_id_short": session_id_short,
        "title": title,
        "date": date_str,
        "messages_read": len(messages),
        "out": str(out_path),
        "classification": classification,
    }


# ─── CLI ─────────────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(description="SpielOS Researcher — session synthesis + classification")
    sub = parser.add_subparsers(dest="cmd", required=True)

    syn = sub.add_parser("synthesize-session", help="Synthesize a session log from opencode DB")
    syn.add_argument("--out", required=True, help="Output .md path")
    syn.add_argument("--cwd", help="Working directory to scope the session lookup (default: vault root)")

    cls = sub.add_parser("classify", help="Classify text or a file")
    cls.add_argument("--input", required=True, help="Text or path to .md file")
    cls.add_argument("--kind", choices=["session", "topic"], default="session")

    sub.add_parser("session-list", help="List recent opencode sessions")

    args = parser.parse_args()
    rules = load_rules()

    if args.cmd == "synthesize-session":
        cwd = Path(args.cwd) if args.cwd else VAULT
        out = Path(args.out)
        if not out.is_absolute():
            out = VAULT / out
        result = synthesize_session(cwd, out)
        print(json.dumps(result, indent=2))
        if not result.get("ok"):
            print(f"ERROR: {result.get('reason')}", file=sys.stderr)
            return 1
        print(f"\nSynthesized: {result['out']}", file=sys.stderr)
        print(f"Classification: {result['classification']}", file=sys.stderr)
        return 0

    if args.cmd == "classify":
        inp = args.input
        if Path(inp).exists():
            text = Path(inp).read_text(encoding="utf-8")
        else:
            text = inp
        result = classify(text, args.kind, rules)
        print(json.dumps(result, indent=2))
        return 0

    if args.cmd == "session-list":
        if not OPENCODE_DB.exists():
            print("[]")
            print(f"opencode DB not found at {OPENCODE_DB}", file=sys.stderr)
            return 0
        conn = sqlite3.connect(str(OPENCODE_DB))
        conn.row_factory = sqlite3.Row
        try:
            rows = conn.execute("SELECT id, time_created, title FROM session ORDER BY time_created DESC LIMIT 10").fetchall()
            print(json.dumps([dict(r) for r in rows], indent=2, default=str))
        except sqlite3.OperationalError as e:
            print(f"ERROR: {e}", file=sys.stderr)
            return 1
        finally:
            conn.close()
        return 0

    return 0


if __name__ == "__main__":
    sys.exit(main())
