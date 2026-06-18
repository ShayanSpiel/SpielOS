#!/usr/bin/env python3
"""engine.py — State machine controller for Spiel Engine.

Validates state transitions, runs automated actions, and reports status.
The LLM performs creative steps (analyzing, drafting); this engine enforces
the sequence.

Usage:
    ./scripts/engine.py status
    ./scripts/engine.py wiki extract <file>
    ./scripts/engine.py wiki analyze
    ./scripts/engine.py wiki reconcile
    ./scripts/engine.py wiki link
    ./scripts/engine.py wiki index
    ./scripts/engine.py wiki validate
    ./scripts/engine.py wiki complete
    ./scripts/engine.py wiki health
    ./scripts/engine.py wiki reset
    ./scripts/engine.py content post [about]
    ./scripts/engine.py content compile
    ./scripts/engine.py content select
    ./scripts/engine.py content draft
    ./scripts/engine.py content banner
    ./scripts/engine.py content gate
    ./scripts/engine.py content queue
    ./scripts/engine.py content hold
    ./scripts/engine.py content publish <id>
    ./scripts/engine.py content archive
    ./scripts/engine.py content analyze
    ./scripts/engine.py content complete
    ./scripts/engine.py queue
    ./scripts/engine.py recover
    ./scripts/engine.py log [--days N] [--level X] [--tail N]
"""

import argparse
import hashlib
import json
import os
import sys
from datetime import datetime
from pathlib import Path

import yaml

from engine_state import (
    VAULT, WIKI_STATE_FILE, LOCK_FILE, CONTENT_BRIEF_FILE, GATES_REPORT_FILE,
    RAW_MANIFEST_FILE, QUEUE_DIR, POSTED_DIR, REJECTED_DIR, SESSIONS_DIR,
    StateMachine,
    read_wiki_state, write_wiki_state, acquire_lock, release_lock,
    save_checkpoint, load_checkpoint, clear_checkpoint,
    read_brief, write_brief,
    set_handoff, clear_handoff, get_active_handoff, check_handoff_expired,
    validate_brief_for_transition, HANDOFF_TTL_MINUTES, MEANING_AXES_DEFAULT,
)
from engine_config import config
from engine_serial import log, log_err, auto_request_id, logged
from engine_frontmatter import parse_frontmatter, write_frontmatter, now_iso
import ui

os.chdir(VAULT)


# ─── Raw Manifest ───────────────────────────────────────────────────────

def read_raw_manifest() -> dict:
    if not RAW_MANIFEST_FILE.exists():
        return {"processed": {}}
    try:
        return json.loads(RAW_MANIFEST_FILE.read_text())
    except (json.JSONDecodeError, OSError):
        return {"processed": {}}


def write_raw_manifest(manifest: dict) -> None:
    RAW_MANIFEST_FILE.write_text(json.dumps(manifest, indent=2))


def compute_sha256(filepath: Path) -> str:
    h = hashlib.sha256()
    for chunk in iter(lambda: filepath.open("rb").read(65536), b""):
        h.update(chunk)
    return h.hexdigest()


def get_unprocessed_raw_files(manifest: dict) -> list[Path]:
    raw_dir = VAULT / "raw"
    if not raw_dir.exists():
        return []
    all_files = sorted(raw_dir.glob("*.md"))
    processed = manifest.get("processed", {})
    unprocessed = []
    for f in all_files:
        rel = str(f.relative_to(VAULT))
        entry = processed.get(rel)
        if entry and entry.get("sha256"):
            if compute_sha256(f) == entry["sha256"]:
                continue
        unprocessed.append(f)
    return unprocessed


def mark_raw_processed(manifest: dict, raw_path: Path) -> None:
    rel = str(raw_path.relative_to(VAULT))
    manifest.setdefault("processed", {})[rel] = {
        "sha256": compute_sha256(raw_path),
        "ingested": datetime.now().strftime("%Y-%m-%d"),
        "size": raw_path.stat().st_size,
    }
    write_raw_manifest(manifest)


# ─── Strategy Pages ────────────────────────────────────────────────────

def load_strategy_pages() -> list[dict]:
    strategy_pages = config.strategy_pages
    results = []
    for name in strategy_pages:
        path = VAULT / "concepts" / f"{name}.md"
        if not path.exists():
            results.append({"name": name, "title": name, "preview": "(not found)", "filepath": ""})
            continue
        content = path.read_text()
        title = name
        for line in content.split("\n"):
            line = line.strip()
            if line.startswith("title:"):
                title = line.split(":", 1)[1].strip()
                break
            if line.startswith("# ") and title == name:
                title = line[2:].strip()
        body_parts = content.split("---", 2)
        preview = body_parts[2].strip()[:300] if len(body_parts) > 2 else content[:300]
        results.append({"name": name, "title": title, "preview": preview, "filepath": f"concepts/{name}.md"})
    return results


def find_latest_session() -> dict | None:
    if not SESSIONS_DIR.exists():
        return None
    sessions = sorted(SESSIONS_DIR.glob("*.md"), reverse=True)
    if not sessions:
        return None
    latest = sessions[0]
    content = latest.read_text()
    meta = {}
    if content.startswith("---"):
        parts = content.split("---", 2)
        if len(parts) >= 2:
            for line in parts[1].strip().split("\n"):
                if ":" in line:
                    key, val = line.split(":", 1)
                    meta[key.strip()] = val.strip()
    return {"filepath": str(latest.relative_to(VAULT)), "filename": latest.name,
            "content": content, "meta": meta}


# ─── State helpers ─────────────────────────────────────────────────────

def print_state(state: dict) -> None:
    loop = state.get("loop", "WIKI")
    current = state.get("current_state", "UNKNOWN")
    loop_label = "content loop" if loop == "CONTENT" else "wiki loop"
    header_text = f"SPIEL ENGINE  ·  STATE  ·  QUEUE  ·  POSTED"
    print(ui.header(header_text, subtitle=f"{current}  ·  {loop_label}", accent="cyan", width=80))
    print()
    state_color = "bright_green" if current == "IDLE" else "bright_cyan"
    pairs = [
        ("Current state", ui._c(f"●  {current}", ui._BOLD, ui._color(state_color) or ui._FG["bright_white"])),
        ("Last change",   state.get("last_state_change", "never") or "never"),
        ("Pending action", str(state.get("pending_action") or "none")),
        ("Last validate", state.get("last_validation", "unknown")),
    ]
    print(ui.kvpairs(pairs, color="bright_cyan"))
    print()
    health = state.get("validation_results", {})
    if any(health.values()) or loop == "WIKI":
        print(ui.panel("HEALTH", [
            f"Orphans:        {health.get('orphans', 0)}",
            f"Broken links:   {health.get('broken_links', 0)}",
            f"Stale:          {len(health.get('stale', []))}",
            f"Warnings:       {len(health.get('warnings', []))}",
        ], accent="bright_blue", width=80))
        print()
    if state.get("last_ingest"):
        print(ui.status("info", f"Last ingest: {state['last_ingest']}"))


def transition(state: dict, target: str, sm: StateMachine | None = None) -> bool:
    current = state.get("current_state", "IDLE")
    if sm is None:
        sm = StateMachine(state.get("loop", "WIKI"))
    valid, reason = sm.validate_transition(current, target)
    if not valid:
        print(f"ERROR: {reason}", file=sys.stderr)
        log_err("engine", "Invalid transition",
                from_state=current, to_state=target, reason=reason)
        return False
    state["current_state"] = target
    write_wiki_state(state)
    save_checkpoint(state)
    print(f"State: {current} \u2192 {target} \u2713")
    log("INFO", "engine", "State transition",
        from_state=current, to_state=target, loop=state.get("loop", "WIKI"))
    return True


def _force_reset_to_idle(state: dict) -> None:
    """Force pipeline to IDLE regardless of current state."""
    prev = state.get("current_state", "?")
    state["current_state"] = "IDLE"
    write_wiki_state(state)
    save_checkpoint(state)
    log("INFO", "engine", "Force reset to IDLE", from_state=prev, loop=state.get("loop", "WIKI"))
    print(f"  (previous state was {prev} \u2014 resetting to IDLE)")


def print_next(state: dict) -> None:
    loop = state.get("loop", "WIKI")
    current = state.get("current_state", "IDLE")
    sm = StateMachine(loop)
    targets = sm.transitions.get(current, [])
    if not targets:
        return
    print(ui.rule("─", width=80, color="bright_black"))
    print()
    for t in targets:
        cmd = _next_command_for(loop, t)
        print(ui.copyable(cmd, label=f"NEXT  →  {t}"))
        print()
    if current in ("COMPILE",):
        try:
            brief = read_brief()
            kind = (brief.get("source") or {}).get("kind") or "session"
        except Exception:
            kind = "session"
        if kind == "topic":
            print(ui.ego("Topic is the subject. Announce it. Name what shipped. End with a verb."))
        else:
            print(ui.ego("Eight steps. One sentence. That is the work."))
    elif current in ("DRAFTING",):
        print(ui.ego("Three platforms. One insight. Ship it."))
    elif current in ("FORMAT_WIZARD",):
        print(ui.ego("Pick your weapons. The system handles the rest."))
    elif current in ("QUEUE",):
        print(ui.ego("Posted. Now the algorithm does its job."))
    elif current in ("GATE_CHECK",):
        print(ui.ego("The gate held. That is the gate's job."))
    elif current in ("BANNER",):
        print(ui.ego("Pixels generated. Drafts dressed. Moving on."))
    elif current in ("PUBLISHING",):
        print(ui.ego("The system writes the meaning. You write the words."))
    print()


_DEPRECATION_WARNED: set[str] = set()


def _deprecation_notice(old_cmd: str, new_cmd: str) -> None:
    """Print a one-time deprecation notice. Used by legacy single-step commands."""
    if old_cmd in _DEPRECATION_WARNED:
        return
    _DEPRECATION_WARNED.add(old_cmd)
    print(ui.status("warn", f"  {old_cmd} is a legacy single-step command. Use `{new_cmd}` instead."))


def _next_command_for(loop: str, target: str) -> str:
    mapping = {
        ("WIKI", "INGESTING"):     "spiel wiki extract",
        ("WIKI", "ANALYZING"):     "spiel wiki analyze",
        ("WIKI", "RECONCILING"):   "spiel wiki reconcile",
        ("WIKI", "LINKING"):       "spiel wiki link",
        ("WIKI", "INDEXING"):      "spiel wiki index",
        ("WIKI", "VALIDATING"):    "spiel wiki validate",
        ("WIKI", "COMPLETE"):      "spiel wiki complete",
        ("CONTENT", "SESSION_CAPTURE"): "spiel content run",
        ("CONTENT", "COMPILE"):    "spiel content run",
        ("CONTENT", "SELECT"):     "spiel content run",
        ("CONTENT", "FORMAT_WIZARD"): "spiel content run",
        ("CONTENT", "DRAFTING"):   "spiel content run",
        ("CONTENT", "BANNER"):     "spiel content banner",
        ("CONTENT", "GATE_CHECK"): "spiel content gate",
        ("CONTENT", "QUEUE"):      "spiel content publish",
        ("CONTENT", "PUBLISHING"): "spiel content publish",
        ("CONTENT", "ARCHIVING"):  "spiel content archive",
        ("CONTENT", "ANALYZING_POST"): "spiel content analyze",
        ("CONTENT", "COMPLETE_POST"): "spiel content complete",
    }
    if target in ("IDLE",):
        if loop == "CONTENT":
            return "spiel content post        # start a new draft"
        return "spiel wiki extract         # start a new ingest"
    return mapping.get((loop, target), f"# manual transition to {target}")


# ─── Wiki Commands ─────────────────────────────────────────────────────

def cmd_status(state: dict) -> int:
    print_state(state)
    return 0


def cmd_wiki_extract(state: dict, args: list) -> int:
    if state.get("current_state") != "IDLE":
        _force_reset_to_idle(state)
    if not transition(state, "INGESTING"):
        return 1
    raw_dir = VAULT / "raw"
    manifest = read_raw_manifest()
    if args:
        targets = []
        for a in args:
            p = raw_dir / a
            if p.exists():
                targets.append(p)
            else:
                print(f"  \u26a0 File not found: raw/{a}")
        if not targets:
            print("  ERROR: No valid target files.")
            return 1
    else:
        targets = get_unprocessed_raw_files(manifest)
        if not targets:
            print("  All raw files already processed. Nothing to do.")
            state["current_state"] = "IDLE"
            write_wiki_state(state)
            return 0
    print(f"  Target: {len(targets)} file(s) to process")
    for t in targets:
        rel = str(t.relative_to(VAULT))
        entry = manifest.get("processed", {}).get(rel)
        if entry:
            print(f"    \u25cf {rel} (changed)")
        else:
            print(f"    \u25cb {rel} (new)")
    print()
    print_next(state)
    return 0


def cmd_wiki_analyze(state: dict) -> int:
    if not transition(state, "ANALYZING"):
        return 1
    print_next(state)
    return 0


def cmd_wiki_reconcile(state: dict) -> int:
    if not transition(state, "RECONCILING"):
        return 1
    print_next(state)
    return 0


def cmd_wiki_link(state: dict) -> int:
    if not transition(state, "LINKING"):
        return 1
    print_next(state)
    return 0


def cmd_wiki_index(state: dict) -> int:
    if not transition(state, "INDEXING"):
        return 1
    print_next(state)
    return 0


def cmd_wiki_validate(state: dict) -> int:
    if not transition(state, "VALIDATING"):
        return 1
    # Import health checks directly
    from engine_health import extract_wikilinks, check_orphans, check_broken_links
    from engine_health import check_stale, check_crosslink_health, check_index_completeness
    pages = {}
    WIKI_DIRS = ["concepts", "entities", "comparisons", "summaries", "templates"]
    for d in WIKI_DIRS:
        dp = VAULT / d
        if dp.exists():
            for f in sorted(dp.glob("*.md")):
                pages[f.stem] = f
    index_path = VAULT / "index.md"
    if index_path.exists():
        pages["index"] = index_path
    all_links = []
    all_page_links = {}
    INFRA = {"index", "log", "AGENTS", "README", "SCHEMA"}
    for key, fp in pages.items():
        if key in INFRA:
            all_page_links[key] = []
            continue
        content = fp.read_text()
        links = extract_wikilinks(content)
        all_links.extend(links)
        all_page_links[key] = links
    orphans = check_orphans(pages, all_links)
    broken = check_broken_links(pages, all_page_links)
    index_content = index_path.read_text() if index_path.exists() else ""
    index_missing = check_index_completeness(pages, index_content) if index_content else []
    print(f"  Orphans: {len(orphans)}")
    print(f"  Broken links: {len(broken)}")
    print(f"  Missing from index: {len(index_missing)}")
    print_next(state)
    return 0


def cmd_wiki_complete(state: dict) -> int:
    if not transition(state, "COMPLETE"):
        return 1
    manifest = read_raw_manifest()
    raw_dir = VAULT / "raw"
    if raw_dir.exists():
        updated = 0
        for f in sorted(raw_dir.glob("*.md")):
            rel = str(f.relative_to(VAULT))
            entry = manifest.get("processed", {}).get(rel)
            if not entry or not entry.get("sha256"):
                mark_raw_processed(manifest, f)
                updated += 1
        if updated:
            print(f"  Manifest: marked {updated} file(s) as processed")
    state["last_ingest"] = datetime.now().isoformat()
    if not transition(state, "IDLE"):
        return 1
    print("Wiki pipeline complete. System back to IDLE.")
    return 0


def cmd_wiki_health(state: dict) -> int:
    print("═══ Read-Only Health Check ═══")
    from engine_health import extract_wikilinks, check_orphans, check_broken_links
    from engine_health import check_stale, check_crosslink_health, check_index_completeness
    from engine_health import find_redundancy_candidates
    pages = {}
    WIKI_DIRS = ["concepts", "entities", "comparisons", "summaries", "templates"]
    for d in WIKI_DIRS:
        dp = VAULT / d
        if dp.exists():
            for f in sorted(dp.glob("*.md")):
                fm = parse_frontmatter(f.read_text())[0]
                pages[f.stem] = (fm, f)
    index_path = VAULT / "index.md"
    all_links = []
    all_page_links = {}
    INFRA = {"index", "log", "AGENTS", "README", "SCHEMA"}
    for key in pages:
        if key in INFRA:
            all_page_links[key] = []
            continue
        fp = pages[key][1]
        content = fp.read_text()
        links = extract_wikilinks(content)
        all_links.extend(links)
        all_page_links[key] = links
    orphans = check_orphans(pages, all_links)
    broken = check_broken_links(pages, all_page_links)
    stale = check_stale(pages)
    index_content = index_path.read_text() if index_path.exists() else ""
    index_missing = check_index_completeness(pages, index_content) if index_content else []
    dead_ends, thin = check_crosslink_health(pages, all_page_links)
    redundancy_pages = []
    for d in WIKI_DIRS:
        dp = VAULT / d
        if dp.exists():
            for f in sorted(dp.glob("*.md")):
                fm = parse_frontmatter(f.read_text())[0]
                if fm:
                    redundancy_pages.append({
                        "slug": f"{d}/{f.stem}",
                        "tags": fm.get("tags", []),
                        "sources": fm.get("sources", []),
                    })
    redun = find_redundancy_candidates(redundancy_pages) if redundancy_pages else []
    print(f"  Orphans: {len(orphans)}")
    print(f"  Broken links: {len(broken)}")
    print(f"  Stale: {len(stale)}")
    print(f"  Missing from index: {len(index_missing)}")
    print(f"  Dead ends: {len(dead_ends)}")
    print(f"  Thin links: {len(thin)}")
    print(f"  Redundancy candidates: {len(redun)}")
    return 0


def cmd_wiki_reset(state: dict) -> int:
    print("WARNING: Force-resetting state to IDLE.")
    try:
        confirm = input("Reset to IDLE? (yes/NO): ")
        if confirm.lower() != "yes":
            print("Cancelled.")
            return 0
    except (EOFError, KeyboardInterrupt):
        print("\nCancelled.")
        return 0
    state["current_state"] = "IDLE"
    state["pending_action"] = None
    write_wiki_state(state)
    print("State reset to IDLE \u2713")
    return 0


# ─── Content Commands ──────────────────────────────────────────────────

def _create_stub_session_log(today: str) -> Path:
    SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
    existing = list(SESSIONS_DIR.glob(f"{today}-session-*.md"))
    nn = max((int(p.stem.split("-")[-1]) for p in existing), default=0) + 1
    stub_path = SESSIONS_DIR / f"{today}-session-{nn:02d}.md"
    stub_content = f"""---
title: <fill in>
date: {today}
session_id: {nn:02d}
tags: []
produces_pillar: no
pillar_outline: none
drafts: []
status: in-progress
---

# Session: <fill in>

## What we did (3-7 bullets)

-

## Decisions made

-

## Lessons learned

-

## Numbers

-

## Pillar decision

- [ ] **Pillar? yes** — work is a system, a turning point, a story, a correction, or a teaching
- [ ] **Pillar? no** — work is a small ship, a quick opinion, a daily dev log, or an announcement
"""
    stub_path.write_text(stub_content, encoding="utf-8")
    return stub_path


def cmd_content_post(state: dict, args: list) -> int:
    """Set up the content brief: load strategy pages, find/create session,
    auto-classify, save .content-brief.json. Transitions IDLE → SESSION_CAPTURE.

    After this returns, the orchestrator (cmd_content_run) will continue
    chaining through SESSION_CAPTURE → COMPILE and set the compile handoff.
    """
    _deprecation_notice("content post", "content run")
    state["loop"] = "CONTENT"
    if state.get("current_state") != "IDLE":
        _force_reset_to_idle(state)
    if not transition(state, "SESSION_CAPTURE"):
        return 1
    print("═══ Content Pipeline: /post ═══")
    print()
    print("── Strategy Pages ──")
    strategy_pages = load_strategy_pages()
    loaded = sum(1 for sp in strategy_pages if sp["filepath"])
    for sp in strategy_pages:
        if sp["filepath"]:
            print(f"  \u2713 {sp['name']}.md \u2014 {sp['title']}")
        else:
            print(f"  \u2717 {sp['name']}.md \u2014 (not found)")
    print(f"  ({loaded}/{len(strategy_pages)} loaded)")
    print()
    source_kind = "session"
    source_text = None
    source_label = None
    if args:
        arg = args[0]
        if arg.startswith("@file:"):
            source_kind = "topic"
            filepath = arg[6:]
            try:
                source_text = Path(filepath).read_text(encoding="utf-8")
                source_label = filepath
            except Exception as e:
                print(f"ERROR: Cannot read file {filepath}: {e}")
                return 1
        else:
            source_kind = "topic"
            source_text = " ".join(args)
            source_label = source_text[:80]
    if source_kind == "session":
        latest = find_latest_session()
        is_stub = latest and "<fill in>" in latest.get("content", "")
        if latest and not is_stub:
            source_text = latest["content"]
            source_label = latest["filepath"]
            print(f"  \u2713 Using latest session: {latest['filepath']}")
        else:
            today = datetime.now().strftime("%Y-%m-%d")
            stub = _create_stub_session_log(today)
            print(f"  \u26a0 No session with content found \u2014 created: {stub.relative_to(VAULT)}")
            print()
    print(f"═══ Mode {'1' if source_kind != 'topic' else '2'}: {'Current Session' if source_kind != 'topic' else 'Topic'} ═══")
    print()
    if source_kind == "topic" and source_text:
        print(f"  Source: {source_label}")
        from classifier import classify
        classification = classify(source_text, config._load())
        try:
            from compiler import _infer_topic_kind
            topic_kind = _infer_topic_kind(source_text)
        except Exception:
            topic_kind = "announcement"
        print(f"  Topic kind: {topic_kind}    (compiler will use TOPIC MODE)")
        print(f"  Archetype: {classification.get('archetype', '?')} — {classification.get('archetype_label', '')}")
        print(f"  Vertical:  {classification.get('vertical', '?')}")
        print(f"  Funnel:    {classification.get('funnel_stage', '?')}")
        print(f"  ICP layer: {classification.get('icp_layer', '?')}")
        print()
    session = find_latest_session()
    if session:
        meta = session["meta"]
        print("── Latest Session ──")
        print(f"  File:   {session['filepath']}")
        print(f"  Topic:  {meta.get('topic', meta.get('title', '?'))}")
        print(f"  Pillar: {meta.get('pillar', '?')}")
        print(f"  Mode:   {meta.get('mode', '?')}")
    else:
        if source_kind == "session":
            print("  (No session found \u2014 stub created above.)")
    print()
    brief = {
        "session": session["filepath"] if session else None,
        "strategy_pages": [s["name"] for s in strategy_pages if s["filepath"]],
        "source": {"kind": source_kind, "text": source_text, "label": source_label, "topic_kind": None},
        "pre_write_gate_required": True,
        "core_insight": "",
        "meanings": {ax: "" for ax in config.compiler_meaning_axes},
        "selected_meaning": {"axis": "", "rationale": ""},
        "template_selection": {"recommendations": {}, "selected": {}},
        "strategy": {},
        "wizard": {"formats": [], "answered_at": None},
        "drafting": {"done": False, "files": []},
        "handoff": None,
    }
    if source_kind == "topic" and source_text:
        try:
            from compiler import _infer_topic_kind
            brief["source"]["topic_kind"] = _infer_topic_kind(source_text)
        except Exception:
            brief["source"]["topic_kind"] = "announcement"
    if source_kind == "topic" and source_text:
        from classifier import classify
        classification = classify(source_text, config._load())
        brief["strategy"] = classification
    elif session and session.get("content"):
        from classifier import classify
        classification = classify(session["content"], config._load())
        brief["strategy"] = classification
    write_brief(brief)
    print(f"── Brief saved to {CONTENT_BRIEF_FILE.relative_to(VAULT)} ──")
    print()
    print("  Re-invoke `engine.py content run` to advance through the pipeline.")
    return 0


def _print_compiler_display(state: dict) -> None:
    """Display the 8-step Compiler sequence (shared by post and compile commands)."""
    brief = json.loads(CONTENT_BRIEF_FILE.read_text())
    icp_path = VAULT / "concepts" / "icp-offer.md"
    if icp_path.exists():
        from icp import extract_icp_world, format_icp_world
        icp_md = icp_path.read_text()
        world = extract_icp_world(icp_md)
        icp_text = format_icp_world(world)
    else:
        icp_text = "(icp-offer.md not found)"
    session_evidence = ""
    session_path = brief.get("session")
    if session_path:
        sp = Path(session_path)
        if not sp.is_absolute():
            sp = VAULT / session_path
        if sp.exists():
            session_evidence = _load_session_evidence(sp)
    from compiler import format_compiler_sequence
    output = format_compiler_sequence(brief, icp_text, session_evidence, config.compiler_meaning_axes)
    print(output)
    print()
    print_next(state)


def cmd_content_compile(state: dict) -> int:
    _deprecation_notice("content compile", "content run")
    if not transition(state, "COMPILE"):
        return 1
    if not CONTENT_BRIEF_FILE.exists():
        print("ERROR: No content brief. Run 'engine.py content post' first.", file=sys.stderr)
        return 1
    _print_compiler_display(state)
    return 0


def _load_session_evidence(path: Path) -> str:
    content = path.read_text()
    evidence = []
    if content.startswith("---"):
        parts = content.split("---", 2)
        if len(parts) >= 2:
            for line in parts[1].strip().split("\n"):
                for key in ("title:", "decision:", "number:", "lesson:", "pattern:", "ship:"):
                    if line.strip().startswith(key):
                        evidence.append(f"  {line.strip()}")
                        break
    if content.startswith("---"):
        parts = content.split("---", 2)
        if len(parts) >= 2:
            try:
                fm_parsed = yaml.safe_load(parts[1])
                if isinstance(fm_parsed, dict):
                    rfm = fm_parsed.get("reader_failure_mode", {})
                    if isinstance(rfm, dict) and rfm.get("belief"):
                        evidence.append("  reader_failure_mode:")
                        evidence.append(f"    belief: {rfm['belief']}")
                        evidence.append(f"    consequence: {rfm['consequence']}")
                        evidence.append(f"    mapping: {rfm['mapping']}")
            except yaml.YAMLError:
                pass
    if "## Divergent Meanings Output" in content:
        dm_section = content.split("## Divergent Meanings Output", 1)[1]
        dm_section = dm_section.split("---", 1)[0] if "---" in dm_section else dm_section
        dm_section = dm_section.split("## ", 1)[0]
        for line in dm_section.strip().split("\n")[:15]:
            evidence.append(f"  {line}")
    return "\n".join(evidence)


def cmd_content_select(state: dict) -> int:
    _deprecation_notice("content select", "content run")
    if not transition(state, "SELECT"):
        return 1
    if not CONTENT_BRIEF_FILE.exists():
        print("ERROR: No content brief. Run 'engine.py content post' first.", file=sys.stderr)
        return 1
    brief = json.loads(CONTENT_BRIEF_FILE.read_text())
    core_insight = brief.get("core_insight", "").strip()
    selected = brief.get("selected_meaning", {})
    if not core_insight or not selected.get("axis"):
        print("ERROR: Compiler fields not populated. Run 'engine.py content compile' first.", file=sys.stderr)
        return 1
    # Run template selector
    registry_path = VAULT / "templates" / "registry" / "viral-templates.yaml"
    if registry_path.exists():
        import yaml as _yaml
        registry = _yaml.safe_load(registry_path.read_text()) or {}
        from selector import flatten_templates, select
        templates = flatten_templates(registry)
        context = {
            "archetype": brief.get("strategy", {}).get("archetype", ""),
            "meaning_axis": selected.get("axis", ""),
            "funnel_stage": brief.get("strategy", {}).get("funnel_stage", ""),
            "icp_layer": brief.get("strategy", {}).get("icp_layer", ""),
            "core_insight": core_insight[:120],
        }
        weights = config.template_weights
        top_n = config.template_top_n
        recommendations = {}
        for plat in sorted(set(t["platform"] for t in templates)):
            n = top_n.get(plat, 5)
            recs = select(templates, context, weights, top_n=n, platform_filter=plat)
            if recs:
                recommendations[plat] = recs
        print("── Template Recommendations ──")
        for plat, recs in recommendations.items():
            print(f"  {plat.upper()}:")
            for r in recs[:3]:
                print(f"    {r['name']} ({r['id']})  score={r['score']}")
        print()
        # Store in brief
        brief["template_selection"] = {
            "context": context,
            "recommendations": recommendations,
            "selected": {},
        }
        CONTENT_BRIEF_FILE.write_text(json.dumps(brief, indent=2))
        print("  Recommendations written to .content-brief.json template_selection.")
        print("  The LLM selects templates and writes template_selection.selected before drafting.")
    print()
    print_next(state)
    return 0


def cmd_content_draft(state: dict) -> int:
    _deprecation_notice("content draft", "content run")
    curr = state.get("current_state", "IDLE")
    # Auto-chain COMPILE → SELECT → DRAFTING
    if curr == "COMPILE":
        result = cmd_content_select(state)
        if result != 0:
            return result
        curr = state.get("current_state", "IDLE")
    if curr == "SELECT":
        if not transition(state, "DRAFTING"):
            return 1
    elif curr != "DRAFTING":
        print(f"ERROR: Cannot draft from {curr}. Run 'engine.py content post' first.", file=sys.stderr)
        return 1
    if not CONTENT_BRIEF_FILE.exists():
        print("ERROR: No content brief. Run 'engine.py content post' first.", file=sys.stderr)
        return 1
    brief = json.loads(CONTENT_BRIEF_FILE.read_text())
    # Validate compiler fields
    from compiler import validate_brief
    missing = validate_brief(brief, config.compiler_meaning_axes)
    if missing:
        print(f"ERROR: Compiler fields missing: {', '.join(missing)}", file=sys.stderr)
        print("  Pipeline halted: cannot draft without core insight from the Compiler.", file=sys.stderr)
        print()
        print_next(state)
        return 1
    print("  \u2713 Compiler fields populated \u2014 core_insight + 6 meanings + selection")
    print("── DRAFTING ──")
    print("  1. Use core_insight as the lens")
    print("  2. Use selected_meaning.axis for narrative frame")
    print("  3. Use selected_meaning.rationale for tone")
    print("  4. Draft posts using templates/")
    print("  5. Save to content/queue/ with full frontmatter")
    print()
    print_next(state)
    return 0


def cmd_content_banner(state: dict) -> int:
    from banner_tool import generate_for_queue
    generate_for_queue(VAULT)
    return 0


def cmd_content_gate(state: dict) -> int:
    if not transition(state, "GATE_CHECK"):
        return 1
    from gates import validate_draft
    queue_dir = QUEUE_DIR
    (VAULT / "logs").mkdir(parents=True, exist_ok=True)
    print("── Mechanical Gates (from rules.yaml) ──")
    if not queue_dir.exists() or not list(queue_dir.glob("*.md")):
        print("  No drafts in queue.")
        print_next(state)
        return 0
    rules = config._load()
    all_pass = True
    report_drafts = []
    for draft in sorted(queue_dir.glob("*.md")):
        content = draft.read_text()
        fm, body = parse_frontmatter(content)
        fm["_file"] = draft.name
        results = validate_draft(fm, body, rules)
        fails = sum(1 for ok, _ in results.values() if not ok)
        all_pass = all_pass and (fails == 0)
        print(f"\n═══ {draft.name} ═══")
        for name, (ok, msg) in sorted(results.items()):
            icon = "\u2713" if ok else "\u2717"
            print(f"  {icon} {name:25s} | {msg}")
        print(f"  Failures: {fails}/{len(results)}")
        report_drafts.append({
            "file": draft.name,
            "checks": {n: bool(ok) for n, (ok, _) in results.items()},
            "score": len(results) - fails,
            "max": len(results),
            "pass": fails == 0,
        })
    report = {"generated_at": datetime.now().isoformat(timespec="milliseconds"),
              "drafts": report_drafts}
    GATES_REPORT_FILE.parent.mkdir(parents=True, exist_ok=True)
    GATES_REPORT_FILE.write_text(json.dumps(report, indent=2))
    print(f"\n═══ Gates report: {GATES_REPORT_FILE} ═══")
    print(f"  {'ALL PASS' if all_pass else 'SOME FAILED'}")
    print()
    print_next(state)
    return 0 if all_pass else 1


def cmd_content_queue(state: dict) -> int:
    # Enforce gates
    if GATES_REPORT_FILE.exists():
        report = json.loads(GATES_REPORT_FILE.read_text())
        drafts_in_report = report.get("drafts", [])
        failed = [d["file"] for d in drafts_in_report if not d.get("pass")]
        if failed:
            print(f"ERROR: {len(failed)} draft(s) failed gates: {', '.join(failed)}", file=sys.stderr)
            print("  Run 'engine.py content gate' first.", file=sys.stderr)
            return 2
    if not transition(state, "QUEUE"):
        return 1
    if not QUEUE_DIR.exists():
        print("ERROR: content/queue/ does not exist.", file=sys.stderr)
        return 1
    drafts = sorted(QUEUE_DIR.glob("*.md"))
    if not drafts:
        print("ERROR: No drafts in content/queue/.", file=sys.stderr)
        return 1
    print(f"── Queue: {len(drafts)} draft(s) ──")
    for d in drafts:
        content = d.read_text()
        frontmatter = ""
        if content.startswith("---"):
            parts = content.split("---", 2)
            if len(parts) >= 2:
                frontmatter = parts[1].strip()
        print(f"  {d.name}")
        if frontmatter:
            for line in frontmatter.split("\n")[:5]:
                print(f"    {line.strip()}")
        print()
    print_next(state)
    return 0


def cmd_content_hold(state: dict) -> int:
    if not transition(state, "IDLE"):
        return 1
    if QUEUE_DIR.exists():
        drafts = sorted(QUEUE_DIR.glob("*.md"))
        print(f"  {len(drafts)} draft(s) remain in content/queue/")
        for d in drafts:
            print(f"    \u00b7 {d.name}")
    print("  State reset to IDLE. Run `/publish` later to publish.")
    return 0


def cmd_content_publish(state: dict, draft_id: str | None = None) -> int:
    state["loop"] = "CONTENT"
    curr = state.get("current_state", "IDLE")
    if curr == "DRAFTING":
        print("── Auto-Banner ──")
        cmd_content_banner(state)
        print()
        gate_result = cmd_content_gate(state)
        if gate_result != 0:
            print("  Gates failed. Fix drafts and retry.", file=sys.stderr)
            return 1
        curr = state.get("current_state", "IDLE")
    if curr == "GATE_CHECK":
        q_result = cmd_content_queue(state)
        if q_result != 0:
            return q_result
        curr = state.get("current_state", "IDLE")
    if curr not in ("QUEUE", "PUBLISHING"):
        print(f"ERROR: Cannot publish from {curr}. Run 'engine.py content run' first.", file=sys.stderr)
        return 1
    if draft_id == "all":
        draft_id = None
    import state_handlers
    return state_handlers.on_publish(
        state,
        draft_id,
        dry_run=False,
        auto_confirm=None,
    )


def cmd_content_archive(state: dict) -> int:
    if not transition(state, "ARCHIVING"):
        return 1
    print_next(state)
    return 0


def cmd_content_analyze(state: dict, args=None) -> int:
    """Pull Buffer engagement, update performance.json, re-rank templates."""
    state["loop"] = "CONTENT"
    if not transition(state, "ANALYZING_POST"):
        return 1
    import analyze
    summary = analyze.analyze_all(re_rank=True)
    if not summary.get("ok"):
        print(ui.status("fail", f"  analyze failed: {summary.get('reason', '?')}"))
        if summary.get("skipped"):
            print(ui.status("info", "  set BUFFER_ACCESS_TOKEN in .env to enable engagement pull"))
        transition(state, "COMPLETE_POST")
        transition(state, "IDLE")
        return 1
    print(ui.header("ANALYZE", subtitle="Engagement pull + re-rank", accent="cyan", width=80))
    print()
    print(ui.panel("ENGAGEMENT", [
        f"  Analyzed:           {summary['analyzed']} post(s)",
        f"  Skipped (no ids):   {summary['skipped_no_postids']}",
        f"  Skipped (not posted):{summary['skipped_not_posted']}",
        f"  Errors:             {len(summary['errors'])}",
    ], accent="bright_blue", width=80))
    if summary.get("re_ranked"):
        print()
        print(ui.panel("RE-RANK", [
            f"  Templates re-ranked: {summary.get('ranked_count', 0)}",
            f"  Curated:             templates/registry/curated/viral-templates.top.yaml",
            f"  Performance:         templates/registry/performance.json",
        ], accent="bright_green", width=80))
    if summary["errors"]:
        print()
        print(ui.status("warn", "  Errors:"))
        for name, err in summary["errors"][:5]:
            print(ui.status("fail", f"    {name}: {err}"))
    print()
    print(ui.ego("We ranked. We archived. We move on."))
    transition(state, "COMPLETE_POST")
    transition(state, "IDLE")
    return 0


# ─── Orchestrator + new creative-handoff commands ──────────────────────

def cmd_content_run(state: dict, args: list) -> int:
    """Run the content loop end-to-end. Single entry point for /post.

    The orchestrator advances the pipeline state by state, pausing at exactly
    two LLM handoffs (COMPILE, DRAFTING) and two human checkpoints
    (FORMAT_WIZARD, QUEUE/publish-wizard). Everything else is script.

    Usage:
        python3 scripts/engine.py content run [topic]

    The caller (LLM subagent or human) invokes this command whenever the
    brief or filesystem has changed. The orchestrator figures out what to do.
    """
    state["loop"] = "CONTENT"
    current = state.get("current_state", "IDLE")

    if current == "IDLE":
        # Set up the brief (session, strategy pages, classification).
        result = cmd_content_post(state, args)
        if result != 0:
            return result
        current = state.get("current_state", "IDLE")

    # Dispatch by state. Each step returns when it hits a handoff or checkpoint.
    steps = {
        "SESSION_CAPTURE": _step_session_capture,
        "COMPILE": _step_compile,
        "SELECT": _step_select,
        "FORMAT_WIZARD": _step_format_wizard,
        "DRAFTING": _step_drafting,
        "BANNER": _step_banner,
        "GATE_CHECK": _step_gate,
        "QUEUE": _step_queue,
        "PUBLISHING": _step_publishing,
        "ARCHIVING": _step_archiving,
        "ANALYZING_POST": _step_analyzing,
        "COMPLETE_POST": _step_complete,
    }
    fn = steps.get(current)
    if fn is None:
        print(f"ERROR: Unknown content state: {current}", file=sys.stderr)
        return 1
    return fn(state)


def _reset_to_idle(state: dict, reason: str) -> int:
    """Reset pipeline to IDLE, log reason, print next instructions."""
    prev = state.get("current_state", "?")
    state["current_state"] = "IDLE"
    write_wiki_state(state)
    save_checkpoint(state)
    brief = read_brief()
    if brief:
        clear_handoff(brief)
        write_brief(brief)
    log("WARN", "engine", "Content pipeline reset to IDLE",
        from_state=prev, reason=reason)
    print(f"  Reset to IDLE (was {prev}): {reason}")
    return 0


def _step_session_capture(state: dict) -> int:
    """SESSION_CAPTURE → COMPILE. The brief + session log are already set up
    by cmd_content_post. We just advance."""
    if not transition(state, "COMPILE"):
        return 1
    return _step_compile(state)


def _step_compile(state: dict) -> int:
    """COMPILE state. LLM handoff #1: LLM writes core_insight + 6 meanings
    + selected_meaning, then calls `content compile-write` to persist.
    """
    brief = read_brief()

    # TTL check
    if check_handoff_expired(brief):
        return _reset_to_idle(state, "compile handoff TTL expired (5 min)")

    handoff = get_active_handoff(brief)
    if handoff and (handoff.get("stage") or "").lower() == "compile":
        # Handoff in progress. Tell caller what to do.
        _print_compile_handoff(state, brief)
        return 0

    # No active compile handoff. Check if brief is already filled.
    valid, reason = validate_brief_for_transition(
        "SELECT", brief, config.compiler_meaning_axes
    )
    if valid:
        # LLM is done. Clear any stale handoff and advance.
        if (brief.get("handoff") or {}).get("stage") == "compile":
            clear_handoff(brief)
            write_brief(brief)
        return _step_select(state)

    # Set handoff and print instructions.
    set_handoff(brief, "compile")
    write_brief(brief)
    _print_compile_handoff(state, brief)
    return 0


def _print_compile_handoff(state: dict, brief: dict) -> None:
    """Print the 8-step Compiler sequence + handoff instructions."""
    source_kind = (brief.get("source") or {}).get("kind") or "session"
    topic_kind = (brief.get("source") or {}).get("topic_kind") or ""
    is_topic = source_kind == "topic"

    print()
    print(ui.header("HANDOFF 1/2  ·  COMPILE  ·  LLM creative work", accent="magenta", width=80))
    print()
    if is_topic:
        print(ui.status("info", f"The kernel is in COMPILE state. Compiler mode: TOPIC ({topic_kind})."))
        print(ui.status("arrow", "Q1 POST TYPE → Q2 READER OUTCOME → Q3 6 ANGLES → Q4 PICK → Q5 INSIGHT → Q6 HOOK+CTA"))
    else:
        print(ui.status("info", "The kernel is in COMPILE state. The LLM runs the 8-step Compiler."))
        print(ui.status("arrow", "LOAD ICP → SIMULATE → EVIDENCE → MAP → 6 MEANINGS → SELECT → INSIGHT → WRITE"))
    print()
    compile_cmd = (
        "python3 scripts/engine.py content compile-write \\\n"
        "  --core-insight \"<one sentence>\" \\\n"
        "  --meaning-systemic \"<...>\" \\\n"
        "  --meaning-behavioral \"<...>\" \\\n"
        "  --meaning-philosophical \"<...>\" \\\n"
        "  --meaning-contrarian \"<...>\" \\\n"
        "  --meaning-leverage \"<...>\" \\\n"
        "  --meaning-human \"<...>\" \\\n"
        "  --selected-axis <systemic|behavioral|philosophical|contrarian|leverage|human> \\\n"
        "  --selected-rationale \"<...>\""
    )
    print(ui.copyable(compile_cmd, label="WRITE"))
    print()
    print(ui.status("warn", f"Handoff TTL: {HANDOFF_TTL_MINUTES} minutes. After that, pipeline resets to IDLE."))
    print()
    if brief.get("_compiler_displayed"):
        return
    _print_compiler_display(state)
    print()
    if is_topic:
        print(ui.ego("Topic is the subject. Announce it. Name what shipped. End with a verb."))
    else:
        print(ui.ego("Eight steps. One sentence. That is the work."))
    print()
    print(ui.copyable("python3 scripts/engine.py content run", label="WHEN DONE"))
    brief["_compiler_displayed"] = True
    write_brief(brief)


def _step_select(state: dict) -> int:
    """SELECT state. Run template selection, advance to FORMAT_WIZARD."""
    # Run the existing select command — it does the SELECT transition and writes
    # brief.template_selection.recommendations.
    result = cmd_content_select(state)
    if result != 0:
        return result
    # Then transition to FORMAT_WIZARD for the human checkpoint.
    if not transition(state, "FORMAT_WIZARD"):
        return 1
    return _step_format_wizard(state)


def _step_format_wizard(state: dict) -> int:
    """FORMAT_WIZARD state. Human checkpoint: pick formats via wizard."""
    brief = read_brief()
    valid, _ = validate_brief_for_transition("DRAFTING", brief)
    if not valid:
        # Topic-mode default: prefill x + linkedin + blog for an announcement campaign.
        # User can still override.
        source_kind = (brief.get("source") or {}).get("kind") or "session"
        if source_kind == "topic":
            wizard = brief.get("wizard") or {}
            if not wizard.get("formats"):
                wizard["formats"] = ["x", "linkedin", "blog"]
                wizard["answered_at"] = datetime.now().isoformat(timespec="seconds")
                wizard["topic_mode_default"] = True
                brief["wizard"] = wizard
                write_brief(brief)
                print()
                print(ui.status("info", "Topic mode detected — defaulting formats to [x, linkedin, blog] (announcement campaign)."))
                print(ui.status("arrow", "Override: `spiel content wizard` if you want a different set."))
        else:
            from wizard import format_wizard
            ok, msg = format_wizard()
            if not ok:
                print(f"ERROR: {msg}", file=sys.stderr)
                return 1
            brief = read_brief()
            if (brief.get("wizard") or {}).get("hold"):
                return _reset_to_idle(state, "user held at format wizard")

    # Transition FORMAT_WIZARD → DRAFTING.
    if not transition(state, "DRAFTING"):
        return 1
    return _step_drafting(state)


def _step_drafting(state: dict) -> int:
    """DRAFTING state. LLM handoff #2: LLM writes draft files via
    `content draft-write --file <path>`, then calls `content draft-done`.
    """
    brief = read_brief()

    if check_handoff_expired(brief):
        return _reset_to_idle(state, "drafting handoff TTL expired (5 min)")

    handoff = get_active_handoff(brief)
    if handoff and (handoff.get("stage") or "").lower() == "draft":
        # Handoff in progress
        if (brief.get("drafting") or {}).get("done"):
            # LLM said done. Clear handoff, transition DRAFTING → BANNER.
            clear_handoff(brief)
            drafting = brief.get("drafting") or {}
            brief["drafting"] = {"done": False, "files": drafting.get("files", [])}
            write_brief(brief)
            if not transition(state, "BANNER"):
                return 1
            return _step_banner(state)
        _print_draft_handoff(state, brief)
        return 0

    # No active draft handoff. Check if LLM already wrote drafts and marked done.
    drafting = brief.get("drafting") or {}
    if drafting.get("done"):
        queue_files = list(QUEUE_DIR.glob("*.md")) if QUEUE_DIR.exists() else []
        if queue_files:
            clear_handoff(brief)
            brief["drafting"] = {"done": False, "files": [f.name for f in queue_files]}
            write_brief(brief)
            if not transition(state, "BANNER"):
                return 1
            return _step_banner(state)

    # No active handoff, not done. Set handoff.
    set_handoff(brief, "draft")
    write_brief(brief)
    _print_draft_handoff(state, brief)
    return 0


def _print_draft_handoff(state: dict, brief: dict) -> None:
    formats = (brief.get("wizard") or {}).get("formats") or ["x", "linkedin", "blog"]
    core = (core_insight if (core_insight := (brief.get("core_insight") or "").strip()) else "(empty)")
    source_kind = (brief.get("source") or {}).get("kind") or "session"
    topic_kind = (brief.get("source") or {}).get("topic_kind") or ""
    print()
    print(ui.header("HANDOFF 2/2  ·  DRAFT  ·  LLM creative work", accent="magenta", width=80))
    print()
    mode_label = "TOPIC" if source_kind == "topic" else "SESSION"
    body = [
        f"Compiler mode: {mode_label}" + (f" ({topic_kind})" if topic_kind else ""),
        f"Core insight:  {core[:160]}{'...' if len(core) > 160 else ''}",
        f"Formats:       {', '.join(formats)}",
        f"Handoff TTL:   {HANDOFF_TTL_MINUTES} minutes",
    ]
    print(ui.panel("BRIEF", body, accent="bright_blue", width=80))
    print()
    # Surface top-3 ranked templates per platform so the LLM uses the right shape.
    recs = ((brief.get("template_selection") or {}).get("recommendations") or {})
    if recs:
        print(ui.status("info", "Top ranked templates per format (use these as your structural shape):"))
        print()
        for plat in formats:
            plat_recs = recs.get(plat) or []
            if not plat_recs:
                continue
            print(f"  {plat.upper()}:")
            for r in plat_recs[:3]:
                hook_line = (r.get("hook") or "").split("\n")[0][:90]
                print(f"    • {r.get('id'):24s}  {r.get('name','')}")
                if hook_line:
                    print(f"      hook: {hook_line}")
            print()
    print(ui.status("arrow", "For each draft, write the file then register it:"))
    print()
    print(ui.copyable(
        "python3 scripts/engine.py content draft-write \\\n  --file content/queue/<filename>.md",
        label="REGISTER ONE DRAFT",
    ))
    print()
    print(ui.status("arrow", "When ALL drafts are written, signal completion:"))
    print()
    print(ui.copyable(
        "python3 scripts/engine.py content draft-done",
        label="SIGNAL DONE",
    ))
    print()
    print(ui.status("info", "Drafts must include full frontmatter (title, platform, etc.)"))
    print(ui.status("info", "See templates/ for structure."))
    if source_kind == "topic":
        print(ui.status("info", "Topic mode: name what shipped, mention partners, end with a verb."))
    print()
    print(ui.ego("Three platforms. One insight. Ship it."))


def _step_banner(state: dict) -> int:
    """BANNER state. Auto-generate banners, advance to GATE_CHECK."""
    from banner_tool import generate_for_queue
    generate_for_queue(VAULT)

    if not transition(state, "GATE_CHECK"):
        return 1
    return _step_gate(state)


def _step_gate(state: dict) -> int:
    """GATE_CHECK state. Run mechanical gates, advance to QUEUE or DRAFTING (re-revise)."""
    from gates import validate_draft
    if not QUEUE_DIR.exists() or not list(QUEUE_DIR.glob("*.md")):
        return _reset_to_idle(state, "no drafts in queue at gate check")

    rules = config._load()
    all_pass = True
    report_drafts = []
    print("── Mechanical Gates ──")
    for draft in sorted(QUEUE_DIR.glob("*.md")):
        content = draft.read_text()
        fm, body = parse_frontmatter(content)
        fm["_file"] = draft.name
        results = validate_draft(fm, body, rules)
        fails = sum(1 for ok, _ in results.values() if not ok)
        all_pass = all_pass and (fails == 0)
        print(f"\n═══ {draft.name} ═══")
        for name, (ok, msg) in sorted(results.items()):
            icon = "✓" if ok else "✗"
            print(f"  {icon} {name:25s} | {msg}")
        print(f"  Failures: {fails}/{len(results)}")
        report_drafts.append({
            "file": draft.name,
            "checks": {n: bool(ok) for n, (ok, _) in results.items()},
            "score": len(results) - fails,
            "max": len(results),
            "pass": fails == 0,
        })

    report = {
        "generated_at": datetime.now().isoformat(timespec="milliseconds"),
        "drafts": report_drafts,
    }
    GATES_REPORT_FILE.parent.mkdir(parents=True, exist_ok=True)
    GATES_REPORT_FILE.write_text(json.dumps(report, indent=2))
    print(f"\n═══ Gates report: {GATES_REPORT_FILE} ═══")
    print(f"  {'ALL PASS' if all_pass else 'SOME FAILED'}")

    if not all_pass:
        # Stay at DRAFTING for revision. Clear handoff so LLM can re-engage.
        if transition(state, "DRAFTING"):
            brief = read_brief()
            clear_handoff(brief)
            set_handoff(brief, "draft")
            brief["drafting"] = {"done": False, "files": [], "needs_revision": [
                d["file"] for d in report_drafts if not d["pass"]
            ]}
            write_brief(brief)
            print()
            print("═══ HANDOFF 2/2 (revision): DRAFT (LLM) ═══")
            print("  Gates failed for:")
            for d in report_drafts:
                if not d["pass"]:
                    print(f"    ✗ {d['file']}")
            print("  Re-invoke `content run` after fixing the drafts.")
        return 1

    if not transition(state, "QUEUE"):
        return 1
    return _step_queue(state)


def _step_queue(state: dict) -> int:
    """QUEUE state. Human checkpoint: run publish wizard."""
    from wizard import publish_wizard
    ok, msg = publish_wizard(QUEUE_DIR)
    if not ok:
        print(f"ERROR: {msg}", file=sys.stderr)
        return 1

    brief = read_brief()
    decisions = (brief.get("wizard") or {}).get("publish_decisions") or {}
    if not (brief.get("wizard") or {}).get("publish_confirmed"):
        return _reset_to_idle(state, "user held drafts at publish wizard")

    # Apply decisions: collect files to publish
    to_publish = [name for name, d in decisions.items() if d == "publish"]
    to_hold = [name for name, d in decisions.items() if d == "hold"]
    to_edit = [name for name, d in decisions.items() if d == "edit"]
    print()
    print(f"  Publish: {len(to_publish)}  Hold: {len(to_hold)}  Edit: {len(to_edit)}")
    if to_publish:
        # Use the existing publish command with first file as anchor
        first = to_publish[0]
        print(f"  Use `engine.py content publish {first}` to dispatch.")
        print(f"  Or: `engine.py content publish all` (after per-draft review).")
    if to_hold:
        print(f"  Held drafts stay in {QUEUE_DIR.relative_to(VAULT)}/")
    return _reset_to_idle(state, "queue stage paused for explicit publish dispatch")


def _step_publishing(state: dict) -> int:
    return cmd_content_publish(state, None)


def _step_archiving(state: dict) -> int:
    return cmd_content_archive(state)


def _step_analyzing(state: dict) -> int:
    return cmd_content_analyze(state)


def _step_complete(state: dict) -> int:
    return cmd_content_complete(state)


def cmd_content_compile_write(state: dict, args) -> int:
    """LLM persists Compiler output (core_insight + 6 meanings + selection).

    Arguments: --core-insight, --meaning-<axis>, --selected-axis, --selected-rationale.
    """
    import argparse
    p = argparse.ArgumentParser(prog="engine.py content compile-write")
    p.add_argument("--core-insight", required=True)
    for ax in MEANING_AXES_DEFAULT:
        p.add_argument(f"--meaning-{ax}", default="", dest=f"meaning_{ax}")
    p.add_argument("--selected-axis", required=True)
    p.add_argument("--selected-rationale", required=True)
    try:
        ns = p.parse_args(args)
    except SystemExit as e:
        return int(e.code or 1)

    from compiler import compile_write
    meanings = {ax: getattr(ns, f"meaning_{ax}") for ax in MEANING_AXES_DEFAULT}
    ok, msg = compile_write(
        core_insight=ns.core_insight,
        meanings=meanings,
        selected_axis=ns.selected_axis,
        selected_rationale=ns.selected_rationale,
        meaning_axes=config.compiler_meaning_axes,
    )
    if not ok:
        print(f"ERROR: {msg}", file=sys.stderr)
        return 1
    print(f"  ✓ {msg}")
    return 0


def cmd_content_draft_write(state: dict, args) -> int:
    """LLM registers a draft file written to content/queue/.

    Validates frontmatter. Does NOT advance state — call `content draft-done`
    when all drafts are written.

    Arguments: --file <path>
    """
    import argparse
    p = argparse.ArgumentParser(prog="engine.py content draft-write")
    p.add_argument("--file", required=True, help="Path to draft markdown file")
    try:
        ns = p.parse_args(args)
    except SystemExit as e:
        return int(e.code or 1)

    fpath = Path(ns.file)
    if not fpath.is_absolute():
        fpath = VAULT / fpath
    if not fpath.exists():
        print(f"ERROR: file not found: {fpath}", file=sys.stderr)
        return 1
    if QUEUE_DIR not in fpath.parents and fpath.parent != QUEUE_DIR:
        print(f"ERROR: file must be in {QUEUE_DIR}, got {fpath}", file=sys.stderr)
        return 1

    text = fpath.read_text()
    fm, body = parse_frontmatter(text)
    missing = [k for k in ("title", "platform") if k not in fm]
    if missing:
        print(f"ERROR: frontmatter missing required fields: {missing}", file=sys.stderr)
        return 1
    if not body.strip():
        print(f"ERROR: draft body is empty", file=sys.stderr)
        return 1

    # Register in brief
    brief = read_brief()
    drafting = brief.get("drafting") or {"done": False, "files": []}
    if fpath.name not in drafting.get("files", []):
        drafting.setdefault("files", []).append(fpath.name)
    brief["drafting"] = drafting
    write_brief(brief)
    print(f"  ✓ registered {fpath.name} (drafts so far: {len(drafting['files'])})")
    return 0


def cmd_content_draft_done(state: dict, args) -> int:
    """LLM signals drafting is complete. Kernel will advance to BANNER on
    next `content run`."""
    brief = read_brief()
    if not brief:
        print("ERROR: no brief", file=sys.stderr)
        return 1
    drafting = brief.get("drafting") or {"done": False, "files": []}
    if not drafting.get("files"):
        print("ERROR: no drafts registered. Use `content draft-write` first.", file=sys.stderr)
        return 1
    drafting["done"] = True
    brief["drafting"] = drafting
    write_brief(brief)
    print(f"  ✓ drafting complete: {len(drafting['files'])} draft(s) ready for BANNER")
    return 0


def cmd_content_wizard(state: dict, args) -> int:
    """Run the format wizard. Records the user's format choice in the brief."""
    from wizard import format_wizard
    about = " ".join(args) if args else ""
    ok, msg = format_wizard(about=about)
    if not ok:
        print(f"ERROR: {msg}", file=sys.stderr)
        return 1
    print(f"  ✓ {msg}")
    return 0


def cmd_content_publish_wizard(state: dict, args) -> int:
    """Run the per-draft publish wizard."""
    from wizard import publish_wizard
    ok, msg = publish_wizard(QUEUE_DIR)
    if not ok:
        print(f"ERROR: {msg}", file=sys.stderr)
        return 1
    print(f"  ✓ {msg}")
    return 0


def cmd_content_session_fill(state: dict, args) -> int:
    """Write into the most recent session log. Args: --topic, --bullet X (repeatable)."""
    import argparse
    p = argparse.ArgumentParser(prog="engine.py content session-fill")
    p.add_argument("--topic", default="")
    p.add_argument("--bullet", action="append", default=[], help="What we did (repeatable)")
    p.add_argument("--decision", action="append", default=[])
    p.add_argument("--lesson", action="append", default=[])
    p.add_argument("--number", action="append", default=[])
    p.add_argument("--path", default="", help="Specific session log path")
    try:
        ns = p.parse_args(args)
    except SystemExit as e:
        return int(e.code or 1)

    if ns.path:
        spath = Path(ns.path)
        if not spath.is_absolute():
            spath = VAULT / spath
    else:
        session = find_latest_session()
        if not session:
            print("ERROR: no session log found and --path not given", file=sys.stderr)
            return 1
        spath = VAULT / session["filepath"]

    if not spath.exists():
        print(f"ERROR: session log not found: {spath}", file=sys.stderr)
        return 1

    text = spath.read_text()
    # Parse frontmatter
    fm: dict = {}
    if text.startswith("---"):
        parts = text.split("---", 2)
        if len(parts) >= 2:
            try:
                import yaml
                fm = yaml.safe_load(parts[1]) or {}
            except Exception:
                fm = {}

    if ns.topic:
        fm["title"] = ns.topic
    if not fm.get("status"):
        fm["status"] = "in-progress"

    # Build body
    new_body = []
    if ns.bullet:
        new_body.append("## What we did (3-7 bullets)")
        new_body.append("")
        for b in ns.bullet:
            new_body.append(f"- {b}")
        new_body.append("")
    if ns.decision:
        new_body.append("## Decisions made")
        new_body.append("")
        for d in ns.decision:
            new_body.append(f"- {d}")
        new_body.append("")
    if ns.lesson:
        new_body.append("## Lessons learned")
        new_body.append("")
        for l in ns.lesson:
            new_body.append(f"- {l}")
        new_body.append("")
    if ns.number:
        new_body.append("## Numbers")
        new_body.append("")
        for n in ns.number:
            new_body.append(f"- {n}")
        new_body.append("")

    # Determine if this is a stub session
    is_stub = "<fill in>" in text or "# Session:" in text and "## What we did (3-7 bullets)\n\n-" in text

    if is_stub:
        # Replace the stub content with what the LLM provided
        body = "\n".join(new_body).strip()
    elif "## What we did" in text or "## Decisions made" in text:
        # Existing non-stub — inject the new sections above the existing body
        rest = text.split("---", 2)[-1] if text.startswith("---") else text
        rest = rest.replace("<fill in>", "").strip()
        body = "\n".join(new_body) + "\n" + rest
    else:
        body = "\n".join(new_body).strip()

    write_frontmatter(spath, fm, body)
    print(f"  ✓ wrote {spath.relative_to(VAULT)}")
    return 0


def cmd_content_complete(state: dict) -> int:
    if not transition(state, "COMPLETE_POST"):
        return 1
    if not transition(state, "IDLE"):
        return 1
    print("Content pipeline complete. System back to IDLE.")
    return 0


def cmd_content_rank_templates(state: dict) -> int:
    """Re-run the template ranker using current performance data."""
    import template_ranker
    print(ui.header("RANK TEMPLATES", subtitle="Re-score the registry using current performance data", accent="cyan", width=80))
    print()
    result = template_ranker.run()
    if not result.get("ok"):
        print(ui.status("fail", f"  ranking failed: {result.get('reason', '?')}"))
        return 1
    print(ui.panel("RANK RESULT", [
        f"  Templates ranked:    {result.get('n_ranked', 0)}",
        f"  Templates kept:      {result.get('n_kept', 0)}",
        f"  Curated file:        {result.get('curated', '')}",
        f"  Archive:             {result.get('archive', '')}",
    ], accent="bright_green", width=80))
    print()
    print(ui.ego("We ranked. We archived. We move on."))
    return 0


def cmd_content_queue_list(state: dict) -> int:
    if not QUEUE_DIR.exists():
        print("No queue directory.")
        return 0
    drafts = sorted(QUEUE_DIR.glob("*.md"))
    if not drafts:
        print("Queue is empty.")
        return 0
    from datetime import datetime, timedelta

    def read_meta(path):
        content = path.read_text()
        if not content.startswith("---"):
            return {}
        parts = content.split("---", 2)
        if len(parts) < 2:
            return {}
        try:
            return yaml.safe_load(parts[1]) or {}
        except yaml.YAMLError:
            return {}

    parsed = []
    for d in drafts:
        meta = read_meta(d)
        platform = (meta.get("platform") or "").lower()
        if not platform:
            if "tweet" in d.name or "-x-" in d.name:
                platform = "x"
            elif "linkedin" in d.name:
                platform = "linkedin"
            elif "pillar" in d.name:
                platform = "pillar"
            elif "blog" in d.name:
                platform = "blog"
            else:
                platform = "other"
        status = meta.get("status", "draft")
        if meta.get("scheduled"):
            status = "scheduled"
        if meta.get("posted_at"):
            status = "published"
        parsed.append({
            "name": d.name, "platform": platform, "status": status,
            "standalone": meta.get("standalone_test", ""),
            "copy_gate": meta.get("copywriting_gate", ""),
            "scheduled": meta.get("scheduled"),
        })
    posted_this_week = 0
    now = datetime.now()
    week_ago = now - timedelta(days=7)
    if POSTED_DIR.exists():
        for d in sorted(POSTED_DIR.glob("*.md")):
            meta = read_meta(d)
            if meta.get("posted_at"):
                try:
                    dt = datetime.strptime(str(meta["posted_at"])[:10], "%Y-%m-%d")
                    if dt >= week_ago:
                        posted_this_week += 1
                except ValueError:
                    pass
    groups: dict = {}
    for p in parsed:
        groups.setdefault(p["platform"], []).append(p)
    print("── Content Queue ──")
    print(f"  Total: {len(parsed)} draft{'s' if len(parsed) != 1 else ''}")
    for plat in ["x", "linkedin", "blog", "offer", "other"]:
        items = groups.get(plat, [])
        bar = "\u2500" * 30
        print(f"\u2500\u2500 {plat.upper()} ({len(items)}) {bar}")
        if not items:
            print("  (none)")
        else:
            for item in items:
                print(f"  \u00b7 {item['name']}  [{item['status']}]")
    print(f"── Posted this week: {posted_this_week}")
    return 0


# ─── Recovery ──────────────────────────────────────────────────────────

def cmd_recover(state: dict) -> int:
    current = state.get("current_state", "IDLE")
    loop = state.get("loop", "WIKI")
    if current == "IDLE":
        cp = load_checkpoint(loop)
        if cp:
            print(f"System is IDLE but has a stale checkpoint from {cp.get('timestamp', 'unknown')}.")
            print(f"  Previous state: {cp.get('state')}")
            if confirm("Clear stale checkpoint?"):
                clear_checkpoint(loop)
                print("Checkpoint cleared.")
        else:
            print("System is already IDLE. No recovery needed.")
        return 0
    print(f"System is stuck in: {current} ({loop} loop)")
    cp = load_checkpoint(loop)
    if cp:
        print(f"Checkpoint from: {cp.get('timestamp', 'unknown')}")
    print("Recovery: run 'engine.py wiki reset' to force IDLE.")
    return 0


def confirm(prompt: str) -> bool:
    try:
        response = input(f"{prompt} (y/N): ")
        return response.lower() == "y"
    except (EOFError, KeyboardInterrupt):
        print()
        return False


# ─── Main CLI ──────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Spiel Engine State Machine Controller",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("status", help="Show current system state")

    wiki = sub.add_parser("wiki", help="Wiki management commands")
    wiki_sub = wiki.add_subparsers(dest="wiki_cmd")
    ext = wiki_sub.add_parser("extract", help="Start INGEST state")
    ext.add_argument("source", nargs="*", help="Source file(s) in raw/")
    wiki_sub.add_parser("analyze")
    wiki_sub.add_parser("reconcile")
    wiki_sub.add_parser("link")
    wiki_sub.add_parser("index")
    wiki_sub.add_parser("validate")
    wiki_sub.add_parser("complete")
    wiki_sub.add_parser("health", help="Read-only health check")
    wiki_sub.add_parser("reset", help="Force reset to IDLE")

    content = sub.add_parser("content", help="Content posting commands")
    content_sub = content.add_subparsers(dest="content_cmd")
    post = content_sub.add_parser("post", help="Start SESSION_CAPTURE (legacy entry)")
    post.add_argument("about", nargs="*")
    run_p = content_sub.add_parser("run", help="Orchestrator: run the content loop end-to-end")
    run_p.add_argument("about", nargs="*")
    cw = content_sub.add_parser("compile-write", help="LLM writes Compiler output (core_insight, meanings, selection)")
    cw.add_argument("--core-insight", required=True)
    for _ax in MEANING_AXES_DEFAULT:
        cw.add_argument(f"--meaning-{_ax}", default="", dest=f"meaning_{_ax}")
    cw.add_argument("--selected-axis", required=True)
    cw.add_argument("--selected-rationale", required=True)
    dw = content_sub.add_parser("draft-write", help="LLM registers one drafted file")
    dw.add_argument("--file", required=True, help="Path to draft markdown file")
    content_sub.add_parser("draft-done", help="LLM signals drafting is complete")
    wz = content_sub.add_parser("wizard", help="Run the format-selection wizard")
    wz.add_argument("about", nargs="*")
    content_sub.add_parser("publish-wizard", help="Run the per-draft publish wizard")
    sf = content_sub.add_parser("session-fill", help="Write into a session log")
    sf.add_argument("--topic", default="")
    sf.add_argument("--bullet", action="append", default=[])
    sf.add_argument("--decision", action="append", default=[])
    sf.add_argument("--lesson", action="append", default=[])
    sf.add_argument("--number", action="append", default=[])
    sf.add_argument("--path", default="")
    content_sub.add_parser("compile", help="Run Content Engine Compiler (legacy single-step)")
    content_sub.add_parser("select", help="Template selection (legacy)")
    content_sub.add_parser("draft", help="Begin drafting (legacy)")
    content_sub.add_parser("banner", help="Auto-generate banners")
    content_sub.add_parser("gate", help="Run mechanical gates")
    content_sub.add_parser("queue", help="View queue")
    content_sub.add_parser("hold", help="QUEUE \u2192 IDLE")
    pub = content_sub.add_parser("publish", help="Publish draft")
    pub.add_argument("draft_id", nargs="?", help="Draft filename or 'all'")
    content_sub.add_parser("archive")
    content_sub.add_parser("analyze")
    content_sub.add_parser("complete")
    content_sub.add_parser("rank-templates", help="Re-run the template ranker")

    sub.add_parser("queue", help="Show queue contents")
    sub.add_parser("recover", help="Diagnose stuck state")

    log_parser = sub.add_parser("log", help="View recent log entries")
    log_parser.add_argument("--days", type=int, default=7)
    log_parser.add_argument("--level")
    log_parser.add_argument("--source")
    log_parser.add_argument("--tail", type=int, default=30)

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        return 0

    state = read_wiki_state()
    auto_request_id("eng")

    try:
        if args.command == "status":
            return cmd_status(state)

        elif args.command == "wiki":
            if not args.wiki_cmd:
                print("Usage: engine.py wiki {extract|analyze|reconcile|link|index|validate|complete|health|reset}")
                return 1
            if not acquire_lock():
                print("ERROR: Another pipeline is running (lock file present).", file=sys.stderr)
                return 1
            try:
                state = read_wiki_state()
                state["loop"] = "WIKI"
                cmds = {
                    "extract": lambda: cmd_wiki_extract(state, args.source),
                    "analyze": lambda: cmd_wiki_analyze(state),
                    "reconcile": lambda: cmd_wiki_reconcile(state),
                    "link": lambda: cmd_wiki_link(state),
                    "index": lambda: cmd_wiki_index(state),
                    "validate": lambda: cmd_wiki_validate(state),
                    "complete": lambda: cmd_wiki_complete(state),
                    "health": lambda: cmd_wiki_health(state),
                    "reset": lambda: cmd_wiki_reset(state),
                }
                fn = cmds.get(args.wiki_cmd)
                if fn:
                    return fn()
                return 1
            finally:
                release_lock()

        elif args.command == "content":
            if not args.content_cmd:
                print("Usage: engine.py content {run|post|compile-write|draft-write|draft-done|wizard|publish-wizard|session-fill|compile|select|draft|banner|gate|queue|publish|archive|analyze|complete}")
                return 1
            if not acquire_lock():
                print("ERROR: Another pipeline is running (lock file present).", file=sys.stderr)
                return 1
            try:
                state = read_wiki_state()
                state["loop"] = "CONTENT"

                def _compile_write_args():
                    cw_args = [
                        "--core-insight", args.core_insight,
                    ]
                    for ax in MEANING_AXES_DEFAULT:
                        v = getattr(args, f"meaning_{ax}", "") or ""
                        cw_args += [f"--meaning-{ax}", v]
                    cw_args += ["--selected-axis", args.selected_axis,
                                "--selected-rationale", args.selected_rationale]
                    return cw_args

                def _draft_write_args():
                    return ["--file", args.file]

                def _wizard_args():
                    return args.about or []

                def _session_fill_args():
                    sf_args = []
                    if args.topic:
                        sf_args += ["--topic", args.topic]
                    for b in args.bullet or []:
                        sf_args += ["--bullet", b]
                    for d in args.decision or []:
                        sf_args += ["--decision", d]
                    for l in args.lesson or []:
                        sf_args += ["--lesson", l]
                    for n in args.number or []:
                        sf_args += ["--number", n]
                    if args.path:
                        sf_args += ["--path", args.path]
                    return sf_args

                cmds = {
                    "post": lambda: cmd_content_post(state, args.about or []),
                    "run": lambda: cmd_content_run(state, args.about or []),
                    "compile-write": lambda: cmd_content_compile_write(state, _compile_write_args()),
                    "draft-write": lambda: cmd_content_draft_write(state, _draft_write_args()),
                    "draft-done": lambda: cmd_content_draft_done(state, []),
                    "wizard": lambda: cmd_content_wizard(state, _wizard_args()),
                    "publish-wizard": lambda: cmd_content_publish_wizard(state, []),
                    "session-fill": lambda: cmd_content_session_fill(state, _session_fill_args()),
                    "compile": lambda: cmd_content_compile(state),
                    "select": lambda: cmd_content_select(state),
                    "draft": lambda: cmd_content_draft(state),
                    "banner": lambda: cmd_content_banner(state),
                    "gate": lambda: cmd_content_gate(state),
                    "queue": lambda: cmd_content_queue(state),
                    "hold": lambda: cmd_content_hold(state),
                    "publish": lambda: cmd_content_publish(state, args.draft_id),
                    "archive": lambda: cmd_content_archive(state),
                    "analyze": lambda: cmd_content_analyze(state),
                    "complete": lambda: cmd_content_complete(state),
                    "rank-templates": lambda: cmd_content_rank_templates(state),
                }
                fn = cmds.get(args.content_cmd)
                if fn:
                    return fn()
                print(f"Unknown content command: {args.content_cmd}", file=sys.stderr)
                return 1
            finally:
                release_lock()

        elif args.command == "queue":
            return cmd_content_queue_list(state)

        elif args.command == "recover":
            return cmd_recover(state)

        elif args.command == "log":
            from engine_serial import print_logs
            print_logs(days=args.days, level=args.level, source=args.source, tail=args.tail)
            return 0

    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
