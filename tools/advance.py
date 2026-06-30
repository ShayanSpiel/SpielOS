#!/usr/bin/env python3
"""tools/advance.py — State machine for the SpielOS content pipeline.

This is the only place that mutates content/.state.json. Every role's last
action is to call this tool. The tool validates the transition against the
state machine table, appends to the history, and writes atomically.

The state machine:
  idle -> capture -> strategy -> draft -> edit -> publish -> complete -> idle
  any step -> error
  error -> idle (via --reset) or error -> <previous> (via --recover-from <step>)

CLI:
  python3 tools/advance.py --to <step> [--by <agent>] [--vault <path>] [--print]
  python3 tools/advance.py --set-error <message> [--by <agent>] [--vault <path>]
  python3 tools/advance.py --reset [--vault <path>]
  python3 tools/advance.py --recover-from <step> [--vault <path>]
  python3 tools/advance.py --init --run-id <id> --mode <session|topic> [--vault <path>]
  python3 tools/advance.py --show [--vault <path>] [--json]

Exit codes:
  0 = success
  1 = state file does not exist (use --init first)
  2 = invalid transition
  3 = vault not found
  4 = bad arguments
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from datetime import datetime
from pathlib import Path

# Shared vault resolver
import sys as _sys
_sys.path.insert(0, str(Path(__file__).resolve().parent))
from _vault import resolve_vault  # noqa: E402


# ─── State machine table ────────────────────────────────────────────────

VALID_STEPS = (
    "idle", "capture", "strategy",
    "draft", "edit", "publish", "complete", "error",
)

VALID_STATUSES = ("routing", "active", "paused", "shipped", "failed")

# allowed_transitions[from] = {to, ...}
ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    "idle":     {"capture", "error"},
    "capture":  {"strategy", "error", "idle"},
    "strategy": {"draft", "error", "idle"},
    "draft":    {"edit", "error", "idle"},
    "edit":     {"publish", "error", "idle"},
    "publish":  {"complete", "error", "idle"},
    "complete": {"idle"},
    "error":    {"idle", "capture", "strategy", "draft", "edit", "publish"},
}

# Map step -> run status (set automatically on transition)
STEP_TO_STATUS: dict[str, str] = {
    "idle":     "routing",
    "capture":  "active",
    "strategy": "active",
    "draft":    "active",
    "edit":     "active",
    "publish":  "active",
    "complete": "shipped",
    "error":    "failed",
}

STATE_FILE_REL = Path("content") / ".state.json"


# ─── Vault resolution ────────────────────────────────────────────────────

def find_vault(cli_vault: str | None) -> Path:
    v = resolve_vault(cli_vault)
    if v is None:
        return Path.cwd()
    return v


def state_path(vault: Path) -> Path:
    return vault / STATE_FILE_REL


# ─── Atomic IO ───────────────────────────────────────────────────────────

def atomic_write_json(path: Path, data: dict) -> None:
    """Write JSON atomically: tmp + fsync + rename. Survives crashes mid-write."""
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
    with tempfile.NamedTemporaryFile(
        "w", dir=path.parent, prefix=".state-", suffix=".tmp", delete=False, encoding="utf-8"
    ) as f:
        tmp = Path(f.name)
        f.write(text)
        f.flush()
        os.fsync(f.fileno())
    tmp.replace(path)


def read_state(vault: Path) -> dict | None:
    p = state_path(vault)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


# ─── Transition logic ────────────────────────────────────────────────────

def is_valid_transition(from_step: str, to_step: str) -> bool:
    if to_step not in VALID_STEPS:
        return False
    if from_step == to_step:
        return True  # idempotent re-set
    return to_step in ALLOWED_TRANSITIONS.get(from_step, set())


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def cmd_init(args, vault: Path) -> int:
    """Initialize a fresh state file. Overwrites any existing state."""
    state = {
        "run_id": args.run_id,
        "status": "routing",
        "step": "idle",
        "mode": args.mode,
        "current": "content/current.md",
        "session": "",
        "drafts": [],
        "ready": [],
        "updated_at": now_iso(),
        "error": None,
        "history": [],
    }
    if args.session:
        state["session"] = args.session
    atomic_write_json(state_path(vault), state)
    if not args.quiet:
        print(json.dumps(state, indent=2, ensure_ascii=False))
    return 0



def cmd_advance(args, vault: Path) -> int:
    """Validate and apply a step transition."""
    state = read_state(vault)
    if state is None:
        sys.stderr.write("ERROR: state file does not exist. Use --init first.\n")
        return 1
    from_step = state.get("step", "idle")
    to_step = args.to
    if not is_valid_transition(from_step, to_step):
        sys.stderr.write(
            f"ERROR: invalid transition {from_step!r} -> {to_step!r}\n"
            f"  Allowed from {from_step!r}: {sorted(ALLOWED_TRANSITIONS.get(from_step, set()))}\n"
        )
        return 2
    # Append to history
    history = state.get("history", [])
    history.append({
        "from": from_step,
        "to": to_step,
        "at": now_iso(),
        "by": args.by or "agent",
    })
    state["step"] = to_step
    state["status"] = STEP_TO_STATUS.get(to_step, state.get("status", "active"))
    state["updated_at"] = now_iso()
    if to_step == "idle" and from_step == "complete":
        state["status"] = "shipped"  # stays shipped briefly until next --init
        # Clear transient lists on a clean run completion so a fresh run
        # never inherits stale drafts/ready pointers from a prior run.
        state["drafts"] = []
        state["ready"] = []
    state["error"] = None  # clear error on successful advance
    state["history"] = history
    # Also accept --add-draft / --add-ready / --set-session flags for the role convenience
    if args.add_draft:
        drafts = state.get("drafts", [])
        for d in args.add_draft:
            if d and d not in drafts:
                drafts.append(d)
        state["drafts"] = drafts
    if args.add_ready:
        ready = state.get("ready", [])
        for r in args.add_ready:
            if r and r not in ready:
                ready.append(r)
        state["ready"] = ready
    if args.set_session:
        state["session"] = args.set_session
    atomic_write_json(state_path(vault), state)
    if not args.quiet:
        out = {k: state[k] for k in ("run_id", "status", "step", "updated_at") if k in state}
        print(json.dumps(out, ensure_ascii=False))
    return 0


def cmd_set_error(args, vault: Path) -> int:
    """Set the error state with a message. Stays on the current step."""
    state = read_state(vault)
    msg = args.set_error
    if state is None:
        # Create a minimal state with error so /post recovery can read it
        state = {
            "run_id": "unknown",
            "status": "failed",
            "step": "error",
            "mode": "session",
            "current": "content/current.md",
            "session": "",
            "drafts": [],
            "ready": [],
            "updated_at": now_iso(),
            "error": msg,
            "history": [],
        }
        atomic_write_json(state_path(vault), state)
        if not args.quiet:
            print(json.dumps({"step": "error", "error": msg}, ensure_ascii=False))
        return 0
    from_step = state.get("step", "idle")
    history = state.get("history", [])
    history.append({
        "from": from_step,
        "to": "error",
        "at": now_iso(),
        "by": args.by or "agent",
    })
    state["step"] = "error"
    state["status"] = "failed"
    state["error"] = msg
    state["updated_at"] = now_iso()
    state["history"] = history
    atomic_write_json(state_path(vault), state)
    if not args.quiet:
        print(json.dumps({"step": "error", "error": msg}, ensure_ascii=False))
    return 0


def cmd_reset(args, vault: Path) -> int:
    """Delete active run state and handoff. User drafts/content are preserved."""
    p = state_path(vault)
    if p.exists():
        p.unlink()
    current = vault / "content" / "current.md"
    if current.exists():
        current.unlink()
    if not args.quiet:
        print(f"  ✓ state reset: {p.relative_to(vault)} deleted")
        print("  ✓ handoff reset: content/current.md deleted")
    return 0


def cmd_recover(args, vault: Path) -> int:
    """Recover from error by jumping to a previous step."""
    state = read_state(vault)
    if state is None:
        sys.stderr.write("ERROR: state file does not exist. Nothing to recover from.\n")
        return 1
    if state.get("step") != "error":
        sys.stderr.write(
            f"ERROR: current step is {state.get('step')!r}, not 'error'. "
            "Use --to for normal transitions.\n"
        )
        return 2
    target = args.recover_from
    if target not in VALID_STEPS or target == "error":
        sys.stderr.write(f"ERROR: cannot recover to {target!r}\n")
        return 4
    history = state.get("history", [])
    history.append({
        "from": "error",
        "to": target,
        "at": now_iso(),
        "by": args.by or "user",
    })
    state["step"] = target
    state["status"] = STEP_TO_STATUS.get(target, "active")
    state["error"] = None
    state["updated_at"] = now_iso()
    state["history"] = history
    atomic_write_json(state_path(vault), state)
    if not args.quiet:
        print(json.dumps({"step": target, "status": state["status"]}, ensure_ascii=False))
    return 0


def cmd_show(args, vault: Path) -> int:
    state = read_state(vault)
    if state is None:
        print("  no active run")
        return 0
    if args.json:
        print(json.dumps(state, indent=2, ensure_ascii=False))
    else:
        print(f"  run_id:     {state.get('run_id', '?')}")
        print(f"  status:     {state.get('status', '?')}")
        print(f"  step:       {state.get('step', '?')}")
        print(f"  mode:       {state.get('mode', '?')}")
        if state.get("session"):
            print(f"  session:    {state['session']}")
        if state.get("drafts"):
            print(f"  drafts:     {len(state['drafts'])}")
        if state.get("ready"):
            print(f"  ready:      {len(state['ready'])}")
        if state.get("error"):
            print(f"  error:      {state['error']}")
        print(f"  updated_at: {state.get('updated_at', '?')}")
    return 0


# ─── CLI ─────────────────────────────────────────────────────────────────

def main() -> int:
    ap = argparse.ArgumentParser(description="SpielOS pipeline state machine")
    ap.add_argument("--vault", help="Path to vault root (default: auto-detect)")
    ap.add_argument("--by", help="Who is making this transition (e.g. 'post', 'writer')")
    ap.add_argument("--quiet", action="store_true", help="No stdout, exit code only")
    ap.add_argument("--json", action="store_true", help="JSON output (for --show)")

    # Mutually exclusive actions
    actions = ap.add_mutually_exclusive_group(required=True)
    actions.add_argument("--to", help="Transition to this step")
    actions.add_argument("--set-error", help="Set error state with this message")
    actions.add_argument("--reset", action="store_true", help="Delete state file")
    actions.add_argument("--recover-from", help="Recover from error to this step")
    actions.add_argument("--init", action="store_true", help="Initialize a fresh state file")
    actions.add_argument("--show", action="store_true", help="Show current state")

    # --init args
    ap.add_argument("--run-id", help="(with --init) run id, e.g. 2026-06-26-001")
    ap.add_argument("--mode", choices=("session", "topic"), help="(with --init) capture mode")
    ap.add_argument("--session", help="(with --init) relative path to session log")

    # --to args
    ap.add_argument("--add-draft", action="append", default=[],
                    help="(with --to) append a draft path to state.drafts (repeatable)")
    ap.add_argument("--add-ready", action="append", default=[],
                    help="(with --to) append a ready path to state.ready (repeatable)")
    ap.add_argument("--set-session", help="(with --to) set state.session")

    args = ap.parse_args()

    vault = find_vault(args.vault)
    if not vault or not (vault / "team" / "strategist.md").is_file():
        sys.stderr.write("ERROR: could not locate SpielOS vault.\n")
        return 3

    if args.init:
        if not args.run_id or not args.mode:
            sys.stderr.write("ERROR: --init requires --run-id and --mode\n")
            return 4
        return cmd_init(args, vault)
    if args.to:
        return cmd_advance(args, vault)
    if args.set_error is not None:
        return cmd_set_error(args, vault)
    if args.reset:
        return cmd_reset(args, vault)
    if args.recover_from:
        return cmd_recover(args, vault)
    if args.show:
        return cmd_show(args, vault)

    sys.stderr.write("ERROR: no action specified\n")
    return 4


if __name__ == "__main__":
    sys.exit(main())
