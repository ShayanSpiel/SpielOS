"""Focused regressions for production-readiness reliability fixes."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import stat
import tomllib
from pathlib import Path


TESTS = Path(__file__).resolve().parent
ROOT = TESTS.parent

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


def make_vault(base: Path, name: str) -> Path:
    vault = base / name
    (vault / "team").mkdir(parents=True)
    (vault / "team" / "strategist.md").write_text("# strategist\n", encoding="utf-8")
    return vault


def test_python_vault_env_precedence() -> None:
    print("\n[1] tools/_vault.py prefers VAULT_DIR over global config")
    base = Path(tempfile.mkdtemp(prefix="spiel-vault-precedence-"))
    env_vault = make_vault(base, "env-vault")
    global_vault = make_vault(base, "global-vault")
    home = base / "home"
    cfg = home / ".config" / "spielos" / "config"
    cfg.parent.mkdir(parents=True)
    cfg.write_text(f"VAULT_DIR={global_vault}\n", encoding="utf-8")
    code = (
        "import sys;"
        f"sys.path.insert(0, {str(ROOT / 'tools')!r});"
        "from _vault import resolve_vault;"
        "print(resolve_vault())"
    )
    env = os.environ.copy()
    env["HOME"] = str(home)
    env["VAULT_DIR"] = str(env_vault)
    r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, env=env)
    check("resolver exits 0", r.returncode == 0, r.stderr)
    check("VAULT_DIR wins", Path(r.stdout.strip()).resolve() == env_vault.resolve(), f"stdout={r.stdout!r}")


def test_claude_empty_hooks_preserve_user_hooks() -> None:
    print("\n[2] empty Claude hook stub preserves user hooks")
    code = (
        "import json, sys;"
        f"sys.path.insert(0, {str(ROOT / 'tools')!r});"
        "import sync_adapters as s;"
        "existing={'hooks': {'UserPromptSubmit': {'command': 'user-hook'}}, 'env': {'KEEP': '1'}};"
        "incoming={};"
        "merged=s._deep_merge_hooks(existing.get('hooks', {}), incoming);"
        "print(json.dumps({'hooks': merged, 'env': existing['env']}, sort_keys=True))"
    )
    r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    data = json.loads(r.stdout)
    check("user hook preserved", data["hooks"]["UserPromptSubmit"]["command"] == "user-hook")
    check("env preserved", data["env"]["KEEP"] == "1")


def test_blog_h1_strip_keeps_first_paragraph() -> None:
    print("\n[3] blog H1 stripping keeps first paragraph")
    script = ROOT / "tools" / "publisher" / "blog.sh"
    text = script.read_text(encoding="utf-8")
    check("duplicate H1 deletion removed", "del lines[0]" not in text)
    check("commit message has no em dash", "— pillar blog" not in text)


def test_publisher_rejects_non_pass_verdict() -> None:
    print("\n[4] publisher rejects non-pass gate verdict")
    sys.path.insert(0, str(ROOT / "tools" / "publisher"))
    from _common import check_gates_verdict
    base = Path(tempfile.mkdtemp(prefix="spiel-publisher-verdict-"))
    draft = base / "draft.md"
    draft.write_text("---\ngates_verdict: pending\n---\n\nbody\n", encoding="utf-8")
    ok, msg = check_gates_verdict(draft)
    check("pending refused", ok is False, msg)
    check("message mentions pass", "pass" in msg.lower(), msg)


def test_codex_hook_session_contract_matches_post_agent() -> None:
    print("\n[5] Codex hook session recipe matches post agent contract")
    base = Path(tempfile.mkdtemp(prefix="spiel-codex-hook-"))
    vault = make_vault(base, "vault")
    (vault / "bin").mkdir()
    shim = vault / "bin" / "spiel"
    shim.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
    shim.chmod(shim.stat().st_mode | stat.S_IXUSR)
    r = subprocess.run(
        [sys.executable, str(ROOT / "tools" / "codex_hook.py"), "--vault", str(vault)],
        input="@post\n",
        capture_output=True,
        text=True,
    )
    check("hook exits 0", r.returncode == 0, r.stderr)
    check("uses /tmp/spiel-capture.md", "/tmp/spiel-capture.md" in r.stdout, r.stdout)
    check("uses /tmp/spiel-capture.json", "/tmp/spiel-capture.json" in r.stdout, r.stdout)
    check("points back to canonical post command", "canonical team/post.md" in r.stdout, r.stdout)
    check("does not mention stale session temp names", "spiel-session" not in r.stdout, r.stdout)
    check("does not instruct spiel continue", "spiel continue" not in r.stdout, r.stdout)


def test_codex_hook_missing_vault_shows_setup_cta() -> None:
    print("\n[6] Codex hook without vault shows setup CTA")
    base = Path(tempfile.mkdtemp(prefix="spiel-codex-no-vault-"))
    env = os.environ.copy()
    env.pop("VAULT_DIR", None)
    env["HOME"] = str(base / "home")
    r = subprocess.run(
        [sys.executable, str(ROOT / "tools" / "codex_hook.py"), "--vault", "/definitely/not/a/spielos/vault"],
        input="@post\n",
        cwd=base,
        env=env,
        capture_output=True,
        text=True,
    )
    check("hook exits 0", r.returncode == 0, r.stderr)
    check("mentions setup", "Set up SpielOS" in r.stdout, r.stdout)
    check("mentions default vault", "~/SpielOS" in r.stdout, r.stdout)
    check("does not start post", "post run started" not in r.stdout, r.stdout)


def test_codex_post_is_thin_wrapper() -> None:
    print("\n[7] Codex post is generated as a thin wrapper")
    post_toml = (ROOT / "adapters" / "codex" / "agents" / "post.toml").read_text(encoding="utf-8")
    post_data = tomllib.loads(post_toml)
    instructions = post_data.get("developer_instructions", "")
    plugin = json.loads((ROOT / "plugins" / "spielos" / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8"))
    setup_skill = ROOT / "plugins" / "spielos" / "skills" / "spiel-setup" / "SKILL.md"
    check("post.toml parses", post_data.get("name") == "post")
    check("post.toml is thin wrapper", "thin adapter" in instructions, instructions)
    check("post.toml embeds canonical post command", "--- canonical team/post.md ---" in instructions, instructions)
    check("post.toml has no separate orchestration loop", "Codex Orchestration Loop" not in instructions, instructions)
    check("post.toml points to canonical team/post.md", "team/post.md" in instructions)
    check("post.toml has no temp vault path",
          "/private/tmp" not in post_toml and "/var/folders" not in post_toml,
          post_toml)
    check("Codex plugin manifest does not expose skills", "skills" not in plugin)
    check("Codex plugin setup skill exists", setup_skill.is_file())
    check("Codex plugin duplicated post skill is absent",
          not (ROOT / "plugins" / "spielos" / "skills" / "spiel-post" / "SKILL.md").exists())
    check("default prompt leads with setup",
          plugin.get("interface", {}).get("defaultPrompt", [""])[0].startswith("Set up SpielOS"),
          str(plugin.get("interface", {}).get("defaultPrompt")))


def main() -> int:
    print("SpielOS reliability regression tests")
    test_python_vault_env_precedence()
    test_claude_empty_hooks_preserve_user_hooks()
    test_blog_h1_strip_keeps_first_paragraph()
    test_publisher_rejects_non_pass_verdict()
    test_codex_hook_session_contract_matches_post_agent()
    test_codex_hook_missing_vault_shows_setup_cta()
    test_codex_post_is_thin_wrapper()
    print(f"\n{PASS} passed, {FAIL} failed")
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
