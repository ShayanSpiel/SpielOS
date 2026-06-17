#!/usr/bin/env python3
"""state_handlers.py — Single source of truth for per-state logic.

Every state in the content loop has a handler here. The orchestrator and
the legacy single-step CLI both call the same handler. No duplication.

Public surface:
    handler_for(state)         -> callable
    run_handler(state, name)   -> int (exit code)
    on_publish(state, ...)     -> the publish handler

The handlers are pure-ish: they take a state dict, do the work, transition
state, return an int. File I/O is allowed (it's a state machine, not pure
math).
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable

import ui
import publish_dispatcher as dispatch
from engine_state import (
    QUEUE_DIR, BANNERS_DIR,
    StateMachine,
    read_wiki_state, write_wiki_state, save_checkpoint, load_checkpoint, clear_checkpoint,
    read_brief, write_brief,
    set_handoff, clear_handoff, get_active_handoff, check_handoff_expired,
    validate_brief_for_transition, HANDOFF_TTL_MINUTES,
)
from engine_config import config
from engine_serial import log, log_err
from engine_frontmatter import parse_frontmatter, write_frontmatter, now_iso


CONTENT_STATES = [
    "IDLE",
    "SESSION_CAPTURE",
    "COMPILE",
    "SELECT",
    "FORMAT_WIZARD",
    "DRAFTING",
    "BANNER",
    "GATE_CHECK",
    "QUEUE",
    "PUBLISHING",
    "ARCHIVING",
    "ANALYZING_POST",
    "COMPLETE_POST",
]


HANDLERS: dict[str, Callable] = {}


def register(state: str):
    def deco(fn: Callable) -> Callable:
        HANDLERS[state] = fn
        return fn
    return deco


def handler_for(state: str) -> Callable | None:
    return HANDLERS.get(state)


def run_handler(state: dict, name: str, *args, **kwargs) -> int:
    fn = HANDLERS.get(name)
    if fn is None:
        log_err("state_handlers", f"no handler for state {name}")
        return 1
    return fn(state, *args, **kwargs)


def transition(state: dict, target: str) -> bool:
    sm = StateMachine(state.get("loop", "CONTENT"))
    valid, reason = sm.validate_transition(state.get("current_state", "IDLE"), target)
    if not valid:
        log_err("state_handlers", f"invalid transition",
                from_state=state.get("current_state"),
                to_state=target,
                reason=reason)
        return False
    prev = state.get("current_state", "?")
    state["current_state"] = target
    write_wiki_state(state)
    save_checkpoint(state)
    log("INFO", "state_handlers", "transition",
        from_state=prev, to_state=target, loop=state.get("loop", "CONTENT"))
    return True


def reset_to_idle(state: dict, reason: str) -> int:
    prev = state.get("current_state", "?")
    state["current_state"] = "IDLE"
    write_wiki_state(state)
    save_checkpoint(state)
    brief = read_brief()
    if brief:
        clear_handoff(brief)
        write_brief(brief)
    log("WARN", "state_handlers", "reset to IDLE",
        from_state=prev, reason=reason)
    print()
    print(ui.ego("We held the line. The drafts are safe."))
    return 0


@register("PUBLISHING")
def on_publish(
    state: dict,
    draft_id: str | None = None,
    *,
    dry_run: bool = False,
    auto_confirm: bool | None = None,
    decisions: dict[str, str] | None = None,
) -> int:
    """PUBLISHING state. Dispatch one or many drafts.

    Form 1: on_publish(state, draft_id)        — publish one specific draft
    Form 2: on_publish(state, None)            — publish all in queue (per decisions)
    """
    state["loop"] = "CONTENT"
    if auto_confirm is None:
        auto_confirm = config.posting_mode != "manual"
    if not transition(state, "PUBLISHING"):
        return 1
    print(ui.header("PUBLISH", subtitle="Dispatch via the right publisher. Archive on success.", accent="magenta", width=80))
    print()
    if draft_id:
        result = _publish_single(state, draft_id, dry_run=dry_run, auto_confirm=auto_confirm)
    else:
        result = _publish_bulk(state, decisions=decisions, dry_run=dry_run, auto_confirm=auto_confirm)
    if not result.get("any_published") and not result.get("any_dispatched"):
        log("INFO", "state_handlers", "publish produced no results",
            reason=result.get("reason", ""))
    if result.get("any_dispatched"):
        transition(state, "ARCHIVING")
        from engine_state import POSTED_DIR
        summary = result.get("summary", {})
        archived_count = len(summary.get("published", []))
        print()
        print(ui.panel("PUBLISH COMPLETE", [
            f"  Published: {archived_count}",
            f"  Held:      {len(summary.get('held', []))}",
            f"  Skipped:   {len(summary.get('skipped', []))} (cadence)",
            f"  Failed:    {len(summary.get('failed', []))}",
        ], accent="bright_green", width=80))
        print()
        print(ui.ego("Filed. The post lives in posted/ now."))
        return 0
    return 0 if result.get("ok") else 1


def _publish_single(state: dict, draft_id: str, *, dry_run: bool, auto_confirm: bool) -> dict:
    """Resolve draft_id to a path and publish."""
    draft_path = _resolve_draft_id(draft_id)
    if not draft_path:
        print(ui.status("fail", f"  draft not found: {draft_id}"))
        return {"ok": False, "any_dispatched": False, "reason": "not found"}
    result = dispatch.dispatch_publish(
        draft_path,
        dry_run=dry_run,
        auto_confirm=auto_confirm,
    )
    if result["ok"]:
        print(ui.status("pass", f"  published {draft_path.name}"))
        if result.get("archived"):
            print(ui.status("info", f"  → {result['archived'].relative_to(draft_path.parent.parent) if result['archived'].is_relative_to(draft_path.parent.parent) else result['archived']}"))
        return {"ok": True, "any_published": True, "any_dispatched": True, "summary": {"published": [draft_path.name]}}
    if result.get("skipped"):
        print(ui.status("warn", f"  skipped: {result['reason']}"))
        return {"ok": False, "any_dispatched": False, "reason": result["reason"]}
    print(ui.status("fail", f"  failed: {result['reason']}"))
    return {"ok": False, "any_dispatched": False, "reason": result["reason"]}


def _publish_bulk(state: dict, decisions: dict | None, *, dry_run: bool, auto_confirm: bool) -> dict:
    summary = dispatch.dispatch_bulk(
        QUEUE_DIR,
        decisions=decisions,
        dry_run=dry_run,
        auto_confirm=auto_confirm,
    )
    if summary.get("published"):
        print(ui.status("pass", f"  published: {len(summary['published'])}"))
    if summary.get("held"):
        print(ui.status("warn", f"  held:      {len(summary['held'])}"))
    if summary.get("skipped_cadence"):
        print(ui.status("warn", f"  skipped:   {len(summary['skipped_cadence'])} (cadence)"))
    if summary.get("failed"):
        print(ui.status("fail", f"  failed:    {len(summary['failed'])}"))
        for name, reason in summary["failed"]:
            print(ui.status("fail", f"    {name}: {reason}"))
    any_published = bool(summary.get("published"))
    any_dispatched = any_published
    return {"ok": not summary.get("failed"), "any_published": any_published, "any_dispatched": any_dispatched, "summary": summary}


def _resolve_draft_id(draft_id: str) -> Path | None:
    """Resolve a draft_id to a path in queue/ or posted/.

    Accepts: full filename, stem, short ref (number), or URL.
    """
    p = Path(draft_id)
    if p.is_absolute() and p.exists():
        return p
    candidate = QUEUE_DIR / draft_id
    if candidate.exists():
        return candidate
    stem = draft_id.replace(".md", "")
    candidate = QUEUE_DIR / f"{stem}.md"
    if candidate.exists():
        return candidate
    drafts = sorted(QUEUE_DIR.glob("*.md"))
    if draft_id.isdigit():
        idx = int(draft_id)
        if 1 <= idx <= len(drafts):
            return drafts[idx - 1]
    return None
