#!/usr/bin/env python3
"""Continue guidance for the current SpielOS run.

This command is intentionally mechanical. It does not ask the model to infer
the pipeline, and it does not mutate state. It reads content/.state.json and
prints the only valid next action.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _vault import resolve_vault  # noqa: E402
from next import MESSAGE_BY_STEP, ROLE_BY_STEP  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description="Show how to continue the current SpielOS run")
    ap.add_argument("--vault", help="SpielOS vault root")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    vault = resolve_vault(args.vault)
    if not vault:
        sys.stderr.write("ERROR: could not locate SpielOS vault\n")
        return 2

    state_path = vault / "content" / ".state.json"
    if not state_path.is_file():
        payload = {
            "ok": True,
            "active": False,
            "step": "idle",
            "role": None,
            "message": "No active run. Start session mode with bare `/post` or `@post`, or topic mode with `/post <topic>` / `@post <topic>`.",
        }
    else:
        try:
            state = json.loads(state_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            payload = {
                "ok": False,
                "active": False,
                "step": "error",
                "role": None,
                "message": f"content/.state.json is invalid JSON: {e}. Run `spiel reset` to start fresh.",
            }
        else:
            step = state.get("step", "idle")
            payload = {
                "ok": True,
                "active": state.get("status") in ("routing", "active", "paused"),
                "run_id": state.get("run_id"),
                "mode": state.get("mode"),
                "step": step,
                "role": ROLE_BY_STEP.get(step),
                "message": MESSAGE_BY_STEP.get(step, f"Unknown step: {step}"),
            }

    if args.json:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        if payload.get("run_id"):
            print(f"run:  {payload['run_id']}")
        if payload.get("mode"):
            print(f"mode: {payload['mode']}")
        print(f"step: {payload['step']}")
        if payload.get("role"):
            print(f"next: {payload['role']}")
        print(payload["message"])
    return 0 if payload.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
