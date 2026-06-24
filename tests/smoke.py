"""tests/smoke.py — Smoke test for SpielOS.

No pytest required. Runs as `python3 tests/smoke.py` or `python3 -m pytest tests/`.

Verifies:
  1. State machine table is parseable
  2. Editor tool runs on a sample draft
  3. Wizard server starts and serves the index
  4. sync_adapters generates all 4 IDE outputs
  5. shim resolves the vault

Exit 0 on pass, non-zero on any failure.
"""

from __future__ import annotations

import json
import os
import re
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path


# ─── Paths ──────────────────────────────────────────────────────────────

TESTS = Path(__file__).resolve().parent
ROOT = TESTS.parent
sys.path.insert(0, str(ROOT))

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


# ─── Tests ─────────────────────────────────────────────────────────────

def test_state_machine() -> None:
    print("\n[1] State machine table")
    sm = (ROOT / "system" / "state-machine.md").read_text()
    # Must have the 10 states
    expected = [
        "IDLE", "SESSION_CAPTURE", "COMPILE", "SELECT",
        "DRAFTING", "BANNER", "GATE_CHECK", "PUBLISHING",
        "ANALYZING_POST", "COMPLETE_POST",
    ]
    for s in expected:
        check(f"state {s} present", f"| {s} " in sm or f"| {s} |" in sm or f" {s} " in sm)
    # Must have a role per state
    for s in expected:
        # The row for s must have a Role column entry
        for line in sm.splitlines():
            if line.strip().startswith("| " + s) or (s in line and line.strip().startswith("|")):
                # crude check: the line has 6+ pipes
                check(f"state {s} has transition row", line.count("|") >= 6, f"line: {line!r}")
                break


def test_team_files() -> None:
    print("\n[2] Team files present + valid frontmatter")
    team = ROOT / "team"
    expected_roles = ["md", "strategist", "researcher", "copywriter", "editor",
                      "designer", "publisher", "analyst"]
    for r in expected_roles:
        f = team / f"{r}.md"
        check(f"team/{r}.md exists", f.exists())
        if f.exists():
            text = f.read_text()
            check(f"team/{r}.md has frontmatter", text.startswith("---"))
            check(f"team/{r}.md has description", "description:" in text[:500])
            check(f"team/{r}.md has role_in_pipeline", "role_in_pipeline:" in text)
            check(f"team/{r}.md has hard rules", "## Hard rules" in text)


def test_editor_runs() -> None:
    print("\n[3] Editor (tools/editor.py)")
    # Build a sample draft in a tmp dir, copy the rules
    with tempfile.TemporaryDirectory() as tmp:
        tmp_vault = Path(tmp) / "vault"
        tmp_vault.mkdir()
        (tmp_vault / "team").mkdir()
        (tmp_vault / "system").mkdir()
        (tmp_vault / "system" / "prompts").mkdir()
        (tmp_vault / "strategy").mkdir()
        (tmp_vault / "templates").mkdir()
        (tmp_vault / "templates" / "registry").mkdir()
        (tmp_vault / "content").mkdir()
        (tmp_vault / "content" / "queue").mkdir()
        (tmp_vault / "content" / "posted").mkdir()
        (tmp_vault / "content" / "rejected").mkdir()
        (tmp_vault / "content" / "sessions").mkdir()
        (tmp_vault / "assets").mkdir()
        (tmp_vault / "assets" / "banners").mkdir()
        (tmp_vault / "assets" / "icons").mkdir()
        (tmp_vault / "logs").mkdir()
        (tmp_vault / "team" / "md.md").write_text("# md\n")
        (tmp_vault / "system" / "state-machine.md").write_text("# sm\n")
        # Copy rules
        import shutil
        shutil.copy(ROOT / "system" / "rules.yaml", tmp_vault / "system" / "rules.yaml")
        # Sample draft
        draft = tmp_vault / "content" / "queue" / "test.md"
        draft.write_text("""---
title: Test
created: 2026-06-22
tags: [S1, x]
platform: x
status: draft
pillar: none
pattern: confessional
icp: helps a founder ship
core_insight: build is content
axis: leverage
funnel: TOFU
voice_register: confessional-teaching
template_id: x-ship-01
sampled_from: corpus #1
engagement_ask: what did you ship?
---

I built the engine so you don't have to.

You can ship without the marketing job.

Lesson: the work is the content.

Note:
What did you ship this week?
""")
        env = os.environ.copy()
        env.pop("VAULT_DIR", None)
        # Run editor with --vault
        r = subprocess.run(
            [sys.executable, str(ROOT / "tools" / "editor.py"), "check", str(draft), "--vault", str(tmp_vault), "--json"],
            capture_output=True, text=True, env=env,
        )
        check("editor.py exits 0", r.returncode == 0, f"stderr: {r.stderr}")
        if r.returncode == 0:
            try:
                report = json.loads(r.stdout)
                check("editor.py returns JSON", True)
                check("editor.py has verdict", report.get("verdict") in ("pass", "fail", "warn"))
                check("editor.py runs 15 gates", report.get("summary", {}).get("total", 0) == 15,
                      f"got total={report.get('summary', {}).get('total')}")
            except Exception as e:
                check("editor.py returns valid JSON", False, str(e))


def test_wizard_server() -> None:
    print("\n[4] Wizard server (install/wizard/serve.py)")
    # Save and restore the global config so test doesn't corrupt the user's setup
    global_cfg = Path.home() / ".config" / "spielos" / "config"
    saved_cfg = global_cfg.read_text() if global_cfg.exists() else None
    with tempfile.TemporaryDirectory() as tmp:
        port = 19331
        proc = subprocess.Popen(
            [sys.executable, str(ROOT / "install" / "wizard" / "serve.py"),
             "--port", str(port), "--target", str(Path(tmp) / "vault"), "--no-open"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
        time.sleep(0.8)
        try:
            # Health
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/health", timeout=3) as r:
                data = json.loads(r.read())
                check("wizard /api/health responds 200", r.status == 200)
                check("wizard /api/health returns ok", data.get("ok") is True)
            # Index
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=3) as r:
                check("wizard / responds 200", r.status == 200)
                check("wizard / serves HTML", "SpielOS" in r.read().decode())
            # CSS
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/design-system.css", timeout=3) as r:
                check("wizard /design-system.css responds 200", r.status == 200)
            # JS
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/steps.js", timeout=3) as r:
                check("wizard /steps.js responds 200", r.status == 200)
            # Finish
            req = urllib.request.Request(
                f"http://127.0.0.1:{port}/api/finish",
                data=json.dumps({"brand_name": "Smoke", "handle": "@smoke", "tagline": "smoke test"}).encode(),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=5) as r:
                data = json.loads(r.read())
                check("wizard /api/finish returns 200", r.status == 200)
                check("wizard /api/finish writes files", len(data.get("written", [])) >= 10)
        finally:
            proc.terminate()
            proc.wait(timeout=3)
            # Restore global config
            if saved_cfg is not None:
                global_cfg.write_text(saved_cfg, encoding="utf-8")
            elif global_cfg.exists():
                global_cfg.unlink()


def test_sync_adapters() -> None:
    print("\n[5] sync_adapters.py")
    r = subprocess.run(
        [sys.executable, str(ROOT / "tools" / "sync_adapters.py")],
        capture_output=True, text=True,
    )
    check("sync_adapters.py exits 0", r.returncode == 0, f"stderr: {r.stderr}")
    # Check the adapters exist (v2: subagents + real skills, no auto-gen role stubs)
    for path in [
        "adapters/opencode/agents/md.md",
        "adapters/opencode/agents/copywriter.md",
        "adapters/claude/agents/md.md",
        "adapters/cursor/commands/md.md",
        "adapters/mcp/server.json",
        # v2: real skills in skills/<name>/SKILL.md (5 user skills, no role stubs)
        "skills/icp_simulation/SKILL.md",
        "skills/format_wizard/SKILL.md",
        "skills/publish_wizard/SKILL.md",
        "skills/voice_match/SKILL.md",
        "skills/template_picker/SKILL.md",
    ]:
        check(f"  {path} exists", (ROOT / path).exists())


def test_shim() -> None:
    print("\n[6] bin/spiel shim")
    env = os.environ.copy()
    env.pop("VAULT_DIR", None)
    env["VAULT_DIR"] = str(ROOT)  # override global config for test isolation
    # The shim is at <vault>/bin/spiel
    shim = ROOT / "bin" / "spiel"
    check("bin/spiel exists", shim.exists())
    check("bin/spiel is executable", os.access(shim, os.X_OK))
    r = subprocess.run([str(shim), "--where"], capture_output=True, text=True, env=env)
    check("bin/spiel --where exits 0", r.returncode == 0, f"stderr: {r.stderr}")
    if r.returncode == 0:
        check("bin/spiel --where returns the vault", r.stdout.strip() == str(ROOT),
              f"got {r.stdout.strip()!r}")


# ─── Runner ─────────────────────────────────────────────────────────────

def main() -> int:
    print(f"SpielOS smoke tests — vault: {ROOT}")
    test_state_machine()
    test_team_files()
    test_editor_runs()
    test_wizard_server()
    test_sync_adapters()
    test_shim()
    print(f"\n{PASS} passed, {FAIL} failed")
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
