"""Concurrent send-path store regression tests (goal-87db557d84, 2.1.0 -> 2.1.1).

Two confirmed concurrent-worker defects on the shared outbound send path:

1. OutboundStore.claim_or_active executed BEGIN IMMEDIATE and then returned
   early for already-active leads WITHOUT commit/rollback, leaking an open
   transaction on the check_same_thread=False shared connection. The next
   BEGIN IMMEDIATE (from any of the 5 concurrent daemon workers) raises
   `cannot start a transaction within a transaction`.
2. save_sent_log wrote to a fixed `sent.json.tmp` then os.replace, so
   concurrent workers collided on the same temp path and the loser failed
   with `[Errno 2] No such file or directory: sent.json.tmp -> sent.json`.

Hermetic: the store is a temp SQLite file and sent.json lives in a temp
directory; .spielos live state is never touched.
"""

import json
import sys
import tempfile
import threading
import unittest
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from company.departments.outbound.data import OutboundStore  # noqa: E402
from company.departments.outbound.workflows.email import config, outbound  # noqa: E402

N_THREADS = 12
LEAD_IDS = [f"CONC-{i:02d}" for i in range(16)]  # 8 active + 8 unclaimed
ACTIVE_LEAD_IDS = LEAD_IDS[:8]
UNCLAIMED_LEAD_IDS = LEAD_IDS[8:]
NESTED_TX_ERROR = "cannot start a transaction within a transaction"
ACTIVE_STATUSES = OutboundStore.SUBMISSION_ACTIVE_STATUSES


class ClaimOrActiveConcurrencyTests(unittest.TestCase):
    """T1 — N threads calling claim_or_active on one shared store for a mix
    of unclaimed and already-active leads: no nested-transaction error, every
    unclaimed lead claimed exactly once, and no open transaction left behind."""

    def setUp(self):
        tmpdir = tempfile.mkdtemp(prefix="claim-or-active-")
        self.addCleanup(__import__("shutil").rmtree, tmpdir, ignore_errors=True)
        self.store = OutboundStore(Path(tmpdir) / "outbound.sqlite")
        self.addCleanup(self.store.close)
        now = datetime.now(timezone.utc).isoformat()
        for lead_id in ACTIVE_LEAD_IDS:
            self.store.record_submission(
                lead_id, f"{lead_id}@test.invalid", "resend",
                attempted_at=now, status="accepted", provider_id="seed")

    def test_concurrent_claims_mix_no_nested_transaction(self):
        n = N_THREADS
        barrier = threading.Barrier(n)
        errors = []
        seen = defaultdict(list)  # per-lead [{"claimed": bool}, ...] (GIL-safe append)

        def worker(_worker_id):
            barrier.wait(timeout=30)
            try:
                for _round in range(3):
                    for lead_id in LEAD_IDS:
                        res = self.store.claim_or_active(
                            lead_id, f"{lead_id}@test.invalid", "resend")
                        seen[lead_id].append(res["claimed"])
            except Exception as exc:  # pragma: no cover - failure path
                errors.append(exc)

        threads = [threading.Thread(target=worker, args=(i,))
                   for i in range(n)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=120)
            self.assertFalse(t.is_alive(), "worker thread hung")

        # Defect 1: no BEGIN IMMEDIATE may ever hit an already-open transaction.
        self.assertEqual(errors, [],
                         f"concurrent claim had {len(errors)} error(s), "
                         f"first: {errors[0] if errors else None!r}")
        for exc in errors:
            self.assertNotIn(NESTED_TX_ERROR, str(exc))

        # Consistency: exactly one worker claimed each originally-unclaimed
        # lead (first claim only; the other 11 workers skip it), and
        # already-active leads were never re-claimed.
        total_calls = n * 3 * len(LEAD_IDS)
        self.assertEqual(sum(len(v) for v in seen.values()), total_calls)
        for lead_id in ACTIVE_LEAD_IDS:
            self.assertEqual(sum(seen[lead_id]), 0,
                             f"already-active lead {lead_id} was claimed")
        for lead_id in UNCLAIMED_LEAD_IDS:
            self.assertEqual(sum(seen[lead_id]), 1,
                             f"unclaimed lead {lead_id} claimed "
                             f"{sum(seen[lead_id])} time(s); expected exactly 1")

        # Final submission registry: every lead has one durable row in an
        # active status, and no transaction is left open on the shared
        # connection (the leak this goal repairs).
        for lead_id in LEAD_IDS:
            sub = self.store.get_submission(lead_id)
            self.assertIsNotNone(sub, f"no submission row for {lead_id}")
            self.assertIn(sub["status"], ACTIVE_STATUSES)
            self.assertGreaterEqual(sub["attempts"], 1)
        self.assertFalse(self.store.db.in_transaction,
                         "claim_or_active left a transaction open")


class SaveSentLogConcurrencyTests(unittest.TestCase):
    """T2 — N threads calling save_sent_log concurrently: no [Errno 2]
    rename collision, and the final sent.json is valid JSON containing every
    thread's entry (torn-file guarantee preserved)."""

    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp(prefix="sent-log-"))
        self.addCleanup(__import__("shutil").rmtree, str(self.tmpdir),
                        ignore_errors=True)
        self.sent_path = self.tmpdir / "sent.json"
        original = config.SENT_LOG_PATH
        self.addCleanup(setattr, config, "SENT_LOG_PATH", original)
        config.SENT_LOG_PATH = self.sent_path

    def _entry(self, i):
        return {"lead_id": f"thread-{i:02d}",
                "email": f"w{i:02d}@test.invalid",
                "provider": "resend", "provider_id": f"m-{i:02d}",
                "timestamp": datetime.now(timezone.utc).isoformat()}

    def test_concurrent_saves_no_enoent_and_full_final_log(self):
        n = N_THREADS
        barrier = threading.Barrier(n)
        errors = []
        expected = {self._entry(i)["lead_id"] for i in range(n)}

        def worker(i):
            entry = self._entry(i)
            barrier.wait(timeout=30)
            try:
                for _attempt in range(500):
                    log = outbound.load_sent_log()
                    if any(s.get("lead_id") == entry["lead_id"]
                           for s in log.get("sent", [])):
                        return  # this thread's entry is durable
                    log.setdefault("sent", []).append(entry)
                    outbound.save_sent_log(log)
                errors.append(RuntimeError(f"thread {i} never converged"))
            except Exception as exc:  # pragma: no cover - failure path
                errors.append(exc)

        threads = [threading.Thread(target=worker, args=(i,))
                   for i in range(n)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=120)
            self.assertFalse(t.is_alive(), "worker thread hung")

        # Defect 2: no [Errno 2] rename/temp collision, no other failure
        # during the concurrent storm.
        self.assertEqual(errors, [],
                         f"concurrent save had {len(errors)} error(s), "
                         f"first: {errors[0] if errors else None!r}")
        for exc in errors:
            self.assertNotIn("[Errno 2]", str(exc))

        # Convergence: read-merge-write until the on-disk log contains every
        # thread's entry. Concurrent writers may have clobbered a finished
        # thread's entry (lost update), so reconcile deterministically —
        # always through the same save_sent_log atomic write under test.
        entries = [self._entry(i) for i in range(n)]
        for _round in range(50):
            log = outbound.load_sent_log()
            present = {s.get("lead_id") for s in log.get("sent", [])}
            if present >= expected:
                break
            for entry in entries:
                if entry["lead_id"] not in present:
                    log.setdefault("sent", []).append(entry)
            outbound.save_sent_log(log)
        else:
            self.fail("convergence loop never produced the complete log")

        # Final file is valid JSON and contains every thread's entry.
        raw = self.sent_path.read_text()
        final = json.loads(raw)
        sent_ids = {s.get("lead_id") for s in final.get("sent", [])}
        self.assertEqual(sent_ids, expected)

    def test_single_save_roundtrip_unchanged(self):
        """The fix preserves plain single-writer semantics."""
        log = {"sent": [self._entry(0)], "failed": []}
        outbound.save_sent_log(log)
        reloaded = json.loads(self.sent_path.read_text())
        self.assertEqual(reloaded, log)


if __name__ == "__main__":
    unittest.main()