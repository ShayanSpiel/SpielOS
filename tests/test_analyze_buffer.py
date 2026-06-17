#!/usr/bin/env python3
"""test_buffer_client.py + test_analyze.py combined."""

import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import buffer_client
import analyze


class TestBufferConfig(unittest.TestCase):
    def test_load_config_empty(self):
        with patch.dict("os.environ", {}, clear=True):
            with patch("buffer_client._read_dotenv_for", return_value={}):
                cfg = buffer_client.load_config()
        self.assertIsInstance(cfg, dict)

    def test_is_configured_false(self):
        with patch.dict("os.environ", {}, clear=True):
            with patch("buffer_client._read_dotenv_for", return_value={}):
                self.assertFalse(buffer_client.is_configured())

    def test_is_configured_true(self):
        with patch.dict("os.environ", {"BUFFER_ACCESS_TOKEN": "test"}):
            self.assertTrue(buffer_client.is_configured())

    def test_parse_channel_ids(self):
        self.assertEqual(
            buffer_client.parse_channel_ids("a,b,c"),
            ["a", "b", "c"],
        )
        self.assertEqual(buffer_client.parse_channel_ids(""), [])
        self.assertEqual(buffer_client.parse_channel_ids("  a , b  "), ["a", "b"])


class TestBufferAggregate(unittest.TestCase):
    def test_empty(self):
        result = buffer_client.aggregate_metrics({})
        self.assertEqual(result["reactions"], 0)
        self.assertEqual(result["rate"], 0.0)

    def test_aggregate(self):
        per = {
            "x": {"reactions": 10, "comments": 5, "reposts": 2, "impressions": 1000, "engagements": 17},
            "linkedin": {"reactions": 20, "comments": 3, "reposts": 1, "impressions": 500, "engagements": 24},
        }
        result = buffer_client.aggregate_metrics(per)
        self.assertEqual(result["reactions"], 30)
        self.assertEqual(result["comments"], 8)
        self.assertEqual(result["reposts"], 3)
        self.assertEqual(result["impressions"], 1500)
        self.assertEqual(result["engagements"], 41)
        self.assertAlmostEqual(result["rate"], 41 / 1500, places=5)

    def test_aggregate_skips_errors(self):
        per = {
            "x": {"error": "auth failed"},
            "linkedin": {"reactions": 10, "impressions": 100, "engagements": 12},
        }
        result = buffer_client.aggregate_metrics(per)
        self.assertEqual(result["reactions"], 10)


class TestBufferFetchInteractions(unittest.TestCase):
    def test_returns_error_dict_on_failure(self):
        with patch("buffer_client._graphql_request") as mock_req:
            mock_req.side_effect = RuntimeError("network")
            result = buffer_client.fetch_interactions("token", "update_123")
        self.assertIn("error", result)


class TestBufferFetchForPost(unittest.TestCase):
    def test_empty_post_ids(self):
        result = buffer_client.fetch_for_post("token", {})
        self.assertEqual(result["aggregate"]["reactions"], 0)

    def test_with_post_ids(self):
        with patch("buffer_client.fetch_interactions") as mock:
            mock.return_value = {"reactions": 10, "comments": 2, "reposts": 1, "impressions": 100, "engagements": 13}
            result = buffer_client.fetch_for_post("token", {"x": "u1", "linkedin": "u2"})
        self.assertEqual(result["aggregate"]["reactions"], 20)


class TestAnalyzeHelpers(unittest.TestCase):
    def test_normalize_perf(self):
        perf = {
            "by_template": {
                "x-listicle-01": {
                    "posts": 5,
                    "total_impressions": 1000,
                    "total_engagements": 50,
                    "rates": [0.05, 0.04, 0.06, 0.05, 0.05],
                }
            }
        }
        flat = analyze.normalize_perf(perf)
        self.assertEqual(flat["x-listicle-01"]["posts"], 5)
        self.assertEqual(flat["x-listicle-01"]["avg_rate"], 0.05)
        self.assertGreater(flat["x-listicle-01"]["last_30d_rate"], 0)

    def test_normalize_empty(self):
        flat = analyze.normalize_perf({})
        self.assertEqual(flat, {})


class TestAnalyzeAll(unittest.TestCase):
    def test_no_token(self):
        with patch.dict("os.environ", {}, clear=True):
            with patch("buffer_client.load_config") as mock_cfg:
                mock_cfg.return_value = {}
                result = analyze.analyze_all(
                    posted_dir=Path("/tmp/test_analyze_no_token_xyz"),
                    re_rank=False,
                )
        self.assertFalse(result["ok"])
        self.assertTrue(result.get("skipped"))

    def test_no_posted_dir(self):
        with patch.dict("os.environ", {"BUFFER_ACCESS_TOKEN": "test"}):
            missing = Path("/tmp/does_not_exist_analyze_xyz")
            if missing.exists():
                missing.rmdir()
            result = analyze.analyze_all(
                posted_dir=missing,
                re_rank=False,
            )
        self.assertFalse(result["ok"])


class TestAnalyzeOne(unittest.TestCase):
    def test_skipped_when_not_posted(self):
        with patch.dict("os.environ", {"BUFFER_ACCESS_TOKEN": "test"}):
            d = Path("/tmp/test_analyze_not_posted.md")
            d.write_text("---\ntitle: T\n---\nbody")
            try:
                result = analyze.analyze_one(d, "test", {})
                self.assertFalse(result["ok"])
                self.assertIn("posted", result.get("error", ""))
            finally:
                d.unlink()

    def test_skipped_no_post_ids(self):
        with patch.dict("os.environ", {"BUFFER_ACCESS_TOKEN": "test"}):
            d = Path("/tmp/test_analyze_no_ids.md")
            d.write_text("---\ntitle: T\nplatform: x\nposted_at: 2026-06-17\n---\nbody")
            try:
                result = analyze.analyze_one(d, "test", {})
                self.assertFalse(result["ok"])
                self.assertIn("post_ids", result.get("error", ""))
            finally:
                d.unlink()


if __name__ == "__main__":
    unittest.main(verbosity=2)
