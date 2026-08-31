"""Tests for the reusable LLM-as-judge evals Lego piece (change-619a3be433).

Covers: core model, report computation, judge connector validation with mocked
agent verdicts, registry auto-discovery, the reusability proof (a second tiny
suite runs on the same engine), threshold/block behavior, and the evidence
payload shape consumed by the content-campaign quality gate.
"""

import unittest

from company.evals import (
    AgentJudgeConnector,
    EvalCriterion,
    EvalReport,
    EvalSuite,
    HttpJudgeConnector,
    compute_report,
    get_suite,
    register_suite,
    render_request,
    report_to_evidence,
    run_suite,
    suite_spec,
    suites,
)


def sample_suite() -> EvalSuite:
    """A second, department-agnostic suite proving the engine is reusable."""
    return EvalSuite(
        id="outbound-email-sample",
        name="Outbound email sample standard",
        scope="email-sample",
        department_id="outbound",
        payload_kind="email_sample",
        description="Reusability proof: a non-content department suite.",
        validity="technical_only",
        thresholds={"all_pass": True, "min_score": 1.0},
        item_selector=lambda payload: [
            (sample["id"], sample) for sample in payload["samples"]
        ],
        payload_id_selector=lambda payload: str(payload.get("batch_id") or "samples"),
        criteria=(
            EvalCriterion(
                "clear", "Clear claim", "The central claim is clear.",
                ".agents/company/strategy/voice.md"),
            EvalCriterion(
                "native", "Native shape", "The shape fits the channel.",
                ".agents/company/skills/copywriting/SKILL.md", severity="warn"),
        ),
    )


def sample_payload():
    return {"batch_id": "outbound-sample-01", "samples": [
        {"id": "sample-1", "to": "operator@acme.com", "text": "Fix your invoicing wait."},
        {"id": "sample-2", "to": "owner@acme.com", "text": "Payroll eats a day monthly."},
    ]}


def all_pass_verdicts(suite, item_ids):
    return {"items": {
        item_id: {
            criterion.id: {"pass": True, "score": 1.0,
                           "reason": f"{item_id}/{criterion.id} is fine",
                           "evidence_refs": ["text"]}
            for criterion in suite.criteria
        }
        for item_id in item_ids
    }}


class CoreModelTests(unittest.TestCase):
    def test_core_model_holds_grounded_criteria_and_thresholds(self):
        suite = sample_suite()
        self.assertEqual("outbound-email-sample", suite.id)
        self.assertEqual("outbound", suite.department_id)
        self.assertEqual("email_sample", suite.payload_kind)
        self.assertEqual(["clear", "native"], [c.id for c in suite.criteria])
        self.assertEqual("block", suite.criteria[0].severity)
        self.assertEqual("warn", suite.criteria[1].severity)
        self.assertEqual(".agents/company/strategy/voice.md", suite.criteria[0].source)
        self.assertEqual({"all_pass": True, "min_score": 1.0}, suite.thresholds)

    def test_suite_spec_is_stable_and_readable(self):
        spec = suite_spec(sample_suite())
        self.assertEqual(spec["id"], "outbound-email-sample")
        self.assertEqual(spec["payload_kind"], "email_sample")
        self.assertEqual(2, len(spec["criteria"]))
        self.assertIn("source", spec["criteria"][0])
        self.assertIn("severity", spec["criteria"][0])

    def test_criterion_requires_grounding(self):
        with self.assertRaises(ValueError):
            EvalCriterion("x", "X", "", "")
        with self.assertRaises(ValueError):
            EvalCriterion("x", "X", "desc", "src", severity="fatal")


class JudgeConnectorTests(unittest.TestCase):
    def test_agent_judge_is_the_default_and_validates_shape(self):
        connector = AgentJudgeConnector()
        suite, payload = sample_suite(), sample_payload()
        request = connector.render_request(suite, payload)
        self.assertEqual(request["payload_id"], "outbound-sample-01")
        self.assertEqual([item["item_id"] for item in request["items"]],
                         ["sample-1", "sample-2"])
        valid = all_pass_verdicts(suite, ["sample-1", "sample-2"])
        self.assertEqual([], connector.validate(suite, payload, valid))

    def test_verdict_validation_rejects_missing_and_malformed_verdicts(self):
        suite, payload = sample_suite(), sample_payload()
        connector = AgentJudgeConnector()
        partial = {"items": {"sample-1": {"clear": {"pass": True, "score": 1.0, "reason": "ok"}}}}
        errors = connector.validate(suite, payload, partial)
        self.assertTrue(any("sample-2" in error for error in errors))
        bad_pass = {"items": {"sample-1": {
            "clear": {"pass": "yes", "score": 1.0, "reason": "ok"},
            "native": {"pass": True, "score": 1.0, "reason": "ok"},
        }, "sample-2": all_pass_verdicts(suite, ["sample-2"])["items"]["sample-2"]}}
        errors = connector.validate(suite, payload, bad_pass)
        self.assertTrue(any("pass: true|false" in error for error in errors))
        unknown_item = {"items": {"ghost": all_pass_verdicts(suite, ["ghost"])["items"]["ghost"]}}
        errors = connector.validate(suite, payload, unknown_item)
        self.assertTrue(any("unknown item" in error for error in errors))

    def test_invalid_verdicts_never_produce_a_report(self):
        suite, payload = sample_suite(), sample_payload()
        with self.assertRaises(ValueError):
            run_suite(suite, payload, {"items": {}})
        with self.assertRaises(ValueError):
            compute_report(suite, payload, {"items": {}})

    def test_http_connector_is_an_inert_provider_seam(self):
        connector = HttpJudgeConnector()
        suite, payload = sample_suite(), sample_payload()
        # The seam shares the request/validation contract...
        self.assertIn("suite", connector.render_request(suite, payload))
        self.assertEqual([], connector.validate(suite, payload, all_pass_verdicts(suite, ["sample-1", "sample-2"])))
        # ...but no hosted provider is wired in this change.
        with self.assertRaises(NotImplementedError):
            connector.compute(suite, payload)


class ReportComputationTests(unittest.TestCase):
    def test_all_pass_computes_a_passing_report(self):
        suite, payload = sample_suite(), sample_payload()
        report = run_suite(suite, payload, all_pass_verdicts(suite, ["sample-1", "sample-2"]))
        self.assertIsInstance(report, EvalReport)
        self.assertTrue(report.overall)
        self.assertEqual({"sample-1": True, "sample-2": True}, report.per_item_pass)
        self.assertEqual("outbound-sample-01", report.payload_id)
        self.assertEqual(suite.validity, report.validity)
        self.assertEqual("agent:cli", report.judge_connector)

    def test_failed_blocking_criterion_fails_the_item_and_report(self):
        suite, payload = sample_suite(), sample_payload()
        verdicts = all_pass_verdicts(suite, ["sample-1", "sample-2"])
        verdicts["items"]["sample-1"]["clear"] = {
            "pass": False, "score": 0.4, "reason": "vague claim", "evidence_refs": ["text"]}
        report = run_suite(suite, payload, verdicts)
        self.assertFalse(report.overall)
        self.assertFalse(report.per_item_pass["sample-1"])
        self.assertTrue(report.per_item_pass["sample-2"])
        self.assertIn("sample-1:clear", report.failed_criteria())

    def test_min_score_threshold_blocks_partial_scores(self):
        suite, payload = sample_suite(), sample_payload()
        verdicts = all_pass_verdicts(suite, ["sample-1", "sample-2"])
        verdicts["items"]["sample-2"]["clear"] = {"pass": True, "score": 0.7, "reason": "mostly clear"}
        report = run_suite(suite, payload, verdicts)
        self.assertFalse(report.overall)
        self.assertFalse(report.per_item_pass["sample-2"])

    def test_warn_criteria_are_advisory_unless_all_pass(self):
        suite = EvalSuite(
            id="advisory-suite", name="Advisory", scope="sample",
            department_id="outbound", payload_kind="email_sample",
            thresholds={},  # all_pass absent: only block criteria gate
            item_selector=lambda payload: [(payload["id"], payload)],
            criteria=(
                EvalCriterion("must", "Must", "Blocking check.", ".agents/company/strategy/voice.md"),
                EvalCriterion("nice", "Nice", "Advisory check.", ".agents/company/strategy/voice.md",
                              severity="warn"),
            ),
        )
        payload = {"id": "advisory-1", "text": "hello"}
        verdicts = {"items": {"advisory-1": {
            "must": {"pass": True, "score": 1.0, "reason": "ok"},
            "nice": {"pass": False, "score": 0.2, "reason": "advisory miss"},
        }}}
        report = run_suite(suite, payload, verdicts)
        self.assertTrue(report.overall, "warn failure must not block without all_pass")
        strict = EvalSuite(
            id="strict-suite", name="Strict", scope="sample",
            department_id="outbound", payload_kind="email_sample",
            thresholds={"all_pass": True, "min_score": 1.0},
            item_selector=lambda payload: [(payload["id"], payload)],
            criteria=suite.criteria,
        )
        strict_report = run_suite(strict, payload, verdicts)
        self.assertFalse(strict_report.overall, "warn failure blocks under all_pass")

    def test_payload_id_defaults_to_batch_or_id(self):
        plain = EvalSuite(
            id="plain-payload-id", name="Plain", scope="sample",
            department_id="outbound", payload_kind="email_sample",
            criteria=(EvalCriterion("must", "Must", "Blocking check.",
                                    ".agents/company/strategy/voice.md"),),
        )
        self.assertEqual(plain.payload_id({"batch_id": "b-2"}), "b-2")
        self.assertEqual(plain.payload_id({"id": "only-id"}), "only-id")
        self.assertEqual(plain.payload_id({}), "payload")


class RegistryTests(unittest.TestCase):
    def test_content_suite_is_auto_discovered_from_its_department(self):
        registered = suites()
        self.assertIn("content-copy-top10", registered)
        suite = get_suite("content-copy-top10")
        self.assertEqual("content", suite.department_id)
        self.assertEqual("campaign_manifest", suite.payload_kind)
        self.assertEqual(10, len(suite.criteria))
        self.assertEqual(["one_reader", "one_moment", "one_idea",
                          "cold_audience_clarity", "buyer_language",
                          "sharp_opening", "honest_claims", "platform_native",
                          "flow_brevity", "fifth_item_reminder"],
                         [c.id for c in suite.criteria])
        self.assertEqual({"all_pass": True, "min_score": 1.0}, suite.thresholds)

    def test_duplicate_registration_is_rejected(self):
        with self.assertRaises(ValueError):
            register_suite(get_suite("content-copy-top10"))

    def test_reusability_second_suite_registers_and_runs_on_the_same_engine(self):
        suite = sample_suite()
        try:
            register_suite(suite)
        except ValueError:
            pass  # already registered in this process
        registered = suites()
        self.assertIn("outbound-email-sample", registered)
        report = run_suite(suite, sample_payload(),
                           all_pass_verdicts(suite, ["sample-1", "sample-2"]))
        self.assertTrue(report.overall)
        self.assertEqual("outbound-email-sample", report.suite_id)
        self.assertEqual("outbound", suite.department_id)
        self.assertEqual("email_sample", report.payload_kind)


class EvidenceShapeTests(unittest.TestCase):
    def test_evidence_payload_shape_feeds_the_quality_gate(self):
        suite, payload = sample_suite(), sample_payload()
        report = run_suite(suite, payload, all_pass_verdicts(suite, ["sample-1", "sample-2"]))
        evidence = report_to_evidence(report)
        self.assertEqual({
            "suite_id", "payload_id", "payload_kind", "overall",
            "per_item_pass", "per_item", "thresholds", "judge_connector",
            "validity", "generated_at",
        }, set(evidence))
        self.assertIs(True, evidence["overall"])
        self.assertEqual("outbound-sample-01", evidence["payload_id"])
        sample_verdict = evidence["per_item"]["sample-1"]["clear"]
        self.assertIs(True, sample_verdict["pass"])
        self.assertEqual(1.0, sample_verdict["score"])
        self.assertIn("reason", sample_verdict)
        self.assertEqual(["text"], sample_verdict["evidence_refs"])
        self.assertEqual("technical_only", evidence["validity"])

    def test_request_render_gives_the_judge_brief_and_items(self):
        suite, payload = sample_suite(), sample_payload()
        request = render_request(suite, payload)
        self.assertEqual("email_sample", request["payload_kind"])
        self.assertEqual(suite_spec(suite), request["suite"])
        self.assertEqual(["sample-1", "sample-2"],
                         [item["item_id"] for item in request["items"]])
        self.assertEqual("operator@acme.com", request["items"][0]["payload"]["to"])


if __name__ == "__main__":
    unittest.main()
