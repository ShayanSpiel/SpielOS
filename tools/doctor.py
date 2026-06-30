#!/usr/bin/env python3
"""SpielOS install/runtime diagnostics."""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _vault import resolve_vault  # noqa: E402


CHECKS = [
    ("vault", "Vault resolves and has team/strategist.md"),
    ("post_tool", "tools/post.py exists"),
    ("advance_tool", "tools/advance.py exists"),
    ("capture_tool", "tools/capture-session.py exists"),
    ("editor_tool", "tools/editor.py exists"),
    ("guard_tool", "tools/guard.py exists"),
    ("next_tool", "tools/next.py exists"),
    ("shim", "bin/spiel exists"),
    ("codex_plugin", "Codex plugin manifest exists"),
    ("codex_marketplace", "Repo Codex marketplace exists"),
]


def check_path(name: str, ok: bool, detail: str, severity: str = "error") -> dict:
    return {"name": name, "ok": bool(ok), "detail": detail, "severity": severity}


def run_check(cmd: list[str], cwd: Path) -> tuple[bool, str]:
    try:
        result = subprocess.run(cmd, cwd=cwd, text=True, capture_output=True, timeout=10)
    except Exception as e:
        return False, str(e)
    if result.returncode == 0:
        return True, (result.stdout or result.stderr).strip()
    return False, (result.stderr or result.stdout).strip()


def main() -> int:
    ap = argparse.ArgumentParser(description="Check SpielOS install health")
    ap.add_argument("--vault", help="Vault root")
    ap.add_argument("--json", action="store_true", help="Print JSON")
    ap.add_argument("--ide", choices=("codex", "all"), default="all")
    args = ap.parse_args()

    vault = resolve_vault(args.vault)
    checks: list[dict] = []
    if not vault:
        checks.append(check_path("vault", False, "could not resolve vault"))
        payload = {"ok": False, "vault": None, "checks": checks}
        print(json.dumps(payload, indent=2) if args.json else "  ✗ vault: could not resolve")
        return 1

    checks.append(check_path("vault", (vault / "team" / "strategist.md").is_file(), str(vault)))
    checks.append(check_path("post_tool", (vault / "tools" / "post.py").is_file(), "tools/post.py"))
    checks.append(check_path("advance_tool", (vault / "tools" / "advance.py").is_file(), "tools/advance.py"))
    checks.append(check_path("capture_tool", (vault / "tools" / "capture-session.py").is_file(), "tools/capture-session.py"))
    checks.append(check_path("editor_tool", (vault / "tools" / "editor.py").is_file(), "tools/editor.py"))
    checks.append(check_path("guard_tool", (vault / "tools" / "guard.py").is_file(), "tools/guard.py"))
    checks.append(check_path("next_tool", (vault / "tools" / "next.py").is_file(), "tools/next.py"))
    checks.append(check_path("shim", (vault / "bin" / "spiel").is_file(), "bin/spiel"))
    checks.append(check_path("codex_plugin", (vault / "plugins" / "spielos" / ".codex-plugin" / "plugin.json").is_file(), "plugins/spielos/.codex-plugin/plugin.json"))
    checks.append(check_path("codex_marketplace", (vault / ".agents" / "plugins" / "marketplace.json").is_file(), ".agents/plugins/marketplace.json"))

    ok_post, post_detail = run_check([sys.executable, str(vault / "tools" / "post.py"), "--help"], vault)
    checks.append(check_path("post_help", ok_post, post_detail.splitlines()[0] if post_detail else "post.py --help"))

    ok_advance, adv_detail = run_check([sys.executable, str(vault / "tools" / "advance.py"), "--show", "--vault", str(vault), "--quiet"], vault)
    checks.append(check_path("advance_callable", ok_advance, adv_detail or "advance.py callable"))

    ok_guard, guard_detail = run_check([sys.executable, str(vault / "tools" / "guard.py"), "--vault", str(vault), "--json"], vault)
    checks.append(check_path("guard_clean", ok_guard, guard_detail.splitlines()[0] if guard_detail else "guard.py clean", severity="warning"))

    if args.ide in ("codex", "all"):
        codex_home = Path.home() / ".codex"
        checks.append(check_path("codex_home", codex_home.exists(), str(codex_home)))
        if codex_home.exists():
            expected_agent = codex_home / "agents" / "post.toml"
            checks.append(check_path("codex_post_agent", expected_agent.exists(), str(expected_agent)))
            # Plugin hook files (deterministic /post on Codex).
            plugin_root = vault / "plugins" / "spielos"
            hooks_src = plugin_root / "hooks.json"
            script_src = plugin_root / "scripts" / "post-hook.sh"
            checks.append(check_path("codex_plugin_hooks", hooks_src.is_file(), str(hooks_src)))
            if hooks_src.is_file():
                try:
                    hooks_doc = json.loads(hooks_src.read_text(encoding="utf-8"))
                    has_userprompt = "UserPromptSubmit" in (hooks_doc.get("hooks") or {})
                    checks.append(check_path(
                        "codex_plugin_userprompt_hook",
                        has_userprompt,
                        "UserPromptSubmit declared in plugins/spielos/hooks.json",
                    ))
                except (OSError, json.JSONDecodeError) as e:
                    checks.append(check_path("codex_plugin_userprompt_hook", False, f"invalid JSON: {e}"))
            checks.append(check_path("codex_post_hook_script", script_src.is_file() and os.access(script_src, os.X_OK), str(script_src)))
            # Live cache check: the cache copy should be present and recent.
            cache_root = codex_home / "plugins" / "cache"
            if cache_root.is_dir():
                cache_hooks = list(cache_root.glob("*/spielos/*/hooks.json"))
                cache_scripts = list(cache_root.glob("*/spielos/*/scripts/post-hook.sh"))
                checks.append(check_path(
                    "codex_cache_hooks",
                    bool(cache_hooks),
                    ", ".join(str(p) for p in cache_hooks) or "<no cache copy found>",
                ))
                if cache_scripts:
                    checks.append(check_path(
                        "codex_cache_hook_script",
                        cache_scripts[0].is_file() and os.access(cache_scripts[0], os.X_OK),
                        str(cache_scripts[0]),
                    ))

    ok = all(c["ok"] or c.get("severity") == "warning" for c in checks)
    payload = {"ok": ok, "vault": str(vault), "checks": checks}
    if args.json:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        print(f"SpielOS doctor: {vault}")
        for check in checks:
            mark = "✓" if check["ok"] else ("!" if check.get("severity") == "warning" else "✗")
            print(f"  {mark} {check['name']}: {check['detail']}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
