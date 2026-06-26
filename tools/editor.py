#!/usr/bin/env python3
"""editor.py — Editor role tool. Runs the 4 mechanical gates on a draft.

The 4 gates are: em_dash, banned_phrases, required_frontmatter, char_count.
All config lives in `system/rules.yaml` so a user can edit them without
touching code.

CLI:
    python3 tools/editor.py check <draft.md>            # JSON to stdout
    python3 tools/editor.py check <draft.md> --quiet     # exit code only
    python3 tools/editor.py check <draft.md> --json      # pure JSON, no summary
    python3 tools/editor.py check <draft.md> --gates a,b # run only these gates
    python3 tools/editor.py stamp <draft.md>             # run gates + write verdict to FM

Exit codes:
    0 = pass
    1 = fail (one or more gates fail)
    3 = error (parse error, missing file, etc.)

The 4 mechanical gates are the deterministic half of the Editor role.
The taste review (clear hook, specific reader, concrete proof, not generic,
sounds like the user) is LLM-judged by the Editor subagent itself.

The `stamp` subcommand is the deterministic record: it runs the 4 gates
and writes `gates_verdict: pass|fail` + `gates_report: <json>` to the
draft's frontmatter atomically. Publishers refuse to ship a draft whose
frontmatter has `gates_verdict: fail`.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path

import sys as _sys
_sys.path.insert(0, str(Path(__file__).resolve().parent))
from _vault import resolve_vault  # noqa: E402


# ─── Rules loader ────────────────────────────────────────────────────────

def load_rules(vault: Path) -> dict:
    """Load system/rules.yaml from the vault. Returns {} on failure."""
    rules_path = vault / "system" / "rules.yaml"
    if not rules_path.exists():
        return {}
    try:
        import yaml
        return yaml.safe_load(rules_path.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}


# ─── Frontmatter parser ─────────────────────────────────────────────────

def parse_frontmatter(text: str) -> tuple[dict, str]:
    """Parse YAML frontmatter. Returns (frontmatter_dict, body)."""
    if not text.startswith("---"):
        return {}, text
    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}, text
    fm_text, body = parts[1], parts[2]
    fm = {}
    try:
        import yaml
        fm = yaml.safe_load(fm_text) or {}
    except Exception:
        for line in fm_text.splitlines():
            if ":" not in line:
                continue
            k, _, v = line.partition(":")
            fm[k.strip()] = v.strip()
    if not isinstance(fm, dict):
        fm = {}
    return fm, body


# ─── 4 mechanical gates ─────────────────────────────────────────────────

def check_em_dash(fm, body, rules):
    """Gate 1: no em-dashes. Use →, colons, or commas instead."""
    if "—" in body:
        n = body.count("—")
        return False, f"FAIL: {n} em-dash(es) (use \u2192 or colons instead)"
    return True, "OK: No em-dashes"


def check_banned_phrases(fm, body, rules):
    """Gate 2: no banned phrases. Reads from system/rules.yaml §banned."""
    banned = rules.get("banned", {}) or {}
    found = []

    for phrase in (banned.get("exact") or []):
        if phrase and phrase in body:
            found.append(f"phrase: {phrase!r}")

    for pattern in (banned.get("regex") or []):
        try:
            m = re.search(pattern, body)
        except re.error:
            continue
        if m:
            found.append(f"regex: {pattern!r} (matched {m.group(0)!r})")

    if found:
        return False, f"FAIL: Banned content found: {', '.join(found)}"
    return True, "OK: No banned phrases"


def check_required_frontmatter(fm, body, rules):
    """Gate 3: all 8 required frontmatter fields present."""
    required = rules.get("required_frontmatter", []) or [
        "title", "created", "platform", "status",
        "source", "reader", "point", "angle",
    ]
    missing = [f for f in required if not fm.get(f)]
    if missing:
        return False, f"FAIL: Missing frontmatter: {', '.join(missing)}"
    return True, f"OK: {len(required)} required frontmatter fields present"


def check_char_count(fm, body, rules):
    """Gate 4: per-platform char/word limit. Reads from system/rules.yaml §drafts."""
    drafts = rules.get("drafts", {}) or {}
    platforms = drafts.get("platforms", {}) or {}
    platform = (fm.get("platform") or "").lower()

    if platform == "x":
        limit = platforms.get("x", {}).get("max_chars", 280)
        n = len(body)
        if n > limit:
            return False, f"FAIL: {n} chars > X limit ({limit})"
        return True, f"OK ({n} chars, X limit {limit})"

    if platform == "linkedin":
        limit = platforms.get("linkedin", {}).get("max_chars", 3000)
        n = len(body)
        if n > limit:
            return False, f"FAIL: {n} chars > LinkedIn limit ({limit})"
        return True, f"OK ({n} chars, LinkedIn limit {limit})"

    if platform == "blog":
        limit = platforms.get("blog", {}).get("max_words", 2500)
        n = len(body.split())
        if n > limit:
            return False, f"FAIL: {n} words > blog limit ({limit})"
        return True, f"OK ({n} words, blog limit {limit})"

    return True, f"OK: unknown platform '{platform}', skipped char check"


# ─── Gate registry ──────────────────────────────────────────────────────

ALL_CHECKS: list[tuple[str, callable]] = [
    ("em_dash", check_em_dash),
    ("banned_phrases", check_banned_phrases),
    ("required_frontmatter", check_required_frontmatter),
    ("char_count", check_char_count),
]


# ─── Validator ───────────────────────────────────────────────────────────

def validate_draft(fm, body, rules, selected_checks=None) -> dict:
    """Run every gate (or the selected subset) and return per-gate results."""
    results = {}
    for name, fn in ALL_CHECKS:
        if selected_checks and name not in selected_checks:
            continue
        try:
            passed, message = fn(fm, body, rules)
            results[name] = {"pass": bool(passed), "message": str(message)}
        except Exception as e:
            results[name] = {"pass": False, "message": f"ERROR: {e}"}
    return results


# ─── Vault detection ─────────────────────────────────────────────────────

def find_vault() -> Path:
    v = resolve_vault()
    if v is None:
        return Path.cwd()
    return v


# ─── Stamp (persist verdict to frontmatter) ─────────────────────────────

def cmd_stamp(args, vault: Path) -> int:
    """Run all 4 gates, then write gates_verdict + gates_report to frontmatter.

    Atomic: write to tmp, fsync, rename. Survives crashes mid-write.
    """
    import tempfile
    import os as _os

    draft_path = Path(args.draft)
    if not draft_path.is_absolute():
        draft_path = vault / draft_path
    if not draft_path.exists():
        print(f"ERROR: draft not found: {draft_path}", file=sys.stderr)
        return 3
    try:
        text = draft_path.read_text(encoding="utf-8")
    except OSError as e:
        print(f"ERROR: cannot read draft: {e}", file=sys.stderr)
        return 3

    fm, body = parse_frontmatter(text)
    rules = load_rules(vault)
    selected = None
    if args.gates:
        selected = {g.strip() for g in args.gates.split(",") if g.strip()}
    results = validate_draft(fm, body, rules, selected_checks=selected)
    passed = sum(1 for r in results.values() if r["pass"])
    failed = sum(1 for r in results.values() if not r["pass"])
    verdict = "pass" if failed == 0 else "fail"

    # Persist verdict + report to frontmatter
    fm["gates_verdict"] = verdict
    fm["gates_stamped_at"] = datetime.now().isoformat(timespec="seconds")
    fm["gates_report"] = results

    import yaml
    new_text = "---\n" + yaml.safe_dump(fm, sort_keys=False, allow_unicode=True) + "---\n" + body

    # Atomic write
    draft_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", dir=draft_path.parent, prefix=".stamp-", suffix=".tmp", delete=False, encoding="utf-8"
    ) as f:
        tmp = Path(f.name)
        f.write(new_text)
        f.flush()
        _os.fsync(f.fileno())
    tmp.replace(draft_path)

    if args.quiet:
        return 0 if verdict == "pass" else 1
    out = {
        "draft": str(draft_path.relative_to(vault)) if draft_path.is_relative_to(vault) else str(draft_path),
        "verdict": verdict,
        "summary": {"passed": passed, "failed": failed, "total": len(results)},
    }
    print(json.dumps(out, indent=2))
    print(f"  stamped: verdict={verdict} ({passed} pass, {failed} fail)", file=sys.stderr)
    return 0 if verdict == "pass" else 1


# ─── CLI ─────────────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(description="SpielOS Editor — 4 mechanical gates")
    sub = parser.add_subparsers(dest="cmd", required=True)

    check = sub.add_parser("check", help="Check a single draft")
    check.add_argument("draft", help="Path to draft .md file")
    check.add_argument("--json", action="store_true", help="Pure JSON to stdout")
    check.add_argument("--quiet", action="store_true", help="No stdout, exit code only")
    check.add_argument("--gates", help="Comma-separated gate ids to run (default: all)")
    check.add_argument("--vault", help="Path to vault root (default: auto-detect)")

    stamp = sub.add_parser("stamp", help="Run gates + write verdict to frontmatter (atomic)")
    stamp.add_argument("draft", help="Path to draft .md file")
    stamp.add_argument("--quiet", action="store_true", help="No stdout, exit code only")
    stamp.add_argument("--gates", help="Comma-separated gate ids to run (default: all)")
    stamp.add_argument("--vault", help="Path to vault root (default: auto-detect)")

    args = parser.parse_args()

    if args.cmd == "check":
        vault = Path(args.vault) if args.vault else find_vault()
        draft_path = Path(args.draft)
        if not draft_path.is_absolute():
            draft_path = vault / draft_path
        if not draft_path.exists():
            print(f"ERROR: draft not found: {draft_path}", file=sys.stderr)
            return 3
        try:
            text = draft_path.read_text(encoding="utf-8")
        except OSError as e:
            print(f"ERROR: cannot read draft: {e}", file=sys.stderr)
            return 3
        fm, body = parse_frontmatter(text)
        rules = load_rules(vault)
        selected = None
        if args.gates:
            selected = {g.strip() for g in args.gates.split(",") if g.strip()}
        results = validate_draft(fm, body, rules, selected_checks=selected)

        passed = sum(1 for r in results.values() if r["pass"])
        failed = sum(1 for r in results.values() if not r["pass"])

        verdict = "pass" if failed == 0 else "fail"
        exit_code = 0 if failed == 0 else 1

        report = {
            "draft": str(draft_path.relative_to(vault)) if draft_path.is_relative_to(vault) else str(draft_path),
            "platform": fm.get("platform", ""),
            "results": results,
            "summary": {"passed": passed, "failed": failed, "total": len(results)},
            "verdict": verdict,
        }

        if args.quiet:
            return exit_code
        if args.json:
            print(json.dumps(report, indent=2))
        else:
            print(json.dumps(report, indent=2))
            print(f"\nverdict: {verdict}  ({passed} pass, {failed} fail)", file=sys.stderr)
        return exit_code

    if args.cmd == "stamp":
        vault = Path(args.vault) if args.vault else find_vault()
        return cmd_stamp(args, vault)

    return 0


if __name__ == "__main__":
    sys.exit(main())
