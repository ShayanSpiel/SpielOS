#!/usr/bin/env python3
"""test_archive.py — Tests for the archive + verify modules."""

import json
import sys
import unittest
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import archive
import verify
from engine_state import POSTED_DIR, QUEUE_DIR
from engine_frontmatter import write_frontmatter, parse_frontmatter


class TestArchiveDraft(unittest.TestCase):
    def setUp(self):
        self.tmp_queue = Path("/tmp/test_archive_queue_xyz")
        self.tmp_posted = Path("/tmp/test_archive_posted_xyz")
        self.tmp_queue.mkdir(exist_ok=True)
        self.tmp_posted.mkdir(exist_ok=True)

    def tearDown(self):
        for d in (self.tmp_queue, self.tmp_posted):
            for f in d.glob("*.md"):
                f.unlink()
            d.rmdir()

    def test_basic_move(self):
        draft = self.tmp_queue / "test.md"
        write_frontmatter(draft, {"title": "T", "platform": "x", "status": "draft"}, "body")
        original_content = draft.read_text()
        result = archive.archive_draft(draft, posted_dir=self.tmp_posted, queue_dir=self.tmp_queue)
        self.assertTrue(result.exists())
        self.assertEqual(result.parent, self.tmp_posted)
        self.assertFalse(draft.exists())

    def test_posted_at_added(self):
        draft = self.tmp_queue / "test.md"
        write_frontmatter(draft, {"title": "T", "platform": "x"}, "body")
        result = archive.archive_draft(draft, posted_dir=self.tmp_posted, queue_dir=self.tmp_queue)
        fm, _ = parse_frontmatter(result.read_text())
        self.assertIn("posted_at", fm)
        self.assertIsNotNone(fm["posted_at"])

    def test_post_ids_added(self):
        draft = self.tmp_queue / "test.md"
        write_frontmatter(draft, {"title": "T", "platform": "x"}, "body")
        result = archive.archive_draft(
            draft,
            posted_dir=self.tmp_posted,
            queue_dir=self.tmp_queue,
            post_ids={"x": "tweet_123", "linkedin": "share_456"},
        )
        fm, _ = parse_frontmatter(result.read_text())
        self.assertEqual(fm.get("tweet_id"), "tweet_123")
        self.assertEqual(fm.get("linkedin_share_urn"), "share_456")
        self.assertEqual(fm.get("buffer_post_ids", {}).get("x"), "tweet_123")

    def test_urls_added(self):
        draft = self.tmp_queue / "test.md"
        write_frontmatter(draft, {"title": "T", "platform": "x"}, "body")
        result = archive.archive_draft(
            draft,
            posted_dir=self.tmp_posted,
            queue_dir=self.tmp_queue,
            urls={"x": "https://x.com/foo/status/123"},
        )
        fm, _ = parse_frontmatter(result.read_text())
        self.assertEqual(fm.get("tweet_url"), "https://x.com/foo/status/123")

    def test_engagement_field_initialized(self):
        draft = self.tmp_queue / "test.md"
        write_frontmatter(draft, {"title": "T", "platform": "x"}, "body")
        result = archive.archive_draft(draft, posted_dir=self.tmp_posted, queue_dir=self.tmp_queue)
        fm, _ = parse_frontmatter(result.read_text())
        self.assertIn("engagement", fm)
        self.assertEqual(fm["engagement"]["reactions"], 0)
        self.assertIsNone(fm["engagement"]["fetched_at"])

    def test_existing_posted_at_preserved(self):
        draft = self.tmp_queue / "test.md"
        write_frontmatter(draft, {"title": "T", "platform": "x"}, "body")
        ts = "2026-06-17T03:00:00"
        result = archive.archive_draft(
            draft,
            posted_dir=self.tmp_posted,
            queue_dir=self.tmp_queue,
            posted_at=ts,
        )
        fm, _ = parse_frontmatter(result.read_text())
        self.assertEqual(fm.get("posted_at"), ts)

    def test_duplicate_filename_gets_suffix(self):
        write_frontmatter(self.tmp_posted / "test.md", {"title": "existing", "platform": "x"}, "old body")
        draft = self.tmp_queue / "test.md"
        write_frontmatter(draft, {"title": "T", "platform": "x"}, "new body")
        result = archive.archive_draft(draft, posted_dir=self.tmp_posted, queue_dir=self.tmp_queue)
        self.assertNotEqual(result.name, "test.md")
        self.assertTrue(result.name.startswith("test-"))

    def test_missing_file_raises(self):
        with self.assertRaises(archive.ArchiveError):
            archive.archive_draft(
                self.tmp_queue / "nonexistent.md",
                posted_dir=self.tmp_posted,
                queue_dir=self.tmp_queue,
            )


class TestVerifyArchive(unittest.TestCase):
    def setUp(self):
        self.tmp_queue = Path("/tmp/test_verify_queue_xyz")
        self.tmp_posted = Path("/tmp/test_verify_posted_xyz")
        self.tmp_queue.mkdir(exist_ok=True)
        self.tmp_posted.mkdir(exist_ok=True)

    def tearDown(self):
        for d in (self.tmp_queue, self.tmp_posted):
            for f in d.glob("*.md"):
                f.unlink()
            d.rmdir()

    def test_all_pass(self):
        original = self.tmp_queue / "ok.md"
        write_frontmatter(self.tmp_posted / "ok.md",
                          {"title": "T", "platform": "x", "posted_at": "2026-06-17T03:00:00"},
                          "body")
        checks = verify.verify_archive(
            original,
            self.tmp_posted / "ok.md",
            queue_dir=self.tmp_queue,
            posted_dir=self.tmp_posted,
        )
        for k, v in checks.items():
            self.assertTrue(v, f"{k} should pass")

    def test_original_gone(self):
        original = self.tmp_queue / "still_here.md"
        original.write_text("placeholder")
        write_frontmatter(self.tmp_posted / "still_here.md",
                          {"title": "T", "platform": "x", "posted_at": "2026-06-17T03:00:00"},
                          "body")
        checks = verify.verify_archive(
            original,
            self.tmp_posted / "still_here.md",
            queue_dir=self.tmp_queue,
            posted_dir=self.tmp_posted,
        )
        self.assertFalse(checks["original_gone"])

    def test_archived_exists(self):
        checks = verify.verify_archive(
            self.tmp_queue / "x.md",
            self.tmp_posted / "missing.md",
            queue_dir=self.tmp_queue,
            posted_dir=self.tmp_posted,
        )
        self.assertFalse(checks["archived_exists"])

    def test_in_posted_dir(self):
        write_frontmatter(self.tmp_queue / "x.md",
                          {"title": "T", "platform": "x", "posted_at": "now"},
                          "body")
        checks = verify.verify_archive(
            self.tmp_queue / "x.md",
            self.tmp_queue / "x.md",
            queue_dir=self.tmp_queue,
            posted_dir=self.tmp_posted,
        )
        self.assertFalse(checks["in_posted_dir"])

    def test_has_posted_at(self):
        write_frontmatter(self.tmp_posted / "x.md", {"title": "T", "platform": "x"}, "body")
        original = self.tmp_queue / "x.md"
        original.write_text("placeholder")
        checks = verify.verify_archive(
            original,
            self.tmp_posted / "x.md",
            queue_dir=self.tmp_queue,
            posted_dir=self.tmp_posted,
        )
        self.assertFalse(checks["has_posted_at"])

    def test_format_results(self):
        checks = {"a": True, "b": False}
        out = verify.format_results(checks)
        self.assertIn("✓", out)
        self.assertIn("✗", out)
        self.assertIn("a", out)
        self.assertIn("b", out)


class TestArchiveError(unittest.TestCase):
    def test_raises(self):
        with self.assertRaises(archive.ArchiveError):
            raise archive.ArchiveError("test error")


if __name__ == "__main__":
    unittest.main(verbosity=2)
