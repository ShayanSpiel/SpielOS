#!/usr/bin/env python3
"""spiel-engine — State machine controller for TheSpielEngine.

Validates state transitions, runs automated actions, and reports status.
The LLM performs creative steps (analyzing, reconciling, drafting); this
engine enforces the sequence.

Usage:
    ./scripts/engine.py status                  # Show current system state
    ./scripts/engine.py wiki extract <file>     # Start INGEST state
    ./scripts/engine.py wiki analyze            # Mark ANALYZE complete
    ./scripts/engine.py wiki reconcile          # Mark RECONCILE complete
    ./scripts/engine.py wiki link               # Run LINKING sub-step
    ./scripts/engine.py wiki index              # Rebuild index.md
    ./scripts/engine.py wiki validate           # Run health checks
    ./scripts/engine.py wiki complete           # Mark pipeline complete
    ./scripts/engine.py wiki health             # Run read-only health checks
    ./scripts/engine.py wiki reset              # Force reset to IDLE
    ./scripts/engine.py content post [about]    # Start SESSION_CAPTURE
    ./scripts/engine.py content banner          # Auto-generate banners for queue drafts
    ./scripts/engine.py content compile         # Start ICP_WORLD_BUILD (Content Engine Compiler)
    ./scripts/engine.py content queue           # Show queue
    ./scripts/engine.py content hold            # QUEUE → IDLE, keep drafts for later
    ./scripts/engine.py content publish <id>    # Publish draft
    ./scripts/engine.py recover                 # Diagnose + fix stuck state
"""

import argparse
import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import yaml

from state_machine import (
    StateMachine,
    read_wiki_state,
    write_wiki_state,
    acquire_lock,
    release_lock,
    VAULT,
)

from logger import log, log_err, logged, auto_request_id, get_request_id

WIKI_SM = StateMachine("WIKI")
CONTENT_SM = StateMachine("CONTENT")
CONTENT_BRIEF_FILE = VAULT / ".content-brief.json"

# ─── Raw Manifest (dedup) ────────────────────────────────────────────────────

RAW_MANIFEST_FILE = VAULT / ".raw-manifest.json"


@logged()
def read_raw_manifest() -> dict:
    if not RAW_MANIFEST_FILE.exists():
        return {"processed": {}}
    try:
        return json.loads(RAW_MANIFEST_FILE.read_text())
    except (json.JSONDecodeError, OSError):
        return {"processed": {}}


@logged()
def write_raw_manifest(manifest: dict) -> None:
    RAW_MANIFEST_FILE.write_text(json.dumps(manifest, indent=2))


@logged()
def compute_sha256(filepath: Path) -> str:
    h = hashlib.sha256()
    for chunk in iter(lambda: filepath.open("rb").read(65536), b""):
        h.update(chunk)
    return h.hexdigest()


@logged()
def get_unprocessed_raw_files(manifest: dict, raw_dir: Path) -> list[Path]:
    if not raw_dir.exists():
        return []
    all_files = sorted(raw_dir.glob("*.md"))
    processed = manifest.get("processed", {})
    unprocessed = []
    for f in all_files:
        rel = str(f.relative_to(VAULT))
        entry = processed.get(rel)
        if entry and entry.get("sha256"):
            current_hash = compute_sha256(f)
            if current_hash == entry["sha256"]:
                continue
        unprocessed.append(f)
    return unprocessed


@logged()
def mark_raw_processed(manifest: dict, raw_path: Path) -> None:
    rel = str(raw_path.relative_to(VAULT))
    manifest.setdefault("processed", {})[rel] = {
        "sha256": compute_sha256(raw_path),
        "ingested": datetime.now().strftime("%Y-%m-%d"),
        "size": raw_path.stat().st_size,
    }
    write_raw_manifest(manifest)


# ─── Rules Loader ────────────────────────────────────────────────────────────

RULES_FILE = VAULT / "rules.yaml"


def _load_rules() -> dict:
    """Load rules.yaml. Cache-friendly — file is small (<600 lines)."""
    import yaml
    if not RULES_FILE.exists():
        print(f"ERROR: {RULES_FILE} not found.", file=sys.stderr)
        sys.exit(2)
    with RULES_FILE.open() as f:
        rules = yaml.safe_load(f)
    return rules or {}


# ─── Strategy Pages ─────────────────────────────────────────────────────────


@logged()
def load_strategy_pages() -> list[dict]:
    """Read all content strategy pages and return metadata + preview.
    
    Strategy page list comes from rules.yaml §strategy.pages.
    """
    rules = _load_rules()
    strategy_pages = rules.get("strategy", {}).get("pages", [
        "icp-offer", "funnel-and-matrix", "voice-and-gates", "session-as-content",
    ])
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
        results.append({
            "name": name,
            "title": title,
            "preview": preview,
            "filepath": f"concepts/{name}.md",
        })
    return results


@logged()
def find_latest_session() -> dict | None:
    """Find the most recent session log in content/sessions/."""
    sessions_dir = VAULT / "content" / "sessions"
    if not sessions_dir.exists():
        return None
    sessions = sorted(sessions_dir.glob("*.md"), reverse=True)
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
    return {
        "filepath": str(latest.relative_to(VAULT)),
        "filename": latest.name,
        "content": content,
        "meta": meta,
    }


# ─── Helpers ────────────────────────────────────────────────────────────────

@logged()
def run_script(script_path: str, *args: str) -> tuple[int, str]:
    """Run a shell script and return (returncode, output)."""
    import time
    full_path = str(VAULT / "scripts" / script_path)
    if not os.path.isfile(full_path):
        log_err("engine", f"Script not found", script=script_path, exit_code=127)
        return 127, f"Script not found: {full_path}"
    t0 = time.time()
    try:
        env = os.environ.copy()
        rid = get_request_id()
        if rid:
            env["SHAYANWIKI_REQUEST_ID"] = rid
        result = subprocess.run(
            [full_path, *args],
            capture_output=True,
            text=True,
            timeout=120,
            env=env,
        )
        output = result.stdout + result.stderr
        elapsed = int((time.time() - t0) * 1000)
        log("INFO", "engine", f"Script completed",
            script=script_path, exit_code=result.returncode, duration_ms=elapsed)
        return result.returncode, output.strip()
    except subprocess.TimeoutExpired:
        log_err("engine", f"Script timed out", script=script_path, duration_ms=120000)
        return 124, "Script timed out after 120s"
    except Exception as e:
        log_err("engine", f"Script error: {e}", script=script_path)
        return 1, f"Script error: {e}"


@logged()
def print_state(state: dict) -> None:
    """Pretty-print the current state."""
    print("═══ Spiel Engine State ═══")
    print(f"State:    {state.get('current_state', 'UNKNOWN')}")
    print(f"Loop:     {state.get('loop', 'WIKI')}")
    print(f"Changed:  {state.get('last_state_change', 'never')}")
    print(f"Action:   {state.get('pending_action', 'none')}")
    print(f"Validate: {state.get('last_validation', 'unknown')}")
    health = state.get("validation_results", {})
    print(f"  orphans:      {health.get('orphans', '?')}")
    print(f"  broken links: {health.get('broken_links', '?')}")
    print(f"  stale:        {len(health.get('stale', []))}")
    print(f"  warnings:     {len(health.get('warnings', []))}")
    if state.get("last_ingest"):
        print(f"Last ingest: {state['last_ingest']}")


@logged()
def transition(state: dict, target: str) -> bool:
    """Transition to a new state after validation. Returns True on success."""
    current = state.get("current_state", "IDLE")
    sm = StateMachine(state.get("loop", "WIKI"))
    valid, reason = sm.validate_transition(current, target)
    if not valid:
        print(f"ERROR: {reason}", file=sys.stderr)
        log_err("engine", f"Invalid transition",
                from_state=current, to_state=target, reason=reason)
        return False
    state["current_state"] = target
    write_wiki_state(state)
    save_checkpoint(state)
    print(f"State: {current} → {target} ✓")
    log("INFO", "engine", f"State transition",
        from_state=current, to_state=target, loop=state.get("loop", "WIKI"))
    return True


# ─── Next-Command Display ───────────────────────────────────────────────────

WIKI_NEXT = {
    "INGESTING": [("wiki-analyze",   "ANALYZING — extract entities, concepts, apply thresholds")],
    "ANALYZING": [("wiki-reconcile", "RECONCILING — create/update pages, preserve contradictions")],
    "RECONCILING": [
        ("wiki-link",              "LINKING — scan for wikilink targets (optional)"),
        ("wiki-index",             "INDEXING — update index.md + log.md"),
    ],
    "LINKING":   [("wiki-index",    "INDEXING — update index.md + log.md")],
    "INDEXING":  [("wiki-validate", "VALIDATING — run health checks")],
    "VALIDATING":[("wiki-complete", "COMPLETE — finish pipeline")],
    "COMPLETE":  [],
    "IDLE":      [],
}

CONTENT_NEXT = {
    "SESSION_CAPTURE": [("post-strategy",   "STRATEGY_LOAD — classify session (S1-S10, vertical, funnel)")],
    "STRATEGY_LOAD":   [("post-compile",    "ICP_WORLD_BUILD — run Content Engine Compiler (6 steps)")],
    "ICP_WORLD_BUILD": [("post-draft",      "DRAFTING — draft posts from core insight")],
    "DRAFTING":        [
        ("post-banner", "BANNER — auto-generate banners for all queue drafts"),
        ("post-gate",   "GATE_CHECK — auto-runs gates.py (rules from rules.yaml)"),
    ],
    "GATE_CHECK": [
        ("post-queue",  "QUEUE — validate + prepare for publishing"),
        ("post-revise", "REVISING — fix failing gates and retry"),
    ],
    "REVISING":        [("post-gate",       "GATE_CHECK — re-run validation after fixes")],
    "QUEUE":           [
        ("post-publish",    "PUBLISHING — post to X / LinkedIn"),
        ("post-queue-hold", "HOLD — keep drafts in queue, reset state to IDLE"),
    ],
    "PUBLISHING":      [("post-archive",    "ARCHIVING — move to content/posted/")],
    "ARCHIVING":       [("post-analyze",    "ANALYZING_POST — review engagement data")],
    "ANALYZING_POST":  [("post-complete",   "COMPLETE_POST — finish content pipeline")],
    "COMPLETE_POST":   [],
    "IDLE":            [],
}


@logged()
def print_next(state: dict) -> None:
    """Print the next bash commands based on current state."""
    loop = state.get("loop", "WIKI")
    current = state.get("current_state", "IDLE")
    table = CONTENT_NEXT if loop == "CONTENT" else WIKI_NEXT
    entries = table.get(current, [])
    if not entries:
        return
    print()
    print("─" * 50)
    print("NEXT — run a command via bash tool:")
    for cmd, label in entries:
        print(f"  bash scripts/pipeline.sh {cmd}")
        print(f"    {label}")
    print("─" * 50)


# ─── Gate Enforcement ───────────────────────────────────────────────────────

GATES_REPORT_PATH = VAULT / "logs" / ".gates-report.json"


class GateBlockedError(Exception):
    """Raised when a hard gate prevents a state transition."""


def enforce_gates() -> dict:
    """Parse the gates JSON report. Raise GateBlockedError if any draft failed.

    Returns the parsed report dict on success. The report must have been
    produced by `gates.py --all --emit-json <report_path>`.
    """
    if not GATES_REPORT_PATH.exists():
        raise GateBlockedError(
            f"Gates report missing: {GATES_REPORT_PATH}. "
            "Run `engine.py content gate` to generate it."
        )
    try:
        report = json.loads(GATES_REPORT_PATH.read_text())
    except json.JSONDecodeError as e:
        raise GateBlockedError(f"Gates report malformed: {e}")

    drafts = report.get("drafts", [])
    if not drafts:
        raise GateBlockedError("Gates report has no drafts to validate.")

    failed = [d["file"] for d in drafts if not d.get("pass")]
    if failed:
        log_err("engine", "GATE_BLOCKED",
                reason="gates_failed",
                blocked_state="QUEUE",
                failed_drafts=failed,
                failed_count=len(failed))
        print("❌ GATES FAILED → PIPELINE BLOCKED", file=sys.stderr)
        for f in failed:
            print(f"   ✗ {f}", file=sys.stderr)
        raise GateBlockedError(
            f"Gates failed for {len(failed)} draft(s): {', '.join(failed)}"
        )

    log("INFO", "engine", "gates_passed",
        drafts=len(drafts), all_pass=True)
    return report


# ─── Wiki Commands ──────────────────────────────────────────────────────────

@logged()
def cmd_status(state: dict) -> int:
    print_state(state)
    return 0


@logged()
def cmd_wiki_extract(state: dict, args: list) -> int:
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
                print(f"  ⚠ File not found: raw/{a}")
        if not targets:
            print("  ERROR: No valid target files.")
            return 1
    else:
        targets = get_unprocessed_raw_files(manifest, raw_dir)
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
            print(f"    ● {rel} (changed — hash differs from {entry.get('sha256', '?')[:12]}...)")
        else:
            print(f"    ○ {rel} (new)")
    print()

    print_next(state)
    return 0


@logged()
def cmd_wiki_analyze(state: dict) -> int:
    if not transition(state, "ANALYZING"):
        return 1
    print_next(state)
    return 0


@logged()
def cmd_wiki_reconcile(state: dict) -> int:
    if not transition(state, "RECONCILING"):
        return 1
    print_next(state)
    return 0


@logged()
def cmd_wiki_link(state: dict) -> int:
    if not transition(state, "LINKING"):
        return 1
    print_next(state)
    return 0


@logged()
def cmd_wiki_index(state: dict) -> int:
    if not transition(state, "INDEXING"):
        return 1
    print_next(state)
    return 0


@logged()
def cmd_wiki_validate(state: dict) -> int:
    if not transition(state, "VALIDATING"):
        return 1

    # Run automated health checks (includes redundancy scan internally)
    rc, output = run_script("wiki-health.py")
    print(output)

    print_next(state)
    return 0


@logged()
def cmd_wiki_complete(state: dict) -> int:
    if not transition(state, "COMPLETE"):
        return 1

    # Update raw manifest with processed files from this session
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

    # Update last_ingest
    state["last_ingest"] = datetime.now().isoformat()

    if not transition(state, "IDLE"):
        return 1
    print("Wiki pipeline complete. System back to IDLE.")
    return 0


@logged()
def cmd_wiki_health(state: dict) -> int:
    """Read-only health check (does not change state)."""
    print("═══ Read-Only Health Check ═══")
    rc, output = run_script("wiki-health.py")
    print(output)
    return rc


@logged()
def cmd_wiki_reset(state: dict) -> int:
    """Force reset to IDLE. Use only when stuck."""
    print("WARNING: Force-resetting state. This should only be used if the")
    print("state machine is stuck (e.g., from a crashed session).")
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
    print("State reset to IDLE ✓")
    return 0


# ─── Content Commands (coded pipeline) ──────────────────────────────────────

@logged()
def _create_stub_session_log(today: str) -> Path:
    """Auto-create an empty session log stub for today."""
    sessions_dir = VAULT / "content" / "sessions"
    sessions_dir.mkdir(parents=True, exist_ok=True)

    # Determine next session number
    existing = list(sessions_dir.glob(f"{today}-session-*.md"))
    nn = max((int(p.stem.split("-")[-1]) for p in existing), default=0) + 1

    stub_path = sessions_dir / f"{today}-session-{nn:02d}.md"
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


@logged()
def cmd_content_post(state: dict, args: list) -> int:
    """2-mode SESSION_CAPTURE.

    Mode 1 (empty): ensure today's session log exists, auto-create stub if missing.
    Mode 2 (topic):  topic from inline string or @file:path, no session required.
    """
    state["loop"] = "CONTENT"
    if not transition(state, "SESSION_CAPTURE"):
        return 1

    print("═══ Content Pipeline: /post ═══")
    print()

    print("── Strategy Pages ──")
    strategy_pages = load_strategy_pages()
    loaded = 0
    for sp in strategy_pages:
        if sp["filepath"]:
            loaded += 1
            print(f"  ✓ {sp['name']}.md — {sp['title']}")
        else:
            print(f"  ✗ {sp['name']}.md — (not found)")
    print(f"  ({loaded}/{len(strategy_pages)} loaded)")
    print()

    # Determine mode
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
        # Mode 1: check for today's session log
        today = datetime.now().strftime("%Y-%m-%d")
        session_logs = sorted((VAULT / "content/sessions").glob(f"{today}-session-*.md"))
        if not session_logs:
            stub = _create_stub_session_log(today)
            print("⚠ Session not saved yet, let me save it first")
            print(f"  Stub created: {stub.relative_to(VAULT)}")
            print(f"  Fill in the 'What we did' / 'Decisions made' / 'Lessons learned' sections.")
            print()

    # Print mode marker
    print(f"═══ Mode {'1' if source_kind != 'topic' else '2'}: {'Current Session' if source_kind != 'topic' else 'Topic'} ═══")
    print()

    if source_kind == "topic":
        print(f"  Source: {source_label}")
        rc, output = run_script("post_topic.py", source_text or source_label)
        if output.strip():
            print(output)
        if rc != 0:
            print(f"WARN: post_topic.py exited with code {rc}")
        print()

    # Session lookup (for mode 1, after potential stub creation)
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
            print("  (No session found — auto-created stub should be visible above.)")
    print()

    # Build brief
    brief = {
        "session": session["filepath"] if session else None,
        "strategy_pages": [s["name"] for s in strategy_pages if s["filepath"]],
        "source": {
            "kind": source_kind,
            "text": source_text,
            "label": source_label,
        },
        "pre_write_gate_required": True,
        "core_insight": "",
        "meanings": {
            "systemic": "",
            "behavioral": "",
            "philosophical": "",
            "contrarian": "",
            "leverage": "",
            "human": "",
        },
        "selected_meaning": {
            "axis": "",
            "rationale": "",
        },
    }
    CONTENT_BRIEF_FILE.write_text(json.dumps(brief, indent=2))
    print(f"── Brief saved to .content-brief.json ──")
    print(f"  Next: run 'bash scripts/pipeline.sh content post-compile'")
    print(f"  to run the Content Engine Compiler before drafting.")
    print()
    print_next(state)
    return 0


@logged()
def cmd_content_strategy(state: dict) -> int:
    """Confirm strategy load. Validates brief exists."""
    if not transition(state, "STRATEGY_LOAD"):
        return 1
    if not CONTENT_BRIEF_FILE.exists():
        print("ERROR: No content brief. Run 'engine.py content post' first.", file=sys.stderr)
        return 1
    brief = json.loads(CONTENT_BRIEF_FILE.read_text())
    print("── Strategy Pages to Read ──")
    for p in brief.get("strategy_pages", []):
        print(f"  ● concepts/{p}.md")
    print()
    print_next(state)
    return 0


@logged()
def cmd_content_compile(state: dict) -> int:
    """ICP_WORLD_BUILD — run Content Engine Compiler (6-step sequence).

    Validates brief exists, loads ICP world + session evidence, prints the
    6-step Compiler sequence. The LLM runs the steps in conversation and
    writes core_insight + selected_meaning to .content-brief.json.
    """
    if not transition(state, "ICP_WORLD_BUILD"):
        return 1
    if not CONTENT_BRIEF_FILE.exists():
        print("ERROR: No content brief. Run 'engine.py content post' first.", file=sys.stderr)
        return 1

    rc, output = run_script("content_compiler.py")
    print(output)
    if rc != 0:
        print(f"WARN: content_compiler.py exited with code {rc}")
    print()
    print_next(state)
    return 0


@logged()
def cmd_content_draft(state: dict) -> int:
    """Begin drafting. Validates brief exists, reader_failure_mode is populated,
    AND core_insight + selected_meaning exist from the Compiler."""
    if not transition(state, "DRAFTING"):
        return 1
    if not CONTENT_BRIEF_FILE.exists():
        print("ERROR: No content brief. Run 'engine.py content post' first.", file=sys.stderr)
        return 1
    brief = json.loads(CONTENT_BRIEF_FILE.read_text())
    session_path = brief.get("session")
    topic = "untitled"

    if session_path:
        session_full = Path(session_path)
        if not session_full.is_absolute():
            session_full = VAULT / session_path
        if session_full.exists():
            session_content = session_full.read_text()
            rfm = None
            if session_content.startswith("---"):
                parts = session_content.split("---", 2)
                if len(parts) >= 2:
                    try:
                        fm_parsed = yaml.safe_load(parts[1])
                        if isinstance(fm_parsed, dict):
                            rfm = fm_parsed.get("reader_failure_mode")
                    except yaml.YAMLError:
                        pass
            if not rfm or not isinstance(rfm, dict):
                print("❌ reader_failure_mode is MISSING from session log frontmatter.", file=sys.stderr)
                print("   Run the Content Engine Compiler first: `bash scripts/pipeline.sh post-compile`", file=sys.stderr)
                print("   Pipeline halted: cannot draft without reader-problem grounding.", file=sys.stderr)
                print()
                print_next(state)
                return 1
            missing = [k for k in ("belief", "consequence", "mapping") if not rfm.get(k)]
            if missing:
                print(f"❌ reader_failure_mode missing required field(s): {', '.join(missing)}", file=sys.stderr)
                print("   Pipeline halted.", file=sys.stderr)
                print()
                print_next(state)
                return 1
            print(f"  ✓ reader_failure_mode populated — belief, consequence, mapping")
        else:
            print(f"  ⚠ Session file not found: {session_full}")

    # Validate Compiler fields exist in brief
    core_insight = brief.get("core_insight", "").strip()
    meanings = brief.get("meanings", {})
    selected = brief.get("selected_meaning", {})
    compiler_missing = []
    if not core_insight:
        compiler_missing.append("core_insight")
    rules_data = _load_rules()
    meaning_axes = rules_data.get("compiler", {}).get("meaning_axes", [
        "systemic", "behavioral", "philosophical", "contrarian", "leverage", "human",
    ])
    for axis in meaning_axes:
        if not meanings.get(axis, "").strip():
            compiler_missing.append(f"meanings.{axis}")
    if not selected.get("axis", "").strip():
        compiler_missing.append("selected_meaning.axis")
    if compiler_missing:
        print(f"❌ Content Engine Compiler fields missing: {', '.join(compiler_missing)}", file=sys.stderr)
        print("   Run `bash scripts/pipeline.sh post-compile` first.", file=sys.stderr)
        print("   Pipeline halted: cannot draft without core insight from the Compiler.", file=sys.stderr)
        print()
        print_next(state)
        return 1
    print(f"  ✓ Compiler fields populated — core_insight + all 6 meanings + selection")

    print(f"── DRAFTING: {topic} ──")
    print("  1. Use core_insight as the lens (from Content Engine Compiler)")
    print("  2. Use selected_meaning.axis to choose the narrative frame")
    print("  3. Use selected_meaning.rationale to guide the tone")
    print("  4. Draft posts using templates/")
    print("  5. Save to content/queue/ with full frontmatter")
    print()
    print_next(state)
    return 0


@logged()
def cmd_content_banner(state: dict) -> int:
    """Auto-generate banners for all queue drafts.
    Does NOT change state — this is a tool step between DRAFTING and GATE_CHECK."""
    queue_dir = VAULT / "content" / "queue"
    if not queue_dir.exists():
        print("No queue directory. Nothing to banner.")
        return 0
    drafts = sorted(queue_dir.glob("*.md"))
    if not drafts:
        print("No drafts in queue. Nothing to banner.")
        return 0

    print("── Auto-Generating Banners ──")
    generated = 0
    for draft in drafts:
        # Read frontmatter to detect platform
        content = draft.read_text()
        fm = {}
        if content.startswith("---"):
            parts = content.split("---", 2)
            if len(parts) >= 2:
                try:
                    fm = yaml.safe_load(parts[1]) or {}
                except yaml.YAMLError:
                    pass

        platform = (fm.get("platform") or "").lower()
        draft_title = fm.get("title", draft.stem)

        # Determine banner type: social for linkedin/x, default for blog
        if platform in ("linkedin", "x", "twitter"):
            banner_type = "social"
        else:
            banner_type = "default"

        queue_id = draft.stem
        print(f"  {queue_id} → {banner_type} ({platform})")

        rc, output = run_script(
            "banner.py",
            "--queue-id", queue_id,
            "--type", banner_type,
        )
        if rc == 0:
            generated += 1
            for line in output.split("\n"):
                if line.strip():
                    print(f"    {line.strip()}")
        else:
            print(f"    ⚠ Banner generation failed (exit {rc}): {output[:200]}")

    print(f"\n  Generated: {generated}/{len(drafts)} banners")
    return 0


@logged()
def cmd_content_gate(state: dict) -> int:
    """Run mechanical gates (gates.py). Voice markers are LLM-only guidance."""
    if not transition(state, "GATE_CHECK"):
        return 1

    (VAULT / "logs").mkdir(parents=True, exist_ok=True)

    print("── Mechanical Gates (gates.py — all rules from rules.yaml) ──")
    rc, output = run_script(
        "gates.py", "--all",
        "--emit-json", str(GATES_REPORT_PATH),
    )
    print(output)
    print()

    # Parse the JSON report for an authoritative per-draft verdict.
    all_pass = False
    if GATES_REPORT_PATH.exists():
        try:
            report = json.loads(GATES_REPORT_PATH.read_text())
            drafts_in_report = report.get("drafts", [])
            if drafts_in_report:
                total_checks = drafts_in_report[0].get("max", 15)
                passed = sum(1 for d in drafts_in_report if d.get("pass"))
                failed_count = len(drafts_in_report) - passed
                print(f"  Gates report: {passed}/{len(drafts_in_report)} drafts pass")
                if failed_count == 0:
                    print(f"  ✓ All gates passed ({total_checks}/{total_checks} per draft)")
                    all_pass = True
                else:
                    print(f"  ⚠ {failed_count} draft(s) failed gates — QUEUE transition will be blocked")
        except json.JSONDecodeError:
            print("  ⚠ Gates report malformed — QUEUE transition will be blocked")
    else:
        print("  ⚠ No gates report written — QUEUE transition will be blocked")
    print()
    print_next(state)
    return 0 if all_pass else 1


@logged()
def cmd_content_revise(state: dict) -> int:
    if not transition(state, "REVISING"):
        return 1
    print_next(state)
    return 0


@logged()
def cmd_content_queue(state: dict) -> int:
    """Queue validated drafts. Hard-gated: cannot reach QUEUE
    state unless all drafts pass gates.py."""
    try:
        enforce_gates()
    except GateBlockedError as e:
        print(f"❌ {e}", file=sys.stderr)
        return 2  # distinct from generic error 1

    if not transition(state, "QUEUE"):
        return 1
    queue_dir = VAULT / "content" / "queue"
    if not queue_dir.exists():
        print("ERROR: content/queue/ does not exist.", file=sys.stderr)
        return 1
    drafts = sorted(queue_dir.glob("*.md"))
    if not drafts:
        print("ERROR: No drafts in content/queue/. Run draft first.", file=sys.stderr)
        return 1
    print(f"── Queue: {len(drafts)} draft(s) ──")
    for d in drafts:
        frontmatter = ""
        content = d.read_text()
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


@logged()
def cmd_content_hold(state: dict) -> int:
    """Transition QUEUE → IDLE, keeping drafts in place for later."""
    if not transition(state, "IDLE"):
        return 1
    queue_dir = VAULT / "content" / "queue"
    if queue_dir.exists():
        drafts = sorted(queue_dir.glob("*.md"))
        print(f"  {len(drafts)} draft(s) remain in content/queue/")
        for d in drafts:
            print(f"    · {d.name}")
    print("  State reset to IDLE. Run `/publish` later to publish.")
    print("  Note: Run `pipeline.sh post-start` for a new content session.")
    return 0


@logged()
def cmd_content_publish(state: dict, draft_id: str = None) -> int:
    state["loop"] = "CONTENT"
    if not transition(state, "PUBLISHING"):
        return 1
    if draft_id and draft_id != "all":
        draft_path = VAULT / "content" / "queue" / draft_id
        if not draft_path.exists():
            print(f"Draft not found: {draft_path}")
            print("Available drafts:")
            for f in sorted((VAULT / "content" / "queue").glob("*.md")):
                print(f"  {f.name}")
            return 1

    if draft_id == "all":
        print("  Target: all ready drafts")
    elif draft_id:
        print(f"  Target: queue/{draft_id}")
    else:
        print("  Target: last draft")
    print_next(state)
    return 0


@logged()
def cmd_content_archive(state: dict) -> int:
    if not transition(state, "ARCHIVING"):
        return 1
    print_next(state)
    return 0


@logged()
def cmd_content_analyze(state: dict) -> int:
    state["loop"] = "CONTENT"
    if not transition(state, "ANALYZING_POST"):
        return 1
    print_next(state)
    return 0


@logged()
def cmd_content_complete(state: dict) -> int:
    if not transition(state, "COMPLETE_POST"):
        return 1
    if not transition(state, "IDLE"):
        return 1
    print("Content pipeline complete. System back to IDLE.")
    return 0


@logged()
def cmd_content_queue_list(state: dict) -> int:
    """Show queue contents (read-only). Grouped by platform with status."""
    from datetime import datetime, timedelta

    queue_dir = VAULT / "content" / "queue"
    if not queue_dir.exists():
        print("No queue directory.")
        return 0
    drafts = sorted(queue_dir.glob("*.md"))
    if not drafts:
        print("Queue is empty.")
        return 0

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

    # Parse all draft frontmatter
    parsed = []
    for d in drafts:
        meta = read_meta(d)
        name = d.name

        platform = (meta.get("platform") or "").lower()
        if not platform:
            if "tweet" in name or "-x-" in name:
                platform = "x"
            elif "linkedin" in name:
                platform = "linkedin"
            elif "blog" in name or "pillar" in name:
                platform = "blog"
            elif "offer" in name:
                platform = "offer"
            else:
                platform = "other"

        status = meta.get("status", "draft")
        if meta.get("scheduled"):
            status = "scheduled"
        if meta.get("posted_at"):
            status = "published"

        standalone = meta.get("standalone_test", "")
        copy_gate = meta.get("copywriting_gate", "")

        parsed.append({
            "name": name,
            "platform": platform,
            "status": status,
            "standalone": standalone,
            "copy_gate": copy_gate,
            "scheduled": meta.get("scheduled"),
        })

    # Count posted/rejected for stats
    now = datetime.now()
    week_ago = now - timedelta(days=7)
    month_ago = now - timedelta(days=30)
    posted_this_week = 0
    rejected_this_month = 0

    for d in sorted((VAULT / "content" / "posted").glob("*.md")):
        meta = read_meta(d)
        if meta.get("posted_at"):
            try:
                dt = datetime.strptime(str(meta["posted_at"])[:10], "%Y-%m-%d")
                if dt >= week_ago:
                    posted_this_week += 1
            except ValueError:
                pass

    for d in sorted((VAULT / "content" / "rejected").glob("*.md")):
        meta = read_meta(d)
        if meta.get("rejected_at"):
            try:
                dt = datetime.strptime(str(meta["rejected_at"])[:10], "%Y-%m-%d")
                if dt >= month_ago:
                    rejected_this_month += 1
            except ValueError:
                pass

    # Group by platform
    groups = {"x": [], "linkedin": [], "blog": [], "offer": [], "other": []}
    for p in parsed:
        g = groups.get(p["platform"], groups["other"])
        g.append(p)

    platform_label = {"x": "X", "linkedin": "LinkedIn", "blog": "Blog", "offer": "Offer", "other": "Other"}
    platform_order = ["x", "linkedin", "blog", "offer", "other"]
    max_label = max(len(platform_label[k]) for k in platform_order)

    print("── Content Queue ───────────────────")
    total_active = len(parsed)
    print(f"  Total: {total_active} draft{'s' if total_active != 1 else ''}")
    print()

    for key in platform_order:
        items = groups[key]
        label = platform_label[key]
        count = len(items)
        print(f"── {label} ({count}) {'─' * (40 - len(label) - len(str(count)) - 4)}")
        if not items:
            print("  (none)")
        else:
            for item in items:
                if item["status"] == "ready":
                    extra = ""
                    if item["standalone"]:
                        extra += f"standalone: {item['standalone']}"
                    if item["copy_gate"]:
                        if extra:
                            extra += "  "
                        extra += f"10-gate: {item['copy_gate']}"
                elif item["status"] == "api-failed":
                    extra = "need to retry"
                elif item["status"] == "needs-manual-post":
                    extra = "no API configured"
                elif item["status"] == "ready-to-publish":
                    extra = "screenshots: missing"
                else:
                    extra = ""
                print(f"  · {item['name']}  [{item['status']}]  {extra}".rstrip())
        print()

    scheduled = [p for p in parsed if p["status"] == "scheduled"]
    print(f"── Scheduled ({len(scheduled)}) {'─' * (40 - len(str(len(scheduled))) - 14)}")
    if scheduled:
        for item in scheduled:
            print(f"  · {item['name']}  → {item['scheduled']}")
    else:
        print("  (none)")
    print()

    print(f"── Posted this week: {posted_this_week}  |  Rejected this month: {rejected_this_month}")


# ─── State Persistence (Checkpoints) ───────────────────────────────────────

CHECKPOINT_DIR = VAULT / ".checkpoints"

@logged()
def save_checkpoint(state: dict) -> None:
    """Save a checkpoint file for recovery."""
    import json
    CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)
    cp = {
        "timestamp": __import__("datetime").datetime.now().isoformat(),
        "state": state.get("current_state"),
        "loop": state.get("loop"),
        "pending_action": state.get("pending_action"),
    }
    cp_file = CHECKPOINT_DIR / f"{state.get('loop', 'WIKI').lower()}-checkpoint.json"
    with open(cp_file, "w") as f:
        json.dump(cp, f, indent=2)


@logged()
def load_checkpoint(loop: str = "WIKI") -> dict | None:
    """Load the most recent checkpoint for a loop."""
    import json
    cp_file = CHECKPOINT_DIR / f"{loop.lower()}-checkpoint.json"
    if not cp_file.exists():
        return None
    try:
        with open(cp_file) as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return None


@logged()
def clear_checkpoint(loop: str = "WIKI") -> None:
    cp_file = CHECKPOINT_DIR / f"{loop.lower()}-checkpoint.json"
    cp_file.unlink(missing_ok=True)


# ─── Recovery ───────────────────────────────────────────────────────────────

@logged()
def cmd_recover(state: dict) -> int:
    """Diagnose and fix stuck states."""
    current = state.get("current_state", "IDLE")
    loop = state.get("loop", "WIKI")

    if current == "IDLE":
        # Check for residual checkpoints
        cp = load_checkpoint(loop)
        if cp:
            print(f"System is IDLE but has a stale checkpoint from {cp.get('timestamp', 'unknown')}.")
            print(f"  Previous state: {cp.get('state')}")
            print(f"  Previous loop: {cp.get('loop')}")
            if confirm("Clear stale checkpoint?"):
                clear_checkpoint(loop)
                print("Checkpoint cleared.")
        else:
            print("System is already IDLE. No recovery needed.")
        return 0

    print(f"System is stuck in: {current} ({loop} loop)")
    print()

    cp = load_checkpoint(loop)
    if cp:
        print(f"Checkpoint found from: {cp.get('timestamp', 'unknown')}")
        print()

    print("Diagnosis:")
    if current in ("INGESTING", "ANALYZING", "RECONCILING", "INDEXING", "VALIDATING"):
        print("  Wiki pipeline was interrupted. Possible causes:")
        print("  - Session crashed mid-pipeline")
        print("  - LLM did not update state after completing a step")
        print()
        print("Recovery options:")
        print("  1. engine.py wiki reset  — force back to IDLE")
        print("  2. Continue pipeline from current state")
        print("     (run the next valid transition: ", end="")
        sm = StateMachine(loop)
        print(", ".join(sm.all_transitions_from(current)), end="")
        print(")")
    elif current in ("SESSION_CAPTURE", "STRATEGY_LOAD", "ICP_WORLD_BUILD", "DRAFTING", "GATE_CHECK", "REVISING"):
        print("  Content pipeline was interrupted.")
        print()
        print("Recovery options:")
        print("  1. engine.py wiki reset  — force back to IDLE")
        print("  2. Continue pipeline from current state")
        print("     (run the next valid transition: ", end="")
        sm = StateMachine(loop)
        print(", ".join(sm.all_transitions_from(current)), end="")
        print(")")
    else:
        print(f"  Unknown state: {current}")
        print("  Run: engine.py wiki reset")

    return 0

@logged()
def confirm(prompt: str) -> bool:
    """Ask for yes/no confirmation."""
    try:
        response = input(f"{prompt} (y/N): ")
        return response.lower() == "y"
    except (EOFError, KeyboardInterrupt):
        print()
        return False


# ─── Main CLI ───────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="ShayanWiki State Machine Engine",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    sub = parser.add_subparsers(dest="command")

    # status
    sub.add_parser("status", help="Show current system state")

    # wiki commands
    wiki = sub.add_parser("wiki", help="Wiki management commands")
    wiki_sub = wiki.add_subparsers(dest="wiki_cmd")
    ext = wiki_sub.add_parser("extract", help="Start INGEST state for a raw file")
    ext.add_argument("source", nargs="*", help="Source file(s) in raw/")
    wiki_sub.add_parser("analyze", help="Mark ANALYZE complete")
    wiki_sub.add_parser("reconcile", help="Mark RECONCILE complete")
    wiki_sub.add_parser("link", help="Run LINKING sub-step")
    wiki_sub.add_parser("index", help="Rebuild index.md")
    wiki_sub.add_parser("validate", help="Run health checks + mark VALIDATE complete")
    wiki_sub.add_parser("complete", help="Mark pipeline complete")
    wiki_sub.add_parser("health", help="Read-only health check (no state change)")
    wiki_sub.add_parser("reset", help="Force reset to IDLE (use when stuck)")

    # content commands
    content = sub.add_parser("content", help="Content posting commands")
    content_sub = content.add_subparsers(dest="content_cmd")
    post = content_sub.add_parser("post", help="Start SESSION_CAPTURE")
    post.add_argument("about", nargs="*", help="Topic or 'about <topic>'")
    content_sub.add_parser("strategy", help="Mark STRATEGY_LOAD complete")
    content_sub.add_parser("compile", help="Mark ICP_WORLD_BUILD complete (Content Engine Compiler)")
    content_sub.add_parser("draft", help="Mark DRAFTING complete")
    content_sub.add_parser("banner", help="Auto-generate banners for queue drafts")
    content_sub.add_parser("gate", help="Mark GATE_CHECK complete")
    content_sub.add_parser("revise", help="Enter REVISING state")
    content_sub.add_parser("queue", help="View queue or mark QUEUE complete")
    content_sub.add_parser("hold", help="QUEUE → IDLE, keep drafts for later")
    pub = content_sub.add_parser("publish", help="Publish draft(s)")
    pub.add_argument("draft_id", nargs="?", help="Draft filename or 'all'")
    content_sub.add_parser("archive", help="Mark ARCHIVING complete")
    content_sub.add_parser("analyze", help="Run content performance analysis")
    content_sub.add_parser("complete", help="Mark content pipeline complete")

    # queue viewer (read-only, top-level)
    sub.add_parser("queue", help="Show queue contents (read-only)")

    # recovery
    sub.add_parser("recover", help="Diagnose + fix stuck state")

    # log viewer
    log_parser = sub.add_parser("log", help="View recent log entries")
    log_parser.add_argument("--days", type=int, default=7, help="Days back to search")
    log_parser.add_argument("--level", help="Filter by level (INFO/WARN/ERROR)")
    log_parser.add_argument("--source", help="Filter by source name")
    log_parser.add_argument("--tail", type=int, default=30, help="Show only last N entries")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 0

    state = read_wiki_state()

    command_str = f"{args.command}"
    if hasattr(args, 'wiki_cmd') and args.wiki_cmd:
        command_str += f" {args.wiki_cmd}"
    if hasattr(args, 'content_cmd') and args.content_cmd:
        command_str += f" {args.content_cmd}"
    log("INFO", "engine", f"Command started", command=command_str)
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
                if args.wiki_cmd == "extract":
                    return cmd_wiki_extract(state, args.source)
                elif args.wiki_cmd == "analyze":
                    return cmd_wiki_analyze(state)
                elif args.wiki_cmd == "reconcile":
                    return cmd_wiki_reconcile(state)
                elif args.wiki_cmd == "link":
                    return cmd_wiki_link(state)
                elif args.wiki_cmd == "index":
                    return cmd_wiki_index(state)
                elif args.wiki_cmd == "validate":
                    return cmd_wiki_validate(state)
                elif args.wiki_cmd == "complete":
                    return cmd_wiki_complete(state)
                elif args.wiki_cmd == "health":
                    return cmd_wiki_health(state)
                elif args.wiki_cmd == "reset":
                    return cmd_wiki_reset(state)
            finally:
                release_lock()

        elif args.command == "content":
            if not args.content_cmd:
                print("Usage: engine.py content {post|strategy|compile|draft|gate|revise|queue|publish|archive|analyze|complete}")
                return 1
            if not acquire_lock():
                print("ERROR: Another pipeline is running (lock file present).", file=sys.stderr)
                return 1
            try:
                state = read_wiki_state()
                state["loop"] = "CONTENT"
                if args.content_cmd == "post":
                    return cmd_content_post(state, args.about)
                elif args.content_cmd == "strategy":
                    return cmd_content_strategy(state)
                elif args.content_cmd == "compile":
                    return cmd_content_compile(state)
                elif args.content_cmd == "draft":
                    return cmd_content_draft(state)
                elif args.content_cmd == "banner":
                    return cmd_content_banner(state)
                elif args.content_cmd == "gate":
                    return cmd_content_gate(state)
                elif args.content_cmd == "revise":
                    return cmd_content_revise(state)
                elif args.content_cmd == "queue":
                    return cmd_content_queue(state)
                elif args.content_cmd == "hold":
                    return cmd_content_hold(state)
                elif args.content_cmd == "publish":
                    return cmd_content_publish(state, args.draft_id)
                elif args.content_cmd == "archive":
                    return cmd_content_archive(state)
                elif args.content_cmd == "analyze":
                    return cmd_content_analyze(state)
                elif args.content_cmd == "complete":
                    return cmd_content_complete(state)
            finally:
                release_lock()

        elif args.command == "queue":
            return cmd_content_queue_list(state)

        elif args.command == "recover":
            return cmd_recover(state)

        elif args.command == "log":
            from logger import print_logs
            print_logs(days=args.days, level=args.level,
                       source=args.source, tail=args.tail)
            return 0

    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
