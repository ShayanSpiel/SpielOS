#!/usr/bin/env python3
"""logger.py — Structured JSONL logging for ShayanWiki.

Appends JSONL entries to daily log files in logs/YYYY-MM-DD.jsonl.
Every engine.py command, state transition, script run, and gate check
is logged for visibility and debugging.

Usage:
    from logger import log, log_err
    log("INFO", "engine", "State transition", from_state="IDLE", to_state="INGESTING")
"""

import contextvars
import functools
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Optional

from state_machine import VAULT

LOG_DIR = VAULT / "logs"

# ─── Request ID (thread-safe context) ──────────────────────────────────────
_request_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("request_id", default="")

def set_request_id(request_id: str) -> None:
    """Set the request_id for the current execution context."""
    _request_id_var.set(request_id)

def get_request_id() -> str:
    """Get the current request_id, or '' if none set."""
    return _request_id_var.get()

def auto_request_id(prefix: str = "req") -> str:
    """Generate a short unique request ID and set it in context."""
    import uuid
    rid = f"{prefix}_{uuid.uuid4().hex[:12]}"
    set_request_id(rid)
    return rid


# ─── log_call context manager ──────────────────────────────────────────────

class log_call:
    """Context manager that logs function entry/exit with duration.

    Usage as context manager:
        with log_call("engine", "cmd_status", state=current_state):
            ...

    Usage as decorator:
        @log_call()
        def my_function(...):
            ...
    """

    def __init__(self, source: str, operation: str, *, level: str = "INFO", **kwargs):
        self.source = source
        self.operation = operation
        self.level = level
        self.kwargs = kwargs
        self._start: float = 0.0

    def __enter__(self):
        self._start = time.monotonic()
        log(self.level, self.source, f"START {self.operation}",
            request_id=get_request_id(), operation=self.operation, **self.kwargs)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        duration_ms = int((time.monotonic() - self._start) * 1000)
        if exc_type is not None:
            log("ERROR", self.source, f"FAIL {self.operation}",
                request_id=get_request_id(), operation=self.operation,
                duration_ms=duration_ms, error=str(exc_val), **self.kwargs)
        else:
            log(self.level, self.source, f"END {self.operation}",
                request_id=get_request_id(), operation=self.operation,
                duration_ms=duration_ms, **self.kwargs)

    # ── Decorator support ──────────────────────────────────────────────────
    def __call__(self, func: Callable) -> Callable:
        source = self.source or func.__module__.split(".")[-1] if func.__module__ else "?"
        operation = self.operation or func.__qualname__

        @functools.wraps(func)
        def wrapper(*args, **kwds):
            with log_call(source, operation, level=self.level, **self.kwargs):
                return func(*args, **kwds)
        return wrapper


# ─── Convenience: auto-decorate with source ────────────────────────────────

def logged(source: str = "", level: str = "INFO") -> Callable:
    """Decorator factory: @logged('engine') wraps func with log_call."""
    def _deco(func: Callable) -> Callable:
        src = source or func.__module__.split(".")[-1] if func.__module__ else "?"
        return log_call(src, func.__qualname__, level=level)(func)
    return _deco


def _ensure_log_dir() -> Path:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    return LOG_DIR


def _log_path() -> Path:
    return _ensure_log_dir() / f"{datetime.now().strftime('%Y-%m-%d')}.jsonl"


def log(level: str, source: str, message: str, **extra) -> None:
    """Write a structured JSONL log entry.

    Args:
        level: INFO, WARN, ERROR
        source: Script or component name (e.g. "engine", "validate_post", "pipeline.sh")
        message: Human-readable description
        extra: Any additional key=value fields to include (exit_code, duration_ms, etc.)
    """
    entry = {
        "timestamp": datetime.now().isoformat(timespec="milliseconds"),
        "level": level.upper(),
        "source": source,
        "message": message,
    }
    entry.update(extra)

    path = _log_path()
    try:
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, default=str) + "\n")
    except OSError:
        pass  # Fail silently — logging should never break the system


def log_err(source: str, message: str, **extra) -> None:
    """Shorthand for log('ERROR', ...)."""
    log("ERROR", source, message, **extra)


def read_logs(days: int = 1, level: str | None = None,
              source: str | None = None, tail: int | None = None) -> list[dict]:
    """Read log entries from recent daily log files.

    Args:
        days: How many days back to read (default 1)
        level: Filter by level (INFO/WARN/ERROR)
        source: Filter by source name
        tail: Only return last N entries

    Returns:
        List of log entry dicts, newest first
    """
    from datetime import timedelta

    entries = []
    now = datetime.now()
    log_dir = _ensure_log_dir()

    for i in range(days):
        date = (now - timedelta(days=i)).strftime("%Y-%m-%d")
        path = log_dir / f"{date}.jsonl"
        if not path.exists():
            continue
        try:
            with open(path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        entry = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if level and entry.get("level", "").upper() != level.upper():
                        continue
                    if source and entry.get("source", "").lower() != source.lower():
                        continue
                    entries.append(entry)
        except OSError:
            continue

    entries.sort(key=lambda e: e.get("timestamp", ""), reverse=True)

    if tail:
        entries = entries[:tail]

    return entries


def print_logs(days: int = 7, level: str | None = None,
               source: str | None = None, tail: int | None = 30) -> None:
    """Pretty-print recent log entries to stdout."""
    entries = read_logs(days=days, level=level, source=source, tail=tail)

    if not entries:
        print(f"No log entries found (days={days}, level={level}, source={source})")
        return

    print(f"── Recent Logs (last {len(entries)} of {days}d"
          f"{f', level={level}' if level else ''}"
          f"{f', source={source}' if source else ''}) ──")
    print()

    for entry in entries:
        ts = entry.get("timestamp", "?")[11:23]  # HH:MM:SS.mmm
        lvl = entry.get("level", "?").ljust(5)
        src = entry.get("source", "?").ljust(16)
        msg = entry.get("message", "")

        extra_parts = []
        for key in ("exit_code", "duration_ms", "from_state", "to_state",
                     "script", "command", "target"):
            val = entry.get(key)
            if val is not None:
                extra_parts.append(f"{key}={val}")
        extra_str = "  ".join(extra_parts)
        sep = " │ " if extra_str else ""

        print(f"  {ts}  {lvl}  {src}  {msg}{sep}{extra_str}")
    print()
