#!/usr/bin/env python3
"""editor.py — Editor role tool. Runs the 15 mechanical gates on a draft.

The 15 check functions live at the bottom of this file (ported from the
original engine/gates.py). This module wraps them in a CLI:

    python3 tools/editor.py check <draft.md>            # JSON to stdout, summary to stderr
    python3 tools/editor.py check <draft.md> --quiet     # exit code only
    python3 tools/editor.py check <draft.md> --json      # pure JSON, no pretty-print
    python3 tools/editor.py check <draft.md> --gates a,b,c   # run only these gates

Exit codes:
    0 = pass (all enabled gates pass)
    1 = fail (one or more gates fail)
    2 = warn (all pass, some soft warn)
    3 = error (parse error, missing file, etc.)

The 15 mechanical gates are the deterministic half of the Editor role.
The 14 soft gates are LLM-judged and applied by the Editor subagent itself
(not by this tool).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path


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


# ─── 15 mechanical gates ────────────────────────────────────────────────

def check_char_count(fm, body, rules):
    limits = rules.get("char_limits", {})
    body_len = len(body)
    platform = (fm.get("platform") or "").lower()
    doc_type = (fm.get("type") or "").lower()
    if doc_type == "thread":
        posts = [p.strip() for p in body.split("\n---\n") if p.strip()]
        x_limit = limits.get("x_single", 280)
        max_posts = limits.get("x_thread_max_tweets", 12)
        if len(posts) > max_posts:
            return False, f"FAIL: {len(posts)} tweets > thread max ({max_posts})"
        for i, post in enumerate(posts):
            if len(post) > x_limit:
                return False, f"FAIL: Post {i+1} is {len(post)} chars > {x_limit} limit"
        return True, f"OK: thread with {len(posts)} posts ({max(len(p) for p in posts)} max chars)"
    if platform in ("x", "twitter"):
        limit = limits.get("x_single", 280)
    elif platform == "linkedin":
        voice_register = (fm.get("voice_register") or "").strip().lower()
        if voice_register == "casual":
            limit = limits.get("linkedin_casual", 1500)
        elif voice_register == "polished":
            limit = limits.get("linkedin_polished", 3000)
        else:
            if body_len > limits.get("linkedin_casual", 1500):
                if body_len <= limits.get("linkedin_polished", 3000):
                    return True, f"OK ({body_len} chars, LinkedIn polished \u22643000)"
                return False, f"FAIL: {body_len} chars > LinkedIn polished limit (3000)"
            limit = limits.get("linkedin_casual", 1500)
    elif platform == "blog":
        word_limit = limits.get("blog_pillar_words", 2500)
        word_count = len(body.split())
        if word_count > word_limit:
            return False, f"FAIL: {word_count} words > blog pillar limit ({word_limit} words)"
        return True, f"OK ({word_count} words, blog pillar limit {word_limit})"
    else:
        limit = limits.get("buffer", 2200)
    if body_len > limit:
        return False, f"FAIL: {body_len} chars > {limit} limit ({platform})"
    return True, f"OK ({body_len} chars, limit {limit})"


def check_hook(fm, body, rules):
    banned = rules.get("banned_openers", [])
    first_line = body.strip().split("\n")[0].strip()
    first_line = re.sub(r"^[-*\u2022]\s*", "", first_line)
    if not first_line:
        return False, "FAIL: Body is empty"
    if len(first_line) < 5:
        return False, f"FAIL: First line too short: '{first_line}'"
    fl_lower = first_line.lower()
    for pattern in banned:
        if re.match(pattern, fl_lower):
            return False, f"FAIL: '{first_line[:60]}' matches banned opener"
    return True, f"OK: '{first_line[:50]}...'"


def check_em_dash(fm, body, rules):
    count = body.count("\u2014")
    if count > 0:
        return False, f"FAIL: {count} em-dash(es) (use \u2192 or colons instead)"
    return True, "OK: No em-dashes"


def check_word_repeat(fm, body, rules):
    common = set(rules.get("common_words", []))
    words = re.findall(r'\b[a-zA-Z]{3,}\b', body.lower())
    filtered = [w for w in words if w not in common]
    counts = Counter(filtered)
    gp = rules.get("gate_params", {})
    body_len = len(body)
    small = gp.get("word_repeat_scale_small", 500)
    medium = gp.get("word_repeat_scale_medium", 1500)
    large_min = gp.get("word_repeat_scale_large_min", 6)
    large_max = gp.get("word_repeat_scale_large_max", 12)
    if body_len < small:
        threshold = 3
    elif body_len < medium:
        threshold = 4
    else:
        threshold = max(large_min, min(large_max, body_len // 300))
    repeated = {w: c for w, c in counts.items() if c >= threshold}
    if repeated:
        items = ", ".join(f"'{w}' ({c}x)" for w, c in sorted(repeated.items()))
        return False, f"FAIL: Words repeated {threshold}+: {items}"
    return True, "OK: No excessive repetition"


def check_architecture_leak(fm, body, rules):
    leaks = rules.get("architecture_leaks", [])
    found = []
    for pattern in leaks:
        matches = re.findall(pattern, body)
        if matches:
            found.append(pattern)
    if found:
        return False, f"FAIL: Architecture leaks: {', '.join(found)}"
    return True, "OK: No architecture leaks"


def check_audience_named(fm, body, rules):
    gp = rules.get("gate_params", {}) or {}
    strong_triggers = gp.get("strong_audience_triggers") or [
        "you ", "your ", "you're", "you'll", "founders", "builders",
        "if you", "when you", "your team", "your code",
    ]
    triggers = rules.get("audience_triggers", [])
    body_lower = body.lower()
    for t in strong_triggers:
        if t in body_lower:
            return True, f"OK: Audience named via '{t.strip()}'"
    for t in triggers:
        if len(t.split()) >= 2 and t in body_lower:
            return True, f"OK: Audience via '{t}'"
    return False, "FAIL: No audience named in body"


def check_lesson_surfaced(fm, body, rules):
    triggers = rules.get("lesson_triggers", [])
    body_lower = body.lower()
    for t in triggers:
        if t in body_lower:
            return True, f"OK: Lesson via '{t}'"
    return False, "FAIL: No lesson surfaced"


def check_generic_statement(fm, body, rules):
    patterns = rules.get("generic_statements", [])
    body_lower = body.lower()
    for p in patterns:
        if re.search(p, body_lower):
            return False, f"FAIL: Generic: '{p}'"
    return True, "OK: No generic statements"


def check_project_as_subject(fm, body, rules):
    safe = set(w.lower() for w in rules.get("safe_openers", []))
    first_line = body.strip().split("\n")[0].strip()
    first_line = re.sub(r"^[-*\u2022#]\s*", "", first_line)
    if not first_line:
        return False, "FAIL: Empty body"
    first_word = first_line.split()[0] if first_line.split() else ""
    if not first_word:
        return True, "OK: No first word to check"
    cleaned = first_word.strip('\'"`*_({[')
    if not cleaned:
        return True, "OK: Only punctuation"
    if not cleaned[0].isalpha():
        return True, f"OK: Non-alpha start '{first_word}'"
    strong_safe = {"i", "we", "you", "your", "remember", "what", "why", "how",
                   "when", "who", "which", "never", "always", "imagine",
                   "stop", "forget", "nobody", "everyone", "anyone"}
    if cleaned.lower() in strong_safe:
        return True, f"OK: Safe opener '{first_word}'"
    if cleaned.lower() in safe and len(cleaned) > 3:
        return True, f"OK: Safe opener '{first_word}'"
    if cleaned in ("I", "We"):
        return True, "OK: Operator-focused opening"
    if cleaned[0].islower():
        return True, "OK: Lowercase opening"
    return False, f"FAIL: Opens with project name '{first_word}' as subject"


def check_closing(fm, body, rules):
    gp = rules.get("gate_params", {})
    window = gp.get("close_detect_window", 200)
    fallback = gp.get("close_fallback_phrases", ["note:", "?"])
    tail = body[-window:].lower()
    bank = rules.get("engagement_bank", [])
    for phrase in bank:
        if phrase in tail:
            return True, f"OK: Closing via '{phrase}'"
    for phrase in fallback:
        if phrase in tail:
            return True, f"OK: Closing via '{phrase}'"
    if "\U0001f91d" in tail or "\U0001f44a" in tail:
        return True, "OK: Emoji close"
    return False, f"WARN: No closing detected in last {window} chars"


def check_frontmatter(fm, body, rules):
    gp = rules.get("gate_params", {})
    required = gp.get(
        "required_frontmatter_fields",
        ["title", "created", "tags", "platform", "status"],
    )
    missing = [f for f in required if f not in fm or fm.get(f) is None]
    if missing:
        return False, f"WARN: Missing frontmatter: {', '.join(missing)}"
    return True, "OK: Required frontmatter present"


def check_dollar_in_note(fm, body, rules):
    note_match = re.search(r"(?:^|\n)Note:\s*(.*)", body, re.IGNORECASE)
    if note_match:
        if re.search(r"\$\d", note_match.group(1)):
            return False, "FAIL: Dollar amount in Note: closer"
    return True, "OK: No dollar in Note:"


def check_strategy_void(fm, body, rules):
    pillar = fm.get("pillar")
    pattern = fm.get("pattern")
    has_pillar = bool(pillar and isinstance(pillar, str) and pillar.strip())
    has_pattern = bool(pattern and isinstance(pattern, str) and pattern.strip())
    if has_pillar or has_pattern:
        return True, "OK: Strategy fields present"
    return False, "FAIL: No 'pillar' or 'pattern' in frontmatter"


def check_icp_present(fm, body, rules):
    icp = fm.get("icp")
    if icp and isinstance(icp, str) and icp.strip():
        return True, "OK: ICP present in frontmatter"
    return False, "FAIL: No ICP in frontmatter"


def check_grounded_reference(fm, body, rules):
    known = rules.get("known_names", [])
    if not known:
        return True, "OK: No known names configured"
    pattern = r"\b(" + "|".join(re.escape(n) for n in known) + r")\b"
    matches = re.findall(pattern, body)
    if not matches:
        return True, "OK: No named references"
    for name in matches:
        idx = body.find(name)
        snippet = body[idx: idx + len(name) + 120]
        grounded = False
        if re.search(re.escape(name) + r",\s+(the|an?)\s+\w+", snippet):
            grounded = True
        if not grounded:
            return False, f"FAIL: '{name}' without grounding (add ', the <role>')"
    return True, "OK: All references grounded"


ALL_CHECKS: list[tuple[str, callable]] = [
    ("char_count", check_char_count),
    ("hook_check", check_hook),
    ("em_dash", check_em_dash),
    ("word_repeat", check_word_repeat),
    ("architecture_leak", check_architecture_leak),
    ("audience_named", check_audience_named),
    ("lesson_surfaced", check_lesson_surfaced),
    ("generic_statement", check_generic_statement),
    ("project_as_subject", check_project_as_subject),
    ("closing", check_closing),
    ("frontmatter", check_frontmatter),
    ("dollar_in_note", check_dollar_in_note),
    ("strategy_void", check_strategy_void),
    ("icp_present", check_icp_present),
    ("grounded_reference", check_grounded_reference),
]


# ─── Validator ───────────────────────────────────────────────────────────

def validate_draft(fm, body, rules, selected_checks=None) -> dict:
    results = {}
    enabled = {k: v for k, v in rules.get("gates", {}).items() if v}
    for name, fn in ALL_CHECKS:
        if selected_checks and name not in selected_checks:
            continue
        if not enabled.get(name, True):
            results[name] = {"pass": True, "message": "SKIP: disabled in rules.yaml"}
            continue
        try:
            passed, message = fn(fm, body, rules)
            results[name] = {"pass": bool(passed), "message": str(message)}
        except Exception as e:
            results[name] = {"pass": False, "message": f"ERROR: {e}"}
    return results


# ─── Vault detection ─────────────────────────────────────────────────────

def find_vault() -> Path:
    """Find the SpielOS vault root. Walk up from cwd, then check ~/.spiel/."""
    cwd = Path.cwd()
    for p in [cwd, *cwd.parents]:
        if (p / "team" / "md.md").exists() and (p / "system" / "state-machine.md").exists():
            return p
    home_vault = Path.home() / ".spiel"
    if (home_vault / "team" / "md.md").exists():
        return home_vault
    return cwd  # best effort


# ─── CLI ─────────────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(description="SpielOS Editor — 15 mechanical gates")
    sub = parser.add_subparsers(dest="cmd", required=True)

    check = sub.add_parser("check", help="Check a single draft")
    check.add_argument("draft", help="Path to draft .md file")
    check.add_argument("--json", action="store_true", help="Pure JSON to stdout")
    check.add_argument("--quiet", action="store_true", help="No stdout, exit code only")
    check.add_argument("--gates", help="Comma-separated gate ids to run (default: all enabled)")
    check.add_argument("--vault", help="Path to vault root (default: auto-detect)")

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
        # verdict
        passed = sum(1 for r in results.values() if r["pass"])
        failed = sum(1 for r in results.values() if not r["pass"] and not r["message"].startswith("WARN"))
        warned = sum(1 for r in results.values() if not r["pass"] and r["message"].startswith("WARN"))
        if failed > 0:
            verdict = "fail"
            exit_code = 1
        elif warned > 0:
            verdict = "warn"
            exit_code = 2
        else:
            verdict = "pass"
            exit_code = 0
        report = {
            "draft": str(draft_path.relative_to(vault)) if draft_path.is_relative_to(vault) else str(draft_path),
            "platform": fm.get("platform", ""),
            "results": results,
            "summary": {"passed": passed, "failed": failed, "warned": warned, "total": len(results)},
            "verdict": verdict,
        }
        if args.quiet:
            return exit_code
        if args.json:
            print(json.dumps(report, indent=2))
        else:
            print(json.dumps(report, indent=2))
            print(f"\nverdict: {verdict}  ({passed} pass, {failed} fail, {warned} warn)", file=sys.stderr)
        return exit_code

    return 0


if __name__ == "__main__":
    sys.exit(main())
