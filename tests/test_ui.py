#!/usr/bin/env python3
"""test_ui.py — Tests for scripts/ui.py rendering helpers.

Verifies that:
  - All functions return non-empty strings
  - Box characters are correct (Unicode when supported, ASCII fallback)
  - ANSI codes present when COLOR_ENABLED, absent when not
  - Visible-length math is right (no padding drift on color-coded text)
  - Tables, panels, headers all have matching widths
  - Ego line is centered
"""

import os
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import ui


def _visible_len(text: str) -> int:
    return len(ui.strip_ansi(text))


def _ansi_codes(text: str) -> list[str]:
    return re.findall(r"\033\[[0-9;]*m", text)


class TestHeader(unittest.TestCase):
    def test_returns_string(self):
        out = ui.header("TITLE", width=80)
        self.assertIsInstance(out, str)
        self.assertGreater(len(out), 0)

    def test_has_top_and_bottom(self):
        out = ui.header("TITLE", width=80)
        lines = out.split("\n")
        self.assertEqual(len(lines), 3)
        for line in lines:
            self.assertEqual(_visible_len(line), 80)

    def test_contains_title(self):
        out = ui.header("HELLO WORLD", width=80)
        self.assertIn("HELLO WORLD", ui.strip_ansi(out))

    def test_subtitle_renders(self):
        out = ui.header("T", subtitle="S", width=80)
        self.assertIn("S", ui.strip_ansi(out))
        self.assertEqual(len(out.split("\n")), 4)

    def test_width_respected(self):
        for w in (40, 60, 80):
            out = ui.header("T", width=w)
            for line in out.split("\n"):
                self.assertEqual(_visible_len(line), w)


class TestPanel(unittest.TestCase):
    def test_basic(self):
        out = ui.panel("TITLE", ["body line"], width=80)
        lines = out.split("\n")
        self.assertEqual(len(lines), 5)
        for line in lines:
            self.assertEqual(_visible_len(line), 80)

    def test_title_inside_separator(self):
        out = ui.panel("TITLE", ["body"], width=80, title_inside=True)
        lines = out.split("\n")
        self.assertEqual(len(lines), 5)
        self.assertIn("TITLE", ui.strip_ansi(lines[1]))

    def test_long_body_truncated(self):
        out = ui.panel("T", "x" * 200, width=40)
        for line in out.split("\n"):
            self.assertLessEqual(_visible_len(line), 40)

    def test_empty_body(self):
        out = ui.panel("T", [], width=80)
        lines = out.split("\n")
        for line in lines:
            self.assertEqual(_visible_len(line), 80)

    def test_no_title(self):
        out = ui.panel("", ["body"], width=80)
        lines = out.split("\n")
        for line in lines:
            self.assertEqual(_visible_len(line), 80)


class TestTable(unittest.TestCase):
    def test_basic_table(self):
        out = ui.table(["A", "B"], [["1", "2"], ["3", "4"]], width=80)
        lines = out.split("\n")
        self.assertEqual(len(lines), 7)
        for line in lines:
            self.assertEqual(_visible_len(line), 80)
        self.assertIn("A", ui.strip_ansi(out))
        self.assertIn("2", ui.strip_ansi(out))

    def test_empty_headers_returns_empty(self):
        self.assertEqual(ui.table([], [], width=80), "")

    def test_alignment(self):
        out = ui.table(
            ["L", "R", "C"],
            [["left", "right", "center"]],
            aligns=["left", "right", "center"],
            width=80,
        )
        plain = ui.strip_ansi(out)
        self.assertIn("left", plain)
        self.assertIn("right", plain)
        self.assertIn("center", plain)

    def test_separator_rows(self):
        out = ui.table(["A"], [["1"]], width=80)
        plain = ui.strip_ansi(out)
        self.assertTrue("═" in plain or "─" in plain or "-" in plain)
        self.assertIn("A", plain)
        self.assertIn("1", plain)


class TestRule(unittest.TestCase):
    def test_default_rule(self):
        out = ui.rule(width=80)
        plain = ui.strip_ansi(out)
        self.assertEqual(len(plain), 80)

    def test_custom_char(self):
        out = ui.rule(char="=", width=40)
        plain = ui.strip_ansi(out)
        self.assertEqual(len(plain), 40)
        self.assertTrue(all(c == "=" for c in plain))


class TestStatus(unittest.TestCase):
    def test_pass_icon(self):
        out = ui.status("pass", "all good")
        self.assertIn("✓", out)
        self.assertIn("all good", ui.strip_ansi(out))

    def test_fail_icon(self):
        out = ui.status("fail", "nope")
        self.assertIn("✗", out)

    def test_warn_icon(self):
        out = ui.status("warn", "careful")
        self.assertIn("⚠", out)

    def test_arrow_icon(self):
        out = ui.status("arrow", "next")
        self.assertIn("→", out)


class TestCopyable(unittest.TestCase):
    def test_basic(self):
        out = ui.copyable("echo hi", label="DO")
        self.assertIn("DO", out)
        self.assertIn("echo hi", out)
        self.assertIn("$", out)

    def test_multiline(self):
        out = ui.copyable("line1\nline2", label="CMD")
        self.assertIn("line1", out)
        self.assertIn("line2", out)


class TestEgo(unittest.TestCase):
    def test_returns_string(self):
        out = ui.ego("We held the line.")
        self.assertIsInstance(out, str)
        self.assertIn("We held the line.", out)

    def test_centered(self):
        out = ui.ego("short text")
        plain = ui.strip_ansi(out)
        self.assertTrue(plain.lstrip().startswith('"'))


class TestBanner(unittest.TestCase):
    def test_basic(self):
        out = ui.banner(["LINE 1", "LINE 2"], width=80)
        lines = out.split("\n")
        for line in lines:
            self.assertEqual(_visible_len(line), 80)
        self.assertIn("LINE 1", ui.strip_ansi(out))


class TestKVpairs(unittest.TestCase):
    def test_basic(self):
        out = ui.kvpairs([("a", "1"), ("longer_key", "2")])
        plain = ui.strip_ansi(out)
        self.assertIn("a", plain)
        self.assertIn("1", plain)
        self.assertIn("longer_key", plain)


class TestProgress(unittest.TestCase):
    def test_zero_total(self):
        self.assertEqual(ui.progress(0, 0), "")

    def test_full(self):
        out = ui.progress(10, 10, width=20)
        self.assertIn("100%", out)

    def test_partial(self):
        out = ui.progress(5, 10, width=20)
        self.assertIn("50%", out)


class TestDotBullet(unittest.TestCase):
    def test_basic(self):
        out = ui.dot_bullet("hello")
        self.assertIn("hello", out)


class TestVisibleLength(unittest.TestCase):
    def test_no_ansi(self):
        self.assertEqual(_visible_len("hello"), 5)

    def test_with_color(self):
        text = ui._c("hello", ui._FG["red"])
        self.assertEqual(_visible_len(text), 5)

    def test_with_bold(self):
        text = ui._c("hello", ui._BOLD, ui._FG["green"])
        self.assertEqual(_visible_len(text), 5)

    def test_padded(self):
        text = ui._c("hi", ui._BOLD)
        self.assertEqual(_visible_len(ui._pad(text, 10)), 10)


class TestColorToggle(unittest.TestCase):
    def test_disabled_color_returns_plain(self):
        original = ui.COLOR_ENABLED
        ui.COLOR_ENABLED = False
        try:
            out = ui.status("pass", "test")
            self.assertEqual(_ansi_codes(out), [])
        finally:
            ui.COLOR_ENABLED = original


class TestWidthFitting(unittest.TestCase):
    def test_cap_at_terminal(self):
        big = 500
        out = ui.header("T", width=big)
        for line in out.split("\n"):
            self.assertLessEqual(_visible_len(line), 200)


if __name__ == "__main__":
    unittest.main(verbosity=2)
