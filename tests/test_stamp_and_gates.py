"""tests/test_stamp_and_gates.py — Tests for editor.py stamp + publisher gate check.

Runs as `python3 tests/test_stamp_and_gates.py` or `python3 -m pytest tests/`.

Verifies:
  1. editor.py stamp writes gates_verdict: pass on a good draft (exit 0)
  2. editor.py stamp writes gates_verdict: fail on a draft with em-dash (exit 1)
  3. stamp is atomic (the original file is replaced, no .tmp left behind)
  4. check_gates_verdict() in _common.py refuses fail verdicts
  5. check_gates_verdict() refuses drafts with no verdict
  6. check_gates_verdict() allows pass verdicts

Exit 0 on all-pass, non-zero on any failure.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path


TESTS = Path(__file__).resolve().parent
ROOT = TESTS.parent
EDITOR = ROOT / "tools" / "editor.py"

PASS = 0
FAIL = 0


def check(name: str, cond: bool, detail: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  ✓ {name}")
    else:
        FAIL += 1
        print(f"  ✗ {name}  {detail}")


def fresh_vault() -> Path:
    tmp = Path(tempfile.mkdtemp(prefix="spiel-stamp-"))
    vault = tmp / "vault"
    vault.mkdir()
    (vault / "team").mkdir()
    (vault / "team" / "strategist.md").write_text("# strategist\n")
    (vault / "system").mkdir()
    import shutil
    shutil.copy(ROOT / "system" / "rules.yaml", vault / "system" / "rules.yaml")
    (vault / "strategy").mkdir()
    (vault / "strategy" / "offer.md").write_text(
        "# Offer\n\n"
        "## Why it is different\n\n"
        "Distribution is engineered before launch. Placement beats more output.\n"
    )
    (vault / "content" / "drafts").mkdir(parents=True)
    return vault


def write_draft(vault: Path, *, em_dash: bool = False) -> Path:
    draft = vault / "content" / "drafts" / "test.md"
    body = "I shipped v2. Small files beat big code."
    if em_dash:
        body = "I shipped v2 — small files beat big code."
    draft.write_text(f"""---
title: Test
created: 2026-06-26
platform: x
status: draft
source: content/current.md
reader: founders
pain: big code hides the customer problem
belief: shipping more is the same as earning attention
point: small files beat big
meaning: smaller surfaces make the work easier to explain
proof: session showed one focused artifact was easier to place
angle: delete more
---

{body}
""")
    return draft


def run_editor(args: list[str], vault: Path) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    env.pop("VAULT_DIR", None)
    env["VAULT_DIR"] = str(vault)
    cmd = [sys.executable, str(EDITOR)] + args + ["--vault", str(vault)]
    return subprocess.run(cmd, capture_output=True, text=True, env=env)


def read_fm(path: Path) -> dict:
    import yaml
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---"):
        return {}
    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}
    return yaml.safe_load(parts[1]) or {}


# ─── Tests ──────────────────────────────────────────────────────────────

def test_stamp_pass() -> None:
    print("\n[1] editor.py stamp: pass case")
    vault = fresh_vault()
    draft = write_draft(vault, em_dash=False)
    r = run_editor(["stamp", str(draft)], vault)
    check("stamp exits 0 on pass", r.returncode == 0, f"stderr: {r.stderr}")
    fm = read_fm(draft)
    check("gates_verdict: pass", fm.get("gates_verdict") == "pass",
          f"got gates_verdict={fm.get('gates_verdict')!r}")
    check("gates_stamped_at present", "gates_stamped_at" in fm)
    check("gates_report present", "gates_report" in fm)
    report = fm.get("gates_report", {})
    check("gates_report has 4 gates", len(report) == 4, f"got {len(report)}")
    check("em_dash gate pass", report.get("em_dash", {}).get("pass") is True)


def test_stamp_fail() -> None:
    print("\n[2] editor.py stamp: fail case (em-dash)")
    vault = fresh_vault()
    draft = write_draft(vault, em_dash=True)
    r = run_editor(["stamp", str(draft)], vault)
    check("stamp exits 1 on fail", r.returncode == 1, f"stderr: {r.stderr}")
    fm = read_fm(draft)
    check("gates_verdict: fail", fm.get("gates_verdict") == "fail",
          f"got gates_verdict={fm.get('gates_verdict')!r}")
    report = fm.get("gates_report", {})
    check("em_dash gate fail", report.get("em_dash", {}).get("pass") is False)


def test_stamp_atomic() -> None:
    print("\n[3] editor.py stamp is atomic (no .tmp left behind)")
    vault = fresh_vault()
    draft = write_draft(vault, em_dash=False)
    r = run_editor(["stamp", str(draft)], vault)
    check("stamp exits 0", r.returncode == 0)
    tmp_files = list(draft.parent.glob(".stamp-*.tmp"))
    check("no .stamp-*.tmp files left", len(tmp_files) == 0,
          f"found: {tmp_files}")
    check("draft file still exists", draft.exists())


def test_check_gates_verdict_pass() -> None:
    print("\n[4] check_gates_verdict: pass verdict is allowed")
    vault = fresh_vault()
    draft = write_draft(vault, em_dash=False)
    run_editor(["stamp", str(draft)], vault)
    sys.path.insert(0, str(ROOT / "tools" / "publisher"))
    from _common import check_gates_verdict
    ok, msg = check_gates_verdict(draft)
    check("pass verdict returns ok=True", ok is True, f"msg: {msg}")
    check("pass verdict message mentions pass", "pass" in msg.lower())


def test_check_gates_verdict_fail() -> None:
    print("\n[5] check_gates_verdict: fail verdict is refused")
    vault = fresh_vault()
    draft = write_draft(vault, em_dash=True)
    run_editor(["stamp", str(draft)], vault)
    sys.path.insert(0, str(ROOT / "tools" / "publisher"))
    from _common import check_gates_verdict
    ok, msg = check_gates_verdict(draft)
    check("fail verdict returns ok=False", ok is False, f"msg: {msg}")
    check("fail verdict message mentions refusing", "refusing" in msg.lower() or "fail" in msg.lower())


def test_check_gates_verdict_missing() -> None:
    print("\n[6] check_gates_verdict: no verdict is refused")
    vault = fresh_vault()
    draft = write_draft(vault, em_dash=False)
    # Don't stamp; the draft has no gates_verdict
    sys.path.insert(0, str(ROOT / "tools" / "publisher"))
    from _common import check_gates_verdict
    ok, msg = check_gates_verdict(draft)
    check("missing verdict returns ok=False", ok is False, f"msg: {msg}")
    check("missing verdict message mentions stamp", "stamp" in msg.lower())


def test_check_gates_verdict_pending() -> None:
    print("\n[7] check_gates_verdict: non-pass verdict is refused")
    vault = fresh_vault()
    draft = write_draft(vault, em_dash=False)
    text = draft.read_text(encoding="utf-8")
    draft.write_text(text.replace("status: draft", "status: draft\ngates_verdict: pending"), encoding="utf-8")
    sys.path.insert(0, str(ROOT / "tools" / "publisher"))
    from _common import check_gates_verdict
    ok, msg = check_gates_verdict(draft)
    check("pending verdict returns ok=False", ok is False, f"msg: {msg}")
    check("pending verdict message requires pass", "pass" in msg.lower())


# ─── grounding_check tests (5th gate, on the brief) ─────────────────────

def write_brief(vault: Path, *, mode: str = "session", pain: str = "default", point: str = "default",
                meaning: str = "Builders learn that placement beats more output.",
                proof: str = '["sample proof with 6-7 min sessions"]',
                trace_axis: str = "systemic",
                example_pattern: str = "launch placement pattern") -> Path:
    brief = vault / "content" / "current.md"
    brief.parent.mkdir(parents=True, exist_ok=True)
    brief.write_text(f"""---
mode: {mode}
run_id: 2026-06-28-001
created_at: 2026-06-28T00:00:00
source: test
---

## Source

Test source.

## Strategy

reader: Test reader
pain: {pain}
point: {point}
proof: {proof}
meaning: {meaning}
angle: Test angle
belief: Shipping more is the same as earning attention
example_pattern: {example_pattern}
formats: ["x", "linkedin", "blog"]

## Trace

selected_axis: {trace_axis}
example_pattern: launch placement pattern
offer_lift: Placement beats more output
worldview_brief: Test worldview
failure_mode_brief: Distribution stays flat because attention is treated as effort-output.
meaning_synthesis: systemic and leverage
""")
    return brief


def write_icp_world(vault: Path, *, consequence: str = "default consequence", mapping: str = "default mapping") -> Path:
    p = vault / "content" / ".icp-world.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({
        "reader": "Test reader",
        "belief": "Shipping more is the same as earning attention",
        "pain": consequence,
        "point": mapping,
        "proof": ["session, 6-7 min, traffic"],
        "meaning": "Test meaning",
        "example_pattern": "launch placement pattern",
        "axis": "systemic",
        "created_at": "2026-06-28T00:00:00",
        "source": "content/current.md",
    }))
    return p


def run_editor_brief(args: list[str], vault: Path) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    env.pop("VAULT_DIR", None)
    env["VAULT_DIR"] = str(vault)
    cmd = [sys.executable, str(EDITOR)] + args + ["--vault", str(vault)]
    return subprocess.run(cmd, capture_output=True, text=True, env=env)


def test_grounding_pass_session() -> None:
    print("\n[7] grounding_check: pass case (session mode, brief traces to simulator)")
    vault = fresh_vault()
    write_icp_world(
        vault,
        consequence="Distribution stays flat despite consistent shipping because attention is treated as effort-output.",
        mapping="Distribution is engineered before launch. Placement beats more output.",
    )
    write_brief(
        vault,
        mode="session",
        pain="Distribution stays flat despite consistent shipping because attention is treated as effort-output.",
        point="Distribution is engineered before launch. Placement beats more output.",
        meaning="Test meaning",
    )
    r = run_editor_brief(["check-brief"], vault)
    check("grounding_check exits 0 on pass", r.returncode == 0, f"stderr: {r.stderr[:300]}")
    report = json.loads(r.stdout)
    check("verdict is pass", report.get("verdict") == "pass", f"got {report.get('verdict')}")


def test_grounding_fail_no_simulator() -> None:
    print("\n[8] grounding_check: fail case (no simulator output in session mode)")
    vault = fresh_vault()
    # No .icp-world.json, no session
    write_brief(vault, mode="session",
                pain="Distribution stays flat",
                point="Distribution is engineered before launch. Placement beats more output.",
                meaning="Test meaning")
    r = run_editor_brief(["check-brief"], vault)
    check("grounding_check exits 1 on missing simulator", r.returncode == 1, f"stderr: {r.stderr[:300]}")


def test_grounding_fail_missing_example_pattern() -> None:
    print("\n[9] grounding_check: fail case (missing example_pattern)")
    vault = fresh_vault()
    write_icp_world(
        vault,
        consequence="Distribution stays flat because attention is treated as effort-output not a system.",
        mapping="Distribution is engineered before launch. Placement beats more output.",
    )
    write_brief(
        vault,
        mode="session",
        pain="Distribution stays flat because attention is treated as effort-output not a system.",
        point="Distribution is engineered before launch. Placement beats more output.",
        meaning="Test meaning",
        example_pattern="",
    )
    r = run_editor_brief(["check-brief"], vault)
    check("grounding_check exits 1 on missing example_pattern", r.returncode == 1, f"stderr: {r.stderr[:300]}")


def test_grounding_fail_proof_has_build_log() -> None:
    print("\n[10] grounding_check: fail case (proof has build-log words, no ICP marker)")
    vault = fresh_vault()
    write_icp_world(vault)
    write_brief(
        vault,
        mode="session",
        pain="Distribution stays flat because attention is treated as effort-output not a system.",
        point="Distribution is engineered before launch. Placement beats more output.",
        meaning="Test meaning",
        proof='["6 source files edited, 73 tests pass, 22/22 doctor clean"]',
    )
    r = run_editor_brief(["check-brief"], vault)
    check("grounding_check exits 1 on build-log proof", r.returncode == 1, f"stderr: {r.stderr[:300]}")


def test_grounding_pass_topic_mode() -> None:
    print("\n[11] grounding_check: pass case (topic mode, simulator present, proof has ICP marker)")
    vault = fresh_vault()
    write_icp_world(
        vault,
        consequence="Founders keep posting more but distribution stays flat",
        mapping="Distribution is engineered before launch. Placement beats more output.",
    )
    write_brief(
        vault,
        mode="topic",
        pain="Founders keep posting more but distribution stays flat",
        point="Distribution is engineered before launch. Placement beats more output.",
        meaning="Builders learn that placement beats more output.",
        proof='["6-7 min average sessions, 300 visitors from a single placed post"]',
    )
    r = run_editor_brief(["check-brief"], vault)
    check("grounding_check exits 0 in topic mode", r.returncode == 0, f"stderr: {r.stderr[:300]}")


# ─── Runner ─────────────────────────────────────────────────────────────

def main() -> int:
    print(f"SpielOS stamp + gate tests — editor: {EDITOR}")
    test_stamp_pass()
    test_stamp_fail()
    test_stamp_atomic()
    test_check_gates_verdict_pass()
    test_check_gates_verdict_fail()
    test_check_gates_verdict_missing()
    test_check_gates_verdict_pending()
    test_grounding_pass_session()
    test_grounding_fail_no_simulator()
    test_grounding_fail_missing_example_pattern()
    test_grounding_fail_proof_has_build_log()
    test_grounding_pass_topic_mode()
    print(f"\n{PASS} passed, {FAIL} failed")
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
