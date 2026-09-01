"""Integrity 6.4: Lego means shared-interpreter behavior, not just catalog shape."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from company.runtime.campaign_contract import COMPATIBLE_SCHEMA_VERSIONS, SCHEMA_VERSION
from company.departments.outbound.department import BESPOKE_STAGE_EXCEPTIONS, OutboundDepartment
from company.runtime.interpreter import InterpretedDepartment, _kinds_satisfied
from company.runtime.loop import Runtime
from company.runtime.models import Department, Goal, GoalContext, WorkflowSpec, WorkflowStep
from company.runtime.package import validate_package
from company.runtime.registry import departments
from company.runtime.legacy_registry import handlers as legacy_handlers
from company.tests.test_campaign_handoff_contract import campaign_manifest


class RequiresAllKindsTests(unittest.TestCase):
    def test_multiple_requires_need_every_kind(self):
        evidence = [{"kind": "campaign_manifest"}]
        self.assertFalse(_kinds_satisfied(evidence, ("campaign_manifest", "render_report")))
        self.assertTrue(_kinds_satisfied(
            evidence + [{"kind": "render_report"}],
            ("campaign_manifest", "render_report")))

    def test_content_quality_gate_waits_for_render_report(self):
        department = legacy_handlers()["content"]
        goal = Goal("g", "Campaign", "content", "published_items", "ge", 1,
                    None, None, "active", {"workflow": "content-campaign"})
        ctx = GoalContext(goal, {"evidence": [
            {"kind": "simulation", "payload": {}},
            {"kind": "human_reality", "payload": {}},
            {"kind": "discovery", "payload": {}},
            {"kind": "content_draft", "payload": {}},
            {"kind": "campaign_manifest", "payload": {"schema_version": SCHEMA_VERSION}},
            {"kind": "design_order", "payload": {}},
            {"kind": "content_ready", "payload": {}},
        ]}, (), lambda _: None)
        decision = department.decide(ctx, department.observe(ctx).payload)
        self.assertEqual("request_agent", decision.payload["action"])
        self.assertEqual("render_handoff", decision.payload["step_id"])
        self.assertEqual(["render_report"], decision.payload["accepted_evidence_kinds"])
        self.assertNotEqual("quality_gate", decision.payload.get("step_id"))


class SharedInterpreterFlowTests(unittest.TestCase):
    def test_content_publish_uses_interpreter_approval_then_connection(self):
        department = legacy_handlers()["content"]
        self.assertIsInstance(department, InterpretedDepartment)
        goal = Goal("g", "publish", "content", "published_items", "ge", 1,
                    None, None, "active",
                    {"workflow": "publish", "connection": "buffer", "execution_mode": "dry_run"})
        evidence = [{"kind": "content_package", "payload": {"channel_id": "channel", "text": "hello"}}]
        waiting = GoalContext(goal, {"evidence": evidence}, (), lambda _: None)
        decision = department.decide(waiting, department.observe(waiting).payload)
        self.assertEqual("request_approval", decision.payload["action"])
        approved = GoalContext(goal, {"evidence": evidence}, (), lambda _: "approved")
        next_decision = department.decide(approved, department.observe(approved).payload)
        self.assertEqual("connection_dispatch", next_decision.payload["action"])

    def test_analytics_funnel_requests_report_through_interpreter(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime = Runtime(Path(tmp) / "company.sqlite")
            goal = runtime.create_goal(
                name="Measure one funnel", owner_id="analytics",
                metric="funnel_reports", operator="ge", target=1,
                config={"workflow": "funnel-analysis"})
            blocked = runtime.once(goal["id"])
            self.assertEqual("blocked", blocked["cycle"]["run_status"])
            order = runtime.store.work_orders(status="open", goal_id=goal["id"])[0]
            self.assertEqual("analytics-operator", order["agent_id"])
            self.assertEqual(["funnel_report"], order["accepts_evidence"])

    def test_outbound_social_research_uses_interpreter_not_custom_stages(self):
        department = legacy_handlers()["outbound"]
        goal = Goal("g", "Research", "outbound", "qualified_social_leads", "ge", 1,
                    None, None, "active", {"workflow": "social-lead-research"})
        self.assertFalse(department.uses_email_exception(GoalContext(goal, {}, (), lambda _: None)))
        with tempfile.TemporaryDirectory() as tmp:
            runtime = Runtime(Path(tmp) / "company.sqlite")
            created = runtime.create_goal(
                name="Research one social prospect", owner_id="outbound",
                metric="qualified_social_leads", operator="ge", target=1,
                config={"workflow": "social-lead-research", "required_count": 1},
                run_type="system_test", evidence_validity="technical_only")
            blocked = runtime.once(created["id"])
            self.assertEqual("blocked", blocked["cycle"]["run_status"])
            order = runtime.store.work_orders(status="open", goal_id=created["id"])[0]
            self.assertEqual("social-researcher", order["agent_id"])
            self.assertEqual(["social_prospect"], order["accepts_evidence"])
            runtime.add_evidence(created["id"], kind="social_prospect",
                                 source="social-researcher",
                                 payload={"lead_id": "lead-1", "name": "Alex Operator",
                                          "company": "Example Ops", "channel": "linkedin"},
                                 validity="technical_only")
            runtime.retry(created["id"])
            done = runtime.once(created["id"])
            self.assertEqual("achieved", done["goal"]["goal_status"])

    def test_email_outreach_is_the_named_stage_exception(self):
        self.assertEqual(set(BESPOKE_STAGE_EXCEPTIONS), {"email-outreach"})
        department = legacy_handlers()["outbound"]
        self.assertIsInstance(department, OutboundDepartment)
        email = Goal("g", "Send", "outbound", "reply_rate", "ge", 0.3,
                     None, None, "active", {"workflow": "email-outreach"})
        social = Goal("g2", "Research", "outbound", "qualified_social_leads", "ge", 1,
                      None, None, "active", {"workflow": "social-lead-research"})
        self.assertTrue(department.uses_email_exception(GoalContext(email, {}, (), lambda _: None)))
        self.assertFalse(department.uses_email_exception(GoalContext(social, {}, (), lambda _: None)))


class PackageHandoffTests(unittest.TestCase):
    def test_required_kind_without_producer_or_handoff_is_a_defect(self):
        class Broken(InterpretedDepartment, Department):
            id = department_id = "broken_handoff"
            version = "1.0.0"
            description = "Missing producer fixture"
            agent_ids = ("content-strategist",)
            goal_schema = {"metrics": ["items"]}
            evidence_metrics = {"items": ("final_item",)}
            workflows = (WorkflowSpec(
                "primary", "fixture", ("gate",), ("content-strategist",), (),
                (), ("final_item",), (), graph=(
                    WorkflowStep("gate", "machine",
                                 requires=("campaign_manifest", "render_report"),
                                 produces=("final_item",)),
                )),)

        defects = validate_package(Broken())
        self.assertTrue(any("requires campaign_manifest" in item for item in defects))
        self.assertTrue(any("requires render_report" in item for item in defects))

    def test_content_declares_design_render_handoff(self):
        defects = validate_package(departments()["content"])
        self.assertEqual([], defects)
        campaign = next(item for item in departments()["content"].workflows
                        if item.id == "content-campaign")
        step_ids = [node.id for node in campaign.graph]
        self.assertIn("render_handoff", step_ids)
        handoff = next(node for node in campaign.graph if node.id == "render_handoff")
        self.assertEqual(("render_report",), handoff.produces)


class CampaignSchemaCompatibilityTests(unittest.TestCase):
    def test_current_schema_is_1_2_and_earlier_remains_compatible(self):
        self.assertEqual(SCHEMA_VERSION, "1.2")
        self.assertEqual(COMPATIBLE_SCHEMA_VERSIONS, frozenset({"1.0", "1.1", "1.2"}))
        manifest = campaign_manifest()
        legacy = dict(manifest)
        for version in ("1.0", "1.1"):
            legacy["schema_version"] = version
            from company.runtime.campaign_contract import validate_campaign
            self.assertEqual(validate_campaign(legacy, "strategy"), [],
                             f"schema {version} must remain readable")


if __name__ == "__main__":
    unittest.main()
