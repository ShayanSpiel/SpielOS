"""P6: one bounded read-only Strategy state over canonical sources."""

from __future__ import annotations

import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from company.__main__ import main
from company.runtime.director import Director
from company.runtime.loop import Runtime
from company.runtime.models import Goal, GoalContext, GoalHandler, RunStatus, StageResult
from company.runtime.strategy import (
    MANIFEST_PATH, load_strategy_kernel, select_strategy_context,
    strategy_kernel_summary,
)


def source_hashes() -> dict[str, str]:
    kernel = load_strategy_kernel()
    return {item["path"]: item["sha256"] for item in kernel["sources"]}


class _StrategyProbe(GoalHandler):
    id = "strategy_probe"
    version = "1.0.0"

    def observe(self, ctx):
        return StageResult(
            "collect_strategy",
            {"strategy": ctx.strategy, "memory_count": len(ctx.memory)},
            RunStatus.WAITING,
        )

    def decide(self, ctx, observation):  # pragma: no cover - suspended in observe
        raise AssertionError("probe should suspend in OBSERVE")

    act = decide
    evaluate = decide


class StrategyKernelTests(unittest.TestCase):
    def test_kernel_exposes_four_layers_and_named_views_without_copying_claims(self):
        kernel = load_strategy_kernel()
        self.assertEqual(
            ["intent", "model", "policy", "constitution"], list(kernel["layers"]))
        self.assertEqual(
            {"icp", "positioning", "voice", "measurement"}, set(kernel["views"]))
        summary = strategy_kernel_summary(kernel)
        self.assertEqual("proposal_only_owner_authorized", summary["mutation"])
        encoded_manifest = MANIFEST_PATH.read_text()
        self.assertNotIn("Established online businesses", encoded_manifest)
        self.assertTrue(all("content" not in atom for values in summary["layers"].values()
                            for atom in values))

    def test_selector_is_relevant_bounded_and_keeps_memory_separate(self):
        goal = Goal(
            id="goal-content", name="Create one useful buyer idea",
            owner_id="content", metric="qualified_visits", operator="ge",
            target=10, deadline=None, parent_id=None, goal_status="active",
            config={"strategy_context": {
                "topics": ["voice"], "scopes": ["content"],
                "layers": ["model", "policy", "constitution"],
            }})
        context = select_strategy_context(goal)
        ids = [item["id"] for item in context["sections"]]
        self.assertIn("intent.operating_thesis", ids)
        self.assertIn("policy.voice.one_idea", ids)
        self.assertIn("constitution.safety", ids)
        self.assertNotIn("model.icp.buyer", ids)
        self.assertLessEqual(len(ids), 8)
        self.assertTrue(context["memory_separate"])
        self.assertFalse(context["strategy_mutable"])

    def test_runtime_supplies_same_bounded_context_to_goal_owner(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime = Runtime(Path(tmp) / "state.sqlite", {
                "strategy_probe": _StrategyProbe()})
            goal = runtime.create_goal(
                name="Use voice policy", owner_id="strategy_probe",
                metric="done", operator="eq", target=True,
                config={"strategy_context": {
                    "topics": ["voice"], "scopes": ["content"],
                    "layers": ["policy", "constitution"],
                }})
            result = runtime.once(goal["id"])
            observed = result["cycle"]["data"]["observation"]
            ids = [item["id"] for item in observed["strategy"]["sections"]]
            self.assertIn("policy.voice.copy_shape", ids)
            self.assertEqual(0, observed["memory_count"])

    def test_malformed_or_escaping_source_references_fail_closed(self):
        manifest = json.loads(MANIFEST_PATH.read_text())
        manifest["layers"]["intent"][0]["source"] = "../outside.md"
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "company"
            root.mkdir()
            outside = root.parent / "outside.md"
            outside.write_text("## Who it is\nOutside")
            path = root / "kernel.json"
            path.write_text(json.dumps(manifest))
            with self.assertRaisesRegex(ValueError, "escapes company authority"):
                load_strategy_kernel(path, company_root=root)

    def test_strategy_cli_is_read_only_and_catalog_reports_kernel(self):
        before = source_hashes()
        captured = io.StringIO()
        with redirect_stdout(captured):
            self.assertEqual(0, main(["strategy"]))
        card = captured.getvalue()
        self.assertTrue(card.startswith("# Strategy kernel"), card)
        self.assertIn("\n- ", card)
        captured = io.StringIO()
        with redirect_stdout(captured):
            self.assertEqual(0, main(["strategy", "--json"]))
        payload = json.loads(captured.getvalue())
        self.assertEqual("proposal_only_owner_authorized", payload["mutation"])
        self.assertEqual(before, source_hashes())
        captured = io.StringIO()
        with redirect_stdout(captured):
            self.assertEqual(0, main(["catalog"]))
        catalog = json.loads(captured.getvalue())
        self.assertEqual("6.0.0", catalog["runtime"]["version"])
        self.assertEqual(payload["state_hash"],
                         catalog["runtime"]["strategy_kernel"]["state_hash"])

    def test_strategic_approval_cannot_mutate_strategy_sources(self):
        before = source_hashes()
        goal = Goal(
            id="parent", name="Improve reply rate", owner_id="director",
            metric="reply_rate", operator="ge", target=0.3, deadline=None,
            parent_id=None, goal_status="active", config={})
        decision = {
            "action": "propose_strategic_experiment",
            "strategic_level": "model", "proposal": "Test the problem frame",
            "strategy_mutated": False,
        }
        ctx = GoalContext(
            goal, {"run": {}, "children": ()}, (),
            lambda key: "approved" if key == "execute" else None)
        result = Director().act(ctx, decision)
        self.assertTrue(result.payload["owner_authorized"])
        self.assertFalse(result.payload["strategy_mutated"])
        self.assertEqual(before, source_hashes())


if __name__ == "__main__":
    unittest.main()
