"""SpielOS1 ships the compatibility-only OpenCode adapter by design:
runtime progression belongs to `company runner watch`/wake and liveness to
the OS supervisor. The website home runs the FULL V2 plugin instead. These
contract tests describe the FULL adapter; run them with
SPIELOS_TEST_FULL_PLUGIN=1 when working on that variant."""
import os
import unittest

FULL_PLUGIN = os.environ.get("SPIELOS_TEST_FULL_PLUGIN") == "1"
requires_full_plugin = unittest.skipUnless(
    FULL_PLUGIN,
    "SpielOS1 ships the compatibility-only host adapter "
    "(set SPIELOS_TEST_FULL_PLUGIN=1 for the full-plugin contract)")
