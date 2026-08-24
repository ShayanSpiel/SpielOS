"""Background work dispatch for long-running operations.

This module provides a minimal mechanism to dispatch long-running work
into background threads while keeping the runner tick fast.
"""

from __future__ import annotations

import json
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

# Patchable override (tests set this to a temp dir). When None, the dispatch
# directory resolves dynamically from the discovered project root
# (runtime/paths.py) instead of the process cwd or this file's location.
DISPATCH_DIR: Path | None = None
STALE_THRESHOLD_SECONDS = 3600  # 1 hour


def dispatch_dir() -> Path:
    if DISPATCH_DIR is not None:
        return Path(DISPATCH_DIR)
    from .paths import find_project_root

    return find_project_root() / ".spielos" / "state" / "outbound" / "async"


def _get_result_path(goal_id: str, batch_id: str) -> Path:
    """Get the file path for a dispatch result."""
    return dispatch_dir() / goal_id / f"{batch_id}.json"


def dispatch(
    goal_id: str,
    batch_id: str,
    work_fn: Callable,
    *args: Any,
    **kwargs: Any,
) -> dict:
    """Start a background thread that runs work_fn and writes result to file.

    Returns a dict with dispatch information.
    """
    result_path = _get_result_path(goal_id, batch_id)
    result_path.parent.mkdir(parents=True, exist_ok=True)

    # Check if already pending
    if result_path.exists():
        try:
            data = json.loads(result_path.read_text())
            if data.get("status") == "pending":
                return {
                    "dispatched": True,
                    "batch_id": batch_id,
                    "already_pending": True,
                    "started_at": data.get("started_at"),
                }
        except (json.JSONDecodeError, KeyError):
            # File exists but is invalid, we can overwrite
            pass

    # Mark as pending
    started_at = datetime.now(timezone.utc).isoformat()
    result_path.write_text(json.dumps({
        "status": "pending",
        "started_at": started_at,
    }))

    def _run():
        try:
            result = work_fn(*args, **kwargs)
            result_path.write_text(json.dumps({
                "status": "done",
                "result": result,
                "completed_at": datetime.now(timezone.utc).isoformat(),
            }))
        except Exception as e:
            result_path.write_text(json.dumps({
                "status": "failed",
                "error": str(e),
                "completed_at": datetime.now(timezone.utc).isoformat(),
            }))

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()

    return {
        "dispatched": True,
        "batch_id": batch_id,
        "already_pending": False,
        "started_at": started_at,
    }


def _started_at_dt(data: dict):
    """Parse started_at into an aware datetime; None if missing/invalid."""
    started_at = data.get("started_at")
    if not started_at:
        return None
    try:
        started_dt = datetime.fromisoformat(started_at)
    except ValueError:
        return None
    if started_dt.tzinfo is None:
        started_dt = started_dt.replace(tzinfo=timezone.utc)
    return started_dt


def _is_stale(data: dict) -> bool:
    """A pending file older than the threshold is stale. A pending file with
    no usable started_at is treated as stale so the workflow can recover
    instead of parking in WAITING forever."""
    started_dt = _started_at_dt(data)
    if started_dt is None:
        return True
    return (datetime.now(timezone.utc) - started_dt).total_seconds() > STALE_THRESHOLD_SECONDS


def failed_age_seconds(data: dict) -> float | None:
    """Seconds elapsed since a failed dispatch record completed.

    Returns None when the record has no usable completed_at; callers treat
    that as immediately retryable so a worker failure can always recover.
    """
    completed_at = data.get("completed_at")
    if not completed_at:
        return None
    try:
        completed_dt = datetime.fromisoformat(completed_at)
    except ValueError:
        return None
    if completed_dt.tzinfo is None:
        completed_dt = completed_dt.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - completed_dt).total_seconds()


def check(goal_id: str, batch_id: str) -> dict | None:
    """Check if background work is done. Returns result or None if pending."""
    result_path = _get_result_path(goal_id, batch_id)
    if not result_path.exists():
        return None

    try:
        data = json.loads(result_path.read_text())
    except (json.JSONDecodeError, KeyError):
        return None

    if data.get("status") == "pending":
        if _is_stale(data):
            return {
                "status": "stale",
                "error": "Background work appears stale (exceeded threshold)",
                "started_at": data.get("started_at"),
            }
        return None

    return data


def is_pending(goal_id: str, batch_id: str) -> bool:
    """Check if background work is currently pending.

    A stale pending file is NOT pending: the workflow must be able to
    re-dispatch it (execute() cleans it up and starts a fresh worker).
    """
    result_path = _get_result_path(goal_id, batch_id)
    if not result_path.exists():
        return False

    try:
        data = json.loads(result_path.read_text())
    except (json.JSONDecodeError, KeyError):
        return False

    return data.get("status") == "pending" and not _is_stale(data)


def cleanup(goal_id: str, batch_id: str) -> None:
    """Remove the dispatch file."""
    result_path = _get_result_path(goal_id, batch_id)
    if result_path.exists():
        result_path.unlink()
