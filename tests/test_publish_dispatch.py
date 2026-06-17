#!/usr/bin/env python3
"""test_publish_dispatch.py — Tests for the publish dispatcher."""

import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import publish_dispatcher as dispatch
from engine_state import QUEUE_DIR
from engine_frontmatter import write_frontmatter


class TestPlatformOf(unittest.TestCase):
    def test_from_frontmatter(self):
        p = Path("/tmp/whatever.md")
        write_frontmatter(p, {"platform": "x"}, "")
        self.assertEqual(dispatch._platform_of(p), "x")

    def test_from_filename_x(self):
        p = Path("/tmp/2026-06-17-x-foo.md")
        p.write_text("")
        self.assertEqual(dispatch._platform_of(p), "x")

    def test_from_filename_linkedin(self):
        p = Path("/tmp/2026-06-17-linkedin-foo.md")
        p.write_text("")
        self.assertEqual(dispatch._platform_of(p), "linkedin")

    def test_from_filename_blog(self):
        p = Path("/tmp/2026-06-17-pillar-foo.md")
        p.write_text("")
        self.assertEqual(dispatch._platform_of(p), "blog")

    def test_unknown(self):
        p = Path("/tmp/2026-06-17-random.md")
        p.write_text("---\ntitle: T\n---\nbody")
        self.assertEqual(dispatch._platform_of(p), "")


class TestRoute(unittest.TestCase):
    def test_x(self):
        self.assertEqual(dispatch._route("x"), "publishers.buffer")
        self.assertEqual(dispatch._route("twitter"), "publishers.buffer")

    def test_linkedin(self):
        self.assertEqual(dispatch._route("linkedin"), "publishers.buffer")

    def test_blog(self):
        self.assertEqual(dispatch._route("blog"), "publishers.blog")
        self.assertEqual(dispatch._route("pillar"), "publishers.blog")

    def test_buffer(self):
        self.assertEqual(dispatch._route("buffer"), "publishers.buffer")

    def test_unknown(self):
        self.assertEqual(dispatch._route("unknown_platform"), "")


class TestNormalizeBufferResults(unittest.TestCase):
    def test_x_result(self):
        results = [{"service": "twitter", "update_id": "abc", "url": "https://x.com/foo"}]
        post_ids, urls = dispatch._normalize_buffer_results(results)
        self.assertEqual(post_ids.get("x"), "abc")
        self.assertEqual(urls.get("x"), "https://x.com/foo")

    def test_linkedin_result(self):
        results = [{"service": "linkedin-page", "update_id": "def", "url": "https://linkedin.com/posts/abc"}]
        post_ids, urls = dispatch._normalize_buffer_results(results)
        self.assertEqual(post_ids.get("linkedin"), "def")

    def test_threads_result(self):
        results = [{"service": "threads", "update_id": "ghi", "url": "https://threads.net/@user/post/abc"}]
        post_ids, urls = dispatch._normalize_buffer_results(results)
        self.assertEqual(post_ids.get("threads"), "ghi")

    def test_empty(self):
        post_ids, urls = dispatch._normalize_buffer_results([])
        self.assertEqual(post_ids, {})
        self.assertEqual(urls, {})

    def test_none(self):
        post_ids, urls = dispatch._normalize_buffer_results(None)
        self.assertEqual(post_ids, {})


class TestSingleResult(unittest.TestCase):
    def test_x(self):
        post_ids, urls = dispatch._single_result({"id": "abc", "url": "https://x.com/x"}, "x")
        self.assertEqual(post_ids["x"], "abc")
        self.assertEqual(urls["x"], "https://x.com/x")

    def test_linkedin(self):
        post_ids, urls = dispatch._single_result({"id": "urn:li:share:123", "url": "https://linkedin.com/posts/abc"}, "linkedin")
        self.assertEqual(post_ids["linkedin"], "urn:li:share:123")

    def test_blog(self):
        post_ids, urls = dispatch._single_result({"url": "https://blog.com/post"}, "blog")
        self.assertEqual(urls.get("blog"), "https://blog.com/post")

    def test_empty_dict(self):
        post_ids, urls = dispatch._single_result({}, "x")
        self.assertEqual(post_ids, {})
        self.assertEqual(urls, {})


class TestDispatchPublish(unittest.TestCase):
    def setUp(self):
        self.tmp_queue = Path("/tmp/test_dispatch_queue_xyz")
        self.tmp_posted = Path("/tmp/test_dispatch_posted_xyz")
        self.tmp_queue.mkdir(exist_ok=True)
        self.tmp_posted.mkdir(exist_ok=True)

    def tearDown(self):
        for d in (self.tmp_queue, self.tmp_posted):
            for f in d.glob("*.md"):
                f.unlink()
            d.rmdir()

    def test_missing_file(self):
        result = dispatch.dispatch_publish(
            self.tmp_queue / "missing.md",
            queue_dir=self.tmp_queue,
            posted_dir=self.tmp_posted,
            dry_run=True,
            skip_cadence=True,
        )
        self.assertFalse(result["ok"])
        self.assertIn("not found", result["reason"])

    def test_wrong_dir(self):
        wrong = Path("/tmp/test_dispatch_wrong.md")
        wrong.write_text("---\nplatform: x\n---\nbody")
        try:
            result = dispatch.dispatch_publish(
                wrong,
                queue_dir=self.tmp_queue,
                posted_dir=self.tmp_posted,
                dry_run=True,
                skip_cadence=True,
            )
            self.assertFalse(result["ok"])
            self.assertIn("must be in", result["reason"])
        finally:
            wrong.unlink()

    def test_unknown_platform(self):
        d = self.tmp_queue / "x.md"
        d.write_text("---\ntitle: T\n---\nbody")
        result = dispatch.dispatch_publish(
            d,
            queue_dir=self.tmp_queue,
            posted_dir=self.tmp_posted,
            dry_run=True,
            skip_cadence=True,
        )
        self.assertFalse(result["ok"])
        self.assertIn("platform", result["reason"])

    def test_dry_run_passes(self):
        d = self.tmp_queue / "x.md"
        write_frontmatter(d, {"title": "T", "platform": "x"}, "body")
        with patch("publish_dispatcher._import_publisher") as mock_imp:
            mock_pub = mock_imp.return_value
            mock_pub.publish.return_value = {"id": "123", "url": "https://x.com/x"}
            result = dispatch.dispatch_publish(
                d,
                queue_dir=self.tmp_queue,
                posted_dir=self.tmp_posted,
                dry_run=True,
                skip_cadence=True,
                auto_confirm=True,
            )
            self.assertTrue(result["ok"])
            self.assertEqual(result["reason"], "dry-run")
            self.assertEqual(result["post_ids"].get("x"), "123")
            self.assertTrue(d.exists())

    def test_successful_publish_archives(self):
        d = self.tmp_queue / "x.md"
        write_frontmatter(d, {"title": "T", "platform": "x"}, "body")
        with patch("publish_dispatcher._import_publisher") as mock_imp:
            mock_pub = mock_imp.return_value
            mock_pub.publish.return_value = {"id": "123", "url": "https://x.com/x"}
            result = dispatch.dispatch_publish(
                d,
                queue_dir=self.tmp_queue,
                posted_dir=self.tmp_posted,
                dry_run=False,
                skip_cadence=True,
                auto_confirm=True,
            )
            self.assertTrue(result["ok"], msg=f"reason: {result['reason']}")
            self.assertTrue(d.exists() is False or result.get("archived"))
            self.assertEqual(result["post_ids"].get("x"), "123")
            self.assertIsNotNone(result["archived"])


class TestDispatchBulk(unittest.TestCase):
    def setUp(self):
        self.tmp = Path("/tmp/test_dispatch_bulk_xyz")
        self.tmp.mkdir(exist_ok=True)

    def tearDown(self):
        for f in self.tmp.glob("*.md"):
            f.unlink()
        self.tmp.rmdir()

    def test_bulk_no_decisions(self):
        write_frontmatter(self.tmp / "a.md", {"title": "A", "platform": "x"}, "a")
        write_frontmatter(self.tmp / "b.md", {"title": "B", "platform": "linkedin"}, "b")
        with patch("publish_dispatcher._import_publisher") as mock_imp:
            mock_pub = mock_imp.return_value
            mock_pub.publish.return_value = {"id": "1", "url": "https://x.com/1"}
            summary = dispatch.dispatch_bulk(
                self.tmp,
                decisions=None,
                dry_run=True,
                skip_cadence=True,
            )
            self.assertEqual(len(summary["published"]), 2)

    def test_bulk_with_decisions(self):
        write_frontmatter(self.tmp / "a.md", {"title": "A", "platform": "x"}, "a")
        write_frontmatter(self.tmp / "b.md", {"title": "B", "platform": "x"}, "b")
        with patch("publish_dispatcher._import_publisher") as mock_imp:
            mock_pub = mock_imp.return_value
            mock_pub.publish.return_value = {"id": "1", "url": "https://x.com/1"}
            summary = dispatch.dispatch_bulk(
                self.tmp,
                decisions={"a.md": "publish", "b.md": "hold"},
                dry_run=True,
                skip_cadence=True,
            )
            self.assertEqual(len(summary["published"]), 1)
            self.assertEqual(len(summary["held"]), 1)


class TestDispatchError(unittest.TestCase):
    def test_raises(self):
        with self.assertRaises(dispatch.DispatchError):
            raise dispatch.DispatchError("test")


if __name__ == "__main__":
    unittest.main(verbosity=2)
