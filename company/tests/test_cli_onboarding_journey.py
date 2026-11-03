"""The terminal handoff should reflect the owner's choices."""
import io
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

from company.runtime import onboard


class TerminalOnboardingJourneyTests(unittest.TestCase):
    def test_host_and_first_job_shape_the_handoff(self):
        style = onboard._Style()
        style.tty = True
        style.enabled = False
        receipt = {"root": "/tmp/example-company", "files_written": 1,
                   "verified": True, "hosts": {"codex": True, "claude": True,
                                                "opencode": False}}
        output = io.StringIO()
        with patch.object(onboard, "_prompt", side_effect=["unknown", "claude", "weekly sales report"]), redirect_stdout(output):
            onboard._render_success(style, receipt, interactive=True)
        text = output.getvalue()
        self.assertIn("Choose codex, claude, or opencode.", text)
        self.assertIn("$ claude", text)
        self.assertNotIn("$ codex", text)
        self.assertIn("tested workflow: weekly sales report", text)
        self.assertIn("Review the company hooks", text)
        self.assertNotIn("Try: Build a lead research", text)

    def test_missing_selected_host_is_explained(self):
        style = onboard._Style()
        style.tty = True
        style.enabled = False
        receipt = {"root": "/tmp/example-company", "files_written": 1,
                   "verified": True, "hosts": {"codex": False, "claude": False,
                                                "opencode": False}}
        output = io.StringIO()
        with patch.object(onboard, "_prompt", side_effect=["codex", ""]), redirect_stdout(output):
            onboard._render_success(style, receipt, interactive=True)
        self.assertIn("was not found on your PATH", output.getvalue())
        self.assertIn("Try: Build a lead research", output.getvalue())


if __name__ == "__main__":
    unittest.main()
