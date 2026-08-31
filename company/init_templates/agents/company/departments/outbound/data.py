"""SQLite-backed Outbound domain data substrate.

The company runtime owns lifecycle state. This store preserves Outbound domain
records, prepared batches, and historical campaign knowledge:

  workflow_state — phase, current batch/snapshot/intervention references,
                   batch cycle counter, evidence deadline, hold reason
  batches      — one row per prepared batch (artifact refs, metrics, verdict,
                 owner, claimed lead ids, executed flag — the idempotent batch
                 registry: a batch id is allocated once per prepare, claims its
                 leads, and releases them when marked executed)
  submissions  — durable per-lead submission registry (lead_id keyed):
                 in_flight before the first provider attempt, resolved to
                 accepted / failed / submitted_unknown on the outcome, with a
                 12h cooldown so no execution or generation re-submits a lead
                 whose submission is recent
  knowledge    — per-variable experiment history (verdicts, trials)
  actions      — append-only per-lead action ledger (channel-neutral)
  goals        — workflow goal rows
  leads        — channel-neutral lead store (future social workflows; the
                 email bundle keeps its own master list — see
                 workflows/email/outbound.py)

Human-written state (goal spec, approvals, knobs) lives in control.json: the
owner edits JSON, the machine writes SQLite.
"""

import functools
import json
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .models import Lead, LeadState, WorkflowGoal


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_iso(value) -> datetime | None:
    """Parse an ISO timestamp for cooldown math; naive values are UTC."""
    if not value:
        return None
    try:
        ts = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return ts


def _locked(method):
    """Serialize access to the shared sqlite3 connection.

    The connection is opened with check_same_thread=False so the
    async-dispatch thread can record actions on a store opened by the
    daemon/tick thread. The (re-entrant) lock keeps concurrent
    execute/commit sequences from interleaving on the shared connection;
    re-entrancy keeps nested public calls (e.g. latest_batch -> get_batch)
    from deadlocking.
    """

    @functools.wraps(method)
    def wrapper(self, *args, **kwargs):
        with self._lock:
            return method(self, *args, **kwargs)

    return wrapper


class OutboundStore:
    def __init__(self, path: str | Path):
        self.path = str(path)
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self.db = sqlite3.connect(self.path, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self._migrate()

    @_locked
    def _migrate(self) -> None:
        # v5 vocabulary migration. Preserve every existing Outbound state row.
        tables = {
            row[0] for row in self.db.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        if "engine_state" in tables and "workflow_state" not in tables:
            self.db.execute("ALTER TABLE engine_state RENAME TO workflow_state")
        self.db.executescript(
            """
            CREATE TABLE IF NOT EXISTS leads (
                lead_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                company TEXT NOT NULL,
                role TEXT,
                location TEXT,
                channels TEXT NOT NULL DEFAULT '[]',
                profile_url TEXT,
                company_url TEXT,
                state TEXT NOT NULL,
                icp_score INTEGER NOT NULL DEFAULT 0,
                research_fact TEXT,
                operational_consequence TEXT,
                message TEXT,
                source_urls TEXT NOT NULL DEFAULT '[]',
                exclusion_reason TEXT,
                metadata TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS actions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                lead_id TEXT NOT NULL,
                channel TEXT NOT NULL,
                action TEXT NOT NULL,
                result TEXT NOT NULL,
                note TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY(lead_id) REFERENCES leads(lead_id)
            );
            CREATE TABLE IF NOT EXISTS goals (
                workflow_id TEXT PRIMARY KEY,
                channel TEXT NOT NULL,
                action TEXT NOT NULL,
                target INTEGER NOT NULL,
                min_icp_score INTEGER NOT NULL,
                queue_target INTEGER NOT NULL,
                enabled INTEGER NOT NULL DEFAULT 1
            );
            CREATE TABLE IF NOT EXISTS workflow_state (
                key TEXT PRIMARY KEY,
                value TEXT
            );
            CREATE TABLE IF NOT EXISTS batches (
                id TEXT PRIMARY KEY,
                workflow TEXT NOT NULL,
                phase TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                intervention_json TEXT,
                batch_json TEXT,
                metrics_json TEXT,
                verdict_json TEXT,
                preview_path TEXT,
                report_path TEXT,
                owner TEXT NOT NULL DEFAULT '',
                leads_json TEXT NOT NULL DEFAULT '[]',
                executed INTEGER NOT NULL DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS submissions (
                lead_id TEXT PRIMARY KEY,
                email TEXT NOT NULL,
                provider TEXT NOT NULL,
                attempted_at TEXT NOT NULL,
                status TEXT NOT NULL,
                provider_id TEXT,
                attempts INTEGER NOT NULL DEFAULT 1,
                message TEXT,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS knowledge (
                variable TEXT PRIMARY KEY,
                tried_json TEXT NOT NULL DEFAULT '[]',
                verdict TEXT,
                updated_at TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_leads_state ON leads(state);
            CREATE INDEX IF NOT EXISTS idx_actions_channel ON actions(channel);
            CREATE INDEX IF NOT EXISTS idx_batches_phase ON batches(phase);
            CREATE INDEX IF NOT EXISTS idx_submissions_status ON submissions(status);
            CREATE INDEX IF NOT EXISTS idx_submissions_attempted_at
                ON submissions(attempted_at);
            """
        )
        # Idempotent-batch registry columns on pre-existing databases
        # (owner/leads_json/executed are new; a plain CREATE TABLE IF NOT
        # EXISTS cannot add columns to an existing table).
        batch_cols = {r[1] for r in self.db.execute(
            "PRAGMA table_info(batches)").fetchall()}
        if "owner" not in batch_cols:
            self.db.execute(
                "ALTER TABLE batches ADD COLUMN owner TEXT NOT NULL DEFAULT ''")
        if "leads_json" not in batch_cols:
            self.db.execute(
                "ALTER TABLE batches ADD COLUMN leads_json TEXT NOT NULL "
                "DEFAULT '[]'")
        if "executed" not in batch_cols:
            self.db.execute(
                "ALTER TABLE batches ADD COLUMN executed INTEGER NOT NULL "
                "DEFAULT 0")
        self.db.commit()

    # ── engine_state ──────────────────────────────────────────────────────────

    @_locked
    def get_state(self, key: str, default: Any = None) -> Any:
        row = self.db.execute(
            "SELECT value FROM workflow_state WHERE key=?", (key,)).fetchone()
        if row is None:
            return default
        try:
            return json.loads(row["value"])
        except (TypeError, ValueError):
            return default

    @_locked
    def set_state(self, key: str, value: Any) -> None:
        payload = json.dumps(value, default=str)
        self.db.execute(
            """INSERT INTO workflow_state(key, value) VALUES(?,?)
               ON CONFLICT(key) DO UPDATE SET value=excluded.value""",
            (key, payload))
        self.db.commit()

    def phase(self) -> str:
        return str(self.get_state("phase", "observe"))

    def set_phase(self, phase: str) -> None:
        self.set_state("phase", phase)

    def cycle(self) -> int:
        return int(self.get_state("batch_cycle", 0))

    def bump_cycle(self) -> int:
        n = self.cycle() + 1
        self.set_state("batch_cycle", n)
        return n

    def current_batch_id(self) -> str | None:
        return self.get_state("current_batch")

    def set_current_batch(self, batch_id: str | None) -> None:
        self.set_state("current_batch", batch_id)

    def evidence_due(self) -> str | None:
        return self.get_state("evidence_due")

    def set_evidence_due(self, ts: str | None) -> None:
        self.set_state("evidence_due", ts)

    def hold_reason(self) -> str | None:
        return self.get_state("hold_reason")

    def set_hold_reason(self, reason: str | None) -> None:
        self.set_state("hold_reason", reason)

    def last_snapshot_path(self) -> str | None:
        return self.get_state("last_snapshot")

    def set_last_snapshot_path(self, path: str) -> None:
        self.set_state("last_snapshot", path)

    def last_intervention_path(self) -> str | None:
        return self.get_state("last_intervention")

    def set_last_intervention_path(self, path: str) -> None:
        self.set_state("last_intervention", path)

    # ── batches ───────────────────────────────────────────────────────────────

    @_locked
    def upsert_batch(self, batch: dict) -> None:
        self.db.execute(
            """INSERT INTO batches(id, workflow, phase, created_at, updated_at,
               intervention_json, batch_json, metrics_json, verdict_json,
               preview_path, report_path)
               VALUES(?,?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(id) DO UPDATE SET phase=excluded.phase,
                 updated_at=excluded.updated_at, batch_json=excluded.batch_json,
                 metrics_json=excluded.metrics_json,
                 verdict_json=excluded.verdict_json,
                 intervention_json=excluded.intervention_json,
                 preview_path=excluded.preview_path,
                 report_path=excluded.report_path""",
            (batch["id"], batch.get("workflow", ""), batch.get("phase", "prepare"),
             batch.get("created_at") or utc_now(),
             batch.get("updated_at") or utc_now(),
             json.dumps(batch.get("intervention") or {}, default=str),
             json.dumps(batch.get("batch") or {}, default=str),
             json.dumps(batch.get("metrics") or {}, default=str),
             json.dumps(batch.get("verdict") or {}, default=str),
             batch.get("preview_path"), batch.get("report_path")))
        self.db.commit()

    @_locked
    def get_batch(self, batch_id: str) -> dict | None:
        row = self.db.execute(
            "SELECT * FROM batches WHERE id=?", (batch_id,)).fetchone()
        if row is None:
            return None

        def _load(key):
            try:
                return json.loads(row[key] or "{}")
            except (TypeError, ValueError):
                return {}

        def _load_list(key):
            try:
                value = json.loads(row[key] or "[]")
                return value if isinstance(value, list) else []
            except (TypeError, ValueError):
                return []

        return {
            "id": row["id"], "workflow": row["workflow"], "phase": row["phase"],
            "created_at": row["created_at"], "updated_at": row["updated_at"],
            "intervention": _load("intervention_json"),
            "batch": _load("batch_json"),
            "metrics": _load("metrics_json"),
            "verdict": _load("verdict_json"),
            "preview_path": row["preview_path"],
            "report_path": row["report_path"],
            "owner": row["owner"] or "",
            "lead_ids": _load_list("leads_json"),
            "executed": bool(row["executed"]),
        }

    @_locked
    def update_batch_phase(self, batch_id: str, phase: str) -> None:
        self.db.execute(
            "UPDATE batches SET phase=?, updated_at=? WHERE id=?",
            (phase, utc_now(), batch_id))
        self.db.commit()

    @_locked
    def update_batch_metrics(self, batch_id: str, metrics: dict, verdict: dict | None = None) -> None:
        self.db.execute(
            "UPDATE batches SET metrics_json=?, verdict_json=?, updated_at=? WHERE id=?",
            (json.dumps(metrics, default=str),
             json.dumps(verdict or {}, default=str), utc_now(), batch_id))
        self.db.commit()

    @_locked
    def update_batch_report(self, batch_id: str, report_path: str) -> None:
        self.db.execute(
            "UPDATE batches SET report_path=?, updated_at=? WHERE id=?",
            (report_path, utc_now(), batch_id))
        self.db.commit()

    @_locked
    def latest_batch(self) -> dict | None:
        row = self.db.execute(
            "SELECT id FROM batches ORDER BY created_at DESC LIMIT 1").fetchone()
        return self.get_batch(row["id"]) if row else None

    # ── idempotent batch registry ────────────────────────────────────────────
    #
    # Every prepared batch gets a unique persisted id (never a shared "unset"
    # fallback) that claims its lead set until the batch is executed. A batch
    # id belongs to exactly one prepare: re-preparing a registered id is
    # rejected, and leads claimed by a prepared-not-executed batch are
    # excluded from new prepares so concurrent prepares are disjoint.

    @_locked
    def register_batch(self, batch_id: str, owner: str = "",
                       lead_ids=(), workflow: str = "email") -> None:
        """Allocate one registered batch. Raises ValueError when the id is
        already registered or when any lead is claimed by another
        prepared-not-executed batch. Cross-process atomic (BEGIN IMMEDIATE)
        so two runtime processes cannot register overlapping claims."""
        self.db.execute("BEGIN IMMEDIATE")
        try:
            row = self.db.execute(
                "SELECT 1 FROM batches WHERE id=?", (batch_id,)).fetchone()
            if row is not None:
                raise ValueError(
                    f"batch id already registered: {batch_id!r} — a batch id "
                    "belongs to exactly one prepared batch")
            ids = list(lead_ids)
            if ids:
                reserved: set = set()
                for prev in self.db.execute(
                        "SELECT leads_json FROM batches WHERE executed=0"
                ).fetchall():
                    try:
                        reserved.update(json.loads(prev["leads_json"] or "[]"))
                    except (TypeError, ValueError):
                        continue
                overlap = sorted(set(ids) & reserved)
                if overlap:
                    raise ValueError(
                        "leads already claimed by a prepared-not-executed "
                        f"batch: {', '.join(overlap[:5])}"
                        + (" …" if len(overlap) > 5 else ""))
            now = utc_now()
            self.db.execute(
                """INSERT INTO batches(id, workflow, phase, created_at,
                   updated_at, intervention_json, batch_json, metrics_json,
                   verdict_json, preview_path, report_path, owner, leads_json,
                   executed)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (batch_id, workflow, "prepare", now, now, "{}", "{}", "{}",
                 "{}", None, None, owner or "", json.dumps(ids), 0))
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise

    @_locked
    def batch_registered(self, batch_id: str) -> bool:
        row = self.db.execute(
            "SELECT 1 FROM batches WHERE id=?", (batch_id,)).fetchone()
        return row is not None

    @_locked
    def mark_batch_executed(self, batch_id: str) -> None:
        """Release the batch's lead claims (executed=1). Idempotent — safe to
        call from every send-path exit, including execution failure."""
        self.db.execute(
            "UPDATE batches SET executed=1, updated_at=? WHERE id=?",
            (utc_now(), batch_id))
        self.db.commit()

    @_locked
    def reserved_lead_ids(self) -> set:
        """Lead ids claimed by any prepared-not-executed batch."""
        reserved: set = set()
        for row in self.db.execute(
                "SELECT leads_json FROM batches WHERE executed=0").fetchall():
            try:
                reserved.update(json.loads(row["leads_json"] or "[]"))
            except (TypeError, ValueError):
                continue
        return reserved

    # ── per-lead submission registry ─────────────────────────────────────────
    #
    # One row per lead, written as in_flight BEFORE the first provider
    # attempt and resolved from the outcome: accepted (provider_id),
    # failed, or submitted_unknown (a hung-cap response where the provider
    # may have accepted without a local success). A row that is in_flight,
    # accepted, or submitted_unknown inside the cooldown window blocks
    # re-submission by any execution or generation; failed rows and rows older
    # than the cooldown are claimable again.

    SUBMISSION_ACTIVE_STATUSES = ("in_flight", "accepted", "submitted_unknown")
    SUBMISSION_COOLDOWN_SECONDS_DEFAULT = 12 * 3600  # 12 hours

    @_locked
    def claim_or_active(self, lead_id: str, email: str, provider: str,
                        cooldown_seconds: int = SUBMISSION_COOLDOWN_SECONDS_DEFAULT,
                        now: str | None = None) -> dict:
        """Atomically claim a lead for one submission attempt.

        Returns {"claimed": True, "submission": {...}} when the lead may be
        submitted now (first claim, or re-claim after a failed/expired
        entry), or {"claimed": False, "submission": {...}} when an active
        entry (in_flight/accepted/submitted_unknown within cooldown) already
        exists — the caller must skip. Cross-process atomic (BEGIN
        IMMEDIATE) so two concurrent executions can never both claim the same lead.
        """
        now_iso = now or utc_now()
        self.db.execute("BEGIN IMMEDIATE")
        try:
            row = self.db.execute(
                "SELECT * FROM submissions WHERE lead_id=?",
                (lead_id,)).fetchone()
            if row is not None and self._submission_active(
                    row, cooldown_seconds, now_iso):
                # End the read transaction before returning: BEGIN IMMEDIATE was
                # taken above and every exit path must commit or roll back so
                # the shared check_same_thread=False connection never leaks an
                # open transaction that breaks the next execution's BEGIN IMMEDIATE.
                self.db.rollback()
                return {"claimed": False,
                        "submission": self._submission(row)}
            attempts = (int(row["attempts"]) + 1) if row is not None else 1
            self.db.execute(
                """INSERT INTO submissions(lead_id, email, provider,
                   attempted_at, status, provider_id, attempts, message,
                   updated_at)
                   VALUES(?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(lead_id) DO UPDATE SET
                     email=excluded.email, provider=excluded.provider,
                     attempted_at=excluded.attempted_at,
                     status=excluded.status, provider_id=excluded.provider_id,
                     attempts=excluded.attempts, message=excluded.message,
                     updated_at=excluded.updated_at""",
                (lead_id, email, provider or "", now_iso, "in_flight", None,
                 attempts, None, now_iso))
            self.db.commit()
            got = self.db.execute(
                "SELECT * FROM submissions WHERE lead_id=?",
                (lead_id,)).fetchone()
            return {"claimed": True, "submission": self._submission(got)}
        except Exception:
            self.db.rollback()
            raise

    @_locked
    def record_submission(self, lead_id: str, email: str, provider: str,
                          attempted_at: str, status: str,
                          provider_id: str | None = None,
                          attempts: int | None = None,
                          message: str | None = None) -> None:
        """Upsert one submission record (per-attempt in_flight refresh or
        resolution to accepted/failed/submitted_unknown). attempts=None
        preserves the existing counter (per-attempt refresh and resolution);
        a value replaces it (claim). Note: `excluded.attempts` in an upsert
        is the already-coalesced insert value, so the preserve path reads
        the current counter in Python first."""
        now = utc_now()
        if attempts is None:
            row = self.db.execute(
                "SELECT attempts FROM submissions WHERE lead_id=?",
                (lead_id,)).fetchone()
            attempts = int(row["attempts"]) if row is not None else 1
        self.db.execute(
            """INSERT INTO submissions(lead_id, email, provider, attempted_at,
               status, provider_id, attempts, message, updated_at)
               VALUES(?,?,?,?,?,?,?,?,?)
               ON CONFLICT(lead_id) DO UPDATE SET
                 email=excluded.email, provider=excluded.provider,
                 attempted_at=excluded.attempted_at, status=excluded.status,
                 provider_id=excluded.provider_id,
                 attempts=excluded.attempts, message=excluded.message,
                 updated_at=excluded.updated_at""",
            (lead_id, email, provider or "", attempted_at, status,
             provider_id, attempts, message, now))
        self.db.commit()

    @_locked
    def get_submission(self, lead_id: str) -> dict | None:
        row = self.db.execute(
            "SELECT * FROM submissions WHERE lead_id=?", (lead_id,)).fetchone()
        if row is None:
            return None
        return self._submission(row)

    @_locked
    def active_submission(self, lead_id: str,
                          cooldown_seconds: int = SUBMISSION_COOLDOWN_SECONDS_DEFAULT,
                          now: str | None = None) -> dict | None:
        """The lead's active submission (in_flight/accepted/submitted_unknown
        inside the cooldown), or None when the lead is claimable."""
        row = self.db.execute(
            "SELECT * FROM submissions WHERE lead_id=?", (lead_id,)).fetchone()
        if row is None:
            return None
        if not self._submission_active(row, cooldown_seconds, now or utc_now()):
            return None
        return self._submission(row)

    @staticmethod
    def _submission(row: sqlite3.Row) -> dict:
        return {
            "lead_id": row["lead_id"], "email": row["email"],
            "provider": row["provider"] or "",
            "attempted_at": row["attempted_at"], "status": row["status"],
            "provider_id": row["provider_id"],
            "attempts": row["attempts"] or 1,
            "message": row["message"], "updated_at": row["updated_at"],
        }

    @classmethod
    def _submission_active(cls, row: sqlite3.Row, cooldown_seconds: int,
                           now_iso: str) -> bool:
        if row["status"] not in cls.SUBMISSION_ACTIVE_STATUSES:
            # failed entries never block; they are claimable immediately
            return False
        ts = _parse_iso(row["attempted_at"])
        now = _parse_iso(now_iso)
        if ts is None or now is None:
            # Unparseable timestamp: do not block a lead forever on a
            # poisoned row — treat it as outside the cooldown.
            return False
        return (now - ts).total_seconds() <= cooldown_seconds

    # ── knowledge (LEARN) ─────────────────────────────────────────────────────

    @_locked
    def record_trial(self, variable: str, trial: dict) -> None:
        row = self.db.execute(
            "SELECT tried_json FROM knowledge WHERE variable=?",
            (variable,)).fetchone()
        tried = []
        if row:
            try:
                tried = json.loads(row["tried_json"] or "[]")
            except (TypeError, ValueError):
                tried = []
        tried.append(trial)
        self.db.execute(
            """INSERT INTO knowledge(variable, tried_json, verdict, updated_at)
               VALUES(?,?,?,?)
               ON CONFLICT(variable) DO UPDATE SET tried_json=excluded.tried_json,
                 verdict=excluded.verdict, updated_at=excluded.updated_at""",
            (variable, json.dumps(tried, default=str),
             trial.get("verdict") or "", utc_now()))
        self.db.commit()

    @_locked
    def knowledge_for(self, variable: str) -> dict:
        row = self.db.execute(
            "SELECT tried_json, verdict FROM knowledge WHERE variable=?",
            (variable,)).fetchone()
        if row is None:
            return {"tried": [], "verdict": None}
        try:
            tried = json.loads(row["tried_json"] or "[]")
        except (TypeError, ValueError):
            tried = []
        return {"tried": tried, "verdict": row["verdict"] or None}

    @_locked
    def all_knowledge(self) -> dict:
        rows = self.db.execute("SELECT variable, tried_json, verdict FROM knowledge").fetchall()
        out = {}
        for row in rows:
            try:
                tried = json.loads(row["tried_json"] or "[]")
            except (TypeError, ValueError):
                tried = []
            out[row["variable"]] = {"tried": tried, "verdict": row["verdict"] or None}
        return out

    # ── leads / actions / goals (channel-neutral store) ──────────────────────

    @_locked
    def upsert_leads(self, leads) -> int:
        rows = list(leads)
        now = utc_now()
        for lead in rows:
            self.db.execute(
                """INSERT INTO leads VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(lead_id) DO UPDATE SET
                  name=excluded.name, company=excluded.company, role=excluded.role,
                  location=excluded.location, channels=excluded.channels,
                  profile_url=excluded.profile_url, company_url=excluded.company_url,
                  icp_score=excluded.icp_score, research_fact=excluded.research_fact,
                  operational_consequence=excluded.operational_consequence,
                  message=excluded.message, source_urls=excluded.source_urls,
                  exclusion_reason=excluded.exclusion_reason, metadata=excluded.metadata,
                  updated_at=excluded.updated_at""",
                (lead.lead_id, lead.name, lead.company, lead.role, lead.location,
                 json.dumps(lead.channels), lead.profile_url, lead.company_url,
                 lead.state.value, lead.icp_score, lead.research_fact,
                 lead.operational_consequence, lead.message,
                 json.dumps(lead.source_urls), lead.exclusion_reason,
                 json.dumps(lead.metadata), now, now))
        self.db.commit()
        return len(rows)

    @_locked
    def add_goal(self, goal: WorkflowGoal) -> None:
        self.db.execute(
            """INSERT INTO goals VALUES (?,?,?,?,?,?,?)
            ON CONFLICT(workflow_id) DO UPDATE SET channel=excluded.channel,
            action=excluded.action, target=excluded.target,
            min_icp_score=excluded.min_icp_score, queue_target=excluded.queue_target,
            enabled=excluded.enabled""",
            (goal.workflow_id, goal.channel, goal.action, goal.target,
             goal.min_icp_score, goal.queue_target, int(goal.enabled)))
        self.db.commit()

    @_locked
    def get_lead(self, lead_id: str) -> Lead | None:
        row = self.db.execute(
            "SELECT * FROM leads WHERE lead_id=?", (lead_id,)).fetchone()
        return self._lead(row) if row else None

    @_locked
    def ready_queue(self, channel: str, limit: int = 50, min_score: int = 75) -> list:
        rows = self.db.execute(
            """SELECT * FROM leads WHERE state='ready' AND icp_score>=?
            AND channels LIKE ? ORDER BY icp_score DESC, updated_at ASC LIMIT ?""",
            (min_score, f'%"{channel}"%', limit)).fetchall()
        return [self._lead(row) for row in rows]

    @_locked
    def record_action(self, lead_id: str, channel: str, action: str, result: str, note: str = "") -> None:
        self.db.execute(
            "INSERT INTO actions(lead_id,channel,action,result,note,created_at) VALUES(?,?,?,?,?,?)",
            (lead_id, channel, action, result, note, utc_now()))
        new_state = LeadState.ACTIONED.value if result in {"sent", "connection_sent", "published"} else result
        self.db.execute(
            "UPDATE leads SET state=?, updated_at=? WHERE lead_id=?",
            (new_state, utc_now(), lead_id))
        self.db.commit()

    @_locked
    def action_count(self, channel: str, action: str, result: str | None = None) -> int:
        query = "SELECT COUNT(*) FROM actions WHERE channel=? AND action=?"
        args: list = [channel, action]
        if result:
            query += " AND result=?"
            args.append(result)
        return int(self.db.execute(query, args).fetchone()[0])

    @_locked
    def counts(self) -> dict:
        rows = self.db.execute("SELECT state, COUNT(*) AS n FROM leads GROUP BY state").fetchall()
        return {row["state"]: row["n"] for row in rows}

    @_locked
    def close(self) -> None:
        self.db.close()

    @staticmethod
    def _lead(row: sqlite3.Row) -> Lead:
        return Lead(
            lead_id=row["lead_id"], name=row["name"], company=row["company"],
            role=row["role"] or "", location=row["location"] or "",
            channels=json.loads(row["channels"] or "[]"), profile_url=row["profile_url"] or "",
            company_url=row["company_url"] or "", state=LeadState(row["state"]),
            icp_score=row["icp_score"], research_fact=row["research_fact"] or "",
            operational_consequence=row["operational_consequence"] or "",
            message=row["message"] or "", source_urls=json.loads(row["source_urls"] or "[]"),
            exclusion_reason=row["exclusion_reason"] or "",
            metadata=json.loads(row["metadata"] or "{}"))
