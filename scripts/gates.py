#!/usr/bin/env python3
"""gates.py — Unified mechanical gate for ShayanWiki drafts.

Replaces both preflight_post.py and validate_post.py.
All rule parameters come from rules.yaml — edit that file to tune behavior.
Voice markers (lowercase-i, absolutely, Note:, self-deprecation, etc.)
are NOT enforced here — they are LLM guidance in concepts/voice-and-gates.md.

Usage:
    ./scripts/gates.py <draft-file>              # Check one draft
    ./scripts/gates.py --all                     # Check all drafts in queue
    ./scripts/gates.py --all --emit-json path    # Machine-readable report
    ./scripts/gates.py --list                    # Show available checks
    ./scripts/gates.py --check hook,em_dash      # Run specific checks only
"""

import json
import os
import re
import sys
from collections import Counter
from pathlib import Path

try:
    import yaml
except ImportError:
    print("gates.py requires PyYAML: pip install pyyaml", file=sys.stderr)
    sys.exit(1)

VAULT = Path(os.environ.get("VAULT_DIR", Path(__file__).resolve().parent.parent))
RULES_FILE = VAULT / "rules.yaml"


# ─── Load Rules ─────────────────────────────────────────────────────────────

def load_rules() -> dict:
    if not RULES_FILE.exists():
        print(f"ERROR: {RULES_FILE} not found. Run `cp rules.yaml.example rules.yaml`.", file=sys.stderr)
        sys.exit(2)
    with RULES_FILE.open() as f:
        rules = yaml.safe_load(f)
    if rules is None:
        print(f"ERROR: {RULES_FILE} is empty or malformed.", file=sys.stderr)
        sys.exit(2)
    return rules


# ─── Read Draft ─────────────────────────────────────────────────────────────

def read_draft(filepath: Path) -> tuple[dict, str]:
    content = filepath.read_text(encoding="utf-8")
    fm = {"title": "unknown", "tags": []}
    body = content
    if content.startswith("---"):
        parts = content.split("---", 2)
        if len(parts) >= 3:
            try:
                parsed = yaml.safe_load(parts[1])
                if isinstance(parsed, dict):
                    fm = parsed
            except yaml.YAMLError:
                pass
            body = parts[2].strip()
    return fm, body


# ─── Pure Check Functions (all take fm, body, rules) ────────────────────────

def check_char_count(fm: dict, body: str, rules: dict) -> tuple[bool, str]:
    limits = rules["char_limits"]
    body_len = len(body)

    platform = (fm.get("platform") or "").lower()
    fname = str(fm.get("_file", ""))

    if platform in ("x", "twitter") or "tweet" in fname:
        limit = limits["x_single"]
    elif platform == "linkedin" or "linkedin" in fname:
        if body_len > limits["linkedin_casual"]:
            if body_len <= limits["linkedin_polished"]:
                return True, f"OK ({body_len} chars, LinkedIn polished ≤{limits['linkedin_polished']})"
            return False, f"FAIL: {body_len} chars > LinkedIn polished limit ({limits['linkedin_polished']})"
        limit = limits["linkedin_casual"]
    elif platform == "blog" or "pillar" in fname:
        limit = limits["blog_pillar_words"] * 6  # rough chars
    else:
        limit = limits["linkedin_casual"]

    if body_len > limit:
        return False, f"FAIL: {body_len} chars > {limit} limit ({platform})"
    return True, f"OK ({body_len} chars, limit {limit})"


def check_hook(fm: dict, body: str, rules: dict) -> tuple[bool, str]:
    banned = rules.get("banned_openers", [])
    first_line = body.strip().split("\n")[0].strip()
    first_line = re.sub(r"^[-*•]\s*", "", first_line)

    if not first_line:
        return False, "FAIL: Body is empty"

    if len(first_line) < 5:
        return False, f"FAIL: First line too short: '{first_line}'"

    fl_lower = first_line.lower()
    for pattern in banned:
        if re.match(pattern, fl_lower):
            return False, f"FAIL: '{first_line[:60]}' matches banned opener"

    return True, f"OK: '{first_line[:50]}...'"


def check_em_dash(fm: dict, body: str, rules: dict) -> tuple[bool, str]:
    count = body.count("—")
    if count > 0:
        return False, f"FAIL: {count} em-dash(es) (use → or colons instead)"
    return True, "OK: No em-dashes"


def check_word_repeat(fm: dict, body: str, rules: dict) -> tuple[bool, str]:
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


def check_architecture_leak(fm: dict, body: str, rules: dict) -> tuple[bool, str]:
    leaks = rules.get("architecture_leaks", [])
    found = []
    for pattern in leaks:
        matches = re.findall(pattern, body)
        if matches:
            found.append(pattern)
    if found:
        return False, f"FAIL: Architecture leaks: {', '.join(found)}"
    return True, "OK: No architecture leaks"


def check_audience_named(fm: dict, body: str, rules: dict) -> tuple[bool, str]:
    triggers = rules.get("audience_triggers", [])
    body_lower = body.lower()
    for t in triggers:
        if t in body_lower:
            return True, f"OK: Audience via '{t}'"
    return False, "FAIL: No audience named in body"


def check_lesson_surfaced(fm: dict, body: str, rules: dict) -> tuple[bool, str]:
    triggers = rules.get("lesson_triggers", [])
    body_lower = body.lower()
    for t in triggers:
        if t in body_lower:
            return True, f"OK: Lesson via '{t}'"
    return False, "FAIL: No lesson surfaced"


def check_generic_statement(fm: dict, body: str, rules: dict) -> tuple[bool, str]:
    patterns = rules.get("generic_statements", [])
    body_lower = body.lower()
    for p in patterns:
        if re.search(p, body_lower):
            return False, f"FAIL: Generic: '{p}'"
    return True, "OK: No generic statements"


def check_project_as_subject(fm: dict, body: str, rules: dict) -> tuple[bool, str]:
    """AP-13 successor: post must not open with a project name as subject.
    
    Passes if the first word is a safe opener (list in rules.yaml),
    or if the first word is "I"/"We" (operator voice),
    or if the first word is a lowercase word not matching a project name.
    
    Strips leading quotes, punctuation, and markdown heading markers
    before checking. Numbers and symbols (non-alpha) are allowed.
    
    Only FAILS if the first word looks like a proper noun (capitalized)
    that is not "I" or "We" — meaning the post opens with a project/tool name.
    """
    safe = set(w.lower() for w in rules.get("safe_openers", []))
    first_line = body.strip().split("\n")[0].strip()
    first_line = re.sub(r"^[-*•#]\s*", "", first_line)
    if not first_line:
        return False, "FAIL: Empty body"
    
    first_word = first_line.split()[0] if first_line.split() else ""
    if not first_word:
        return True, "OK: No first word to check"

    # Strip leading quotes and punctuation for the check
    cleaned = first_word.strip('\'"`*_({[')

    if not cleaned:
        return True, "OK: Only punctuation"

    # If it doesn't start with a letter → number, symbol, or quoted — allow it
    if not cleaned[0].isalpha():
        return True, f"OK: Non-alpha start '{first_word}' — not a project name"

    # Accept safe openers (including reader-first, negative, question, etc.)
    if cleaned.lower() in safe:
        return True, f"OK: Safe opener '{first_word}'"
    
    # Accept "I" and "We" (operator voice still allowed)
    if cleaned in ("I", "We"):
        return True, "OK: Operator-focused opening"
    
    # Accept lowercase words (not project names)
    if cleaned[0].islower():
        return True, "OK: Lowercase opening — not a project name"
    
    # Capitalized word that's not I/We and not in safe list — likely a project name
    return False, f"FAIL: Opens with project name '{first_word}' as subject"


def check_closing(fm: dict, body: str, rules: dict) -> tuple[bool, str]:
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

    if "🤝" in tail or "👊" in tail:
        return True, "OK: Emoji close"
    
    return False, f"WARN: No closing detected in last {window} chars"


def check_frontmatter(fm: dict, body: str, rules: dict) -> tuple[bool, str]:
    gp = rules.get("gate_params", {})
    required = gp.get("required_frontmatter_fields", ["title", "created", "tags", "platform"])
    missing = [f for f in required if f not in fm or fm.get(f) is None]
    if missing:
        return False, f"WARN: Missing frontmatter: {', '.join(missing)}"
    return True, "OK: Required frontmatter present"


def check_dollar_in_note(fm: dict, body: str, rules: dict) -> tuple[bool, str]:
    note_match = re.search(r"(?:^|\n)Note:\s*(.*)", body, re.IGNORECASE)
    if note_match:
        if re.search(r"\$\d", note_match.group(1)):
            return False, "FAIL: Dollar amount in Note: closer"
    return True, "OK: No dollar in Note:"


def check_strategy_void(fm: dict, body: str, rules: dict) -> tuple[bool, str]:
    pillar = fm.get("pillar")
    pattern = fm.get("pattern")
    has_pillar = bool(pillar and isinstance(pillar, str) and pillar.strip())
    has_pattern = bool(pattern and isinstance(pattern, str) and pattern.strip())
    if has_pillar or has_pattern:
        return True, "OK: Strategy fields present"
    return False, "FAIL: No 'pillar' or 'pattern' in frontmatter"


def check_icp_present(fm: dict, body: str, rules: dict) -> tuple[bool, str]:
    icp = fm.get("icp")
    if icp and isinstance(icp, str) and icp.strip():
        return True, "OK: ICP present in frontmatter"
    return False, "FAIL: No ICP in frontmatter"


def check_banner(fm: dict, body: str, rules: dict) -> tuple[bool, str]:
    banner = fm.get("banner")
    if not banner or not isinstance(banner, str) or not banner.strip():
        return False, "FAIL: No 'banner' field in frontmatter"
    banner_path = VAULT / banner.strip()
    if not banner_path.exists():
        return False, f"FAIL: Banner file not found: {banner}"
    return True, f"OK: Banner present at {banner}"


def check_grounded_reference(fm: dict, body: str, rules: dict) -> tuple[bool, str]:
    known = rules.get("known_names", [])
    if not known:
        return True, "OK: No known names configured"

    pattern = r"\b(" + "|".join(re.escape(n) for n in known) + r")\b"
    matches = re.findall(pattern, body)
    if not matches:
        return True, "OK: No named references"

    for name in matches[:3]:
        idx = body.find(name)
        snippet = body[idx: idx + len(name) + 120]
        grounded = False
        after = snippet[len(name):].strip()
        if after.startswith(("—", "--", "–")):
            grounded = True
        if re.search(re.escape(name) + r",\s+(the|an?)\s+\w+", snippet):
            grounded = True
        if not grounded:
            return False, f"FAIL: '{name}' without grounding"
    return True, "OK: All references grounded"


# ─── Registry ───────────────────────────────────────────────────────────────

ALL_CHECKS = [
    ("char_count",          check_char_count),
    ("hook_check",          check_hook),
    ("em_dash",             check_em_dash),
    ("word_repeat",         check_word_repeat),
    ("architecture_leak",   check_architecture_leak),
    ("audience_named",      check_audience_named),
    ("lesson_surfaced",     check_lesson_surfaced),
    ("generic_statement",   check_generic_statement),
    ("project_as_subject",  check_project_as_subject),
    ("closing",             check_closing),
    ("frontmatter",         check_frontmatter),
    ("dollar_in_note",      check_dollar_in_note),
    ("strategy_void",       check_strategy_void),
    ("icp_present",         check_icp_present),
    ("banner",              check_banner),
    ("grounded_reference",  check_grounded_reference),
]


# ─── Validate ───────────────────────────────────────────────────────────────

def validate_draft(fm: dict, body: str, rules: dict, filepath: str = "",
                   selected_checks: list[str] | None = None) -> dict:
    results = {}
    enabled = {k: v for k, v in rules.get("gates", {}).items() if v}
    
    for name, fn in ALL_CHECKS:
        if selected_checks and name not in selected_checks:
            continue
        if not enabled.get(name, True):
            results[name] = (True, "SKIP: disabled in rules.yaml")
            continue
        try:
            results[name] = fn(fm, body, rules)
        except Exception as e:
            results[name] = (False, f"ERROR: {e}")

    fails = sum(1 for ok, _ in results.values() if not ok)
    
    # Log to logs/ dir
    from datetime import datetime
    log_dir = VAULT / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / f"{datetime.now().strftime('%Y-%m-%d')}.jsonl"
    log_entry = json.dumps({
        "timestamp": datetime.now().isoformat(timespec="milliseconds"),
        "level": "INFO",
        "source": "gates",
        "message": f"Checked {filepath or 'draft'}",
        "file": filepath,
        "ap_passed": len(results) - fails,
        "ap_total": len(results),
        "ap_fails": fails,
    })
    with log_file.open("a") as f:
        f.write(log_entry + "\n")
    
    return results


# ─── CLI ────────────────────────────────────────────────────────────────────

def main():
    import argparse
    from datetime import datetime

    parser = argparse.ArgumentParser(description="Gates: unified mechanical gate for ShayanWiki")
    parser.add_argument("file", nargs="?", help="Draft file to validate")
    parser.add_argument("--all", action="store_true", help="Validate all queue drafts")
    parser.add_argument("--list", action="store_true", help="List available checks")
    parser.add_argument("--check", nargs="+", help="Run specific checks only")
    parser.add_argument("--emit-json", metavar="PATH", help="Write JSON report")
    args = parser.parse_args()

    rules = load_rules()
    selected = args.check

    if args.list:
        enabled = {k: v for k, v in rules.get("gates", {}).items() if v}
        print("Available gates:")
        for name, _ in ALL_CHECKS:
            status = "✓" if enabled.get(name, True) else "○ (disabled)"
            print(f"  {name:25s} {status}")
        return 0

    if args.all:
        queue_dir = VAULT / "content" / "queue"
        if not queue_dir.exists():
            print("No queue directory.")
            return 0
        drafts = sorted(queue_dir.glob("*.md"))
        if not drafts:
            print("Queue is empty.")
            return 0

        total_fails = 0
        report_drafts = []

        for draft in drafts:
            fm, body = read_draft(draft)
            fm["_file"] = draft.name
            results = validate_draft(fm, body, rules, filepath=draft.name,
                                     selected_checks=selected)
            fails = sum(1 for ok, _ in results.values() if not ok)
            total_fails += fails

            print(f"\n═══ {draft.name} ═══")
            for name, (ok, msg) in sorted(results.items()):
                icon = "✓" if ok else "✗"
                print(f"  {icon} {name:25s} | {msg}")
            print(f"  {'─' * 60}")
            print(f"  Failures: {fails}/{len(results)}")

            report_drafts.append({
                "file": draft.name,
                "checks": {n: bool(ok) for n, (ok, _) in results.items()},
                "score": len(results) - fails,
                "max": len(results),
                "pass": fails == 0,
            })

        print(f"\n═══ Total: {len(drafts)} drafts, {total_fails} failures ═══")

        if args.emit_json:
            report = {
                "generated_at": datetime.now().isoformat(timespec="milliseconds"),
                "drafts": report_drafts,
            }
            Path(args.emit_json).write_text(json.dumps(report, indent=2))
            print(f"  JSON report: {args.emit_json}")

        return 1 if total_fails > 0 else 0

    elif args.file:
        filepath = Path(args.file)
        if not filepath.exists():
            print(f"File not found: {filepath}")
            return 1
        fm, body = read_draft(filepath)
        fm["_file"] = filepath.name
        results = validate_draft(fm, body, rules, filepath=filepath.name,
                                 selected_checks=selected)
        fails = 0
        print(f"\n═══ Gates: {filepath.name} ═══")
        for name, (ok, msg) in sorted(results.items()):
            icon = "✓" if ok else "✗"
            print(f"  {icon} {name:25s} | {msg}")
            if not ok:
                fails += 1
        print(f"  {'─' * 60}")
        print(f"  Result: {fails}/{len(results)} failures")
        return 1 if fails > 0 else 0

    else:
        parser.print_help()
        return 0


if __name__ == "__main__":
    sys.exit(main())
