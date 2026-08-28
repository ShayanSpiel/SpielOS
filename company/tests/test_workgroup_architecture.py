"""The canonical execution catalog is Workgroup → Worker → Workflow."""

import unittest

from company.runtime.catalog import catalog
from company.runtime.registry import workgroups


class WorkgroupArchitectureTests(unittest.TestCase):
    def test_stock_packages_resolve_to_nonempty_workgroups_and_workers(self):
        values = workgroups()
        self.assertEqual({"analytics", "content", "design", "outbound", "seo"}, set(values))
        for handler in values.values():
            self.assertTrue(handler.workgroup.workers)
            self.assertEqual(
                {worker.id for worker in handler.workgroup.workers},
                set(handler.agent_ids))
            for workflow in handler.workflows:
                self.assertIsNotNone(handler.worker_for_workflow(workflow.id))

    def test_catalog_exposes_worker_owned_workflows(self):
        value = catalog()
        self.assertEqual("worker-workflow-interpreter",
                         value["runtime"]["execution_runtime"])
        content = next(item for item in value["workgroups"] if item["id"] == "content")
        strategist = next(item for item in content["workers"]
                          if item["id"] == "content-strategist")
        self.assertTrue(strategist["workflows"])
        self.assertTrue(strategist["workbook"])
        self.assertTrue(strategist["workkit"])


if __name__ == "__main__":
    unittest.main()
