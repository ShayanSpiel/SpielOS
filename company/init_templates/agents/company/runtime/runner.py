"""Durable pull worker that turns persisted state into an active company loop."""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .alignment import approval_key, priority_score
from .loop import Runtime
from .notifications import digest_payload
from .service import automation_enabled
from .util import parse_dt

logger = logging.getLogger("company.runtime.runner")

# Watchdog constants. The runner is its own watchdog: the watch loop stamps a
# heartbeat file every cycle so external readers (the OpenCode notifications
# plugin) can distinguish a dead daemon from an idle one, and a rate-limited
# stall scan emits actionable stuck_goal notifications instead of parking
# silently (2026-08-15 incident: daemon crash went unnoticed for ~34 minutes).
#
# 2026-08-15 wedge hardening: the heartbeat is now TWO signals so a normal
# long tick can never false-alarm "runner down" while a wedged loop is still
# caught. The watch loop stamps ``last_tick`` once per cycle (loop progress);
# a dedicated lightweight heartbeat thread stamps ``alive_at`` every
# ``HEARTBEAT_INTERVAL_SECONDS`` regardless of how long a tick takes (process
# liveness). The plugin alerts on a stale ``alive_at`` (process dead) or a
# stale ``last_tick`` beyond the loop-wedge threshold (hung serial loop).
HEARTBEAT_FILENAME = "runner.heartbeat"
HEARTBEAT_INTERVAL_SECONDS = 10     # alive_at cadence while the daemon runs
STALL_CHECK_INTERVAL_SECONDS = 60   # how often the watchdog scan runs
STALL_GRACE_SECONDS = 90            # resume_at may be this late before alerting
DISPATCH_STALE_SECONDS = 3600       # mirrors runtime.async_dispatch threshold
# Lease liveness: store.acquire() grants a 60s TTL lease (no renewal). A tick
# that holds its lease beyond LEASE_HELD_GRACE_SECONDS with no cycle
# advancement is wedged — the bounded measure path completes well under this.
LEASE_TTL_SECONDS = 60              # mirrors store.acquire(seconds=60)
LEASE_HELD_GRACE_SECONDS = 55       # above the bounded-tick budget, below TTL
# A pending async dispatch file whose worker thread died with its process can
# be recovered as soon as it predates this daemon generation by more than
# DISPATCH_DEAD_WORKER_GRACE_SECONDS (a fresh pending file in THIS generation
# has a live worker thread and must never be touched).
DISPATCH_DEAD_WORKER_GRACE_SECONDS = 90
# Send-activity liveness (2026-08-15 quota-stall incident): outbound batches
# b6/b7 stalled ~6h on provider daily-quota exhaustion while their workers
# stayed alive and the runtime stayed healthy — nothing alerted because every
# watchdog signal above needs a dead or wedged worker, and a live-but-starved
# worker is indistinguishable from normal slow sending. The sent ledger is the
# only liveness proof: a dispatch pending longer than SEND_STALL_GRACE_SECONDS
# whose newest ledger send is ALSO older than the grace is stalled. A dedicated
# rate limiter bounds re-emission (the store upsert keeps one notification row
# per goal/run/kind, but re-stamping it refreshes created_at).
SEND_ACTIVITY_CHECK_INTERVAL_SECONDS = 300  # dedicated send-scan limiter
SEND_STALL_GRACE_SECONDS = 900              # pending w/o a new send -> alert
# Scheduled progress digest (goal-chat-visible-supervision-20260815): the
# runner's watch loop emits one company-wide ``watchdog_digest`` notification
# at most once per digest interval while ANY goal is active, so supervision is
# visibly present inside the chat on a schedule even when no event fires. The
# last-emitted stamp is durable (state file beside the heartbeat), so a daemon
# restart inside the interval never re-emits and an interval that elapsed while
# the daemon was down produces exactly one digest on the next watch cycle.
DIGEST_INTERVAL_SECONDS = 900               # default 15 minutes
DIGEST_FILENAME = "runner_digest.json"      # durable last-emitted stamp
DIGEST_RECENT_TERMINAL_LIMIT = 5            # last N terminal outcomes shown
DIGEST_PENDING_SCAN_LIMIT = 100             # pending rows scanned for approvals
# Watchdog v2 live HUD (goal-577aaacc7d / change-7cc84900b7): the daemon
# watch loop writes ``live_status.json`` beside the heartbeat once per cycle
# so the OpenCode plugin HUD ticker and any external reader can render a live
# countdown surface (heartbeat ages, next digest, goal resume countdowns,
# pending approvals, retry ledger, watchdog incidents tail) without running
# company CLI queries. Written ONLY from the daemon watch path — standalone
# ``tick()`` calls must never refresh it (same rule as the heartbeat), or a
# fallback tick would mask a dead daemon's stale surface.
LIVE_STATUS_FILENAME = "live_status.json"
LIVE_STATUS_RECENT_TERMINAL_LIMIT = 3       # last N terminal outcomes shown
LIVE_STATUS_RETRY_LIMIT = 5                 # newest retry ledger rows shown
LIVE_STATUS_INCIDENTS_TAIL = 3              # last N watchdog incidents shown
INCIDENTS_FILENAME = "watchdog_incidents.jsonl"


def heartbeat_age(heartbeat_path, now=None) -> float | None:
    """Seconds since the last watch tick; None when missing or unparsable.

    ``last_tick`` is the LOOP signal: it goes stale when the serial watch
    loop stops completing cycles (wedged or dead), even though the alive_at
    thread keeps stamping.
    """
    try:
        data = json.loads(Path(heartbeat_path).read_text(encoding="utf-8"))
        last_tick = data.get("last_tick")
        if not last_tick:
            return None
        parsed = datetime.fromisoformat(str(last_tick).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        now = now or datetime.now(timezone.utc)
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)
        return max(0.0, (now - parsed).total_seconds())
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return None


def heartbeat_alive_age(heartbeat_path, now=None) -> float | None:
    """Seconds since the heartbeat thread last stamped ``alive_at``.

    This is the PROCESS signal: the dedicated heartbeat thread stamps it
    every HEARTBEAT_INTERVAL_SECONDS independently of how long the current
    tick runs, so a normal ~3-minute measure poll never makes it stale. Only
    a dead (or hard-hung) process stops the thread. None when the payload
    predates the alive_at field or is unreadable.
    """
    try:
        data = json.loads(Path(heartbeat_path).read_text(encoding="utf-8"))
        alive_at = data.get("alive_at")
        if not alive_at:
            return None
        parsed = datetime.fromisoformat(str(alive_at).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        now = now or datetime.now(timezone.utc)
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)
        return max(0.0, (now - parsed).total_seconds())
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return None


def runner_down_signal(heartbeat_path, max_age_seconds: float, now=None) -> dict | None:
    """The runner_down watchdog payload when the heartbeat is stale, else None.

    A missing or unparsable heartbeat yields None: a freshly installed runner
    (or one that predates the heartbeat) must not false-positive. This is the
    primary dead-daemon detector; the watch loop's own death notification is
    only a best-effort secondary signal.
    """
    age = heartbeat_age(heartbeat_path, now=now)
    if age is None or age <= max_age_seconds:
        return None
    return {
        "signal": "runner_down",
        "heartbeat_age_seconds": age,
        "max_age_seconds": max_age_seconds,
    }


def last_send_at(sent_log_path, now=None) -> datetime | None:
    """Newest send timestamp in the outbound sent ledger, else None.

    The ledger (``.spielos/state/outbound/sent.json``) is a dict with a
    ``sent`` list; entries carry ``timestamp`` (``sent_at`` accepted as a
    fallback). Returns None — the caller then skips quietly — when the ledger
    is missing, unreadable, not a dict, has no sent entries, or no entry
    timestamp is usable, because there is no send-liveness signal to reason
    about. A ledger timestamp in the future (clock skew) also yields None: it
    is not evidence of stalled sending either way.
    """
    try:
        data = json.loads(Path(sent_log_path).read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    newest = None
    for entry in data.get("sent", []):
        if not isinstance(entry, dict):
            continue
        parsed = Runner._parse_dt(entry.get("timestamp") or entry.get("sent_at"))
        if parsed is None:
            continue
        if newest is None or parsed > newest:
            newest = parsed
    if newest is None:
        return None
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    return newest if newest <= now else None


class Runner:
    def __init__(self, runtime: Runtime, *,
                 stall_check_interval_seconds: float = STALL_CHECK_INTERVAL_SECONDS,
                 stall_grace_seconds: float = STALL_GRACE_SECONDS,
                 dispatch_stale_seconds: float = DISPATCH_STALE_SECONDS,
                 heartbeat_interval_seconds: float = HEARTBEAT_INTERVAL_SECONDS,
                 lease_held_grace_seconds: float = LEASE_HELD_GRACE_SECONDS,
                 dead_worker_grace_seconds: float = DISPATCH_DEAD_WORKER_GRACE_SECONDS,
                 send_activity_check_interval_seconds: float = SEND_ACTIVITY_CHECK_INTERVAL_SECONDS,
                 send_stall_grace_seconds: float = SEND_STALL_GRACE_SECONDS,
                 digest_interval_seconds: float = DIGEST_INTERVAL_SECONDS):
        self.runtime = runtime
        self._stall_check_interval_seconds = stall_check_interval_seconds
        self._stall_grace_seconds = stall_grace_seconds
        self._dispatch_stale_seconds = dispatch_stale_seconds
        self._heartbeat_interval_seconds = heartbeat_interval_seconds
        self._lease_held_grace_seconds = lease_held_grace_seconds
        self._dead_worker_grace_seconds = dead_worker_grace_seconds
        self._send_activity_check_interval_seconds = send_activity_check_interval_seconds
        self._send_stall_grace_seconds = send_stall_grace_seconds
        self._digest_interval_seconds = digest_interval_seconds
        self._last_stall_check = 0.0
        self._last_send_activity_check = 0.0
        self._active_goal_id = None
        self._cycle = 0
        # Heartbeat state: the watch loop stamps last_tick/cycle per cycle;
        # the heartbeat thread stamps alive_at on the same payload. A lock
        # keeps the two writers from losing each other's fields.
        self._hb_lock = threading.Lock()
        self._hb_payload = {"pid": os.getpid()}
        self._hb_stop = threading.Event()
        self._hb_thread: threading.Thread | None = None
        # Daemon generation boundary for dead-worker dispatch recovery: any
        # pending dispatch file created before this Runner existed cannot
        # have a live worker thread (threads die with their process).
        self._generation_started_at = datetime.now(timezone.utc)

    def heartbeat_path(self) -> Path:
        """The heartbeat file lives beside the runtime database (.spielos/state)."""
        return self.runtime.store.path.parent / HEARTBEAT_FILENAME

    def write_heartbeat(self) -> None:
        """Stamp the watch cycle so external readers detect a dead daemon.

        Only the daemon watch loop calls this; standalone `tick()` calls (the
        plugin's fallback tick, manual CLI ticks) must NOT refresh the file or
        they would mask a dead daemon. Best-effort: a failed write is the
        signal.
        """
        self._cycle += 1
        with self._hb_lock:
            self._hb_payload.update({
                "last_tick": datetime.now(timezone.utc).isoformat(),
                "cycle": self._cycle,
            })
            self._write_heartbeat_payload()

    def _stamp_alive(self) -> None:
        """Heartbeat-thread stamp: process liveness, independent of tick length."""
        with self._hb_lock:
            self._hb_payload["alive_at"] = datetime.now(timezone.utc).isoformat()
            self._write_heartbeat_payload()

    def _write_heartbeat_payload(self) -> None:
        try:
            path = self.heartbeat_path()
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(self._hb_payload) + "\n", encoding="utf-8")
        except OSError:  # pragma: no cover - defensive; stale heartbeat is the signal
            pass

    def _start_heartbeat_thread(self) -> None:
        """Run the alive_at stamper while the watch loop lives.

        Idempotent: a second watch() on the same Runner must not spawn a
        second thread. The thread is daemon so a wedged tick can never keep
        the daemon process from exiting.
        """

        def _loop():
            while not self._hb_stop.wait(self._heartbeat_interval_seconds):
                self._stamp_alive()

        if self._hb_thread is not None and self._hb_thread.is_alive():
            return
        self._hb_stop.clear()
        self._hb_thread = threading.Thread(target=_loop, name="runner-heartbeat",
                                           daemon=True)
        self._hb_thread.start()

    def _stop_heartbeat_thread(self) -> None:
        self._hb_stop.set()

    # ------------------------------------------------------------------ #
    # Live status surface (Watchdog v2)                                  #
    # ------------------------------------------------------------------ #

    def live_status_path(self) -> Path:
        """The live HUD file lives beside the heartbeat (.spielos/state)."""
        return self.runtime.store.path.parent / LIVE_STATUS_FILENAME

    def _write_live_status(self, now=None) -> None:
        """Refresh ``live_status.json`` (daemon watch path only).

        Best-effort like the heartbeat: a failed write must never break the
        watch loop — the HUD is a surface, not a liveness signal. Standalone
        ``tick()`` calls never reach here (see module constants).
        """
        now = now or datetime.now(timezone.utc)
        try:
            path = self.live_status_path()
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(self._live_status_payload(now)) + "\n",
                            encoding="utf-8")
        except Exception:  # pragma: no cover - cosmetic surface; never kill the daemon
            pass

    def _live_status_payload(self, now: datetime) -> dict:
        """Bounded projection for the HUD: heartbeat ages, digest countdown,
        active goal resume countdowns, pending approvals, recent terminals,
        retry ledger, and the watchdog incident tail."""
        rows = self.runtime.list_goals()
        active = [row for row in rows if row["goal"]["goal_status"] == "active"]
        active_goals = []
        for row in active:
            cycle = row["cycle"]
            resume_in_seconds = None
            resume_at = cycle.get("resume_at")
            if resume_at:
                parsed = self._parse_dt(resume_at)
                if parsed is not None:
                    resume_in_seconds = round((parsed - now).total_seconds())
            active_goals.append({
                "goal_id": row["goal"]["id"], "name": row["goal"]["name"],
                "stage": cycle["stage"], "step": cycle["step"],
                "run_status": cycle["run_status"], "resume_at": resume_at,
                "resume_in_seconds": resume_in_seconds,
            })
        approvals = [
            row for row in self.runtime.store.notifications(
                "pending", DIGEST_PENDING_SCAN_LIMIT)
            if row["kind"] == "approval_required"]
        recent_terminals = [
            {"goal_id": row["id"], "name": row["name"],
             "goal_status": row["goal_status"]}
            for row in self.runtime.store.goal_summaries(
                statuses=("achieved", "abandoned", "expired"),
                limit=LIVE_STATUS_RECENT_TERMINAL_LIMIT)]
        retry_ledger = [
            {"goal_id": row["goal_id"], "run_id": row["run_id"],
             "attempt": row["attempt"], "status": row["status"],
             "first_error": row.get("first_error"),
             "next_retry_at": row.get("next_retry_at"),
             "updated_at": row["updated_at"]}
            for row in self.runtime.store.dispatch_retries(
                limit=LIVE_STATUS_RETRY_LIMIT)]
        next_digest_at = None
        if active:
            last = self._last_digest_emitted_at()
            if last is None:
                # No digest yet this period: the first one is due now.
                next_digest_at = now.isoformat()
            else:
                next_digest_at = (last + timedelta(
                    seconds=self._digest_interval_seconds)).isoformat()
        return {
            "ts": now.isoformat(),
            "heartbeat": dict(self._hb_payload),
            "next_digest_at": next_digest_at,
            "active_goals": active_goals,
            "pending_approvals": len(approvals),
            "recent_terminals": recent_terminals,
            "retry_ledger": retry_ledger,
            "incidents_tail": self._incidents_tail(),
        }

    def _incidents_tail(self, limit: int = LIVE_STATUS_INCIDENTS_TAIL) -> list[dict]:
        """Last ``limit`` parsed lines of the watchdog incident JSONL."""
        path = self.runtime.store.path.parent / INCIDENTS_FILENAME
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except OSError:
            return []
        tail = []
        for line in lines[-max(1, limit):]:
            try:
                tail.append(json.loads(line))
            except (ValueError, json.JSONDecodeError):  # pragma: no cover - defensive
                continue
        return tail

    def heartbeat_age(self, now=None) -> float | None:
        return heartbeat_age(self.heartbeat_path(), now=now)

    def heartbeat_alive_age(self, now=None) -> float | None:
        return heartbeat_alive_age(self.heartbeat_path(), now=now)

    def runner_down(self, max_age_seconds: float = STALL_GRACE_SECONDS,
                    now=None) -> dict | None:
        return runner_down_signal(self.heartbeat_path(), max_age_seconds, now=now)

    def tick(self, goal_id: str | None = None, max_advances: int = 100) -> dict:
        if not automation_enabled(self.runtime.store.path.parent):
            return {"advanced": [], "pending_notifications": [],
                    "quiescent": True, "stopped": True}
        advanced = []
        self._active_goal_id = None
        for _ in range(max_advances):
            candidates = self._candidates(goal_id)
            if not candidates:
                break
            progress = False
            for candidate in candidates:
                before = self._signature(candidate)
                self._active_goal_id = candidate
                # change-a8869554dd (runner-resilience-1): a failure on ONE
                # goal — a live lease held by another client ("already
                # running in another client"), a malformed cycle, or any
                # other per-goal error — used to propagate out of tick() and
                # kill the whole watch loop. Contain it: skip this goal,
                # log, and keep advancing the rest of the company.
                try:
                    state = self.runtime.once(candidate, holder="company-runner")
                except Exception as exc:
                    logger.warning("tick skipped goal %s: %s", candidate, exc)
                    continue
                after = self._signature(candidate)
                if after != before:
                    progress = True
                    advanced.append({"goal_id": candidate, "state": after})
            if not progress:
                break
        return {
            "advanced": advanced,
            "pending_notifications": self.runtime.store.notifications("pending"),
            "quiescent": not self._candidates(goal_id),
        }

    def wake(self, goal_id: str, *, every_seconds: float = 600.0,
             instruction: str = "Continue the Goal cycle and handle its next actionable work.",
             at: str | None = None, max_wakes: int | None = None, runner_status=None):
        """Foreground sleep/echo helper for an attached Director host session.

        This is intentionally *not* another runtime loop and never calls
        ``tick``. It sleeps, then prints one deterministic wake event. The
        host session receiving stdout decides and acts; a terminal Goal or an
        explicit runtime stop ends the helper. ``--at`` supports one future
        calendar wake using an ISO-8601 timestamp.
        """
        if every_seconds <= 0:
            raise ValueError("--every must be greater than zero")
        due = parse_dt(at) if at else None
        if at and due is None:
            raise ValueError("--at must be an ISO-8601 timestamp")
        count = 0
        while max_wakes is None or count < max_wakes:
            if due is not None:
                delay = max(0.0, (due - datetime.now(timezone.utc)).total_seconds())
            else:
                delay = every_seconds
            time.sleep(delay)
            try:
                state = self.runtime.status(goal_id)
            except KeyError:
                yield {"event": "wake_stopped", "goal_id": goal_id,
                       "reason": "goal_not_found"}
                return
            goal = state["goal"]
            if goal["goal_status"] in {"achieved", "abandoned", "expired", "paused"}:
                yield {"event": "wake_stopped", "goal_id": goal_id,
                       "reason": f"goal_{goal['goal_status']}"}
                return
            if not automation_enabled(self.runtime.store.path.parent):
                yield {"event": "wake_stopped", "goal_id": goal_id,
                       "reason": "automation_disabled"}
                return
            service = runner_status() if runner_status else {}
            yield {"event": "director_wake", "goal_id": goal_id,
                   "instruction": instruction,
                   "goal_status": goal["goal_status"],
                   "run_status": state["cycle"]["run_status"],
                   "runner_running": service.get("running"),
                   "why_next": state.get("why_next")}
            count += 1
            if due is not None:
                return

    def watch(self, interval_seconds: float = 2.0, goal_id: str | None = None,
              max_ticks: int | None = None):
        ticks, previous_pending = 0, None
        self._start_heartbeat_thread()
        try:
            while max_ticks is None or ticks < max_ticks:
                self.write_heartbeat()
                # Live HUD surface: refreshed once per watch cycle, only from
                # the daemon path (tick() never writes it). Bounded content;
                # best-effort write.
                self._write_live_status()
                try:
                    result = self.tick(goal_id)
                    pending = tuple(item["id"] for item in result["pending_notifications"])
                    if result["advanced"] or pending != previous_pending:
                        yield result
                    previous_pending = pending
                    ticks += 1
                    self._check_stalled(goal_id)
                    # Scheduled progress digest: emitted by the daemon watch
                    # loop (not the plugin) so supervision stays visible on a
                    # schedule while goals are active, independently of events.
                    self._maybe_emit_digest(goal_id)
                except Exception as exc:
                    # Best-effort: tell the world the watch loop is dying before
                    # the daemon exits. The heartbeat reader remains the primary
                    # dead-daemon detector.
                    self._emit_runner_down(exc)
                    raise
                if max_ticks is None or ticks < max_ticks:
                    time.sleep(interval_seconds)
        finally:
            self._stop_heartbeat_thread()

    def _candidates(self, goal_id: str | None) -> list[str]:
        rows = self.runtime.list_goals()
        rows = self._scope_rows(goal_id, rows)
        runnable = [row for row in rows if self._runnable(row)]
        runnable.sort(key=lambda row: (
            -self._root_priority(row["goal"], rows),
            -priority_score(row["goal"]),
            -self._depth(row["goal"], rows),
            row["goal"]["created_at"]))
        return [row["goal"]["id"] for row in runnable]

    @staticmethod
    def _root_priority(goal: dict, rows: list[dict]) -> float:
        by_id = {row["goal"]["id"]: row["goal"] for row in rows}
        current, seen = goal, set()
        while current.get("parent_id") and current["parent_id"] not in seen:
            seen.add(current["id"])
            parent = by_id.get(current["parent_id"])
            if not parent:
                break
            current = parent
        return priority_score(current)

    def _runnable(self, row: dict) -> bool:
        if row["goal"]["goal_status"] != "active":
            return False
        cycle = row["cycle"]
        status = cycle["run_status"]
        if status == "idle":
            return True
        if status == "completed":
            return self.runtime.continuation_decision(row["goal"]["id"])["eligible"]
        if status in {"blocked", "failed"}:
            return self.runtime.repair_iteration_decision(row["goal"]["id"])["eligible"]
        if status == "awaiting_approval":
            return self.runtime._approval_status(
                row["goal"], cycle, approval_key(cycle)) == "approved"
        if status == "running":
            # Mid-flight cycle whose client died (no live lease) must stay
            # resumable, or the goal parks invisibly until a manual `once`.
            return self.runtime.store.live_lease(row["goal"]["id"]) is None
        if status != "waiting" or not cycle.get("resume_at"):
            return False
        # Shared parse: legacy naive resume_at values normalize to UTC instead
        # of raising TypeError and killing the whole tick.
        resume_at = parse_dt(cycle["resume_at"])
        return resume_at is not None and resume_at <= datetime.now(timezone.utc)

    def _signature(self, goal_id: str):
        state = self.runtime.status(goal_id)
        return (state["goal"]["goal_status"], state["cycle"]["id"],
                state["cycle"]["stage"], state["cycle"]["step"],
                state["cycle"]["run_status"], state["cycle"].get("resume_at"),
                len(state["evidence"]), bool(state["evaluation"]))

    @staticmethod
    def _descendants(goal_id: str, rows: list[dict]) -> set[str]:
        found, frontier = set(), {goal_id}
        while frontier:
            children = {row["goal"]["id"] for row in rows
                        if row["goal"].get("parent_id") in frontier}
            children -= found
            found |= children
            frontier = children
        return found

    @staticmethod
    def _ancestors(goal_id: str, rows: list[dict]) -> set[str]:
        parents = {row["goal"]["id"]: row["goal"].get("parent_id") for row in rows}
        found, parent = set(), parents.get(goal_id)
        while parent:
            found.add(parent)
            parent = parents.get(parent)
        return found

    @staticmethod
    def _depth(goal: dict, rows: list[dict]) -> int:
        parents = {row["goal"]["id"]: row["goal"].get("parent_id") for row in rows}
        depth, parent = 0, goal.get("parent_id")
        while parent:
            depth += 1
            parent = parents.get(parent)
        return depth

    def _scope_rows(self, goal_id: str | None, rows: list[dict]) -> list[dict]:
        """Rows restricted to a goal plus its descendants/ancestors (None = all)."""
        if not goal_id:
            return rows
        descendants = self._descendants(goal_id, rows)
        ancestors = self._ancestors(goal_id, rows)
        allowed = descendants | ancestors | {goal_id}
        return [row for row in rows if row["goal"]["id"] in allowed]

    def _check_stalled(self, goal_id: str | None = None) -> list[str]:
        """Watchdog scan: stalled waiting goals and stale async dispatches.

        Emits ``action_required`` notifications whose payload carries
        ``watchdog.signal == "stuck_goal"`` plus the goal id, run id, why, and
        what to do. Rate-limited so a healthy daemon does not hammer the store
        on every tick; the store's (goal_id, run_id, kind) upsert keeps one
        row per stuck goal and the plugin's re-prompt throttle bounds chat
        spam.
        """
        if time.monotonic() - self._last_stall_check < self._stall_check_interval_seconds:
            return []
        self._last_stall_check = time.monotonic()
        emitted: list[str] = []
        rows = self._scope_rows(goal_id, self.runtime.list_goals())
        now = datetime.now(timezone.utc)
        for row in rows:
            goal = row["goal"]
            if goal["goal_status"] != "active":
                continue
            cycle = row["cycle"]
            # Lease-held cycles (2026-08-15 wedge hardening): a cycle whose
            # lease is held beyond the grace with no advancement since the
            # lease was acquired is a tick that never completes. The bounded
            # measure path finishes far under the grace, so a legit tick
            # never trips this; a wedged one is called out while its lease is
            # still live (once the lease expires, the resume_at detector
            # above — or a fresh runner — takes over).
            lease = self.runtime.store.live_lease(goal["id"])
            if lease is not None:
                acquired = self._lease_acquired_at(lease)
                if acquired is not None:
                    held_seconds = (now - acquired).total_seconds()
                    if held_seconds > self._lease_held_grace_seconds:
                        updated_at = self._parse_dt(cycle.get("updated_at"))
                        if updated_at is None or updated_at <= acquired:
                            self._emit_stuck_goal(
                                goal, cycle,
                                reason="cycle lease held without advancement",
                                detail={"holder": lease.get("holder"),
                                        "lease_acquired_at": acquired.isoformat(),
                                        "lease_held_seconds": held_seconds,
                                        "cycle_updated_at": cycle.get("updated_at")})
                            emitted.append(goal["id"])
            if cycle["run_status"] != "waiting" or not cycle.get("resume_at"):
                continue
            resume_at = self._parse_dt(cycle.get("resume_at"))
            if resume_at is None:
                continue
            due_since = (now - resume_at).total_seconds()
            if due_since < self._stall_grace_seconds:
                continue
            updated_at = self._parse_dt(cycle.get("updated_at"))
            if updated_at is not None and updated_at > resume_at:
                # The cycle advanced after resume_at passed; not stalled.
                continue
            self._emit_stuck_goal(goal, cycle, reason="resume_at passed without advancement",
                                  detail={"resume_at": cycle.get("resume_at"),
                                          "cycle_updated_at": cycle.get("updated_at"),
                                          "due_seconds_ago": due_since})
            emitted.append(goal["id"])
        # Dead-worker pending dispatches: recover (remove) files whose worker
        # thread died with a previous daemon generation, then emit. The files
        # are gone before the stale scan below, so the two paths never
        # double-report the same dispatch.
        for dispatch_goal_id, batch_id, started_at in self._recover_dead_worker_dispatches():
            try:
                goal = self.runtime.store.goal(dispatch_goal_id)
                cycle = self.runtime.store.cycle(dispatch_goal_id)
            except KeyError:
                continue  # dispatch file for a goal that no longer exists
            if goal["goal_status"] != "active":
                continue
            self._emit_stuck_goal(goal, cycle,
                                  reason="async dispatch worker died; pending file removed for re-dispatch",
                                  detail={"batch_id": batch_id, "started_at": started_at,
                                          "grace_seconds": self._dead_worker_grace_seconds})
            emitted.append(dispatch_goal_id)
        for dispatch_goal_id, batch_id, started_at in self._stale_dispatch_files():
            try:
                goal = self.runtime.store.goal(dispatch_goal_id)
                cycle = self.runtime.store.cycle(dispatch_goal_id)
            except KeyError:
                continue  # dispatch file for a goal that no longer exists
            if goal["goal_status"] != "active":
                continue
            self._emit_stuck_goal(goal, cycle, reason="async dispatch pending beyond stale threshold",
                                  detail={"batch_id": batch_id, "started_at": started_at,
                                          "stale_threshold_seconds": self._dispatch_stale_seconds})
            emitted.append(dispatch_goal_id)
        # Send-activity liveness (2026-08-15 quota-stall incident): a live
        # worker that stopped recording sends (provider quota/rate-limit
        # exhaustion or provider outage) is invisible to every check above —
        # the daemon, heartbeat, leases, and cycle clocks all stay healthy.
        # The sent ledger is the only proof the worker is progressing: a
        # pending dispatch with no new send within the grace is called out
        # with an actionable payload instead of waiting hours invisibly.
        # Failed files are intentionally not scanned (they re-dispatch via
        # the 6.6.0 grace semantics), and a missing/unreadable ledger is
        # skipped quietly by the scanner.
        if time.monotonic() - self._last_send_activity_check >= self._send_activity_check_interval_seconds:
            self._last_send_activity_check = time.monotonic()
            for (dispatch_goal_id, batch_id, started_at, last_send_at,
                 pending_seconds, idle_seconds) in self._send_stalled_dispatches():
                try:
                    goal = self.runtime.store.goal(dispatch_goal_id)
                    cycle = self.runtime.store.cycle(dispatch_goal_id)
                except KeyError:
                    continue  # dispatch file for a goal that no longer exists
                if goal["goal_status"] != "active":
                    continue
                self._emit_stuck_goal(
                    goal, cycle,
                    reason="no send activity for pending async dispatch",
                    detail={
                        "batch_id": batch_id,
                        "started_at": started_at,
                        "last_send_at": last_send_at,
                        "pending_seconds": pending_seconds,
                        "idle_seconds": idle_seconds,
                        "send_stall_grace_seconds": self._send_stall_grace_seconds,
                        "likely_cause": "quota exhaustion / provider rate limit / provider outage",
                    })
                emitted.append(dispatch_goal_id)
        return emitted

    def _lease_acquired_at(self, lease: dict):
        """The lease acquisition time = expires_at - the fixed TTL.

        store.acquire() grants a single-row lease with expires_at = now + 60s
        and never renews; there is no acquired_at column, so the TTL is
        subtracted (leases are immutable while held — the only renewal is a
        fresh acquire after expiry).
        """
        expires = self._parse_dt(lease.get("expires_at"))
        if expires is None:
            return None
        return expires - timedelta(seconds=LEASE_TTL_SECONDS)

    def _recover_dead_worker_dispatches(self) -> list[tuple[str, str, str]]:
        """(goal_id, batch_id, started_at) for pending dispatch files whose
        worker cannot be alive, removed so the workflow re-dispatches.

        Dispatch workers are daemon threads of the process that dispatched
        them; threads die with their process. A pending file created before
        this Runner generation started (by more than the grace, so a fresh
        dispatch in a just-started generation is never misread) therefore has
        no live worker: removing it is exactly the manual cleanup from the
        2026-08-15 incident, made safe and automatic. Files within this
        generation, or younger than the grace, keep their live-worker status.
        """
        dispatch_dir = self.runtime.store.path.parent / "outbound" / "async"
        if not dispatch_dir.is_dir():
            return []
        recovered = []
        now = datetime.now(timezone.utc)
        for path in dispatch_dir.glob("*/*.json"):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if data.get("status") != "pending":
                continue
            started = self._parse_dt(data.get("started_at"))
            if started is None:
                continue  # no usable started_at -> the stale path owns it
            if started >= self._generation_started_at:
                continue  # dispatched by this generation: worker is live
            if (now - started).total_seconds() <= self._dead_worker_grace_seconds:
                continue  # within the short grace: do not race a fresh start
            try:
                path.unlink()
            except OSError:  # pragma: no cover - defensive; retry next scan
                continue
            recovered.append((path.parent.name, path.stem, data.get("started_at")))
        return recovered

    def _stale_dispatch_files(self) -> list[tuple[str, str, str]]:
        """(goal_id, batch_id, started_at) for pending async dispatch files
        older than the stale threshold. Missing directory -> no dispatches."""
        dispatch_dir = self.runtime.store.path.parent / "outbound" / "async"
        if not dispatch_dir.is_dir():
            return []
        stale = []
        now = datetime.now(timezone.utc)
        for path in dispatch_dir.glob("*/*.json"):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if data.get("status") != "pending":
                continue
            started_at = data.get("started_at")
            started = self._parse_dt(started_at)
            if started is None:
                # Parity with async_dispatch._is_stale: no usable started_at
                # is treated as stale so the workflow can recover.
                stale.append((path.parent.name, path.stem, started_at))
                continue
            if (now - started).total_seconds() > self._dispatch_stale_seconds:
                stale.append((path.parent.name, path.stem, started_at))
        return stale

    def _send_stalled_dispatches(self) -> list[tuple[str, str, str, str, float, float]]:
        """(goal_id, batch_id, started_at, last_send_at, pending_seconds,
        idle_seconds) for pending dispatch files with no recent send activity.

        The sent ledger is the only liveness proof for a pending dispatch
        whose worker thread is alive: a worker that records no sends is
        stalled no matter how healthy the daemon looks. Fires only when BOTH
        the dispatch has been pending longer than the send-stall grace AND the
        newest ledger send is older than the grace, so normal slow sending and
        young re-dispatches never false-positive. Returns nothing when the
        ledger cannot be read or carries no usable send timestamps (skip
        quietly — no signal to reason about). Failed files are intentionally
        ignored: they re-dispatch through the 6.6.0 grace semantics.
        """
        dispatch_dir = self.runtime.store.path.parent / "outbound" / "async"
        if not dispatch_dir.is_dir():
            return []
        newest = last_send_at(self.runtime.store.path.parent / "outbound" / "sent.json")
        if newest is None:
            return []
        stalled = []
        now = datetime.now(timezone.utc)
        for path in dispatch_dir.glob("*/*.json"):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if data.get("status") != "pending":
                continue
            started = self._parse_dt(data.get("started_at"))
            if started is None:
                continue  # no usable started_at -> the stale path owns it
            pending_seconds = (now - started).total_seconds()
            if pending_seconds <= self._send_stall_grace_seconds:
                continue  # young dispatch / re-dispatch: still within grace
            idle_seconds = (now - newest).total_seconds()
            if idle_seconds <= self._send_stall_grace_seconds:
                continue  # a send was recorded within the grace: worker is live
            stalled.append((path.parent.name, path.stem, data.get("started_at"),
                            newest.isoformat(), pending_seconds, idle_seconds))
        return stalled

    @staticmethod
    def _parse_dt(value):
        # Shared normalization (naive timestamps -> UTC); see runtime/util.py.
        return parse_dt(value)

    # ------------------------------------------------------------------ #
    # Scheduled progress digest (goal-chat-visible-supervision-20260815)  #
    # ------------------------------------------------------------------ #

    def digest_marker_path(self) -> Path:
        """Durable last-emitted stamp for the progress digest.

        Lives beside the heartbeat file, so the cadence survives daemon
        restarts: a restart inside the interval must not re-emit, and an
        interval that elapsed while the daemon was down must produce exactly
        one digest on the next watch cycle.
        """
        return self.runtime.store.path.parent / DIGEST_FILENAME

    def _last_digest_emitted_at(self) -> datetime | None:
        try:
            data = json.loads(self.digest_marker_path().read_text(encoding="utf-8"))
        except (OSError, ValueError, json.JSONDecodeError):
            return None
        if not isinstance(data, dict):
            return None
        return self._parse_dt(data.get("last_emitted_at"))

    def _stamp_digest(self, emitted_at: datetime) -> None:
        """Record the last digest emission. Best-effort: a failed write only
        delays the next digest by one interval (the store row still exists)."""
        try:
            path = self.digest_marker_path()
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps({
                "last_emitted_at": emitted_at.isoformat(),
                "interval_seconds": self._digest_interval_seconds,
            }) + "\n", encoding="utf-8")
        except OSError:  # pragma: no cover - defensive; not a liveness signal
            pass

    def _maybe_emit_digest(self, goal_id: str | None = None, now=None) -> list[str]:
        """Emit one company-wide ``watchdog_digest`` per digest interval.

        Fires while at least one goal in the runner's scope is active
        (``goal_status == "active"``). The last-emitted stamp is durable, so
        a daemon restart inside the interval re-emits nothing. With no active
        goals nothing is emitted and the stamp is not advanced, so the first
        digest of a newly active period is immediately due. Returns the goal
        ids the digest was attached to (empty list => nothing emitted).
        """
        now = now or datetime.now(timezone.utc)
        rows = self._scope_rows(goal_id, self.runtime.list_goals())
        active = [row for row in rows if row["goal"]["goal_status"] == "active"]
        if not active:
            return []
        last = self._last_digest_emitted_at()
        if (last is not None
                and (now - last).total_seconds() < self._digest_interval_seconds):
            return []
        anchor = active[0]  # deterministic: store.goals() orders by created_at
        self.runtime.store.notify(anchor["goal"]["id"], anchor["cycle"]["id"],
                                  "watchdog_digest", self._digest_payload(active, now),
                                  reopen=True)
        self._stamp_digest(now)
        return [anchor["goal"]["id"]]

    def _digest_payload(self, active: list[dict], now: datetime) -> dict:
        """Digest payload: active goals with stage/step, last tick and
        resume_at; pending approvals; recent terminal outcomes; blockers."""
        approvals = [
            {"goal_id": row["goal_id"], "run_id": row["run_id"],
             "created_at": row["created_at"]}
            for row in self.runtime.store.notifications("pending",
                                                        DIGEST_PENDING_SCAN_LIMIT)
            if row["kind"] == "approval_required"]
        recent_terminal = [
            {"goal_id": row["id"], "name": row["name"],
             "goal_status": row["goal_status"]}
            for row in self.runtime.store.goal_summaries(
                statuses=("achieved", "abandoned", "expired"),
                limit=DIGEST_RECENT_TERMINAL_LIMIT)]
        blockers = [
            {"goal_id": row["goal"]["id"], "name": row["goal"]["name"],
             "run_status": row["cycle"]["run_status"]}
            for row in active
            if row["cycle"]["run_status"] in {"blocked", "failed"}]
        return digest_payload(
            emitted_at=now.isoformat(),
            interval_seconds=self._digest_interval_seconds,
            active_goals=[
                {"goal_id": row["goal"]["id"], "name": row["goal"]["name"],
                 "owner_id": row["goal"]["owner_id"],
                 "stage": row["cycle"]["stage"], "step": row["cycle"]["step"],
                 "run_status": row["cycle"]["run_status"],
                 "resume_at": row["cycle"].get("resume_at"),
                 "last_tick_at": row["cycle"].get("updated_at")}
                for row in active],
            pending_approvals=approvals,
            recent_terminal=recent_terminal,
            blockers=blockers)

    def _emit_stuck_goal(self, goal: dict, cycle: dict, *, reason: str,
                         detail: dict) -> dict:
        message = (f"goal {goal['id']} ({goal['name']}) is stuck: {reason} "
                   f"(run {cycle['id']})")
        return self.runtime.store.notify(goal["id"], cycle["id"], "action_required", {
            "watchdog": {
                "signal": "stuck_goal",
                "reason": reason,
                "detected_at": datetime.now(timezone.utc).isoformat(),
                **detail,
            },
            "goal": {"id": goal["id"], "name": goal["name"]},
            "run": {"id": cycle["id"]},
            "result": {"message": message},
            "required_user_action": (
                f"Inspect and resume goal {goal['id']}: `company status {goal['id']}` "
                f"then `company once {goal['id']}`"),
            "next_trigger": f"company once {goal['id']}",
        }, reopen=True)

    def _emit_runner_down(self, exc: Exception) -> None:
        """Best-effort action_required notification when the watch loop dies.

        Attached to the goal being processed (or the first active goal) only
        because notifications are foreign-keyed to a goal/run; the payload is
        about the runner, not the goal. Never raises.
        """
        goal_id = self._active_goal_id
        if goal_id is None:
            for row in self.runtime.list_goals():
                if row["goal"]["goal_status"] == "active":
                    goal_id = row["goal"]["id"]
                    break
        if goal_id is None:
            return
        try:
            cycle = self.runtime.store.cycle(goal_id)
            goal = self.runtime.store.goal(goal_id)
        except KeyError:
            return
        try:
            self.runtime.store.notify(goal_id, cycle["id"], "action_required", {
                "watchdog": {
                    "signal": "runner_down",
                    "detected_at": datetime.now(timezone.utc).isoformat(),
                    "error": {"type": type(exc).__name__, "message": str(exc)},
                },
                "goal": {"id": goal_id, "name": goal["name"]},
                "run": {"id": cycle["id"]},
                "result": {"message": f"runner watch loop died: {type(exc).__name__}: {exc}"},
                "required_user_action": "Restart the runner daemon: `company runner start`",
                "next_trigger": "company runner start",
            }, reopen=True)
        except Exception:  # pragma: no cover - best-effort; never mask the death
            pass
