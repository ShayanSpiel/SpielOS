"""tests/test_simulator.py — Tests for the ICP World Simulator script.

Covers:
  1. simulator show: prints the system prompt with injected context
  2. simulator write: validates and atomically writes content/.icp-world.json
  3. simulator write: rejects empty/malformed inputs
  4. simulator check: validates an existing file
  5. simulator read: prints the JSON to stdout
  6. Atomic write: no .tmp left behind

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
SIMULATOR = ROOT / "tools" / "simulator.py"

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
    """Create a fresh vault with all the files the simulator needs."""
    tmp = Path(tempfile.mkdtemp(prefix="spiel-sim-"))
    vault = tmp / "vault"
    vault.mkdir()
    # team/strategist.md as vault marker
    (vault / "team").mkdir()
    (vault / "team" / "strategist.md").write_text("# strategist\n")
    # strategy files
    (vault / "strategy").mkdir()
    (vault / "strategy" / "audience.md").write_text(
        "They are founders who ship. They want predictable attention. "
        "They are stuck because they keep posting more.\n\n"
        "They will pay attention when: real numbers and mechanics show how attention moves."
    )
    (vault / "strategy" / "offer.md").write_text(
        "A system for engineering attention.\n\n"
        "Why it is different:\nIt's systems, not posts.\n\n"
        "Proof:\n6-7 min average sessions. 300 visitors from a single placed post."
    )
    (vault / "strategy" / "voice.md").write_text("# Voice\n")
    (vault / "strategy" / "examples.md").write_text("# Examples\n")
    # system/ for the simulator prompt + rules
    import shutil
    (vault / "system").mkdir()
    (vault / "system" / "prompts").mkdir()
    shutil.copy(
        ROOT / "system" / "prompts" / "simulator.md",
        vault / "system" / "prompts" / "simulator.md",
    )
    shutil.copy(ROOT / "system" / "rules.yaml", vault / "system" / "rules.yaml")
    # content/ for the brief + icp world
    (vault / "content").mkdir()
    (vault / "content" / "sessions").mkdir()
    return vault


def run_simulator(args: list[str], vault: Path) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    env.pop("VAULT_DIR", None)
    env["VAULT_DIR"] = str(vault)
    cmd = [sys.executable, str(SIMULATOR)] + args + ["--vault", str(vault)]
    return subprocess.run(cmd, capture_output=True, text=True, env=env)


def write_world_args() -> list[str]:
    return [
        "write",
        "--reader", "A founder who keeps shipping but never sees attention. They are tired of generic growth advice.",
        "--belief", "More posts and more content will eventually produce predictable attention and growth.",
        "--pain", "They keep shipping more and posting more, but distribution stays flat because attention is treated as effort-output, not as a system to engineer.",
        "--point", "Distribution is engineered before launch. The right placement, not more output, drives attention. One post in the right wave beats ten posts in the void.",
        "--proof", "6-7 min average sessions",
        "--proof", "300 visitors from a single placed post",
        "--meaning", "The ICP walks away believing that placement beats more output, and that distribution is a system you engineer, not a result you wait for.",
        "--example-pattern", "Example 5 (contrarian: not more output but better placement)",
        "--axis", "systemic",
    ]


# ─── Tests ──────────────────────────────────────────────────────────────

def test_show() -> None:
    print("\n[1] simulator show: prints the system prompt with injected context")
    vault = fresh_vault()
    r = run_simulator(["show"], vault)
    check("show exits 0", r.returncode == 0, f"stderr: {r.stderr[:200]}")
    check("output mentions simulator", "SIMULATOR" in r.stdout.upper() or "simulator" in r.stdout.lower(),
          "missing SIMULATOR marker in output")
    check("output injects audience.md", "They are founders" in r.stdout or "founder" in r.stdout,
          "audience.md content not injected")
    check("output injects offer.md", "Why it is different" in r.stdout or "engineering attention" in r.stdout,
          "offer.md content not injected")


def test_write_pass() -> None:
    print("\n[2] simulator write: pass case")
    vault = fresh_vault()
    r = run_simulator(write_world_args(), vault)
    check("write exits 0", r.returncode == 0, f"stderr: {r.stderr[:300]}")
    out = vault / "content" / ".icp-world.json"
    check(".icp-world.json was created", out.is_file(), f"path: {out}")
    data = json.loads(out.read_text(encoding="utf-8"))
    check("reader field present", bool(data.get("reader")))
    check("belief field present", bool(data.get("belief")))
    check("pain field present", bool(data.get("pain")))
    check("point field present", bool(data.get("point")))
    check("proof field present", bool(data.get("proof")))
    check("meaning field present", bool(data.get("meaning")))
    check("example_pattern field present", bool(data.get("example_pattern")))
    check("axis field present", data.get("axis") == "systemic")


def test_write_atomic() -> None:
    print("\n[3] simulator write is atomic (no .tmp left behind)")
    vault = fresh_vault()
    r = run_simulator(write_world_args(), vault)
    check("write exits 0", r.returncode == 0, f"stderr: {r.stderr[:200]}")
    tmp_files = list((vault / "content").glob(".icp-world.json-*.tmp"))
    check("no .icp-world.json-*.tmp files left", len(tmp_files) == 0,
          f"found: {tmp_files}")


def test_write_missing_field() -> None:
    print("\n[4] simulator write: missing field rejected")
    vault = fresh_vault()
    args = write_world_args()
    # Pass an empty value for --meaning (CLI requires the flag, so we
    # simulate "missing" by passing an empty value).
    args[args.index("--meaning") + 1] = ""
    r = run_simulator(args, vault)
    check("write exits 1 on missing field", r.returncode == 1, f"stderr: {r.stderr[:200]}")
    check("no .icp-world.json written", not (vault / "content" / ".icp-world.json").is_file())


def test_write_empty_field() -> None:
    print("\n[5] simulator write: empty field rejected")
    vault = fresh_vault()
    args = write_world_args()
    args[args.index("--reader") + 1] = "  "
    r = run_simulator(args, vault)
    check("write exits 1 on empty reader", r.returncode == 1, f"stderr: {r.stderr[:200]}")


def test_check_pass() -> None:
    print("\n[6] simulator check: pass case")
    vault = fresh_vault()
    run_simulator(write_world_args(), vault)
    r = run_simulator(["check"], vault)
    check("check exits 0 on complete world", r.returncode == 0, f"stderr: {r.stderr[:200]}")
    check("OK message printed", "OK" in r.stdout)


def test_check_missing_file() -> None:
    print("\n[7] simulator check: missing file rejected")
    vault = fresh_vault()
    r = run_simulator(["check"], vault)
    check("check exits 1 on missing file", r.returncode == 1, f"stderr: {r.stderr[:200]}")


def test_read() -> None:
    print("\n[8] simulator read: prints the JSON to stdout")
    vault = fresh_vault()
    run_simulator(write_world_args(), vault)
    r = run_simulator(["read"], vault)
    check("read exits 0", r.returncode == 0, f"stderr: {r.stderr[:200]}")
    data = json.loads(r.stdout)
    check("output is valid JSON", isinstance(data, dict))
    check("JSON has reader", bool(data.get("reader")))


# ─── Runner ─────────────────────────────────────────────────────────────

def main() -> int:
    print(f"SpielOS simulator tests — script: {SIMULATOR}")
    test_show()
    test_write_pass()
    test_write_atomic()
    test_write_missing_field()
    test_write_empty_field()
    test_check_pass()
    test_check_missing_file()
    test_read()
    print(f"\n{PASS} passed, {FAIL} failed")
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
