#!/usr/bin/env python3
"""Codex UserPromptSubmit hook entrypoint.

Hooks are best-effort lifecycle helpers, not the only product surface. This
script keeps the hook stable by living behind `spiel codex-hook`, where vault
resolution and PATH behavior are controlled by the shim.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _vault import resolve_vault  # noqa: E402
from hook_log import append_event  # noqa: E402


def now_ms() -> int:
    return int(time.time() * 1000)


def extract_prompt(raw: str) -> str:
    raw = raw.strip()
    if not raw:
        return ""
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return raw
    if isinstance(data, dict):
        for key in ("prompt", "message", "text", "user_message"):
            value = data.get(key)
            if isinstance(value, str):
                return value
        for key in ("event", "payload"):
            nested = data.get(key)
            if isinstance(nested, dict):
                for nested_key in ("prompt", "message", "text", "user_message"):
                    value = nested.get(nested_key)
                    if isinstance(value, str):
                        return value
    return ""


def strip_invocation(prompt: str) -> tuple[bool, str]:
    first = prompt.splitlines()[0].strip() if prompt.strip() else ""
    if not first:
        return False, ""
    matched = False
    text = first
    patterns = [
        r"^\[@post\]\(subagent://post\)\s*",
        r"^/post\b\s*",
        r"^@post\b\s*",
    ]
    for pattern in patterns:
        new_text = re.sub(pattern, "", text, count=1)
        if new_text != text:
            matched = True
            text = new_text
            break
    return matched, text.strip()


def log(vault: Path, *, start_ms: int, prompt: str, decision: str, result: str, run_id: str | None, detail: str) -> None:
    append_event(
        vault,
        event="user_prompt_submit",
        prompt=prompt,
        decision=decision,
        result=result,
        run_id=run_id,
        duration_ms=now_ms() - start_ms,
        detail=detail,
    )


def extract_run_id(output: str) -> str | None:
    for line in output.splitlines():
        if "post run started:" in line:
            return line.split("post run started:", 1)[1].strip()
    return None


def setup_cta() -> str:
    return (
        "[spiel post] SpielOS is installed in Codex, but no vault is set up yet.\n\n"
        "SpielOS needs one vault folder for strategy files and generated content.\n"
        "Use the Codex prompt \"Set up SpielOS in ~/SpielOS\", or run:\n\n"
        "  SPIELOS_INSTALL_DIR=\"$HOME/SpielOS\" bash <(curl -fsSL https://spielos.xyz/install)\n\n"
        "If you already have a vault, run:\n\n"
        "  spiel set-vault /path/to/your/SpielOS\n\n"
        "After setup finishes, /post will save to that vault from any Codex project.\n"
    )


def main() -> int:
    ap = argparse.ArgumentParser(description="SpielOS Codex hook")
    ap.add_argument("--vault", help="SpielOS vault root")
    args = ap.parse_args()
    start = now_ms()

    if args.vault:
        explicit_vault = Path(args.vault).expanduser()
        if not (explicit_vault / "team" / "strategist.md").is_file():
            sys.stdout.write(setup_cta())
            return 0

    vault = resolve_vault(args.vault)
    if not vault:
        sys.stdout.write(setup_cta())
        return 0

    raw_payload = sys.stdin.read()
    prompt = extract_prompt(raw_payload)
    matched, topic = strip_invocation(prompt)
    if not matched:
        if prompt:
            log(vault, start_ms=start, prompt=prompt, decision="skip", result="no_match", run_id=None, detail="not a post invocation")
        return 0

    decision = "session" if not topic else ("file" if topic.startswith("@file:") else "topic")
    if decision == "session":
        # Deterministic pre-reset: clear any prior run state so the LLM never
        # sees a stuck run. tools/advance.py --reset only touches state and
        # current.md; user content in drafts/, ready/, posted/, rejected/,
        # sessions/ is preserved. This is the Codex-side counterpart to the
        # auto-reset in tools/post.py — both layers enforce the rule.
        reset_cmd = [str(vault / "bin" / "spiel"), "reset"]
        reset_env = os.environ.copy()
        reset_env["VAULT_DIR"] = str(vault)
        subprocess.run(reset_cmd, cwd=vault, env=reset_env, check=False, capture_output=True)
        log(vault, start_ms=start, prompt=prompt, decision="session", result="needs_transcript", run_id=None, detail="session mode — agent must compile transcript and run spiel post --mode session")
        sys.stdout.write(
            "[spiel post] Session mode detected. You are the @post agent.\n\n"
            "1. Compile the visible Codex conversation into two files:\n"
            "   - /tmp/spiel-capture.md  (clean user/assistant text only, no tool noise)\n"
            "   - /tmp/spiel-capture.json  (decision, number, lesson, pattern, ship, summary, tags)\n"
            "2. Run: SPIELOS_ADAPTER=codex SPIELOS_INVOKED_BY=post-agent "
            "SPIELOS_TRANSCRIPT_SOURCE=live_conversation_llm_compiled "
            "spiel post --mode session "
            "--transcript-file /tmp/spiel-capture.md "
            "--structured-json /tmp/spiel-capture.json "
            "--title \"<short session title>\" --tags \"build,ship\"\n"
            "3. Follow the canonical team/post.md command and dispatch the next "
            "role returned by `spiel next`.\n\n"
            "Do not ask the user for a topic. Bare @post is always session mode. "
            "Never write drafts from @post.\n"
        )
        return 0

    cmd = [str(vault / "bin" / "spiel"), "post", topic]
    env = os.environ.copy()
    env["VAULT_DIR"] = str(vault)
    env["SPIELOS_ADAPTER"] = "codex"
    env["SPIELOS_INVOKED_BY"] = "hook"
    env["SPIELOS_TRANSCRIPT_SOURCE"] = "prompt"
    proc = subprocess.run(cmd, cwd=vault, env=env, text=True, capture_output=True)
    output = (proc.stdout or "").strip()
    error = (proc.stderr or "").strip()
    if proc.returncode != 0:
        log(vault, start_ms=start, prompt=prompt, decision=decision, result="cli_error", run_id=None, detail=error[:500])
        sys.stdout.write(
            f"[spiel post] ERROR: `spiel post` exited {proc.returncode}.\n"
            f"{error or output}\n"
            "Run `spiel status` to inspect an active run, or `spiel reset` to start fresh.\n"
        )
        return 0

    run_id = extract_run_id(output)
    log(vault, start_ms=start, prompt=prompt, decision=decision, result="ok", run_id=run_id, detail="spiel post succeeded")
    sys.stdout.write(
        "[spiel post] deterministic runtime started.\n\n"
        f"{output}\n\n"
        "Next: follow team/post.md and dispatch the role returned by `spiel next`. Never write drafts from @post.\n"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
