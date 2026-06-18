#!/usr/bin/env python3
"""gates.py — 16 pure mechanical check functions.

All rules parameters come from rules.yaml via Config.
Functions are pure: (fm, body, rules) -> (bool, str).
No file I/O, no CLI. Kernel imports and calls these.
"""

import re
from collections import Counter


def check_char_count(fm: dict, body: str, rules: dict) -> tuple[bool, str]:
    limits = rules.get("char_limits", {})
    body_len = len(body)
    platform = (fm.get("platform") or "").lower()
    fname = str(fm.get("_file", ""))
    if platform in ("x", "twitter") or "tweet" in fname:
        limit = limits.get("x_single", 280)
    elif platform == "linkedin" or "linkedin" in fname:
        if body_len > limits.get("linkedin_casual", 1500):
            if body_len <= limits.get("linkedin_polished", 3000):
                return True, f"OK ({body_len} chars, LinkedIn polished \u22643000)"
            return False, f"FAIL: {body_len} chars > LinkedIn polished limit (3000)"
        limit = limits.get("linkedin_casual", 1500)
    elif platform == "blog" or "pillar" in fname:
        limit = limits.get("blog_pillar_words", 2500) * 6
    else:
        limit = limits.get("buffer", 2200)
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
    count = body.count("\u2014")
    if count > 0:
        return False, f"FAIL: {count} em-dash(es) (use \u2192 or colons instead)"
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
    safe = set(w.lower() for w in rules.get("safe_openers", []))
    first_line = body.strip().split("\n")[0].strip()
    first_line = re.sub(r"^[-*•#]\s*", "", first_line)
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
    if cleaned.lower() in safe:
        return True, f"OK: Safe opener '{first_word}'"
    if cleaned in ("I", "We"):
        return True, "OK: Operator-focused opening"
    if cleaned[0].islower():
        return True, "OK: Lowercase opening"
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
    if "\U0001f91d" in tail or "\U0001f44a" in tail:
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
        if after.startswith(("\u2014", "--", "\u2013")):
            grounded = True
        if re.search(re.escape(name) + r",\s+(the|an?)\s+\w+", snippet):
            grounded = True
        if not grounded:
            return False, f"FAIL: '{name}' without grounding"
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


def validate_draft(fm: dict, body: str, rules: dict,
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
    return results
