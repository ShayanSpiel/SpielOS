"""Department Lego interpreter: graphs, packages, and memory learnings."""

import tempfile
import unittest
from pathlib import Path

from company.runtime.loop import Runtime
from company.runtime.interpreter import InterpretedDepartment
from company.runtime.models import Department, Goal, GoalContext, WorkflowSpec, WorkflowStep
from company.runtime.package import package_spec, validate_package
from company.runtime.registry import departments


class PackageShapeTests(unittest.TestCase):
    def test_growth_departments_are_valid_lego_packages(self):
        for dept_id in ("content", "design", "analytics", "seo", "outbound"):
            department = departments()[dept_id]
            defects = validate_package(department)
            self.assertEqual([], defects, msg=f"{dept_id}: {defects}")
            package = package_spec(department)
            self.assertEqual(dept_id, package["id"])
            self.assertTrue(package["workflows"])
            self.assertTrue(package["metrics"])


class InterpreterRuntimeTests(unittest.TestCase):
    def test_persisted_decision_links_only_evidence_used(self):
        class ProvenanceDepartment(InterpretedDepartment, Department):
            id = department_id = "provenance-fixture"
            version = "1.0.0"
            description = "Exact evidence provenance fixture"
            agent_ids = ("publisher",)
            goal_schema = {"metrics": ["published"],
                           "config": {"workflow": {"enum": ["primary"]}}}
            evidence_metrics = {"published": ("publication_receipt",)}
            workflows = (WorkflowSpec(
                "primary", "fixture", ("approve", "dispatch"),
                ("publisher",), (), ("publish",),
                ("campaign_ready", "publication_receipt"), (), graph=(
                    WorkflowStep("approve", "approval", requires=("campaign_ready",)),
                )),)

        with tempfile.TemporaryDirectory() as tmp:
            runtime = Runtime(Path(tmp) / "company.sqlite", {
                ProvenanceDepartment.id: ProvenanceDepartment(),
            })
            goal = runtime.create_goal(
                name="Link the decision", owner_id=ProvenanceDepartment.id,
                metric="published", operator="ge", target=1,
                config={"workflow": "primary"})
            relevant = runtime.add_evidence(
                goal["id"], kind="campaign_ready", source="quality-gate",
                payload={"ready": True}, validity="technical_only")["evidence"][-1]
            runtime.add_evidence(
                goal["id"], kind="unrelated_observation", source="observer",
                payload={"visible": True}, validity="technical_only")

            runtime.once(goal["id"])

            decisions = runtime.store.decisions(runtime.store.cycle(goal["id"])["id"])
            approval = next(item for item in decisions
                            if item["decision_type"] == "request_approval")
            self.assertEqual(approval["evidence_ids"], [relevant["id"]])

    def test_machine_evidence_is_reobserved_before_the_approval_node(self):
        class MachineThenApprovalDepartment(InterpretedDepartment, Department):
            id = department_id = "machine-then-approval"
            version = "1.0.0"
            description = "Machine evidence refresh regression fixture"
            agent_ids = ("publisher",)
            goal_schema = {"metrics": ["published"],
                           "config": {"workflow": {"enum": ["primary"]}}}
            evidence_metrics = {"published": ("publication_receipt",)}
            workflows = (WorkflowSpec(
                "primary", "fixture", ("quality_gate", "approve", "dispatch"),
                ("publisher",), (), ("publish",),
                ("campaign_ready", "publication_receipt"), (), graph=(
                    WorkflowStep("quality_gate", "machine", produces=("campaign_ready",)),
                    WorkflowStep("approve", "approval", requires=("campaign_ready",)),
                )),)

            def __init__(self):
                self.machine_calls = 0

            def run_machine_step(self, ctx, decision):
                self.machine_calls += 1
                return {"evidence": [{"kind": "campaign_ready", "source": "quality-gate",
                                      "validity": "technical_only", "payload": {"ready": True}}]}

        with tempfile.TemporaryDirectory() as tmp:
            department = MachineThenApprovalDepartment()
            runtime = Runtime(Path(tmp) / "company.sqlite", {
                department.id: department,
            })
            goal = runtime.create_goal(
                name="Machine then approval", owner_id=department.id,
                metric="published", operator="ge", target=1,
                config={"workflow": "primary"})

            parked = runtime.once(goal["id"])

            self.assertEqual(1, department.machine_calls)
            self.assertEqual("awaiting_approval", parked["cycle"]["run_status"])
            self.assertEqual("approve", parked["cycle"]["data"]["action_result"]["step_id"])
            self.assertEqual(1, len([
                item for item in parked["evidence"] if item["kind"] == "campaign_ready"
            ]))

    def test_only_explicit_approval_nodes_pause_after_run_approval(self):
        class ExplicitApprovalDepartment(InterpretedDepartment, Department):
            id = department_id = "explicit-approval"
            version = "1.0.0"
            description = "Approval contract fixture"
            agent_ids = ("designer",)
            goal_schema = {"metrics": ["items"],
                           "config": {"workflow": {"enum": ["primary"]}}}
            evidence_metrics = {"items": ("final_item",)}
            workflows = (WorkflowSpec(
                "primary", "fixture", ("approve_one", "draft", "approve_two", "finish"),
                ("designer",), ("spielos-ui",), (), ("final_item",), (), graph=(
                    WorkflowStep("approve_one", "approval"),
                    WorkflowStep("draft", "employee", "designer", produces=("draft_item",)),
                    WorkflowStep("approve_two", "approval", requires=("draft_item",)),
                    WorkflowStep("finish", "employee", "designer", produces=("final_item",),
                                 requires=("draft_item",)),
                )),)

        with tempfile.TemporaryDirectory() as tmp:
            runtime = Runtime(Path(tmp) / "company.sqlite", {
                "explicit-approval": ExplicitApprovalDepartment(),
            })
            goal = runtime.create_goal(
                name="Explicit gates", owner_id="explicit-approval", metric="items",
                operator="ge", target=1, config={})
            first = runtime.once(goal["id"])
            self.assertEqual("awaiting_approval", first["cycle"]["run_status"])
            runtime.approve(goal["id"])
            blocked = runtime.once(goal["id"])
            order = runtime.store.work_orders(status="open", goal_id=goal["id"])[0]
            self.assertEqual("draft", order["step_id"])
            runtime.add_evidence(
                goal["id"], kind="draft_item", source="designer", payload={})
            runtime.retry(goal["id"])
            second = runtime.once(goal["id"])
            self.assertEqual("awaiting_approval", second["cycle"]["run_status"])
            self.assertEqual(
                "approve_two", second["cycle"]["data"]["action_result"]["step_id"])

    def test_design_graph_opens_work_order_without_completion_diary(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime = Runtime(Path(tmp) / "company.sqlite")
            goal = runtime.create_goal(
                name="One rendition", owner_id="design", metric="rendition_count",
                operator="ge", target=1, config={"workflow": "rendition-pack"})
            blocked = runtime.once(goal["id"])
            self.assertEqual("blocked", blocked["cycle"]["run_status"])
            order = runtime.store.work_orders(status="open", goal_id=goal["id"])[0]
            self.assertEqual("designer", order["employee_id"])
            self.assertEqual(["render_report"], order["accepts_evidence"])
            step_id = (
                order.get("step_id")
                or (order.get("brief") or {}).get("step_id")
                or blocked["cycle"]["data"]["action_result"].get("step_id")
            )
            self.assertEqual("render_sizes", step_id)
            runtime.add_evidence(goal["id"], kind="render_report", source="designer",
                                 payload={"file": "render-report.json"}, validity="technical_only")
            runtime.retry(goal["id"])
            done = runtime.once(goal["id"])
            self.assertEqual("achieved", done["goal"]["goal_status"])
            memories = runtime.store.memories("design", goal["id"])
            self.assertEqual((), memories)

    def test_content_publish_graph_approves_then_connection_work_order(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime = Runtime(Path(tmp) / "company.sqlite")
            goal = runtime.create_goal(
                name="Publish pack", owner_id="content", metric="published_items",
                operator="ge", target=1,
                config={"workflow": "publish", "connection": "buffer",
                        "execution_mode": "dry_run"})
            runtime.add_evidence(goal["id"], kind="content_package", source="content-strategist",
                                 payload={"channel_id": "x", "text": "hello"},
                                 validity="technical_only")
            parked = runtime.once(goal["id"])
            self.assertEqual("awaiting_approval", parked["cycle"]["run_status"])
            runtime.approve(goal["id"])
            # Same-cycle approval satisfies the graph approve node; connection
            # dispatch then parks on a publisher work order in one advance.
            blocked = runtime.once(goal["id"])
            self.assertEqual("blocked", blocked["cycle"]["run_status"])
            orders = runtime.store.work_orders(status="open", goal_id=goal["id"])
            self.assertEqual(1, len(orders))
            self.assertEqual("publisher", orders[0]["employee_id"])
            self.assertEqual(["publication_receipt"], orders[0]["accepts_evidence"])

    def test_observe_surfaces_memory_for_department(self):
        department = departments()["design"]
        goal = Goal("g", "Graphics", "design", "rendition_count", "ge", 1,
                    None, None, "active", {"workflow": "rendition-pack"})
        memory = ({"claim": "Square cards convert better", "confidence": 0.7, "goal_id": "g"},)
        ctx = GoalContext(goal, {"evidence": []}, memory, lambda _: None)
        observation = department.observe(ctx).payload
        self.assertEqual(1, len(observation["memory"]))
        self.assertEqual("Square cards convert better", observation["memory"][0]["claim"])
        self.assertEqual("render_sizes", observation["current_step"]["id"])


if __name__ == "__main__":
    unittest.main()
