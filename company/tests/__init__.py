"""Company runtime tests."""

import os

# Fail closed: Store/Runtime write paths must not open the live company database.
os.environ.setdefault("SPIELOS_TEST_ISOLATION", "1")
