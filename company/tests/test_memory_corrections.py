from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from company.runtime.memory import rank_workflow_memories
from company.runtime.memory_capture import apply_candidate
from company.runtime.store import Store


def candidate(intent, *, scope="workflow", payload=None, explicit=False,
              ambiguous=False, diagnosis=None):
    return {
        "intent": intent,
        "scope": scope,
        "confidence": 0.96,
        "ambiguous": ambiguous,
        "explicit": explicit,
        "payload": payload or {},
        "diagnosis": diagnosis or {},
        "source": {"ref": "chat:owner:1", "excerpt": "owner correction"},
    }


class MemoryCorrectionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.temp.name) / "state.sqlite")

    def tearDown(self):
        self.temp.cleanup()

    def workflow_payload(self, instructions, **extra):
        return {
            "workflow_id": "invoice-posting",
            "behavior_key": "verify-totals-before-posting",
            "title": "Verify invoice totals",
            "instructions": instructions,
            "trigger": {},
            "dependencies": [],
            **extra,
        }

    def test_explicit_workflow_correction_is_authoritative_next_run(self):
        result = apply_candidate(self.store, candidate(
            "workflow_correction", explicit=True,
            payload=self.workflow_payload(["Verify totals before posting"]),
            diagnosis={"corrected_behavior": "Posting without total validation",
                       "cause": "model_behavior"}))

        self.assertEqual("workflow_memory", result["route"])
        self.assertEqual("owner_explicit", result["record"]["authority"])
        ranked = rank_workflow_memories(
            self.store.workflow_memories(), workflow_id="invoice-posting")
        self.assertEqual(result["record"]["id"], ranked[0]["id"])

    def test_canonical_workflow_defect_routes_to_repair_not_memory(self):
        repairs = []
        result = apply_candidate(self.store, candidate(
            "workflow_correction", explicit=True,
            payload=self.workflow_payload(["Validate totals"]),
            diagnosis={
                "corrected_behavior": "The canonical step posts before validation",
                "cause": "canonical_workflow_defect",
                "canonical_repair": {"workflow_id": "invoice-posting",
                                     "change": "move validate before post"},
            }), canonical_repair=lambda repair: repairs.append(repair) or {"ok": True})

        self.assertEqual("canonical_workflow_repair", result["route"])
        self.assertEqual("applied", result["repair_status"])
        self.assertEqual([], list(self.store.workflow_memories()))
        self.assertEqual(1, len(repairs))
        self.assertEqual("routed", self.store.memory_candidates()[0]["status"])

    def test_task_only_correction_stays_temporary(self):
        result = apply_candidate(self.store, candidate(
            "workflow_correction", scope="task", explicit=True,
            payload=self.workflow_payload(["Only do this for customer A"]),
            diagnosis={"corrected_behavior": "Customer-specific formatting",
                       "cause": "model_behavior"}))
        self.assertEqual("temporary", result["route"])
        self.assertFalse(result["persisted"])
        self.assertEqual([], list(self.store.workflow_memories()))

    def test_semantic_equivalents_reinforce_by_behavior_key(self):
        first = apply_candidate(self.store, candidate(
            "workflow_instruction",
            payload=self.workflow_payload(["Check invoice totals before posting"])))
        second = apply_candidate(self.store, candidate(
            "workflow_instruction",
            payload=self.workflow_payload(["Verify invoice totals prior to posting"])))

        self.assertEqual(first["record"]["id"], second["record"]["id"])
        self.assertEqual(2, second["record"]["occurrence_count"])
        self.assertEqual("hardening", second["record"]["status"])
        self.assertEqual(["Verify invoice totals prior to posting"],
                         second["record"]["instructions"])

    def test_explicit_new_behavior_supersedes_old_record(self):
        old = self.store.observe_workflow_memory(
            workflow_id="invoice-posting", behavior_key="posting-order",
            title="Posting order", instructions=["Post then verify"],
            explicit_update=True)
        new = self.store.observe_workflow_memory(
            workflow_id="invoice-posting", behavior_key="posting-order",
            title="Posting order", instructions=["Verify then post"],
            explicit_update=True)

        self.assertEqual("superseded", self.store.workflow_memory(old["id"])["status"])
        self.assertEqual(old["id"], new["supersedes_id"])
        ranked = rank_workflow_memories(
            [self.store.workflow_memory(old["id"]), new],
            workflow_id="invoice-posting")
        self.assertEqual([new["id"]], [item["id"] for item in ranked])

    def test_trigger_and_dependencies_are_hard_applicability_filters(self):
        memory = self.store.observe_workflow_memory(
            workflow_id="invoice-posting", behavior_key="foreign-currency-check",
            title="Foreign currency check", instructions=["Verify exchange rate"],
            trigger={"currency": "foreign"}, dependencies=["exchange-rate"],
            explicit_update=True)
        all_memory = [memory]

        self.assertEqual([], rank_workflow_memories(
            all_memory, workflow_id="invoice-posting",
            trigger_context={"currency": "domestic"},
            available_dependencies=["exchange-rate"]))
        self.assertEqual([], rank_workflow_memories(
            all_memory, workflow_id="invoice-posting",
            trigger_context={"currency": "foreign"}))
        self.assertEqual([memory["id"]], [item["id"] for item in
            rank_workflow_memories(
                all_memory, workflow_id="invoice-posting",
                trigger_context={"currency": "foreign"},
                available_dependencies=["exchange-rate"])])

    def test_ambiguous_criticism_is_audited_not_promoted(self):
        result = apply_candidate(self.store, candidate(
            "workflow_instruction", ambiguous=True,
            payload=self.workflow_payload(["Maybe do better"])))
        self.assertEqual("none", result["route"])
        self.assertEqual("rejected", result["candidate_status"])
        self.assertEqual([], list(self.store.workflow_memories()))


if __name__ == "__main__":
    unittest.main()
