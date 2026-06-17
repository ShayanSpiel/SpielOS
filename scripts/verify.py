#!/usr/bin/env python3
"""verify.py — Post-archive assertions.

Runs after every archive_draft() call. Verifies that:
  - The original draft is gone from queue/
  - The new file exists in posted/
  - Frontmatter has posted_at
  - The new file is in the posted/ directory
  - The original is gone (no duplicate)

Returns a dict of {check_name: bool}. Logs failures to logs/.

Pure functions + one file I/O read. No CLI. No external API.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from engine_state import POSTED_DIR, QUEUE_DIR
from engine_frontmatter import parse_frontmatter
from engine_serial import log, log_err


def verify_archive(
    original: Path,
    archived: Path,
    queue_dir: Path | None = None,
    posted_dir: Path | None = None,
) -> dict:
    """Run all post-archive checks. Returns {check_name: bool}."""
    checks: dict[str, bool] = {}
    if not isinstance(original, Path):
        original = Path(original)
    if not isinstance(archived, Path):
        archived = Path(archived)
    queue_dir = queue_dir or QUEUE_DIR
    posted_dir = posted_dir or POSTED_DIR
    checks["original_gone"] = _check_original_gone(original)
    checks["archived_exists"] = _check_archived_exists(archived)
    checks["in_posted_dir"] = _check_in_posted_dir(archived, posted_dir=posted_dir)
    checks["in_queue_gone"] = _check_in_queue_gone(archived, queue_dir=queue_dir)
    checks["has_posted_at"] = _check_has_posted_at(archived)
    checks["has_platform"] = _check_has_platform(archived)
    if not all(checks.values()):
        failed = [k for k, v in checks.items() if not v]
        log_err("verify", f"archive verification FAILED: {archived}",
                failed_checks=failed,
                original=str(original),
                archived=str(archived))
    else:
        log("INFO", "verify", "archive verification passed",
            original=str(original),
            archived=str(archived))
    return checks


def verify_quiet(original: Path, archived: Path) -> bool:
    """Returns True if all checks pass, False otherwise. No logging."""
    return all(verify_archive(original, archived).values())


def format_results(checks: dict) -> str:
    """Format check results as a human-readable string."""
    lines = []
    for name, ok in checks.items():
        icon = "✓" if ok else "✗"
        lines.append(f"  {icon} {name}")
    return "\n".join(lines)


def _check_original_gone(original: Path) -> bool:
    if not original.exists():
        return True
    return False


def _check_archived_exists(archived: Path) -> bool:
    return archived.exists()


def _check_in_posted_dir(archived: Path, posted_dir: Path | None = None) -> bool:
    posted_dir = posted_dir or POSTED_DIR
    try:
        return archived.resolve().parent == posted_dir.resolve()
    except (OSError, ValueError):
        return False


def _check_in_queue_gone(archived: Path, queue_dir: Path | None = None) -> bool:
    queue_dir = queue_dir or QUEUE_DIR
    queue_copy = queue_dir / archived.name
    return not queue_copy.exists()


def _check_has_posted_at(archived: Path) -> bool:
    if not archived.exists():
        return False
    try:
        text = archived.read_text(encoding="utf-8")
        fm, _ = parse_frontmatter(text)
    except (OSError, ValueError):
        return False
    if not fm:
        return False
    return bool(fm.get("posted_at"))


def _check_has_platform(archived: Path) -> bool:
    if not archived.exists():
        return False
    try:
        text = archived.read_text(encoding="utf-8")
        fm, _ = parse_frontmatter(text)
    except (OSError, ValueError):
        return False
    if not fm:
        return False
    plat = fm.get("platform")
    if not plat:
        return False
    return plat in ("x", "linkedin", "blog", "buffer", "pillar")


def check_all_posted() -> dict:
    """Verify all files in posted/ have valid post-archive structure.

    Returns {"total": N, "valid": M, "invalid": [filenames]}.
    """
    if not POSTED_DIR.exists():
        return {"total": 0, "valid": 0, "invalid": []}
    results = {"total": 0, "valid": 0, "invalid": []}
    for f in sorted(POSTED_DIR.glob("*.md")):
        results["total"] += 1
        if _check_has_posted_at(f) and _check_has_platform(f):
            results["valid"] += 1
        else:
            results["invalid"].append(f.name)
    return results
