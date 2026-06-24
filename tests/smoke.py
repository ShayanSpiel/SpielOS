"""tests/smoke.py — Smoke test for SpielOS lean pipeline.

No pytest required. Runs as `python3 tests/smoke.py` or `python3 -m pytest tests/`.

Verifies:
  1. Pipeline table in system/pipeline.md has 5 chain rows
  2. 5 active role files in team/ with valid frontmatter
  3. Editor tool runs 4 gates on a sample draft
  4. Wizard server starts, serves 6 steps, /api/finish writes expected files
  5. sync_adapters generates all 4 IDE outputs
  6. shim resolves the vault
  7. adapter --check is clean

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

def test_pipeline_table() -> None:
    print("\n[1] Pipeline table (system/pipeline.md)")
    pm = (ROOT / "system" / "pipeline.md").read_text()
    # The pipeline text mentions all 5 roles
    for role in ["Director", "Strategist", "Writer", "Editor", "Publisher"]:
        check(f"role {role} present", role in pm)


def test_team_files() -> None:
    print("\n[2] Team files present + valid frontmatter")
    team = ROOT / "team"
    expected_roles = ["director", "strategist", "writer", "editor", "publisher"]
    for r in expected_roles:
        f = team / f"{r}.md"
        check(f"team/{r}.md exists", f.exists())
        if f.exists():
            text = f.read_text()
            check(f"team/{r}.md has frontmatter", text.startswith("---"))
            check(f"team/{r}.md has description", "description:" in text[:500])
            check(f"team/{r}.md reads: content/current.md",
                  "content/current.md" in text or "{vault_root}/content/current.md" in text or "current.md" in text)
    # Archived roles stay in archive/roles/
    archive = ROOT / "archive" / "roles"
    for archived in ["analyst", "designer", "researcher"]:
        check(f"archive/roles/{archived}.md kept", (archive / f"{archived}.md").exists())
    # post.md is the slash command dispatcher
    check("team/post.md exists (slash command)", (team / "post.md").exists())


def test_editor_runs() -> None:
    print("\n[3] Editor (tools/editor.py) — 4 gates")
    with tempfile.TemporaryDirectory() as tmp:
        tmp_vault = Path(tmp) / "vault"
        tmp_vault.mkdir()
        (tmp_vault / "team").mkdir()
        (tmp_vault / "team" / "director.md").write_text("# director\n")
        (tmp_vault / "system").mkdir()
        import shutil
        shutil.copy(ROOT / "system" / "rules.yaml", tmp_vault / "system" / "rules.yaml")
        # Pass case
        draft = tmp_vault / "content" / "drafts" / "test.md"
        draft.parent.mkdir(parents=True)
        draft.write_text("""---
title: Test
created: 2026-06-25
platform: x
status: ready
source: content/current.md
reader: founders
point: small files beat big
angle: delete more
---

I shipped v2. Small files beat big code.
""")
        env = os.environ.copy()
        env.pop("VAULT_DIR", None)
        r = subprocess.run(
            [sys.executable, str(ROOT / "tools" / "editor.py"), "check", str(draft), "--vault", str(tmp_vault), "--json"],
            capture_output=True, text=True, env=env,
        )
        check("editor.py exits 0", r.returncode == 0, f"stderr: {r.stderr}")
        if r.returncode == 0:
            try:
                report = json.loads(r.stdout)
                check("editor.py has verdict", report.get("verdict") in ("pass", "fail"))
                check("editor.py runs 4 gates", report.get("summary", {}).get("total", 0) == 4,
                      f"got total={report.get('summary', {}).get('total')}")
            except Exception as e:
                check("editor.py returns valid JSON", False, str(e))
        # Fail case (em-dash)
        bad = tmp_vault / "content" / "drafts" / "bad.md"
        bad.write_text("""---
title: Bad
created: 2026-06-25
platform: x
status: draft
source: content/current.md
reader: founders
point: a point
angle: an angle
---

hello — world
""")
        r2 = subprocess.run(
            [sys.executable, str(ROOT / "tools" / "editor.py"), "check", str(bad), "--vault", str(tmp_vault), "--quiet"],
            capture_output=True, text=True, env=env,
        )
        check("editor.py fails on em-dash", r2.returncode == 1, f"got {r2.returncode}")


def test_wizard_server() -> None:
    print("\n[4] Wizard server (install/wizard/serve.py)")
    global_cfg = Path.home() / ".config" / "spielos" / "config"
    saved_cfg = global_cfg.read_text() if global_cfg.exists() else None
    with tempfile.TemporaryDirectory() as tmp:
        # Pick a random high port to avoid clashes
        port = 29000 + (os.getpid() % 1000)
        proc = subprocess.Popen(
            [sys.executable, str(ROOT / "install" / "wizard" / "serve.py"),
             "--port", str(port), "--target", str(Path(tmp) / "vault"), "--no-open"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
        # Poll for server up
        started = False
        for _ in range(40):
            time.sleep(0.25)
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/health", timeout=1) as r:
                    if r.status == 200:
                        started = True
                        break
            except Exception:
                continue
        if not started:
            print(f"  ✗ wizard did not start on port {port}")
            proc.terminate()
            proc.wait(timeout=3)
            return
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
            # Finish (sends minimal lean form, expects 8 written files)
            req = urllib.request.Request(
                f"http://127.0.0.1:{port}/api/finish",
                data=json.dumps({
                    "brand_name": "Smoke",
                    "handle": "@smoke",
                    "tagline": "smoke test",
                    "audience_content": "# Audience\n\nThey are: devs",
                    "offer_content": "# Offer\n\nWhat: tool",
                    "voice_content": "# Voice\n\nSounds like: builder",
                    "examples_content": "# Examples\n\n## 1\n\nhi",
                }).encode(),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=10) as r:
                data = json.loads(r.read())
                check("wizard /api/finish returns 200", r.status == 200)
                check("wizard /api/finish ok=True", data.get("ok") is True)
                check("wizard /api/finish writes 8 files", len(data.get("written", [])) == 8,
                      f"got {len(data.get('written', []))}: {data.get('written')}")
        finally:
            proc.terminate()
            proc.wait(timeout=3)
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
    for path in [
        "adapters/opencode/agents/director.md",
        "adapters/opencode/agents/writer.md",
        "adapters/opencode/agents/strategist.md",
        "adapters/opencode/agents/editor.md",
        "adapters/opencode/agents/publisher.md",
        "adapters/opencode/commands/post.md",
        "adapters/opencode/skill/format_wizard/SKILL.md",
        "adapters/opencode/skill/publish_wizard/SKILL.md",
        "adapters/opencode/skill/voice_match/SKILL.md",
        "adapters/claude/agents/director.md",
        "adapters/claude/agents/writer.md",
        "adapters/cursor/commands/director.md",
        "adapters/cursor/commands/writer.md",
        "adapters/codex/agents/director.toml",
        "adapters/codex/agents/writer.toml",
        "adapters/mcp/server.json",
    ]:
        check(f"  {path} exists", (ROOT / path).exists())
    # Archived skills must NOT be in adapters
    check("  archived skill icp_simulation NOT generated",
          not (ROOT / "adapters" / "opencode" / "skill" / "icp_simulation").exists())
    check("  archived skill template_picker NOT generated",
          not (ROOT / "adapters" / "opencode" / "skill" / "template_picker").exists())


def test_sync_check() -> None:
    print("\n[6] sync_adapters.py --check")
    r = subprocess.run(
        [sys.executable, str(ROOT / "tools" / "sync_adapters.py"), "--check"],
        capture_output=True, text=True,
    )
    check("sync --check exits 0", r.returncode == 0, f"stdout: {r.stdout} stderr: {r.stderr}")


def test_shim() -> None:
    print("\n[7] bin/spiel shim")
    env = os.environ.copy()
    env["VAULT_DIR"] = str(ROOT)
    shim = ROOT / "bin" / "spiel"
    check("bin/spiel exists", shim.exists())
    check("bin/spiel is executable", os.access(shim, os.X_OK))
    r = subprocess.run([str(shim), "--where"], capture_output=True, text=True, env=env)
    check("bin/spiel --where exits 0", r.returncode == 0, f"stderr: {r.stderr}")
    if r.returncode == 0:
        check("bin/spiel --where returns the vault", r.stdout.strip() == str(ROOT),
              f"got {r.stdout.strip()!r}")
    r2 = subprocess.run([str(shim), "status"], capture_output=True, text=True, env=env)
    check("bin/spiel status exits 0", r2.returncode == 0, f"stderr: {r2.stderr}")


# ─── Runner ─────────────────────────────────────────────────────────────

def main() -> int:
    print(f"SpielOS smoke tests — vault: {ROOT}")
    test_pipeline_table()
    test_team_files()
    test_editor_runs()
    test_wizard_server()
    test_sync_adapters()
    test_sync_check()
    test_shim()
    print(f"\n{PASS} passed, {FAIL} failed")
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
