import unittest
from types import SimpleNamespace

from company.runtime.contracts import approval_interaction


class NotificationInteractionTests(unittest.TestCase):
    def test_approval_interaction_exposes_natural_authority_scopes(self):
        goal = SimpleNamespace(id="goal-1", name="Publish proof")
        result = SimpleNamespace(attention={}, payload={}, evaluation={},
                                 message="Publish the prepared artifact")
        value = approval_interaction(goal, result)
        self.assertEqual(
            ["per_action", "per_run", "everything_approved"],
            [item["scope"] for item in value["authority_scopes"]])
        self.assertTrue(value["authority_scopes"][2]["command"].endswith(
            "--scope everything_approved"))


if __name__ == "__main__":
    unittest.main()
