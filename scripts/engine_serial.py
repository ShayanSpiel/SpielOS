#!/usr/bin/env python3
"""engine_serial.py — File I/O + structured JSONL logging.

Kernel-level I/O: all disk reads and writes go through this module.
Tools never read or write files directly.
"""

import contextvars
import functools
import json
import os
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable

from engine_state import LOG_DIR

# ─── Atomic File I/O ────────────────────────────────────────────────────

def atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = tempfile.NamedTemporaryFile(
        mode="w", dir=str(path.parent), prefix=".tmp-", suffix=path.suffix, delete=False
    )
    try:
        tmp.write(content)
        tmp.close()
        os.replace(tmp.name, str(path))
    except Exception:
        if os.path.exists(tmp.name):
            os.unlink(tmp.name)
        raise


def read_file(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def write_file(path: Path, content: str) -> None:
    atomic_write(path, content)


def read_json(path: Path) -> dict | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def write_json(path: Path, data: Any) -> None:
    atomic_write(path, json.dumps(data, indent=2, default=str))


# ─── JSONL Logger ───────────────────────────────────────────────────────

_request_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("request_id", default="")

def set_request_id(request_id: str) -> None:
    _request_id_var.set(request_id)

def get_request_id() -> str:
    return _request_id_var.get()

def auto_request_id(prefix: str = "req") -> str:
    import uuid
    rid = f"{prefix}_{uuid.uuid4().hex[:12]}"
    set_request_id(rid)
    return rid


def _log_path() -> Path:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    return LOG_DIR / f"{datetime.now().strftime('%Y-%m-%d')}.jsonl"


def log(level: str, source: str, message: str, **extra) -> None:
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
        pass


def log_err(source: str, message: str, **extra) -> None:
    log("ERROR", source, message, **extra)


# ─── Log Call Context Manager / Decorator ────────────────────────────────

class log_call:
    def __init__(self, source: str, operation: str, *, level: str = "INFO", **kwargs):
        self.source = source
        self.operation = operation
        self.level = level
        self.kwargs = kwargs
        self._start: float = 0.0

    def __enter__(self):
        import time
        self._start = time.monotonic()
        log(self.level, self.source, f"START {self.operation}",
            request_id=get_request_id(), operation=self.operation, **self.kwargs)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        import time
        duration_ms = int((time.monotonic() - self._start) * 1000)
        if exc_type is not None:
            log("ERROR", self.source, f"FAIL {self.operation}",
                request_id=get_request_id(), operation=self.operation,
                duration_ms=duration_ms, error=str(exc_val), **self.kwargs)
        else:
            log(self.level, self.source, f"END {self.operation}",
                request_id=get_request_id(), operation=self.operation,
                duration_ms=duration_ms, **self.kwargs)

    def __call__(self, func: Callable) -> Callable:
        source = self.source or (func.__module__.split(".")[-1] if func.__module__ else "?")
        operation = self.operation or func.__qualname__

        @functools.wraps(func)
        def wrapper(*args, **kwds):
            with log_call(source, operation, level=self.level, **self.kwargs):
                return func(*args, **kwds)
        return wrapper


def logged(source: str = "", level: str = "INFO") -> Callable:
    def _deco(func: Callable) -> Callable:
        src = source or (func.__module__.split(".")[-1] if func.__module__ else "?")
        return log_call(src, func.__qualname__, level=level)(func)
    return _deco


# ─── Log Reader ─────────────────────────────────────────────────────────

def read_logs(days: int = 1, level: str | None = None,
              source: str | None = None, tail: int | None = None) -> list[dict]:
    entries: list[dict] = []
    now = datetime.now()
    for i in range(days):
        date = (now - timedelta(days=i)).strftime("%Y-%m-%d")
        path = LOG_DIR / f"{date}.jsonl"
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
    entries = read_logs(days=days, level=level, source=source, tail=tail)
    if not entries:
        print(f"No log entries found (days={days}, level={level}, source={source})")
        return
    print(f"── Recent Logs (last {len(entries)} of {days}d"
          f"{f', level={level}' if level else ''}"
          f"{f', source={source}' if source else ''}) ──")
    print()
    for entry in entries:
        ts = entry.get("timestamp", "?")[11:23]
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
