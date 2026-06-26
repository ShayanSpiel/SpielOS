"""tests/test_advance.py — Tests for tools/advance.py state machine.

Runs as `python3 tests/test_advance.py` or `python3 -m pytest tests/`.

Verifies:
  1. --init creates a fresh state file
  2. The full happy-path chain: idle → capture → director → strategy → draft → edit → publish → complete → idle
  3. Invalid transitions are rejected (exit code 2)
  4. --set-error sets the error state with a message
  5. --recover-from can jump back from error
  6. --reset deletes the state file
  7. --add-draft and --add-ready append to the state
  8. --show displays the current state
  9. History is appended on every transition
  10. The full content pipeline flow: capture session → init state → advance through all 5 roles

Exit 0 on all-pass, non-zero on any failure.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path


# ─── Paths ──────────────────────────────────────────────────────────────

TESTS = Path(__file__).resolve().parent
ROOT = TESTS.parent
ADVANCE = ROOT / "tools" / "advance.py"

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


def fresh_vault() -> tuple[Path, str]:
    """Create a fresh temp vault. Returns (vault_path, env_var_value)."""
    tmp = Path(tempfile.mkdtemp(prefix="spiel-test-"))
    vault = tmp / "vault"
    vault.mkdir()
    (vault / "team").mkdir()
    (vault / "team" / "director.md").write_text("# director\n")
    (vault / "content").mkdir()
    (vault / "content" / "sessions").mkdir()
    (vault / "content" / "drafts").mkdir()
    (vault / "content" / "ready").mkdir()
    (vault / "content" / "posted").mkdir()
    (vault / "content" / "rejected").mkdir()
    return vault, str(vault)


def run(args: list[str], vault: Path, expect: int | None = None) -> subprocess.CompletedProcess:
    """Run advance.py against the given vault. Optionally assert return code."""
    env = os.environ.copy()
    env.pop("VAULT_DIR", None)
    env["VAULT_DIR"] = str(vault)
    cmd = [sys.executable, str(ADVANCE)] + args + ["--vault", str(vault)]
    r = subprocess.run(cmd, capture_output=True, text=True, env=env)
    if expect is not None and r.returncode != expect:
        print(f"    CMD: {' '.join(cmd)}")
        print(f"    STDOUT: {r.stdout}")
        print(f"    STDERR: {r.stderr}")
    return r


def read_state(vault: Path) -> dict | None:
    p = vault / "content" / ".state.json"
    if not p.exists():
        return None
    return json.loads(p.read_text(encoding="utf-8"))


# ─── Tests ──────────────────────────────────────────────────────────────

def test_init_creates_state_file() -> None:
    print("\n[1] --init creates a fresh state file")
    vault, _ = fresh_vault()
    r = run(["--init", "--run-id", "2026-06-26-001", "--mode", "session"], vault, expect=0)
    state = read_state(vault)
    check("state file exists", state is not None)
    if state:
        check("run_id is 2026-06-26-001", state.get("run_id") == "2026-06-26-001")
        check("mode is session", state.get("mode") == "session")
        check("step is idle", state.get("step") == "idle")
        check("status is routing", state.get("status") == "routing")
        check("error is null", state.get("error") is None)
        check("history is empty list", state.get("history") == [])


def test_full_happy_path() -> None:
    print("\n[2] Full happy-path chain (8 transitions)")
    vault, _ = fresh_vault()
    run(["--init", "--run-id", "2026-06-26-001", "--mode", "session"], vault)
    chain = [
        ("capture", "post"),
        ("director", "post"),
        ("strategy", "director"),
        ("draft", "strategist"),
        ("edit", "writer"),
        ("publish", "editor"),
        ("complete", "publisher"),
    ]
    for i, (to_step, by) in enumerate(chain):
        r = run(["--to", to_step, "--by", by], vault, expect=0)
        check(f"  transition {i+1}/{len(chain)}: -> {to_step} (rc=0)", r.returncode == 0,
              f"stderr: {r.stderr}")
    state = read_state(vault)
    if state:
        check("final step is complete", state.get("step") == "complete")
        check("final status is shipped", state.get("status") == "shipped")
        check("history has 7 entries", len(state.get("history", [])) == 7,
              f"got {len(state.get('history', []))}")
    # back to idle
    r = run(["--to", "idle", "--by", "agent"], vault, expect=0)
    check("complete -> idle (rc=0)", r.returncode == 0)


def test_invalid_transitions() -> None:
    print("\n[3] Invalid transitions are rejected (exit 2)")
    vault, _ = fresh_vault()
    run(["--init", "--run-id", "2026-06-26-001", "--mode", "topic"], vault)
    # idle -> publish is NOT allowed
    r = run(["--to", "publish", "--by", "agent"], vault, expect=2)
    check("idle -> publish rejected (rc=2)", r.returncode == 2)
    # idle -> director is NOT allowed (must go via capture)
    r = run(["--to", "director", "--by", "agent"], vault, expect=2)
    check("idle -> director rejected (rc=2)", r.returncode == 2)
    # advance to capture, then try strategy (must go via director)
    run(["--to", "capture", "--by", "post"], vault, expect=0)
    r = run(["--to", "strategy", "--by", "agent"], vault, expect=2)
    check("capture -> strategy rejected (rc=2)", r.returncode == 2)


def test_set_error() -> None:
    print("\n[4] --set-error sets the error state")
    vault, _ = fresh_vault()
    run(["--init", "--run-id", "2026-06-26-001", "--mode", "session"], vault)
    run(["--to", "capture", "--by", "post"], vault)
    run(["--to", "director", "--by", "post"], vault)
    r = run(["--set-error", "test error message", "--by", "director"], vault, expect=0)
    check("--set-error exit 0", r.returncode == 0)
    state = read_state(vault)
    if state:
        check("step is error", state.get("step") == "error")
        check("status is failed", state.get("status") == "failed")
        check("error message saved", state.get("error") == "test error message")


def test_recover_from_error() -> None:
    print("\n[5] --recover-from jumps back from error")
    vault, _ = fresh_vault()
    run(["--init", "--run-id", "2026-06-26-001", "--mode", "session"], vault)
    run(["--to", "capture", "--by", "post"], vault)
    run(["--to", "director", "--by", "post"], vault)
    run(["--set-error", "boom", "--by", "director"], vault)
    r = run(["--recover-from", "director", "--by", "user"], vault, expect=0)
    check("--recover-from director (rc=0)", r.returncode == 0)
    state = read_state(vault)
    if state:
        check("step recovered to director", state.get("step") == "director")
        check("error cleared", state.get("error") is None)
        check("status is active", state.get("status") == "active")


def test_reset() -> None:
    print("\n[6] --reset deletes the state file")
    vault, _ = fresh_vault()
    run(["--init", "--run-id", "2026-06-26-001", "--mode", "session"], vault)
    check("state file exists before reset", (vault / "content" / ".state.json").exists())
    r = run(["--reset"], vault, expect=0)
    check("--reset exit 0", r.returncode == 0)
    check("state file deleted", not (vault / "content" / ".state.json").exists())


def test_add_draft_and_ready() -> None:
    print("\n[7] --add-draft and --add-ready append to state")
    vault, _ = fresh_vault()
    run(["--init", "--run-id", "2026-06-26-001", "--mode", "topic"], vault)
    run(["--to", "capture", "--by", "post"], vault)
    run(["--to", "director", "--by", "post"], vault)
    run(["--to", "strategy", "--by", "director"], vault)
    run(["--to", "draft", "--by", "strategist", "--add-draft", "content/drafts/2026-06-26-x-foo.md"], vault, expect=0)
    state = read_state(vault)
    if state:
        check("drafts has 1 entry", len(state.get("drafts", [])) == 1)
        check("drafts[0] is correct", state.get("drafts", [""])[0] == "content/drafts/2026-06-26-x-foo.md")
    run(["--to", "edit", "--by", "writer"], vault)
    run(["--to", "publish", "--by", "editor", "--add-ready", "content/ready/2026-06-26-x-foo.md"], vault, expect=0)
    state = read_state(vault)
    if state:
        check("ready has 1 entry", len(state.get("ready", [])) == 1)
        check("ready[0] is correct", state.get("ready", [""])[0] == "content/ready/2026-06-26-x-foo.md")


def test_show_displays_state() -> None:
    print("\n[8] --show displays the current state")
    vault, _ = fresh_vault()
    # no state yet
    r = run(["--show"], vault, expect=0)
    check("--show with no state exits 0", r.returncode == 0)
    check("--show prints 'no active run'", "no active run" in r.stdout,
          f"got: {r.stdout!r}")
    # init + advance
    run(["--init", "--run-id", "2026-06-26-001", "--mode", "session"], vault)
    run(["--to", "capture", "--by", "post"], vault)
    r = run(["--show", "--json"], vault, expect=0)
    try:
        data = json.loads(r.stdout)
        check("--show --json returns valid JSON", True)
        check("--show --json has step=capture", data.get("step") == "capture")
    except json.JSONDecodeError as e:
        check("--show --json returns valid JSON", False, str(e))


def test_history_appended() -> None:
    print("\n[9] history is appended on every transition")
    vault, _ = fresh_vault()
    run(["--init", "--run-id", "2026-06-26-001", "--mode", "session"], vault)
    run(["--to", "capture", "--by", "post"], vault)
    run(["--to", "director", "--by", "post"], vault)
    run(["--set-error", "oops", "--by", "director"], vault)
    state = read_state(vault)
    history = state.get("history", []) if state else []
    check("history has 3 entries", len(history) == 3, f"got {len(history)}")
    if len(history) >= 3:
        check("history[0]: idle -> capture", history[0].get("from") == "idle" and history[0].get("to") == "capture")
        check("history[1]: capture -> director", history[1].get("from") == "capture" and history[1].get("to") == "director")
        check("history[2]: director -> error", history[2].get("from") == "director" and history[2].get("to") == "error")
        check("history has timestamps", all("at" in h for h in history))
        check("history has by-agents", all("by" in h for h in history))


def test_full_pipeline_simulation() -> None:
    print("\n[10] End-to-end pipeline simulation (capture -> complete)")
    vault, _ = fresh_vault()
    # Simulate /post: init state, advance through capture + director
    run(["--init", "--run-id", "2026-06-26-001", "--mode", "session",
         "--session", "content/sessions/2026-06-26-session-current.md"], vault)
    check("/post init (rc=0)", read_state(vault) is not None)
    run(["--to", "capture", "--by", "post"], vault)
    run(["--to", "director", "--by", "post"], vault)
    # Director's turn
    run(["--to", "strategy", "--by", "director"], vault)
    # Strategist's turn
    r = run(["--to", "draft", "--by", "strategist",
             "--add-draft", "content/drafts/2026-06-26-x-foo.md",
             "--add-draft", "content/drafts/2026-06-26-linkedin-foo.md"], vault, expect=0)
    check("Writer adds 2 drafts (rc=0)", r.returncode == 0)
    # Writer's turn
    run(["--to", "edit", "--by", "writer"], vault)
    # Editor's turn: stamp + add-ready
    run(["--to", "publish", "--by", "editor",
         "--add-ready", "content/ready/2026-06-26-x-foo.md"], vault, expect=0)
    # Publisher's turn
    r = run(["--to", "complete", "--by", "publisher"], vault, expect=0)
    check("Publisher -> complete (rc=0)", r.returncode == 0)
    state = read_state(vault)
    if state:
        check("final state is shipped", state.get("status") == "shipped")
        check("drafts list has 2", len(state.get("drafts", [])) == 2)
        check("ready list has 1", len(state.get("ready", [])) == 1)
        check("history has 7 entries", len(state.get("history", [])) == 7)
    # Reset
    r = run(["--reset"], vault, expect=0)
    check("post-pipeline reset (rc=0)", r.returncode == 0)


# ─── Runner ─────────────────────────────────────────────────────────────

def main() -> int:
    print(f"SpielOS advance.py tests — advance: {ADVANCE}")
    test_init_creates_state_file()
    test_full_happy_path()
    test_invalid_transitions()
    test_set_error()
    test_recover_from_error()
    test_reset()
    test_add_draft_and_ready()
    test_show_displays_state()
    test_history_appended()
    test_full_pipeline_simulation()
    print(f"\n{PASS} passed, {FAIL} failed")
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
