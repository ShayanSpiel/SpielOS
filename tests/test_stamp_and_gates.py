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
    (vault / "team" / "director.md").write_text("# director\n")
    (vault / "system").mkdir()
    import shutil
    shutil.copy(ROOT / "system" / "rules.yaml", vault / "system" / "rules.yaml")
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
point: small files beat big
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


# ─── Runner ─────────────────────────────────────────────────────────────

def main() -> int:
    print(f"SpielOS stamp + gate tests — editor: {EDITOR}")
    test_stamp_pass()
    test_stamp_fail()
    test_stamp_atomic()
    test_check_gates_verdict_pass()
    test_check_gates_verdict_fail()
    test_check_gates_verdict_missing()
    print(f"\n{PASS} passed, {FAIL} failed")
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
