import json
import unittest
from pathlib import Path

from company.connections.buffer import BufferClient
from company.runtime.campaign_contract import SCHEMA_VERSION, validate_campaign
from company.departments.content.department import (
    _eval_gate_errors,
    validate_campaign_package,
)
from company.runtime.models import Goal, GoalContext
from company.runtime.registry import departments
from company.tests.test_campaign_handoff_contract import campaign_manifest


ROOT = Path(__file__).resolve().parents[2]


class ContentCampaignContractTests(unittest.TestCase):
    def test_current_authority_is_campaign_contract(self):
        manifest = campaign_manifest()
        self.assertEqual(manifest["schema_version"], SCHEMA_VERSION)
        self.assertEqual(validate_campaign(manifest, "strategy"), [])
        self.assertEqual(validate_campaign_package(manifest), [])

    def test_legacy_package_is_rejected_by_current_authority(self):
        errors = validate_campaign_package({
            "campaign": "content-leads-20260812",
            "one_idea": "Visible operating proof beats generic AI claims",
            "platform_packages": [],
        })
        self.assertTrue(any("legacy campaign package is retired" in error for error in errors))
        self.assertTrue(any(SCHEMA_VERSION in error for error in errors))

    def test_legacy_batch_shape_is_not_current_authority(self):
        errors = validate_campaign_package({
            "campaign": "content-leads-20260812", "batch_number": 1, "batch_size": 5,
            "daily_targets": {"threads": 50, "youtube": 50},
            "batch_items": [{"batch_item": 1, "narrative_type": "live-journey"}],
        })
        self.assertTrue(any("legacy campaign package is retired" in error for error in errors))

    def test_buffer_capacity_uses_live_daily_limits(self):
        client = BufferClient.__new__(BufferClient)
        client.posting_limits = lambda ids: [
            {"channelId": "threads", "limit": 10, "scheduled": 3},
            {"channelId": "youtube", "limit": 5, "scheduled": 5},
        ]
        self.assertEqual(client.available_capacity(["threads", "youtube"]), {"threads": 7, "youtube": 0})

    def test_buffer_preserves_an_explicitly_unlimited_channel(self):
        client = BufferClient.__new__(BufferClient)
        client.posting_limits = lambda ids: [{"channelId": "youtube", "limit": None, "scheduled": 0, "isAtLimit": False}]
        self.assertEqual(client.available_capacity(["youtube"]), {"youtube": None})

    def test_registered_platform_sizes_and_quality_gate_are_present(self):
        presets = (ROOT / "company/departments/design/presets.json").read_text()
        content = (ROOT / "company/departments/content/department.py").read_text()
        self.assertIn('"youtube-shorts"', presets)
        self.assertIn('"threads-portrait"', presets)
        self.assertIn("content-campaign", content)
        self.assertIn("dailyPostingLimits", (ROOT / "company/connections/buffer.py").read_text())

    def test_dispatch_is_publish_commitment_with_final_receipt(self):
        """The clean workflow contract: scheduled == published, final receipt."""
        content = (ROOT / "company/departments/content/department.py").read_text()
        buffer = (ROOT / "company/connections/buffer.py").read_text()
        self.assertIn('version = "4.3.0"', content)
        self.assertIn("PUBLICATION_RECEIPT_CONTRACT", content)
        self.assertIn("scheduled or sent is a commitment", content)
        self.assertIn("duplicate_guard", buffer)
        self.assertIn("--queue", buffer)
        self.assertIn("commitment_type", buffer)
        self.assertIn("ok:true", buffer)


class ContentCampaignEvalGateTests(unittest.TestCase):
    """The quality_gate is judge-gated: campaign copy cannot advance to
    campaign_ready without a passing eval_report for every declared suite."""

    BATCH_ID = "content-leads-20260812-batch-04"

    #: Declared suites must each carry a passing eval_report (v3.6).
    SUITE_IDS = ("content-copy-top10", "content-story-whole")

    def setUp(self):
        """The archived batch-04 manifest predates the v3.6 Design rotation
        registry (its template family repeats are exactly what that registry
        now forbids). These tests target the EVAL gate, not rotation, so the
        rotation check is stubbed out."""
        import unittest.mock
        from company.departments.content import department as content_department
        patcher = unittest.mock.patch.object(
            content_department, "_design_rotation_errors", lambda *a, **k: [])
        patcher.start()
        self.addCleanup(patcher.stop)

    def _manifest(self):
        # The batch-04 approved manifest was archived; artifacts are
        # gitignored, so this fixture only exists on the owner machine.
        candidates = [
            ROOT / ".spielos/artifacts/content-growth-20260812/batch-04/campaign-approved.json",
            ROOT / ".spielos/artifacts/content-growth-20260812/_archive/fresh-start-20260819/batch-04/campaign-approved.json",
        ]
        for path in candidates:
            if path.is_file():
                return json.loads(path.read_text())
        self.skipTest("local artifact batch-04/campaign-approved.json not present")

    def _context(self, evidence):
        goal = Goal("gate-test", "Campaign", "content", "published_items", "ge", 1,
                    None, None, "active", {"workflow": "content-campaign"})
        return GoalContext(goal, {"evidence": evidence}, (), lambda _: None)

    def _run_gate(self, evidence):
        return departments()["content"].run_machine_step(
            self._context(evidence), {"step_id": "quality_gate"})

    def _render_report_evidence(self):
        return {"kind": "render_report", "source": "design", "validity": "technical_only",
                "payload": {"campaign_id": "content-leads-20260812",
                            "batch_id": self.BATCH_ID}}

    def _eval_report_evidence(self, payload):
        return {"kind": "eval_report", "source": f"evals:{payload.get('suite_id')}",
                "validity": "business", "payload": payload}

    def _eval_report(self, overall=True, payload_id=BATCH_ID, per_item=None,
                     suite_id="content-copy-top10"):
        return self._eval_report_evidence({
            "suite_id": suite_id,
            "payload_id": payload_id,
            "payload_kind": "campaign_manifest",
            "overall": overall,
            "per_item_pass": {f"batch-04-item-{i:02d}": overall for i in range(1, 6)},
            "per_item": per_item or {},
            "thresholds": {"all_pass": True, "min_score": 1.0},
            "judge_connector": "agent:cli",
            "validity": "business",
            "generated_at": "2026-08-17T00:00:00+00:00",
        })

    def _eval_reports(self, **kwargs):
        """One passing (or failing) eval report per declared suite."""
        return [self._eval_report(suite_id=suite_id, **kwargs)
                for suite_id in self.SUITE_IDS]

    def test_quality_gate_requires_eval_report_before_campaign_ready(self):
        result = self._run_gate([
            {"kind": "campaign_manifest", "source": "content-strategist",
             "validity": "business", "payload": self._manifest()},
            self._render_report_evidence(),
        ])
        self.assertEqual("blocked", result["run_status"])
        errors = (result.get("attention") or {}).get("errors") or []
        self.assertTrue(any(
            "eval_report" in error and "content-copy-top10" in error
            for error in errors))
        self.assertNotIn("campaign_ready",
                         [item.get("kind") for item in (result.get("evidence") or [])])

    def test_quality_gate_blocks_failed_eval_with_criterion_errors(self):
        result = self._run_gate([
            {"kind": "campaign_manifest", "source": "content-strategist",
             "validity": "business", "payload": self._manifest()},
            self._render_report_evidence(),
            *self._eval_reports(overall=False, per_item={
                "batch-04-item-03": {
                    "cold_audience_clarity": {
                        "pass": False, "score": 0.2,
                        "reason": "body uses machinery vocabulary",
                        "evidence_refs": ["threads.copy"]},
                },
            }),
        ])
        self.assertEqual("blocked", result["run_status"])
        errors = (result.get("attention") or {}).get("errors") or []
        self.assertTrue(any("failed" in error for error in errors))
        self.assertTrue(any(
            "batch-04-item-03:cold_audience_clarity" in error
            for error in errors))

    def test_quality_gate_blocks_eval_report_for_a_different_batch(self):
        result = self._run_gate([
            {"kind": "campaign_manifest", "source": "content-strategist",
             "validity": "business", "payload": self._manifest()},
            self._render_report_evidence(),
            *self._eval_reports(payload_id="content-leads-20260812-batch-03"),
        ])
        self.assertEqual("blocked", result["run_status"])
        errors = (result.get("attention") or {}).get("errors") or []
        self.assertTrue(any("payload_id must match batch_id" in error for error in errors))

    def test_quality_gate_passes_with_a_passing_eval_report(self):
        result = self._run_gate([
            {"kind": "campaign_manifest", "source": "content-strategist",
             "validity": "business", "payload": self._manifest()},
            self._render_report_evidence(),
            *self._eval_reports(),
        ])
        self.assertEqual("Campaign quality gate passed", result.get("message"))
        kinds = [item.get("kind") for item in (result.get("evidence") or [])]
        self.assertIn("campaign_ready", kinds)

    def test_eval_gate_helper_requires_each_declared_suite(self):
        errors = _eval_gate_errors([], {"batch_id": "b-7"}, ("content-copy-top10",))
        self.assertTrue(any(
            "eval_report for suite 'content-copy-top10' is required" in error
            for error in errors))
        errors = _eval_gate_errors([], {"batch_id": "b-7"}, ())
        self.assertEqual([], errors)

    def test_department_declares_evals_module_and_suites(self):
        dept_source = (ROOT / "company/departments/content/department.py").read_text()
        self.assertIn('eval_suites = ("content-copy-top10", "content-story-whole")',
                      dept_source)
        evals_source = (ROOT / "company/departments/content/evals.py").read_text()
        self.assertIn("EVAL_SUITES", evals_source)
        self.assertIn('"content-copy-top10"', evals_source)
        from company.evals import get_suite
        suite = get_suite("content-copy-top10")
        self.assertEqual(10, len(suite.criteria))
        self.assertEqual({"all_pass": True, "min_score": 1.0}, suite.thresholds)
        self.assertEqual("campaign_manifest", suite.payload_kind)


if __name__ == "__main__":
    unittest.main()
