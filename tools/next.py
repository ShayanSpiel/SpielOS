#!/usr/bin/env python3
"""Print the next valid SpielOS pipeline action from current state."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _vault import resolve_vault  # noqa: E402


ROLE_BY_STEP = {
    "strategy": "@strategist",
    "draft": "@writer",
    "edit": "@editor",
    "publish": "@publisher",
}

MESSAGE_BY_STEP = {
    "strategy": "Invoke @strategist. Formats default to x, linkedin, and blog. Do not ask a format question.",
    "draft": "Invoke @writer. Writer may create drafts because state.step is draft.",
    "edit": "Invoke @editor. Editor stamps gates and moves passing drafts.",
    "publish": "Invoke @publisher. Must ask publish/hold/reject.",
    "complete": "Run is complete.",
    "idle": "No active run. Start with `spiel post <topic>` or session mode.",
    "error": "Run is in error. Use `tools/advance.py --recover-from <step>` or reset.",
}

CONTINUE_MESSAGE_BY_STEP = {
    "strategy": "Invoke @strategist. Formats default to x, linkedin, and blog. Do not ask a format question.",
    "draft": "Invoke @writer. Writer may create drafts because state.step is draft.",
    "edit": "Invoke @editor. Editor stamps gates and moves passing drafts.",
    "publish": "Invoke @publisher. Must ask publish/hold/reject.",
    "complete": "Run is complete. Next `/post` overwrites the state.",
    "idle": "No active run. Start session mode with bare `/post` or topic mode with `/post <topic>`.",
    "error": "Run is in error. Use `tools/advance.py --recover-from <step>` or `spiel reset` to start fresh.",
}


def _stale_warning(state: dict, threshold_min: int = 30) -> str | None:
    """If a non-terminal run hasn't advanced in `threshold_min` minutes,
    warn. This catches the common "pipeline stuck" case without a manual
    reset.
    """
    if not isinstance(state, dict):
        return None
    step = state.get("step", "idle")
    if step in ("idle", "complete", "error"):
        return None
    updated_at = state.get("updated_at")
    if not updated_at:
        return None
    try:
        from datetime import datetime
        # SpielOS writes timestamps in local time (no tzinfo). Compare
        # against local now — no UTC conversion — to avoid false positives
        # when local != UTC.
        ts = datetime.fromisoformat(updated_at)
        now = datetime.now()
        if ts.tzinfo is not None and now.tzinfo is None:
            now = now.astimezone(ts.tzinfo).replace(tzinfo=None)
        elif ts.tzinfo is None and now.tzinfo is not None:
            ts = ts.replace(tzinfo=now.tzinfo)
    except (TypeError, ValueError):
        return None
    age_min = (now - ts).total_seconds() / 60
    if age_min < threshold_min:
        return None
    return (
        f"  ⚠ STALE: this run has been on step '{step}' for {int(age_min)} minutes "
        f"(threshold {threshold_min}). The role subagent may have failed to advance. "
        f"Run `spiel reset` to start fresh, or `tools/advance.py --to <next-step>` to recover."
    )


def main() -> int:
    ap = argparse.ArgumentParser(description="Show next SpielOS pipeline action")
    ap.add_argument("--vault", help="SpielOS vault root")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--stale-min", type=int, default=30,
                    help="Warn if a non-terminal run is older than N minutes (default 30)")
    ap.add_argument("--continue", action="store_true", dest="continue_mode",
                    help="Show continue guidance (adds active field, guidance messages)")
    args = ap.parse_args()
    vault = resolve_vault(args.vault)
    if not vault:
        sys.stderr.write("ERROR: could not locate SpielOS vault\n")
        return 2
    state_path = vault / "content" / ".state.json"
    state = None
    if not state_path.is_file():
        if args.continue_mode:
            payload = {
                "ok": True,
                "active": False,
                "step": "idle",
                "role": None,
                "message": CONTINUE_MESSAGE_BY_STEP["idle"],
            }
        else:
            payload = {"ok": True, "step": "idle", "role": None, "message": MESSAGE_BY_STEP["idle"]}
    else:
        state = json.loads(state_path.read_text(encoding="utf-8"))
        step = state.get("step", "idle")
        if args.continue_mode:
            payload = {
                "ok": True,
                "active": state.get("status") in ("routing", "active", "paused"),
                "run_id": state.get("run_id"),
                "mode": state.get("mode"),
                "step": step,
                "role": ROLE_BY_STEP.get(step),
                "message": CONTINUE_MESSAGE_BY_STEP.get(step, f"Unknown step: {step}"),
            }
        else:
            payload = {
                "ok": True,
                "run_id": state.get("run_id"),
                "step": step,
                "role": ROLE_BY_STEP.get(step),
                "message": MESSAGE_BY_STEP.get(step, f"Unknown step: {step}"),
            }
    warning = _stale_warning(state, threshold_min=args.stale_min)
    if args.json:
        out = dict(payload)
        if warning:
            out["warning"] = warning
        print(json.dumps(out, indent=2, ensure_ascii=False))
    else:
        if payload.get("run_id"):
            print(f"run:  {payload['run_id']}")
        if state and state.get("mode"):
            print(f"mode: {state['mode']}")
        print(f"step: {payload['step']}")
        if payload.get("role"):
            print(f"next: {payload['role']}")
        print(payload["message"])
        if warning:
            print(warning)
    return 0


if __name__ == "__main__":
    sys.exit(main())
