"""Outbound state substrate tests: workflow state, batches, knowledge, actions."""

import tempfile
import unittest
from pathlib import Path

from company.departments.outbound.models import Lead, LeadState
from company.departments.outbound.data import OutboundStore


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = OutboundStore(Path(self.tmp.name) / "outbound.sqlite")

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def test_phase_defaults_to_observe(self):
        self.assertEqual(self.store.phase(), "observe")

    def test_phase_roundtrip(self):
        self.store.set_phase("review")
        self.assertEqual(self.store.phase(), "review")

    def test_batch_cycle_counter(self):
        self.assertEqual(self.store.cycle(), 0)
        self.assertEqual(self.store.bump_cycle(), 1)
        self.assertEqual(self.store.bump_cycle(), 2)
        self.assertEqual(self.store.cycle(), 2)

    def test_batch_upsert_and_roundtrip(self):
        batch = {
            "id": "EMAIL-2026-08-09-b01",
            "workflow": "email",
            "phase": "prepare",
            "intervention": {"action": "prepare_batch", "variable": "subject"},
            "batch": {"emails": [{"lead_id": "L1"}]},
        }
        self.store.upsert_batch(batch)
        got = self.store.get_batch(batch["id"])
        self.assertEqual(got["id"], batch["id"])
        self.assertEqual(got["intervention"]["variable"], "subject")
        self.assertEqual(got["batch"]["emails"][0]["lead_id"], "L1")
        self.store.update_batch_phase(batch["id"], "review")
        self.assertEqual(self.store.get_batch(batch["id"])["phase"], "review")

    def test_latest_batch_ordering(self):
        self.store.upsert_batch({"id": "A", "workflow": "w", "phase": "p"})
        self.store.upsert_batch({"id": "B", "workflow": "w", "phase": "p"})
        self.assertEqual(self.store.latest_batch()["id"], "B")

    def test_knowledge_trials_append(self):
        self.store.record_trial("subject", {"verdict": "keep", "at": "t1"})
        self.store.record_trial("subject", {"verdict": "reject", "at": "t2"})
        k = self.store.knowledge_for("subject")
        self.assertEqual(len(k["tried"]), 2)
        self.assertEqual(k["verdict"], "reject")

    def test_action_ledger_append_only(self):
        self.store.upsert_leads([Lead(lead_id="L1", name="A", company="C")])
        self.store.record_action("L1", "email", "send_email", "sent", "batch B1")
        self.store.record_action("L1", "email", "send_email", "sent", "batch B2")
        self.assertEqual(self.store.action_count("email", "send_email"), 2)
        self.assertEqual(self.store.get_lead("L1").state, LeadState.ACTIONED)


if __name__ == "__main__":
    unittest.main()
