from __future__ import annotations

import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from company.runtime.context import ContextAssembler, TURN_CHAR_BUDGET, codex_hook_output
from company.__main__ import main
from company.runtime.memory import rank_experiment_memories
from company.runtime.store import Store


class ContextMemoryV2Tests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.store = Store(self.root / "state.sqlite")

    def tearDown(self):
        self.temp.cleanup()

    def test_profile_claims_supersede_only_the_same_scope(self):
        first = self.store.set_profile_claim(
            namespace="voice", claim_key="active_voice", value=True,
            source_ref="chat:1", source_excerpt="Use active voice")
        second = self.store.set_profile_claim(
            namespace="voice", claim_key="active_voice", value=False,
            source_ref="chat:2", source_excerpt="Stop enforcing it")
        active = self.store.profile_claims()
        self.assertEqual([second["id"]], [item["id"] for item in active])
        self.assertEqual("superseded", self.store.profile_claim(first["id"])["status"])
        self.assertEqual(first["id"], second["supersedes_id"])

    def test_experiment_memory_reinforces_with_typed_context(self):
        context = {"metrics": ["reply_rate"], "workflows": ["outbound-email"]}
        first = self.store.record_experiment_memory(
            owner_id="growth", goal_id="goal-a", run_id="run-a",
            claim="Short subject lines improved replies", verdict="confirmed",
            context=context, evidence_ids=["ev-1"], confidence=.7)
        second = self.store.record_experiment_memory(
            owner_id="growth", goal_id="goal-b", run_id="run-b",
            claim="Short subject lines improved replies", verdict="confirmed",
            context=context, evidence_ids=["ev-2"], confidence=.7)
        self.assertEqual(first["id"], second["id"])
        self.assertEqual(2, second["confirmations"])
        self.assertEqual(["ev-1", "ev-2"], second["evidence_ids"])
        ranked = rank_experiment_memories(
            [second], prompt="write outbound email subject", workflow_id="outbound-email")
        self.assertEqual(second["id"], ranked[0]["id"])

    def test_workflow_candidate_hardens_on_second_use_and_one_off_expires(self):
        first = self.store.observe_workflow_memory(
            workflow_id="demo-gif", title="Make a narrated demo GIF",
            instructions=["record", "convert", "overlay copy"],
            observed_at="2026-08-01T00:00:00+00:00", source_ref="chat:1")
        self.assertEqual("candidate", first["status"])
        second = self.store.observe_workflow_memory(
            workflow_id="demo-gif", title="Make a narrated demo GIF",
            instructions=["record", "convert", "overlay copy"],
            observed_at="2026-08-10T00:00:00+00:00", source_ref="chat:2")
        self.assertEqual("hardening", second["status"])
        self.assertEqual(2, second["occurrence_count"])
        stale = self.store.observe_workflow_memory(
            workflow_id="one-off", title="One-off", instructions=["do once"],
            observed_at="2026-08-01T00:00:00+00:00")
        receipt = self.store.consolidate_operating_memory(at="2026-08-16T00:00:00+00:00")
        self.assertEqual(1, receipt["expired_workflow_candidates"])
        self.assertEqual("expired", self.store.workflow_memory(stale["id"])["status"])

    def test_projection_applies_workflow_trigger_and_dependencies(self):
        memory = self.store.observe_workflow_memory(
            workflow_id="invoice-posting", behavior_key="exchange-rate-check",
            title="Exchange rate check", instructions=["Verify exchange rate"],
            trigger={"currency": "foreign"}, dependencies=["exchange-rate"],
            explicit_update=True)
        hidden = ContextAssembler(self.store, project_root=self.root).assemble(
            prompt="post invoice", workflow_id="invoice-posting",
            trigger_context={"currency": "domestic"},
            available_dependencies=["exchange-rate"])
        visible = ContextAssembler(self.store, project_root=self.root).assemble(
            prompt="post invoice", workflow_id="invoice-posting",
            trigger_context={"currency": "foreign"},
            available_dependencies=["exchange-rate"])

        self.assertNotIn(memory["id"], hidden["sources"])
        self.assertIn(memory["id"], visible["sources"])

    def test_projection_is_bounded_relevant_and_hook_readable(self):
        self.store.create_goal(
            name="Increase qualified replies", owner_id="growth",
            metric="reply_rate", operator="ge", target=10,
            config={"priority": "high"})
        claim = self.store.set_profile_claim(
            namespace="icp", claim_key="primary", value="founder-led B2B SaaS",
            source_excerpt="Focus on founder-led B2B SaaS")
        projection = ContextAssembler(self.store, project_root=self.root).assemble(
            prompt="draft copy for our primary ICP", owner_id="growth")
        self.assertLessEqual(len(projection["context"]), TURN_CHAR_BUDGET)
        self.assertIn("Increase qualified replies", projection["context"])
        self.assertIn("founder-led B2B SaaS", projection["context"])
        self.assertIn(claim["id"], projection["sources"])
        payload = codex_hook_output(projection, "UserPromptSubmit")
        self.assertEqual("UserPromptSubmit",
                         payload["hookSpecificOutput"]["hookEventName"])

    def test_status_projection_is_fresh_and_includes_active_goal_overview(self):
        first = self.store.create_goal(
            name="Ship the primary offer", owner_id="growth",
            metric="qualified_replies", operator="ge", target=10,
            config={"priority": "high"})
        second = self.store.create_goal(
            name="Improve onboarding", owner_id="product",
            metric="activation_rate", operator="ge", target=50,
            config={"priority": "normal"})

        projection = ContextAssembler(self.store, project_root=self.root).assemble(
            prompt="give me the status", owner_id="director")

        self.assertLessEqual(len(projection["context"]), TURN_CHAR_BUDGET)
        self.assertIn("Snapshot: fresh for this model request", projection["context"])
        self.assertIn("runner paused", projection["context"])
        self.assertIn("2 active Goal(s)", projection["context"])
        self.assertIn("Ship the primary offer", projection["context"])
        self.assertIn("Improve onboarding", projection["context"])
        self.assertIn(f"goal:{first['id']}", projection["sources"])
        self.assertIn(f"goal:{second['id']}", projection["sources"])

    def test_bare_greeting_projection_forbids_redundant_state_tools(self):
        projection = ContextAssembler(self.store, project_root=self.root).assemble(
            prompt="hi", owner_id="director")
        context = projection["context"]
        self.assertIn("Request route · bare greeting", context)
        self.assertIn("Make no tool calls", context)
        self.assertIn("Do not run company status, overview", context)
        self.assertIn("fresh company-state read for this exact request", context)
        self.assertNotIn("Company profile", context)
        self.assertNotIn("Persistence rule", context)

    def test_fresh_home_projection_offers_planning_without_execution_authority(self):
        projection = ContextAssembler(self.store, project_root=self.root).assemble(
            prompt="I have an existing website in another folder", owner_id="director")
        context = projection["context"]
        self.assertIn("Fresh-home route", context)
        self.assertIn("offer read-only migration planning", context)
        self.assertIn("does not authorize copying", context)

        self.store.create_goal(
            name="Ship current site", owner_id="product",
            metric="activation_rate", operator="ge", target=50)
        active = ContextAssembler(self.store, project_root=self.root).assemble(
            prompt="I have an existing website in another folder", owner_id="director")
        self.assertNotIn("Fresh-home route", active["context"])

    def test_memory_summary_counts_profile_as_durable_memory(self):
        profile_output = io.StringIO()
        with redirect_stdout(profile_output):
            self.assertEqual(0, main([
                "--db", str(self.store.path), "profile", "set",
                "--namespace", "operating_principles", "--key", "review_ux",
                "--value", "Review UX and Director tone", "--json"]))
        claim = json.loads(profile_output.getvalue())
        output = io.StringIO()
        with redirect_stdout(output):
            exit_code = main([
                "--db", str(self.store.path), "memory", "summary", "--json"])
        payload = json.loads(output.getvalue())

        self.assertEqual(0, exit_code)
        self.assertEqual(1, payload["counts"]["owner"])
        self.assertEqual(
            claim["id"], payload["durable_memory"]["owner"][0]["id"])
        self.assertEqual(0, payload["counts"]["strategy"])
        context_output = io.StringIO()
        with redirect_stdout(context_output):
            self.assertEqual(0, main([
                "--db", str(self.store.path), "context", "--prompt",
                "what permanent instructions do you remember?", "--json"]))
        projection = json.loads(context_output.getvalue())
        self.assertIn("operating_principles.review_ux", projection["context"])
        self.assertIn("Review UX and Director tone", projection["context"])


if __name__ == "__main__":
    unittest.main()
