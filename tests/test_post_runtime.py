"""Tests for deterministic tools/post.py runtime."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
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
    tmp = Path(tempfile.mkdtemp(prefix="spiel-post-"))
    vault = tmp / "vault"
    vault.mkdir()
    (vault / "team").mkdir()
    (vault / "team" / "strategist.md").write_text("# strategist\n", encoding="utf-8")
    (vault / "tools").mkdir()
    for name in ("_vault.py", "advance.py", "capture-session.py", "guard.py", "post.py"):
        shutil.copy(ROOT / "tools" / name, vault / "tools" / name)
    return vault


def run_post(vault: Path, args: list[str]) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    env.pop("VAULT_DIR", None)
    return subprocess.run(
        [sys.executable, str(vault / "tools" / "post.py"), *args, "--vault", str(vault), "--json"],
        cwd=vault,
        env=env,
        text=True,
        capture_output=True,
    )


def read_state(vault: Path) -> dict:
    return json.loads((vault / "content" / ".state.json").read_text(encoding="utf-8"))


def test_topic_post_starts_strategy_step() -> None:
    vault = fresh_vault()
    result = run_post(vault, ["Just shipped deterministic post runtime"])
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["ok"] is True
    assert payload["mode"] == "topic"
    assert payload["step"] == "strategy"

    state = read_state(vault)
    assert state["step"] == "strategy"
    assert state["mode"] == "topic"
    assert [h["to"] for h in state["history"]] == ["capture", "strategy"]

    current = (vault / "content" / "current.md").read_text(encoding="utf-8")
    assert "mode: topic" in current
    assert "Just shipped deterministic post runtime" in current

    events = vault / payload["events"]
    rows = [json.loads(line) for line in events.read_text(encoding="utf-8").splitlines()]
    assert [r["event"] for r in rows] == [
        "run_started",
        "artifact_written",
        "step_completed",
        "step_started",
    ]


def test_session_post_captures_session_log() -> None:
    vault = fresh_vault()
    structured = vault / "structured.json"
    structured.write_text(
        json.dumps(
            {
                "decision": "Move orchestration into Python",
                "number": "1 runtime entrypoint",
                "lesson": "Prompts should not own state",
                "pattern": "IDE adapters drift",
                "ship": "tools/post.py",
                "summary": "Stabilized the post runtime",
                "tags": ["runtime"],
                "patterns": ["IDE adapters drift when they own orchestration"],
                "decisions": ["Move orchestration into Python"],
                "what_we_did": ["Added deterministic post runtime"],
                "shipped": ["tools/post.py"],
                "numbers": ["1 runtime entrypoint"],
                "lesson_section": ["Prompts should not own state"],
            }
        ),
        encoding="utf-8",
    )
    transcript = vault / "transcript.md"
    transcript.write_text("User: stabilize the foundation\n\nAssistant: implemented runtime\n", encoding="utf-8")

    result = run_post(
        vault,
        [
            "--mode",
            "session",
            "--transcript-file",
            str(transcript),
            "--structured-json",
            str(structured),
            "--title",
            "Runtime stabilization",
        ],
    )
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["mode"] == "session"

    state = read_state(vault)
    assert state["step"] == "strategy"
    assert state["mode"] == "session"
    assert state["session"].startswith("content/sessions/")

    session_path = vault / state["session"]
    session_text = session_path.read_text(encoding="utf-8")
    assert "Move orchestration into Python" in session_text
    assert "## Transcript" in session_text


def test_post_allows_untracked_drafts_after_reset() -> None:
    vault = fresh_vault()
    drafts = vault / "content" / "drafts"
    drafts.mkdir(parents=True)
    (drafts / "manual.md").write_text("manual bypass\n", encoding="utf-8")
    result = run_post(vault, ["A topic"])
    assert result.returncode == 0, result.stderr
    state = read_state(vault)
    assert state["step"] == "strategy"


def main() -> int:
    print(f"SpielOS post runtime tests — vault source: {ROOT}")
    tests = [
        ("topic post starts strategy step", test_topic_post_starts_strategy_step),
        ("session post captures session log", test_session_post_captures_session_log),
        ("post allows untracked drafts after reset", test_post_allows_untracked_drafts_after_reset),
    ]
    for name, fn in tests:
        try:
            fn()
            check(name, True)
        except Exception as e:
            check(name, False, str(e))
    print(f"\n{PASS} passed, {FAIL} failed")
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
