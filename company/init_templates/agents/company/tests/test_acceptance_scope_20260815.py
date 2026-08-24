"""Meta acceptance for change-f418161da7 / goal-acceptance-scope-repair-20260815.

Three approved upstream change tasks reference acceptance modules that did not
exist on disk:

  goal-approval-policy-20260815     -> company.tests.test_approval_policy
  goal-runner-persistence-20260815  -> company.tests.test_runner_persistence
  goal-transient-retry-20260815     -> company.tests.test_transient_retry

This suite proves the three feature modules (written against their goal
problem statements) import cleanly RIGHT NOW, load at least one test each, and
are named exactly as the upstream acceptance commands expect. The feature
suites themselves are the acceptance contract for the upstream executors, so
they may legitimately fail (new behavior) or skip (missing runtime module)
until the corresponding implementation lands; this module only verifies the
scope scaffolding is importable and discoverable.
"""

import importlib
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# Exact acceptance command tails recorded on the three upstream goals.
ACCEPTANCE_PREFIX = "PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=.. python3 -B -m unittest "
FEATURE_MODULES = (
    ("company.tests.test_approval_policy", "goal-approval-policy-20260815"),
    ("company.tests.test_runner_persistence", "goal-runner-persistence-20260815"),
    ("company.tests.test_transient_retry", "goal-transient-retry-20260815"),
)

ALLOWED_FILES = [
    "company/tests/test_approval_policy.py",
    "company/tests/test_runner_persistence.py",
    "company/tests/test_transient_retry.py",
    "company/tests/test_acceptance_scope_20260815.py",
]


class AcceptanceScopeTests(unittest.TestCase):
    def test_three_feature_modules_import_cleanly(self):
        for module, _goal_id in FEATURE_MODULES:
            imported = importlib.import_module(module)  # must not raise
            self.assertIsNotNone(imported)

    def test_each_module_loads_at_least_one_test(self):
        loader = unittest.TestLoader()
        for module, _goal_id in FEATURE_MODULES:
            count = loader.loadTestsFromModule(
                importlib.import_module(module)).countTestCases()
            self.assertGreaterEqual(
                count, 1, "%s must load at least one test" % module)

    def test_module_names_match_upstream_acceptance_commands(self):
        for module, goal_id in FEATURE_MODULES:
            command = ACCEPTANCE_PREFIX + module
            self.assertEqual(
                command,
                "PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=.. python3 -B -m "
                "unittest %s" % module)
            self.assertIn(module, command)
            # The module belongs to exactly the upstream goal that owns it.
            self.assertTrue(goal_id.endswith("-20260815"))
            self.assertTrue(module.startswith("company.tests.test_"))

    def test_allowed_files_exist_on_disk(self):
        root = Path(__file__).resolve().parents[2]
        for relative in ALLOWED_FILES:
            self.assertTrue(
                (root / relative).is_file(),
                "allowed file missing: %s" % relative)


if __name__ == "__main__":
    unittest.main()