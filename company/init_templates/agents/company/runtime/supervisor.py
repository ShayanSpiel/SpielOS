"""OS-level external supervisor for the company runner (Watchdog v2).

Goal goal-577aaacc7d / change-7cc84900b7: the runner daemon crashed on
2026-08-15 about 13:40Z and nothing detected it for over 12 minutes — the
runner self-observes (writes its own heartbeat, creates and delivers its own
notifications), so a dead daemon has no in-process detector left. This module
is the OUT-OF-PROCESS watchdog: it runs outside the runner (launchd agent,
cron, `--loop`, or one-shot `--check`) and, on heartbeat/PID staleness:

* appends one line to ``watchdog_incidents.jsonl`` (the same file the runner's
  live HUD surfaces in ``live_status.json``),
* restarts the daemon through ``RunnerService`` (direct subprocess, no shell,
  no pipes, no redirects),
* alerts via a macOS notification (best-effort),
* respects ``automation.json``: a deliberately stopped runner (``company
  runner stop``) is never restarted,
* rate-limits restarts (``supervisor.json`` bookkeeping) so a crash-looping
  daemon cannot trigger a restart storm under launchd StartInterval.

Heartbeat semantics match the plugin's contract: ``alive_at`` (heartbeat
thread, every 10s) is the PROCESS signal — stale past ``alive_stale_seconds``
means the daemon is dead; ``last_tick`` (per watch cycle) is the LOOP signal —
stale past ``loop_stale_seconds`` with a fresh ``alive_at`` means the process
lives but its serial watch loop is wedged. A wedged process is terminated
(SIGTERM, then SIGKILL after a short grace) before restart, because
``RunnerService.start`` will not replace a live-but-hung process.

Runnable as a script (``python3 -B .agents/company/runtime/supervisor.py
--check``) or imported (``from company.runtime.supervisor import Supervisor``).
"""

from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# Works both as a script (`python3 -B .../supervisor.py`) and as a module
# (`company.runtime.supervisor`): as a script, the repo root goes on sys.path
# so `company.*` imports resolve without PYTHONPATH.
if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from company.runtime.service import RunnerService  # noqa: E402
from company.runtime import config as runtime_config  # noqa: E402

# Thresholds mirror the plugin constants (ALIVE_STALE_MS 45_000 / LOOP_STALE_MS
# 75_000) in seconds.
SUPERVISOR_ALIVE_STALE_SECONDS = 45
SUPERVISOR_LOOP_STALE_SECONDS = 75
# Minimum gap between two supervisor-initiated restarts (crash-loop guard).
SUPERVISOR_RESTART_COOLDOWN_SECONDS = 60
# How long to wait for a wedged process to exit on SIGTERM before SIGKILL.
SUPERVISOR_TERMINATE_GRACE_SECONDS = 5

HEARTBEAT_FILENAME = "runner.heartbeat"
PID_FILENAME = "runner.pid"
INCIDENTS_FILENAME = "watchdog_incidents.jsonl"
SUPERVISOR_META_FILENAME = "supervisor.json"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_dt(value):
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _age_seconds(value, now: datetime) -> float | None:
    """Age of an ISO timestamp in seconds; None when unparsable."""
    parsed = _parse_dt(value)
    if parsed is None:
        return None
    return max(0.0, (now - parsed).total_seconds())


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def _terminate(pid: int, grace_seconds: float = SUPERVISOR_TERMINATE_GRACE_SECONDS) -> bool:
    """SIGTERM, then SIGKILL after the grace. Returns True when the process is
    gone (or was already gone). Never raises."""
    if not _pid_alive(pid):
        return True
    try:
        os.kill(pid, signal.SIGTERM)
    except OSError:
        pass
    deadline = time.monotonic() + grace_seconds
    while time.monotonic() < deadline:
        if not _pid_alive(pid):
            return True
        time.sleep(0.2)
    try:
        os.kill(pid, signal.SIGKILL)
    except OSError:
        pass
    time.sleep(0.2)
    return not _pid_alive(pid)


class Supervisor:
    """External watchdog: heartbeat/PID freshness + restart + incident log.

    All state lives under ``state_dir`` (default ``<project_root>/.spielos/
    state``) so tests can point it at a temp directory; restart actions go
    through ``RunnerService`` (or a patched ``_restart`` in tests).
    """

    def __init__(self, project_root, *, state_dir=None, db_path=None,
                 alive_stale_seconds: float = SUPERVISOR_ALIVE_STALE_SECONDS,
                 loop_stale_seconds: float = SUPERVISOR_LOOP_STALE_SECONDS,
                 restart_cooldown_seconds: float = SUPERVISOR_RESTART_COOLDOWN_SECONDS,
                 terminate_grace_seconds: float = SUPERVISOR_TERMINATE_GRACE_SECONDS):
        self.project_root = Path(project_root)
        self.state_dir = Path(state_dir) if state_dir else self.project_root / ".spielos" / "state"
        self.db_path = Path(db_path) if db_path else self.state_dir / "company.sqlite"
        self.alive_stale_seconds = alive_stale_seconds
        self.loop_stale_seconds = loop_stale_seconds
        self.restart_cooldown_seconds = restart_cooldown_seconds
        self.terminate_grace_seconds = terminate_grace_seconds
        self.heartbeat_path = self.state_dir / HEARTBEAT_FILENAME
        self.pid_path = self.state_dir / PID_FILENAME
        self.incidents_path = self.state_dir / INCIDENTS_FILENAME
        self.meta_path = self.state_dir / SUPERVISOR_META_FILENAME

    # ------------------------------------------------------------------ #
    # State readers                                                       #
    # ------------------------------------------------------------------ #

    def _read_heartbeat(self) -> dict:
        """Parsed heartbeat payload; {} when missing or unparsable."""
        try:
            value = json.loads(self.heartbeat_path.read_text(encoding="utf-8"))
            return value if isinstance(value, dict) else {}
        except (OSError, ValueError, json.JSONDecodeError):
            return {}

    def _read_pid(self) -> int | None:
        try:
            value = json.loads(self.pid_path.read_text(encoding="utf-8"))
            return int(value["pid"])
        except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError):
            return None

    def _automation_enabled(self) -> bool:
        """True when automation.json is absent (default-on) or enabled."""
        try:
            value = json.loads((self.state_dir / "automation.json").read_text(encoding="utf-8"))
            return bool(value.get("enabled", True))
        except OSError:
            return True
        except (ValueError, json.JSONDecodeError):
            return False

    def _restart_bookkeeping(self) -> dict:
        try:
            value = json.loads(self.meta_path.read_text(encoding="utf-8"))
            return value if isinstance(value, dict) else {}
        except (OSError, ValueError, json.JSONDecodeError):
            return {}

    def _record_restart(self, *, action: str) -> dict:
        meta = self._restart_bookkeeping()
        meta["last_restart_at"] = _now_iso()
        meta["restart_count"] = int(meta.get("restart_count", 0)) + 1
        meta["last_action"] = action
        try:
            self.meta_path.parent.mkdir(parents=True, exist_ok=True)
            self.meta_path.write_text(json.dumps(meta) + "\n", encoding="utf-8")
        except OSError:  # pragma: no cover - defensive; bookkeeping only
            pass
        return meta

    def _restart_attempted_recently(self, now=None) -> bool:
        """True when a restart happened inside the cooldown window."""
        meta = self._restart_bookkeeping()
        last = _parse_dt(meta.get("last_restart_at"))
        if last is None:
            return False
        now = now or datetime.now(timezone.utc)
        return (now - last).total_seconds() < self.restart_cooldown_seconds

    # ------------------------------------------------------------------ #
    # Actions                                                             #
    # ------------------------------------------------------------------ #

    def _append_incident(self, incident: dict) -> None:
        """Append one JSON line to watchdog_incidents.jsonl (best-effort)."""
        try:
            self.incidents_path.parent.mkdir(parents=True, exist_ok=True)
            with self.incidents_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(incident, ensure_ascii=False) + "\n")
        except OSError:  # pragma: no cover - defensive; never raise from supervision
            pass

    def _notify_macos(self, title: str, message: str) -> bool:
        """Best-effort macOS notification via osascript (no shell, no pipes)."""
        try:
            completed = subprocess.run(
                ["osascript", "-e",
                 f'display notification "{message}" with title "{title}"'],
                capture_output=True, text=True, timeout=10)
            return completed.returncode == 0
        except (OSError, subprocess.TimeoutExpired):
            return False

    def _restart(self, interval: float = 2.0) -> dict:
        """Start the daemon through RunnerService; return its status."""
        service = RunnerService(self.project_root, self.db_path)
        return service.start(interval=interval)

    def _terminate_pid(self, pid: int) -> bool:
        return _terminate(pid, self.terminate_grace_seconds)

    # ------------------------------------------------------------------ #
    # One supervised pass                                                 #
    # ------------------------------------------------------------------ #

    def supervise_once(self, *, restart: bool = True, alert: bool = True,
                       now=None) -> dict:
        """One external watchdog pass.

        Returns a status dict with ``healthy`` (bool), ``signal``
        (None | "runner_down" | "loop_wedged"), ``actions`` (list of what the
        supervisor did), ``incident`` (the appended record, if any) and
        ``exit_code`` (0 = healthy or recovered, 1 = still down).
        """
        now = now or datetime.now(timezone.utc)
        enabled = self._automation_enabled()
        if not enabled:
            return {"healthy": True, "signal": None, "actions": ["disabled"],
                    "incident": None, "exit_code": 0,
                    "reason": "automation disabled; supervisor stands down"}

        heartbeat = self._read_heartbeat()
        alive_age = _age_seconds(heartbeat.get("alive_at"), now)
        tick_age = _age_seconds(heartbeat.get("last_tick"), now)
        pid = self._read_pid()
        pid_alive = bool(pid and _pid_alive(pid))

        runner_down = (not pid_alive) or (alive_age is not None and alive_age > self.alive_stale_seconds)
        loop_wedged = (not runner_down) and alive_age is not None and tick_age is not None \
            and tick_age > self.loop_stale_seconds

        if not runner_down and not loop_wedged:
            return {"healthy": True, "signal": None, "actions": ["ok"],
                    "incident": None, "exit_code": 0, "pid": pid,
                    "alive_age_seconds": alive_age, "tick_age_seconds": tick_age}

        signal_name = "runner_down" if runner_down else "loop_wedged"
        actions: list[str] = []
        if runner_down and pid_alive and pid is not None:
            # PID file says alive but the heartbeat thread is silent: hard
            # terminate before restart (RunnerService.start would not replace
            # a live process).
            actions.append("terminated")
            self._terminate_pid(pid)

        action = "none"
        if restart:
            if self._restart_attempted_recently(now=now):
                action = "cooldown_skipped"
                actions.append("cooldown_skipped")
            else:
                try:
                    status = self._restart()
                    # Truthful bookkeeping: record what actually happened
                    # AFTER checking the restart result, so supervisor.json
                    # never claims a restart that failed. The timestamp still
                    # advances on a failed attempt to keep the crash-loop
                    # cooldown effective.
                    if status.get("running"):
                        action = "restarted"
                        actions.append("restarted")
                    else:
                        action = "restart_failed"
                        actions.append("restart_failed")
                    self._record_restart(action=action)
                except Exception as exc:  # pragma: no cover - defensive
                    action = "restart_failed"
                    actions.append(f"restart_failed: {exc}")
                    self._record_restart(action="restart_failed")

        if alert and action in {"restarted", "restart_failed"}:
            notified = self._notify_macos(
                runtime_config.supervisor_alert_title(),
                f"Runner {signal_name} detected; {action}.")
            actions.append("alerted" if notified else "alert_failed")

        incident = {
            "ts": now.isoformat(),
            "incident": signal_name,
            "signal": signal_name,
            "heartbeat_age_seconds": alive_age,
            "tick_age_seconds": tick_age,
            "pid": pid,
            "action": action,
            "detail": {"supervisor": "external", "restart": restart},
        }
        self._append_incident(incident)
        # A supervised restart that brought the daemon back is a recovery, so
        # the pass reports healthy; anything still down exits non-zero.
        recovered = action == "restarted"
        return {"healthy": recovered, "signal": signal_name,
                "actions": actions, "incident": incident,
                "exit_code": 0 if recovered else 1,
                "pid": pid, "alive_age_seconds": alive_age,
                "tick_age_seconds": tick_age}

    # ------------------------------------------------------------------ #
    # Continuous loop (launchd/cron alternative)                          #
    # ------------------------------------------------------------------ #

    def supervise_loop(self, *, interval_seconds: float = 30.0, restart: bool = True,
                       alert: bool = True, max_passes: int | None = None) -> None:
        """Run supervised passes until interrupted (or max_passes reached).

        For launchd, prefer StartInterval with one-shot ``--check``; this loop
        exists for cron-less manual/foreground supervision.
        """
        passes = 0
        while max_passes is None or passes < max_passes:
            result = self.supervise_once(restart=restart, alert=alert)
            print(json.dumps(result, ensure_ascii=False, default=str), flush=True)
            passes += 1
            if max_passes is not None and passes >= max_passes:
                break
            time.sleep(interval_seconds)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="supervisor.py",
        description="External OS-level supervisor for the SpielOS company runner "
                    "(heartbeat check, restart, incident log, macOS alert).")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true",
                      help="run ONE supervised pass and exit (default; launchd/cron friendly)")
    mode.add_argument("--loop", action="store_true",
                      help="run supervised passes continuously")
    parser.add_argument("--interval", type=float, default=30.0,
                        help="seconds between passes in --loop mode (default 30)")
    parser.add_argument("--project-root", default=None,
                        help="repo root (default: derived from this file's location)")
    parser.add_argument("--state-dir", default=None,
                        help="state directory (default: <root>/.spielos/state)")
    parser.add_argument("--db", default=None,
                        help="company database path (default: <state-dir>/company.sqlite)")
    parser.add_argument("--no-restart", action="store_true",
                        help="detect and record only; never restart the daemon")
    parser.add_argument("--no-alert", action="store_true",
                        help="do not send macOS notifications")
    parser.add_argument("--alive-stale-seconds", type=float, default=SUPERVISOR_ALIVE_STALE_SECONDS)
    parser.add_argument("--loop-stale-seconds", type=float, default=SUPERVISOR_LOOP_STALE_SECONDS)
    parser.add_argument("--restart-cooldown-seconds", type=float,
                        default=SUPERVISOR_RESTART_COOLDOWN_SECONDS)
    parser.add_argument("--json", action="store_true",
                        help="print the pass result as JSON")
    return parser


def _human(result: dict) -> str:
    signal_name = result.get("signal")
    if not signal_name:
        return "SpielOS runner healthy (heartbeat fresh)."
    return (f"SpielOS runner {signal_name} detected: "
            f"actions={', '.join(result.get('actions') or [])} "
            f"exit={result.get('exit_code')}")


def main(argv=None) -> int:
    args = _build_parser().parse_args(argv)
    project_root = Path(args.project_root) if args.project_root \
        else find_project_root()
    supervisor = Supervisor(
        project_root, state_dir=args.state_dir, db_path=args.db,
        alive_stale_seconds=args.alive_stale_seconds,
        loop_stale_seconds=args.loop_stale_seconds,
        restart_cooldown_seconds=args.restart_cooldown_seconds)
    restart = not args.no_restart
    alert = not args.no_alert
    if args.loop:
        supervisor.supervise_loop(interval_seconds=args.interval,
                                  restart=restart, alert=alert)
        return 0
    result = supervisor.supervise_once(restart=restart, alert=alert)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, default=str))
    else:
        print(_human(result))
    return int(result.get("exit_code", 0))


if __name__ == "__main__":
    sys.exit(main())
