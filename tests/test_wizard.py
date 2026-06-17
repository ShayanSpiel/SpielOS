#!/usr/bin/env python3
"""test_wizard.py — Tests for the format + publish wizards."""

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import ui
import wizard
from engine_state import CONTENT_BRIEF_FILE


def _visible_len(text: str) -> int:
    return len(ui.strip_ansi(text))


class TestFormatWizard(unittest.TestCase):
    def setUp(self):
        CONTENT_BRIEF_FILE.parent.mkdir(parents=True, exist_ok=True)
        brief = {
            "core_insight": "Sample insight for testing.",
            "wizard": {},
        }
        CONTENT_BRIEF_FILE.write_text(json.dumps(brief))

    def test_returns_tuple(self):
        import io
        sys.stdin = io.StringIO("")
        try:
            ok, msg = wizard.format_wizard()
            self.assertFalse(ok)
            self.assertIsInstance(msg, str)
        finally:
            sys.stdin = sys.__stdin__

    def test_hold_choice(self):
        import io
        sys.stdin = io.StringIO("h")
        try:
            ok, msg = wizard.format_wizard()
            self.assertTrue(ok)
            self.assertIn("HOLD", msg)
            brief = json.loads(CONTENT_BRIEF_FILE.read_text())
            self.assertEqual(brief["wizard"]["formats"], [])
            self.assertTrue(brief["wizard"]["hold"])
        finally:
            sys.stdin = sys.__stdin__

    def test_preset_4_choice(self):
        import io
        sys.stdin = io.StringIO("4")
        try:
            ok, msg = wizard.format_wizard()
            self.assertTrue(ok)
            self.assertIn("x", msg)
            self.assertIn("linkedin", msg)
            brief = json.loads(CONTENT_BRIEF_FILE.read_text())
            self.assertEqual(brief["wizard"]["formats"], ["x", "linkedin"])
        finally:
            sys.stdin = sys.__stdin__

    def test_preset_7_all(self):
        import io
        sys.stdin = io.StringIO("7")
        try:
            ok, msg = wizard.format_wizard()
            self.assertTrue(ok)
            brief = json.loads(CONTENT_BRIEF_FILE.read_text())
            self.assertEqual(brief["wizard"]["formats"], ["x", "linkedin", "blog"])
        finally:
            sys.stdin = sys.__stdin__

    def test_custom_list(self):
        import io
        sys.stdin = io.StringIO("x,blog")
        try:
            ok, msg = wizard.format_wizard()
            self.assertTrue(ok)
            brief = json.loads(CONTENT_BRIEF_FILE.read_text())
            self.assertEqual(brief["wizard"]["formats"], ["x", "blog"])
        finally:
            sys.stdin = sys.__stdin__

    def test_invalid_choice(self):
        import io
        sys.stdin = io.StringIO("z")
        try:
            ok, msg = wizard.format_wizard()
            self.assertFalse(ok)
        finally:
            sys.stdin = sys.__stdin__

    def test_aliases(self):
        result = wizard._parse_format_list("twitter, li")
        self.assertEqual(result, ["x", "linkedin"])


class TestPublishWizard(unittest.TestCase):
    def setUp(self):
        CONTENT_BRIEF_FILE.parent.mkdir(parents=True, exist_ok=True)
        brief = {"wizard": {}}
        CONTENT_BRIEF_FILE.write_text(json.dumps(brief))

    def test_empty_queue(self):
        from engine_state import QUEUE_DIR
        empty = QUEUE_DIR.parent / "test_empty_queue"
        empty.mkdir(exist_ok=True)
        try:
            ok, msg = wizard.publish_wizard(empty)
            self.assertFalse(ok)
        finally:
            for f in empty.glob("*.md"):
                f.unlink()
            empty.rmdir()

    def test_missing_queue(self):
        missing = Path("/tmp/does_not_exist_xyz_123")
        ok, msg = wizard.publish_wizard(missing)
        self.assertFalse(ok)


class TestPlatformColor(unittest.TestCase):
    def test_known_platforms(self):
        self.assertEqual(wizard.platform_color("x"), "bright_cyan")
        self.assertEqual(wizard.platform_color("linkedin"), "bright_blue")
        self.assertEqual(wizard.platform_color("blog"), "bright_magenta")
        self.assertEqual(wizard.platform_color("buffer"), "bright_yellow")

    def test_unknown_platform(self):
        self.assertEqual(wizard.platform_color("unknown"), "white")


class TestPlatformCards(unittest.TestCase):
    def test_cards_have_required_keys(self):
        for key in ("x", "linkedin", "blog"):
            card = wizard.PLATFORM_CARDS[key]
            for field in ("name", "limits", "volume", "purpose", "trigger", "color"):
                self.assertIn(field, card)


class TestPublishWizardsEmptyDrafts(unittest.TestCase):
    def test_creates_draft_files(self):
        import io
        from engine_state import QUEUE_DIR
        test_dir = QUEUE_DIR.parent / "test_pub_dir"
        test_dir.mkdir(exist_ok=True)
        try:
            draft = test_dir / "test-draft.md"
            draft.write_text("---\ntitle: Test\nplatform: x\ngates: pass\n---\n\nBody here.")
            ok, msg = wizard.publish_wizard(test_dir)
            self.assertFalse(ok)
        finally:
            for f in test_dir.glob("*.md"):
                f.unlink()
            test_dir.rmdir()


class TestFormatWizardValidation(unittest.TestCase):
    def test_missing_brief(self):
        CONTENT_BRIEF_FILE.unlink(missing_ok=True)
        ok, msg = wizard.format_wizard()
        self.assertFalse(ok)
        self.assertIn("no .content-brief.json", msg)

    def test_empty_core(self):
        brief = {"core_insight": "", "wizard": {}}
        CONTENT_BRIEF_FILE.write_text(json.dumps(brief))
        ok, msg = wizard.format_wizard()
        self.assertFalse(ok)
        self.assertIn("core_insight", msg)


if __name__ == "__main__":
    unittest.main(verbosity=2)
