"""WorkflowSpec contracts: goal validation and catalog-backed work orders."""

import tempfile
import unittest
from pathlib import Path

from company.departments.design.department import DesignDepartment
from company.connections import connection, connections
from company.runtime.catalog import catalog
from company.runtime.contracts import agent_shortfall, validate_goal_request
from company.runtime.loop import Runtime
from company.runtime.registry import departments


class GoalValidationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.runtime = Runtime(Path(self.temp.name) / "company.sqlite")

    def test_rejects_unknown_metric_for_department(self):
        with self.assertRaisesRegex(ValueError, "metric 'nope'"):
            self.runtime.create_goal(
                name="Bad metric", owner_id="design", metric="nope",
                operator="ge", target=1, config={"workflow": "rendition-pack"})

    def test_rejects_unknown_workflow(self):
        with self.assertRaisesRegex(ValueError, "workflow 'not-a-workflow'"):
            self.runtime.create_goal(
                name="Bad workflow", owner_id="design", metric="rendition_count",
                operator="ge", target=1, config={"workflow": "not-a-workflow"})

    def test_defaults_workflow_from_schema_enum(self):
        goal = self.runtime.create_goal(
            name="Default workflow", owner_id="content", metric="content_packages",
            operator="ge", target=1, config={})
        self.assertEqual("content-package", goal["config"]["workflow"])

    def test_outbound_defaults_to_email_outreach(self):
        goal = self.runtime.create_goal(
            name="Default outbound", owner_id="outbound", metric="reply_rate",
            operator="ge", target=0.3, config={"execution_mode": "dry_run", "batch_size": 5})
        self.assertEqual("email-outreach", goal["config"]["workflow"])


class CatalogWorkOrderTests(unittest.TestCase):
    def test_agent_shortfall_uses_workflow_spec_and_evidence_metrics(self):
        department = DesignDepartment()
        payload = agent_shortfall(
            department, goal_id="goal-1", metric="rendition_count", needed=2,
            workflow_id="rendition-pack")
        self.assertEqual("request_agent", payload["action"])
        self.assertEqual("designer", payload["agent_id"])
        self.assertEqual("rendition-pack", payload["workflow_id"])
        self.assertEqual(["render_report"], payload["accepted_evidence_kinds"])
        self.assertEqual(["spielos-ui"], payload["skill_ids"])
        self.assertEqual(2, payload["needed"])

    def test_runtime_work_order_carries_catalog_brief(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime = Runtime(Path(tmp) / "company.sqlite")
            goal = runtime.create_goal(
                name="One graphic", owner_id="design", metric="rendition_count",
                operator="ge", target=1, config={"workflow": "rendition-pack"})
            blocked = runtime.once(goal["id"])
            self.assertEqual("blocked", blocked["cycle"]["run_status"])
            orders = runtime.store.work_orders(status="open", goal_id=goal["id"])
            self.assertEqual(1, len(orders))
            self.assertEqual("designer", orders[0]["employee_id"])
            self.assertEqual(["render_report"], orders[0]["accepts_evidence"])
            self.assertEqual("rendition-pack", orders[0]["workflow_id"])
            self.assertEqual(["spielos-ui"], orders[0]["brief"]["skill_ids"])

    def test_validate_goal_request_is_pure(self):
        design = departments()["design"]
        config = validate_goal_request(design, metric="video_renders", config={})
        self.assertEqual("social-visual", config["workflow"])

    def test_work_order_claim_is_exclusive_and_completion_advances_goal(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "company.sqlite"
            runtime = Runtime(db)
            goal = runtime.create_goal(
                name="One graphic", owner_id="design", metric="rendition_count",
                operator="ge", target=1, config={"workflow": "rendition-pack"})
            runtime.once(goal["id"])
            order = runtime.store.work_orders(status="active", goal_id=goal["id"])[0]

            claimed = runtime.claim_work_order(order["id"], "host-a")
            self.assertEqual("claimed", claimed["status"])
            self.assertEqual("host-a", claimed["claimed_by"])
            with self.assertRaisesRegex(RuntimeError, "owned by host-a"):
                Runtime(db).claim_work_order(order["id"], "host-b")

            result = runtime.complete_work_order(order["id"], "host-a", [{
                "kind": "render_report",
                "source": "host-a",
                "payload": {"path": "artifact.png"},
            }])
            self.assertEqual("done", result["work_order"]["status"])
            linked = [item for item in result["goal"]["evidence"]
                      if item["kind"] == "render_report"]
            self.assertEqual(order["id"], linked[0]["payload"]["work_order_id"])
            self.assertEqual("achieved", result["goal"]["goal"]["goal_status"])

    def test_work_order_rejects_wrong_evidence_kind(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime = Runtime(Path(tmp) / "company.sqlite")
            goal = runtime.create_goal(
                name="One graphic", owner_id="design", metric="rendition_count",
                operator="ge", target=1, config={"workflow": "rendition-pack"})
            runtime.once(goal["id"])
            order = runtime.store.work_orders(status="active", goal_id=goal["id"])[0]
            runtime.claim_work_order(order["id"], "host-a")
            with self.assertRaisesRegex(ValueError, "needs 1 accepted evidence"):
                runtime.complete_work_order(order["id"], "host-a", [{
                    "kind": "unrelated", "payload": {},
                }])


class AttioConnectionContractTests(unittest.TestCase):
    """Acceptance contract for the attio host-first OAuth CRM Connection."""

    def test_attio_is_registered_in_the_connections_registry(self):
        self.assertIn("attio", connections())
        item = connection("attio")
        self.assertEqual("attio", item.id)
        self.assertIn("mcp.attio.com/mcp", item.description)

    def test_attio_is_host_first_opencode_oauth_with_no_secret(self):
        item = connection("attio")
        self.assertIn("opencode", item.hosts)
        self.assertFalse(item.unattended)
        self.assertEqual((), item.required_environment)

    def test_attio_capabilities_cover_read_and_write(self):
        item = connection("attio")
        read = {"records_query", "records_search", "list_entries", "notes"}
        write = {"records_create", "records_update"}
        self.assertTrue(read.intersection(item.capabilities))
        self.assertTrue(write.intersection(item.capabilities))

    def test_attio_catalog_entry_validates_with_zero_defects(self):
        entries = {item["id"]: item for item in catalog()["connections"]}
        self.assertIn("attio", entries)
        entry = entries["attio"]
        self.assertEqual({"id", "description", "capabilities", "hosts",
                          "unattended", "required_environment"}, set(entry))
        defects = []
        if entry["id"] != "attio":
            defects.append("unexpected id")
        if not entry["description"]:
            defects.append("missing description")
        if not entry["capabilities"]:
            defects.append("missing capabilities")
        if "opencode" not in entry["hosts"]:
            defects.append("opencode host missing")
        if entry["unattended"]:
            defects.append("unattended flag set")
        if entry["required_environment"]:
            defects.append("unexpected required environment")
        self.assertEqual([], defects)


if __name__ == "__main__":
    unittest.main()
