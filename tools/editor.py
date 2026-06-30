#!/usr/bin/env python3
"""editor.py — Editor role tool. Runs the mechanical gates on drafts and briefs.

The 4 draft gates are: em_dash, banned_phrases, required_frontmatter, char_count.
The 5th gate (grounding_check) runs on the BRIEF in content/current.md
(not on individual drafts) and verifies the brief is grounded in the
ICP World Simulator's output (content/.icp-world.json). All config
lives in `system/rules.yaml` so a user can edit them without touching code.

CLI:
    python3 tools/editor.py check <draft.md>            # JSON to stdout
    python3 tools/editor.py check <draft.md> --quiet     # exit code only
    python3 tools/editor.py check <draft.md> --json      # pure JSON, no summary
    python3 tools/editor.py check <draft.md> --gates a,b # run only these gates
    python3 tools/editor.py stamp <draft.md>             # run 4 draft gates + write verdict
    python3 tools/editor.py check-brief                  # run grounding_check on the brief

Exit codes:
    0 = pass
    1 = fail (one or more gates fail)
    3 = error (parse error, missing file, etc.)

The 4 draft gates + grounding_check are the deterministic half of the
Editor role. The taste review (clear hook, specific reader, concrete
proof, not generic, sounds like the user) is LLM-judged by the Editor
subagent itself.

The `stamp` subcommand is the deterministic record: it runs the 4 gates
and writes `gates_verdict: pass|fail` + `gates_report: <json>` to the
draft's frontmatter atomically. Publishers refuse to ship a draft whose
frontmatter has `gates_verdict: fail`.

The `check-brief` subcommand runs grounding_check on content/current.md.
It does NOT write to any file. The Editor role is responsible for
writing the verdict to `## Editorial` and either advancing or setting
the error.
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


# ─── Rules loader ───────────────────────────────────────────────────────

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
    """Gate 3: all 11 required frontmatter fields present."""
    required = rules.get("required_frontmatter", []) or [
        "title", "created", "platform", "status", "source",
        "reader", "pain", "belief", "point", "meaning", "proof",
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


# ─── 5th gate: grounding_check (brief, not draft) ────────────────────────

STOPWORDS = frozenset(
    "the a an and or but if then so to of in on at by for from with as is "
    "are was were be been being have has had do does did this that these those "
    "i you he she it we they me him her us them my your his hers its our their "
    "what which who whom whose not no nor only own same than too very can will "
    "just dont don't im i'm ive i've youll you'll".split()
)


def _tokenize(text: str) -> set[str]:
    """Lowercase, strip non-alpha, drop stopwords + tokens <3 chars."""
    if not text:
        return set()
    out = set()
    for tok in re.findall(r"[a-z0-9]+", text.lower()):
        if len(tok) < 3:
            continue
        if tok in STOPWORDS:
            continue
        out.add(tok)
    return out


def _jaccard(a: str, b: str) -> float:
    """Token Jaccard similarity in [0, 1]."""
    sa, sb = _tokenize(a), _tokenize(b)
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)


def _extract_brief_fields(brief_md: str) -> dict:
    """Parse `## Strategy` section, return the 6 brief fields + volume + example_pattern.

    The brief is YAML inside a markdown section. We extract the strategy
    block then parse it as YAML. Falls back to {} on parse error.
    """
    if not brief_md:
        return {}
    # Find the ## Strategy section
    in_section = False
    block_lines: list[str] = []
    for line in brief_md.splitlines():
        if line.strip() == "## Strategy":
            in_section = True
            continue
        if in_section:
            if line.startswith("## ") and line.strip() != "## Strategy":
                break
            block_lines.append(line)
    block = "\n".join(block_lines).strip()
    if not block:
        return {}
    try:
        import yaml
        parsed = yaml.safe_load(block)
        if not isinstance(parsed, dict):
            return {}
        # Coerce proof to a string for tokenization
        proof = parsed.get("proof", "")
        if isinstance(proof, list):
            proof = " ".join(str(x) for x in proof)
        parsed["proof"] = str(proof or "")
        return parsed
    except Exception:
        return {}


def _extract_run_mode(brief_md: str) -> str:
    """Return the frontmatter `mode:` value. Default 'session' for backward compat."""
    if not brief_md or not brief_md.startswith("---"):
        return "session"
    parts = brief_md.split("---", 2)
    if len(parts) < 3:
        return "session"
    try:
        import yaml
        fm = yaml.safe_load(parts[1]) or {}
        m = (fm.get("mode") or "session").lower()
        return m if m in ("session", "topic") else "session"
    except Exception:
        return "session"


def _extract_section(brief_md: str, heading: str) -> str:
    """Return the text inside a `## <heading>` section, excluding the heading line.

    Empty string if section not found. Stops at the next `## ` heading.
    """
    if not brief_md or not heading:
        return ""
    needle = f"## {heading}"
    out: list[str] = []
    in_section = False
    for line in brief_md.splitlines():
        if line.strip() == needle:
            in_section = True
            continue
        if in_section:
            if line.startswith("## "):
                break
            out.append(line)
    return "\n".join(out).strip()


def _extract_offer_section(vault: Path, section_heading: str) -> str:
    """Read strategy/offer.md and return the text under a `## <heading>` line.

    The offer.md is structured with short headings like "What you sell:",
    "Why it is different:", "Proof:". This helper returns the body text
    under the first matching heading (case-insensitive prefix match).
    Empty string on missing file or no match.
    """
    offer_path = vault / "strategy" / "offer.md"
    if not offer_path.is_file():
        return ""
    try:
        text = offer_path.read_text(encoding="utf-8")
    except OSError:
        return ""
    needle = section_heading.lower().rstrip(":")
    out: list[str] = []
    in_section = False
    for line in text.splitlines():
        stripped = line.strip()
        # Headings in offer.md are short, end with ":", and are not list items
        if (
            stripped
            and stripped.endswith(":")
            and not stripped.startswith("-")
            and not in_section
        ):
            if stripped.lower().rstrip(":").startswith(needle):
                in_section = True
                continue
        if in_section:
            # Stop at next short heading line (one that ends with ":")
            if stripped and stripped.endswith(":") and not stripped.startswith("-"):
                break
            out.append(line)
    return "\n".join(out).strip()


VALID_AXES = frozenset({"systemic", "behavioral", "philosophical", "contrarian", "leverage", "human"})


def _axis_valid(axis: str) -> bool:
    """Return True if `axis` is one of the 6 valid ICP-World-Simulator axes."""
    return bool(axis) and axis.strip().lower() in VALID_AXES


def _has_icp_marker(text: str, markers: list[str]) -> str | None:
    """Return the first ICP-language marker found in `text`, or None."""
    if not text or not markers:
        return None
    low = text.lower()
    for m in markers:
        if m and m.lower() in low:
            return m
    return None


def check_grounding(vault: Path, brief_md: str, icp_world: dict, rules: dict) -> dict:
    """Run the 5th gate: grounding_check on the brief in content/current.md.

    The 5 checks:
      1. brief_complete — all 6 brief fields present (reader, pain, belief,
         point, proof, meaning) + example_pattern
      2. simulator_present (both modes) — content/.icp-world.json exists
         and is complete
      3. point_blends_offer (both modes) — Jaccard overlap between brief's
         `point` and offer.md "Why it is different" >=
         rules.grounding.point_offer_overlap_min. Proves the point field
         blends offer content.
      4. proof_grounded (both modes) — proof has at least 1 ICP-language
         marker AND no build-log banned words
      5. example_pattern_present — `example_pattern` is set in the brief

    In topic mode, the simulator still runs (with lower volume), so all
    5 checks apply in both modes.

    Returns {"pass": bool, "message": str, "checks": {name: result, ...}}.
    """
    cfg = rules.get("grounding", {}) or {}
    banned = [w.lower() for w in (cfg.get("banned_words") or [])]
    markers = cfg.get("icp_markers") or []
    point_offer_min = float(cfg.get("point_offer_overlap_min", 0.15) or 0.15)

    mode = _extract_run_mode(brief_md)
    brief = _extract_brief_fields(brief_md)
    results: dict[str, dict] = {}

    if not brief:
        return {
            "pass": False,
            "message": "FAIL: brief is empty or unparseable. Strategist must write `## Strategy` first.",
            "checks": {"brief_present": {"pass": False, "message": "no `## Strategy` block"}},
        }

    # Check 1: brief is complete (6 fields + example_pattern)
    missing = [k for k in ("reader", "pain", "belief", "point", "proof", "meaning") if not brief.get(k)]
    if not brief.get("example_pattern"):
        missing.append("example_pattern")
    results["brief_complete"] = {
        "pass": not missing,
        "message": f"OK: all 6 brief fields + example_pattern present" if not missing
                   else f"FAIL: missing fields: {', '.join(missing)}",
    }

    # Check 2: simulator output exists and is complete (both modes)
    required_world_keys = ("reader", "belief", "pain", "point", "meaning", "proof",
                           "example_pattern", "axis")
    if not icp_world or not all(icp_world.get(k) for k in required_world_keys):
        results["simulator_present"] = {
            "pass": False,
            "message": "FAIL: content/.icp-world.json is missing or incomplete. Strategist must run `python3 tools/simulator.py write ...` first.",
        }
    else:
        results["simulator_present"] = {
            "pass": True,
            "message": "OK: simulator output present and complete (6 fields + example_pattern + axis)",
        }

    # Check 3: point blends offer.md "Why it is different"
    offer_diff = _extract_offer_section(vault, "Why it is different")
    point = brief.get("point", "")
    if offer_diff:
        overlap = _jaccard(point, offer_diff)
        results["point_blends_offer"] = {
            "pass": overlap >= point_offer_min,
            "message": f"OK: point blends offer.md 'Why it is different' (Jaccard={overlap:.2f}, threshold={point_offer_min})" if overlap >= point_offer_min
                       else f"FAIL: brief's `point` doesn't blend offer.md 'Why it is different' (Jaccard={overlap:.2f}, threshold={point_offer_min}). Lift at least one token from offer.md's 'Why it is different' section into `point`.",
        }
    else:
        # offer.md missing or no "Why it is different" section — skip the check
        results["point_blends_offer"] = {
            "pass": True,
            "message": "SKIP: offer.md 'Why it is different' not found; check skipped",
        }

    # Check 4: proof is ICP-grounded
    proof = brief.get("proof", "")
    found_banned = [w for w in banned if w and re.search(rf"\b{re.escape(w)}\b", proof, re.IGNORECASE)]
    found_marker = _has_icp_marker(proof, markers)
    if not found_banned and found_marker:
        results["proof_grounded"] = {
            "pass": True,
            "message": f"OK: proof is ICP-grounded (found marker: '{found_marker}')",
        }
    elif not found_marker and found_banned:
        results["proof_grounded"] = {
            "pass": False,
            "message": f"FAIL: proof contains build-log words ({', '.join(found_banned)}) AND no ICP-language marker. Use ICP-world proof from offer.md 'Proof' + session evidence.",
        }
    elif not found_marker:
        results["proof_grounded"] = {
            "pass": False,
            "message": f"FAIL: proof has no ICP-language marker. At least one of [{', '.join(markers[:5])}, ...] must appear. Use ICP-world proof, not build-log.",
        }
    else:
        results["proof_grounded"] = {
            "pass": False,
            "message": f"FAIL: proof contains build-log words ({', '.join(found_banned)}). Use ICP-world proof from offer.md 'Proof' + session evidence.",
        }

    # Check 5: example_pattern is set
    ep = (brief.get("example_pattern") or "").strip()
    results["example_pattern_present"] = {
        "pass": bool(ep),
        "message": f"OK: example_pattern is set ('{ep[:60]}')" if ep
                   else f"FAIL: `example_pattern` is missing in ## Strategy. The Strategist must pick an example from strategy/examples.md.",
    }

    all_pass = all(r.get("pass") for r in results.values())
    failed = [name for name, r in results.items() if not r.get("pass")]
    return {
        "pass": all_pass,
        "message": f"OK: all {len(results)} grounding checks passed" if all_pass
                   else f"FAIL: {len(failed)} grounding check(s) failed: {', '.join(failed)}",
        "checks": results,
    }


def cmd_check_brief(args, vault: Path) -> int:
    """Run grounding_check on the brief in content/current.md.

    Reads content/.icp-world.json (the simulator output) and validates
    that the brief in content/current.md is grounded in it. Both modes
    (session and topic) run the same 5 checks. Exits 0 on pass, 1 on
    fail, 3 on error.
    """
    rules = load_rules(vault)
    brief_path = vault / "content" / "current.md"
    if not brief_path.is_file():
        print("FAIL: content/current.md does not exist. Run `spiel post` first.", file=sys.stderr)
        return 3
    brief_md = brief_path.read_text(encoding="utf-8")

    # Load simulator output (both modes)
    icp_world: dict = {}
    icp_path = vault / "content" / ".icp-world.json"
    if icp_path.is_file():
        try:
            icp_world = json.loads(icp_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            print(f"FAIL: content/.icp-world.json is not valid JSON: {e}", file=sys.stderr)
            return 3

    result = check_grounding(vault, brief_md, icp_world, rules)
    passed = sum(1 for r in result["checks"].values() if r.get("pass"))
    failed = sum(1 for r in result["checks"].values() if not r.get("pass"))

    report = {
        "verdict": "pass" if result["pass"] else "fail",
        "summary": {"passed": passed, "failed": failed, "total": len(result["checks"])},
        "message": result["message"],
        "checks": result["checks"],
    }
    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        print(json.dumps(report, indent=2, ensure_ascii=False))
        print(f"\nverdict: {report['verdict']}  ({passed} pass, {failed} fail)", file=sys.stderr)
    return 0 if result["pass"] else 1


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

    check_brief = sub.add_parser("check-brief", help="Run grounding_check on the brief in content/current.md (5th gate)")
    check_brief.add_argument("--json", action="store_true", help="Pure JSON to stdout")
    check_brief.add_argument("--vault", help="Path to vault root (default: auto-detect)")

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

    if args.cmd == "check-brief":
        vault = Path(args.vault) if args.vault else find_vault()
        return cmd_check_brief(args, vault)

    return 0


if __name__ == "__main__":
    sys.exit(main())
