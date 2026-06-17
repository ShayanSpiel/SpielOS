#!/usr/bin/env python3
"""test_state_handlers.py — Tests for the state handler registry."""

import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import state_handlers
from engine_state import QUEUE_DIR
from engine_frontmatter import write_frontmatter


class TestHandlerRegistry(unittest.TestCase):
    def test_handler_for_known(self):
        fn = state_handlers.handler_for("PUBLISHING")
        self.assertIsNotNone(fn)

    def test_handler_for_unknown(self):
        fn = state_handlers.handler_for("UNKNOWN_STATE")
        self.assertIsNone(fn)

    def test_run_handler(self):
        state = {"current_state": "IDLE", "loop": "CONTENT"}
        with patch("state_handlers.HANDLERS", {"TEST": lambda s: 0}):
            result = state_handlers.run_handler(state, "TEST")
            self.assertEqual(result, 0)

    def test_run_handler_missing(self):
        state = {"current_state": "IDLE", "loop": "CONTENT"}
        result = state_handlers.run_handler(state, "MISSING")
        self.assertEqual(result, 1)


class TestContentStates(unittest.TestCase):
    def test_known_states(self):
        expected = {
            "IDLE", "SESSION_CAPTURE", "COMPILE", "SELECT",
            "FORMAT_WIZARD", "DRAFTING", "BANNER", "GATE_CHECK",
            "QUEUE", "PUBLISHING", "ARCHIVING", "ANALYZING_POST",
            "COMPLETE_POST",
        }
        self.assertEqual(set(state_handlers.CONTENT_STATES), expected)


class TestTransition(unittest.TestCase):
    def test_valid_transition(self):
        state = {"current_state": "PUBLISHING", "loop": "CONTENT"}
        ok = state_handlers.transition(state, "ARCHIVING")
        self.assertTrue(ok)
        self.assertEqual(state["current_state"], "ARCHIVING")

    def test_invalid_transition(self):
        state = {"current_state": "IDLE", "loop": "CONTENT"}
        ok = state_handlers.transition(state, "ARCHIVING")
        self.assertFalse(ok)


class TestResolveDraftId(unittest.TestCase):
    def setUp(self):
        self.tmp = Path("/tmp/test_resolve_draft_xyz")
        self.tmp.mkdir(exist_ok=True)

    def tearDown(self):
        for f in self.tmp.glob("*.md"):
            f.unlink()
        self.tmp.rmdir()

    def test_resolve_filename(self):
        with patch("state_handlers.QUEUE_DIR", self.tmp):
            write_frontmatter(self.tmp / "test.md", {"title": "T"}, "body")
            result = state_handlers._resolve_draft_id("test.md")
            self.assertEqual(result, self.tmp / "test.md")

    def test_resolve_stem(self):
        with patch("state_handlers.QUEUE_DIR", self.tmp):
            write_frontmatter(self.tmp / "test.md", {"title": "T"}, "body")
            result = state_handlers._resolve_draft_id("test")
            self.assertEqual(result, self.tmp / "test.md")

    def test_resolve_not_found(self):
        with patch("state_handlers.QUEUE_DIR", self.tmp):
            result = state_handlers._resolve_draft_id("nonexistent.md")
            self.assertIsNone(result)

    def test_resolve_short_ref(self):
        with patch("state_handlers.QUEUE_DIR", self.tmp):
            write_frontmatter(self.tmp / "a.md", {"title": "A"}, "a")
            write_frontmatter(self.tmp / "b.md", {"title": "B"}, "b")
            result = state_handlers._resolve_draft_id("2")
            self.assertEqual(result.name, "b.md")


class TestOnPublish(unittest.TestCase):
    def setUp(self):
        self.tmp_queue = Path("/tmp/test_on_publish_queue_xyz")
        self.tmp_posted = Path("/tmp/test_on_publish_posted_xyz")
        self.tmp_queue.mkdir(exist_ok=True)
        self.tmp_posted.mkdir(exist_ok=True)

    def tearDown(self):
        for d in (self.tmp_queue, self.tmp_posted):
            for f in d.glob("*.md"):
                f.unlink()
            d.rmdir()

    def test_publish_specific(self):
        write_frontmatter(self.tmp_queue / "x.md", {"title": "T", "platform": "x"}, "body")
        state = {"current_state": "QUEUE", "loop": "CONTENT"}
        with patch("state_handlers.QUEUE_DIR", self.tmp_queue):
            with patch("engine_state.POSTED_DIR", self.tmp_posted):
                with patch("publish_dispatcher.dispatch_publish") as mock_d:
                    mock_d.return_value = {
                        "ok": True,
                        "post_ids": {"x": "123"},
                        "urls": {"x": "https://x.com/x"},
                        "archived": self.tmp_posted / "x.md",
                        "skipped": False,
                        "reason": "",
                    }
                    result = state_handlers.on_publish(state, "x.md", dry_run=True, auto_confirm=True)
                    self.assertEqual(result, 0)
                    mock_d.assert_called_once()

    def test_publish_missing_draft(self):
        state = {"current_state": "QUEUE", "loop": "CONTENT"}
        with patch("state_handlers.QUEUE_DIR", self.tmp_queue):
            result = state_handlers.on_publish(state, "nonexistent.md", dry_run=True, auto_confirm=True)
            self.assertEqual(result, 1)

    def test_publish_bulk_all_hold(self):
        write_frontmatter(self.tmp_queue / "a.md", {"title": "A", "platform": "x"}, "a")
        state = {"current_state": "QUEUE", "loop": "CONTENT"}
        with patch("state_handlers.QUEUE_DIR", self.tmp_queue):
            with patch("engine_state.POSTED_DIR", self.tmp_posted):
                result = state_handlers.on_publish(
                    state,
                    None,
                    dry_run=True,
                    auto_confirm=True,
                    decisions={"a.md": "hold"},
                )
                self.assertEqual(result, 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
