#!/usr/bin/env python3
"""Detect pipeline bypasses and runtime consistency issues."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _vault import resolve_vault  # noqa: E402


def load_state(vault: Path) -> dict | None:
    path = vault / "content" / ".state.json"
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"_invalid": True}


def rel(vault: Path, path: Path) -> str:
    return str(path.resolve().relative_to(vault.resolve()))


def check(vault: Path) -> dict:
    state = load_state(vault)
    drafts_dir = vault / "content" / "drafts"
    ready_dir = vault / "content" / "ready"
    draft_files = sorted(p for p in drafts_dir.glob("*.md")) if drafts_dir.is_dir() else []
    ready_files = sorted(p for p in ready_dir.glob("*.md")) if ready_dir.is_dir() else []
    state_drafts = set(state.get("drafts", []) if isinstance(state, dict) else [])
    state_ready = set(state.get("ready", []) if isinstance(state, dict) else [])
    active_state = isinstance(state, dict) and not state.get("_invalid")
    orphan_severity = "error" if active_state else "warning"

    issues = []
    if state is None and (draft_files or ready_files):
        issues.append({
            "code": "content_without_state",
            "severity": "warning",
            "message": "content drafts/ready files exist but content/.state.json is missing",
        })
    if isinstance(state, dict) and state.get("_invalid"):
        issues.append({"code": "invalid_state", "severity": "error", "message": "content/.state.json is not valid JSON"})

    for path in draft_files:
        r = rel(vault, path)
        if r not in state_drafts:
            issues.append({
                "code": "untracked_draft",
                "severity": orphan_severity,
                "path": r,
                "message": "draft exists but is not listed in state.drafts",
            })
    for path in ready_files:
        r = rel(vault, path)
        if r not in state_ready:
            issues.append({
                "code": "untracked_ready",
                "severity": orphan_severity,
                "path": r,
                "message": "ready draft exists but is not listed in state.ready",
            })

    errors = [issue for issue in issues if issue.get("severity") == "error"]
    return {
        "ok": not errors,
        "state_step": state.get("step") if isinstance(state, dict) else "missing",
        "draft_count": len(draft_files),
        "ready_count": len(ready_files),
        "issues": issues,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Check SpielOS runtime consistency")
    ap.add_argument("--vault", help="SpielOS vault root")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--clean", action="store_true",
                    help="Move untracked drafts/ready into rejected/ and report. "
                         "Use this to recover from a guard failure without --ignore-guard.")
    args = ap.parse_args()
    vault = resolve_vault(args.vault)
    if not vault:
        sys.stderr.write("ERROR: could not locate SpielOS vault\n")
        return 2
    if args.clean:
        return cmd_clean(vault)
    result = check(vault)
    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        mark = "✓" if result["ok"] else "✗"
        print(f"{mark} guard: {len(result['issues'])} issue(s)")
        for issue in result["issues"]:
            path = f" {issue.get('path')}" if issue.get("path") else ""
            print(f"  - {issue['code']}{path}: {issue['message']}")
    return 0 if result["ok"] else 1


def cmd_clean(vault: Path) -> int:
    """Move untracked drafts and ready files into rejected/ with a
    `rejection_reason: untracked_orphan` frontmatter field. This is the
    non-destructive way to recover from a guard failure without using
    --ignore-guard. Always succeeds unless vault is missing.
    """
    import shutil
    from datetime import datetime
    state = load_state(vault)
    drafts_dir = vault / "content" / "drafts"
    ready_dir = vault / "content" / "ready"
    rejected_dir = vault / "content" / "rejected"
    rejected_dir.mkdir(parents=True, exist_ok=True)
    state_drafts = set(state.get("drafts", []) if isinstance(state, dict) else [])
    state_ready = set(state.get("ready", []) if isinstance(state, dict) else [])
    moved = []
    for d in [drafts_dir, ready_dir]:
        if not d.is_dir():
            continue
        for path in sorted(d.glob("*.md")):
            r = rel(vault, path)
            in_state = (d is drafts_dir and r in state_drafts) or (d is ready_dir and r in state_ready)
            if in_state:
                continue
            dest = rejected_dir / path.name
            now = datetime.now().isoformat(timespec="seconds")
            try:
                old_text = path.read_text(encoding="utf-8")
            except OSError:
                old_text = ""
            if old_text.startswith("---"):
                parts = old_text.split("---", 2)
                if len(parts) >= 3:
                    new_fm = parts[1].rstrip() + f"\nrejection_reason: untracked_orphan\nrejected_at: {now}\n"
                    new_text = "---" + new_fm + "---" + parts[2]
                else:
                    new_text = f"---\nrejection_reason: untracked_orphan\nrejected_at: {now}\n---\n\n" + old_text
            else:
                new_text = f"---\nrejection_reason: untracked_orphan\nrejected_at: {now}\n---\n\n" + old_text
            try:
                dest.write_text(new_text, encoding="utf-8")
                path.unlink()
                moved.append(rel(vault, dest))
            except OSError as e:
                print(f"WARN: could not move {r}: {e}")
    if moved:
        print(f"  ✓ moved {len(moved)} untracked file(s) to rejected/:")
        for m in moved:
            print(f"    → {m}")
        print("  → run `spiel guard` again to confirm clean")
    else:
        print("  ✓ nothing to clean (no untracked drafts or ready files)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
