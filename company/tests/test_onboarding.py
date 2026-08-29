from __future__ import annotations

import io
import tempfile
import unittest
from contextlib import redirect_stderr
from pathlib import Path
from unittest.mock import patch

from company.runtime import onboard
from company.runtime.paths import validate_home_destination


class OnboardingTests(unittest.TestCase):
    def test_next_steps_handoff_to_director_in_both_hosts(self):
        root = Path("/tmp/new-company")
        steps, notes = onboard._next_steps(
            root, {"opencode": True, "codex": True}, True, [])

        rendered = "\n".join(
            [f"{command} {note}" for command, note in steps]
            + list(notes.values()))
        self.assertIn("Choose Codex or OpenCode", rendered)
        self.assertIn("codex call @Director", rendered)
        self.assertIn("opencode run /agent, select the Director agent", rendered)
        self.assertNotIn("Workgroup", rendered)
        self.assertNotIn(".env", rendered)

    def test_interactive_init_does_not_ask_for_starter_workgroups(self):
        receipt = {
            "root": "/tmp/new-company",
            "files_written": 1,
            "next_steps": [],
        }
        style = onboard._Style()
        style.tty = True
        with patch.object(onboard, "_Style", return_value=style), \
                patch.object(onboard.sys.stdin, "isatty", return_value=True), \
                patch.object(onboard, "banner"), \
                patch.object(onboard, "_confirm_overwrite", return_value=False), \
                patch.object(onboard, "scaffold", return_value=receipt) as scaffold, \
                patch.object(onboard, "_verify_home", return_value=(True, "")), \
                patch.object(onboard, "_render_success"):
            result = onboard.run_init(dir="/tmp/new-company")

        self.assertEqual(0, result)
        self.assertIsNone(scaffold.call_args.kwargs["workgroups"])

    def test_trash_destination_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "inside macOS Trash"):
            validate_home_destination(
                "/Users/example/.Trash/SpielOS-Website-pre-cleanup")

    def test_trash_error_does_not_suggest_workgroups(self):
        stderr = io.StringIO()
        with redirect_stderr(stderr):
            result = onboard.run_init(
                dir="/Users/example/.Trash/SpielOS-Website-pre-cleanup",
                assume_yes=True)

        self.assertEqual(1, result)
        self.assertIn("inside macOS Trash", stderr.getvalue())
        self.assertNotIn("Workgroup", stderr.getvalue())

    def test_normal_destination_is_allowed(self):
        with tempfile.TemporaryDirectory() as directory:
            self.assertEqual(Path(directory).resolve(),
                             validate_home_destination(directory))


if __name__ == "__main__":
    unittest.main()
