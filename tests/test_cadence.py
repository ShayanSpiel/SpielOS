#!/usr/bin/env python3
"""test_cadence.py — Tests for the per-platform posting rate limiter."""

import json
import sys
import unittest
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import cadence
from engine_frontmatter import write_frontmatter


class TestCadenceCounts(unittest.TestCase):
    def test_empty_posted_dir(self):
        empty = Path("/tmp/test_cadence_empty_xyz")
        empty.mkdir(exist_ok=True)
        try:
            counts = cadence._counts("x", posted_dir=empty)
            self.assertEqual(counts["today"], 0)
            self.assertEqual(counts["this_week"], 0)
        finally:
            empty.rmdir()

    def test_missing_dir(self):
        missing = Path("/tmp/does_not_exist_cadence_xyz")
        if missing.exists():
            missing.rmdir()
        counts = cadence._counts("x", posted_dir=missing)
        self.assertEqual(counts["today"], 0)


class TestCadenceCheck(unittest.TestCase):
    def setUp(self):
        self.tmp = Path("/tmp/test_cadence_run_xyz")
        self.tmp.mkdir(exist_ok=True)

    def tearDown(self):
        for f in self.tmp.glob("*.md"):
            f.unlink()
        self.tmp.rmdir()

    def test_under_limit(self):
        ok, reason = cadence.check_cadence("x", posted_dir=self.tmp)
        self.assertTrue(ok)
        self.assertEqual(reason, "")

    def test_unknown_platform_skips(self):
        ok, reason = cadence.check_cadence("unknown_platform", posted_dir=self.tmp)
        self.assertTrue(ok)

    def test_daily_limit(self):
        today = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
        for i in range(3):
            f = self.tmp / f"x-today-{i:02d}.md"
            write_frontmatter(f, {"platform": "x", "posted_at": today, "title": f"x{i}"}, "body")
        ok, reason = cadence.check_cadence("x", posted_dir=self.tmp)
        self.assertFalse(ok)
        self.assertIn("daily limit", reason)


class TestCadenceParsePostedAt(unittest.TestCase):
    def test_iso_with_time(self):
        dt = cadence._parse_posted_at("2026-06-17T03:24:21")
        self.assertIsNotNone(dt)
        self.assertEqual(dt.year, 2026)
        self.assertEqual(dt.month, 6)

    def test_iso_with_microseconds(self):
        dt = cadence._parse_posted_at("2026-06-17T03:24:21.123456")
        self.assertIsNotNone(dt)
        self.assertEqual(dt.microsecond, 123456)

    def test_date_only(self):
        dt = cadence._parse_posted_at("2026-06-17")
        self.assertIsNotNone(dt)
        self.assertEqual(dt.day, 17)

    def test_garbage(self):
        dt = cadence._parse_posted_at("not a date")
        self.assertIsNone(dt)

    def test_none(self):
        dt = cadence._parse_posted_at(None)
        self.assertIsNone(dt)

    def test_empty(self):
        dt = cadence._parse_posted_at("")
        self.assertIsNone(dt)

    def test_datetime_passthrough(self):
        original = datetime(2026, 6, 17, 12, 0, 0)
        dt = cadence._parse_posted_at(original)
        self.assertEqual(dt, original)


class TestCadenceStatus(unittest.TestCase):
    def test_returns_string(self):
        out = cadence.status()
        self.assertIsInstance(out, str)
        self.assertIn("x", out)
        self.assertIn("linkedin", out)
        self.assertIn("blog", out)


class TestPlatformOf(unittest.TestCase):
    def test_explicit_platform(self):
        plat = cadence._platform_of({"platform": "x"}, Path("anything.md"))
        self.assertEqual(plat, "x")

    def test_filename_x(self):
        plat = cadence._platform_of({}, Path("2026-06-17-x-foo.md"))
        self.assertEqual(plat, "x")

    def test_filename_linkedin(self):
        plat = cadence._platform_of({}, Path("2026-06-17-linkedin-foo.md"))
        self.assertEqual(plat, "linkedin")

    def test_filename_pillar(self):
        plat = cadence._platform_of({}, Path("2026-06-17-pillar-foo.md"))
        self.assertEqual(plat, "blog")


if __name__ == "__main__":
    unittest.main(verbosity=2)
