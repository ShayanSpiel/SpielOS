import io
import os
import json
import re
import unittest
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from company.connections.buffer import (
    BufferClient, BufferError, _content_matches, _env_values, _metrics_campaign_report,
    _post_metrics, _publication_input, _public_https_url, _queue_report, commitment_type,
    content_fingerprint, dispatch, main, metric_staleness,
)
from company.runtime.campaign_contract import apply_render_report, approve_rendered_campaign
from company.departments.design.department import accept_design_order, render_report
from company.tests.test_campaign_handoff_contract import campaign_manifest


def _approved_buffer_package() -> dict:
    """One fully approved 10-post Buffer handoff used by dispatch tests."""
    designed = accept_design_order(campaign_manifest())
    assets = [
        {"item_id": item["item_id"], "platform": platform,
         "type": "image" if platform == "threads" else "video",
         "local_path": "asset", "sha256": "sha", "render_report_id": "render"}
        for item in designed["items"] for platform in ("threads", "youtube")
    ]
    rendered = apply_render_report(designed, render_report(designed, assets))
    approved = approve_rendered_campaign(rendered, [
        {"item_id": item["item_id"], "platform": platform, "status": "approved",
         "approval_id": f"batch-review-{item['item_id']}-{platform}",
         "public_url": f"https://spielos.xyz/campaign-assets/batch/{item['item_id']}-{platform}"}
        for item in rendered["items"] for platform in ("threads", "youtube")
    ])
    return _publication_input({"campaign_manifest": approved, "review_required": True})


class BufferConnectionTests(unittest.TestCase):
    def test_dotenv_parser_never_executes_shell_syntax(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / ".env"
            path.write_text("BUFFER_API_KEY='safe-token'\nBAD $(echo nope)\n")
            self.assertEqual({"BUFFER_API_KEY": "safe-token"}, _env_values(path))

    def test_media_requires_public_https_url(self):
        self.assertEqual("https://cdn.example.com/video.mp4", _public_https_url("https://cdn.example.com/video.mp4"))
        for value in ("http://cdn.example.com/a.jpg", "https://localhost/a.jpg", "https://127.0.0.1/a.jpg"):
            with self.assertRaises(BufferError):
                _public_https_url(value)

    @patch.dict(os.environ, {"BUFFER_API_KEY": "test-token", "BUFFER_ORGANIZATION_ID": "org-1"}, clear=False)
    def test_draft_mutation_and_rate_headers(self):
        client = BufferClient()
        seen = {}
        def fake_graphql(query):
            seen["query"] = query
            client.last_rate_limits = {"x-ratelimit-remaining": "99"}
            return {"createPost": {"post": {"id": "post-1", "status": "draft"}}}
        client.graphql = fake_graphql
        post = client.create_post(channel_id="channel-1", text="check", mode="draft")
        self.assertEqual("post-1", post["id"])
        self.assertIn("saveToDraft: true", seen["query"])
        self.assertEqual("99", client.last_rate_limits["x-ratelimit-remaining"])

    @patch.dict(os.environ, {"BUFFER_API_KEY": "test-token"}, clear=False)
    def test_caption_normalizes_literal_line_break_markers_before_graphql(self):
        client = BufferClient()
        seen = {}

        def fake_graphql(query):
            seen["query"] = query
            return {"createPost": {"post": {"id": "post-1", "status": "draft"}}}

        client.graphql = fake_graphql
        client.create_post(channel_id="channel-1", text=r"First paragraph\n\n• one\n• two", mode="draft")
        serialized = re.search(r"text: (.*?), channelId:", seen["query"]).group(1)
        self.assertEqual("First paragraph\n\n• one\n• two", json.loads(serialized))

    @patch.dict(os.environ, {"BUFFER_API_KEY": "test-token"}, clear=False)
    def test_youtube_metadata_emitted_with_title_and_category(self):
        client = BufferClient()
        seen = {}

        def fake_graphql(query):
            seen["query"] = query
            return {"createPost": {"post": {"id": "post-yt", "status": "draft"}}}

        client.graphql = fake_graphql
        client.create_post(channel_id="channel-yt", text="check", mode="draft",
                           metadata={"youtube": {"title": "One clear workflow.", "categoryId": "28"}})
        self.assertIn('metadata: { youtube: { title: "One clear workflow.", categoryId: "28" } }',
                      seen["query"])

    @patch.dict(os.environ, {"BUFFER_API_KEY": "test-token"}, clear=False)
    def test_youtube_metadata_requires_title_and_category(self):
        client = BufferClient()
        client.graphql = lambda query: {"createPost": {"post": {"id": "post-yt", "status": "draft"}}}
        with self.assertRaisesRegex(BufferError, "title and categoryId"):
            client.create_post(channel_id="channel-yt", text="check", mode="draft",
                               metadata={"youtube": {"title": "  ", "categoryId": "28"}})
        with self.assertRaisesRegex(BufferError, "title and categoryId"):
            client.create_post(channel_id="channel-yt", text="check", mode="draft",
                               metadata={"youtube": {"title": "One clear workflow."}})

    @patch.dict(os.environ, {"BUFFER_API_KEY": "test-token"}, clear=False)
    def test_private_asset_rejected_before_request(self):
        client = BufferClient()
        with self.assertRaises(BufferError):
            client.create_post(channel_id="channel-1", text="check", assets=[{"type": "video", "url": "https://10.0.0.1/a.mp4"}])

    def test_hosted_approved_batch_handoff_becomes_buffer_package(self):
        designed = accept_design_order(campaign_manifest())
        assets = [
            {"item_id": item["item_id"], "platform": platform,
             "type": "image" if platform == "threads" else "video",
             "local_path": "asset", "sha256": "sha", "render_report_id": "render"}
            for item in designed["items"] for platform in ("threads", "youtube")
        ]
        rendered = apply_render_report(designed, render_report(designed, assets))
        approved = approve_rendered_campaign(rendered, [
            {"item_id": item["item_id"], "platform": platform, "status": "approved",
             "approval_id": f"batch-review-{item['item_id']}-{platform}",
             "public_url": f"https://spielos.xyz/campaign-assets/batch/{item['item_id']}-{platform}"}
            for item in rendered["items"] for platform in ("threads", "youtube")
        ])
        package = _publication_input({"campaign_manifest": approved, "review_required": True})
        self.assertEqual(10, len(package["posts"]))
        self.assertTrue(all(item["approval_id"].startswith("batch-review-") for item in package["posts"]))
        for item in package["posts"]:
            if item["platform"] == "youtube":
                # YouTube title is the joined design.title_lines of the item
                self.assertTrue(item["metadata"]["youtube"]["title"].endswith(
                    " ".join(next(i["renditions"]["youtube"]["design"]["title_lines"]
                                  for i in approved["items"] if i["item_id"] == item["item_id"]))),
                    f"unexpected YouTube title for {item['item_id']}")
                self.assertEqual("28", item["metadata"]["youtube"]["categoryId"])
            else:
                self.assertIsNone(item.get("metadata"))

    def test_rendered_batch_cannot_bypass_approval(self):
        with self.assertRaisesRegex(BufferError, "hosted approved"):
            _publication_input({"campaign_manifest": {"phase": "rendered"}, "review_required": True})

    def test_post_metrics_returns_measurement_without_post_copy(self):
        client = object.__new__(BufferClient)
        client.last_rate_limits = {"x-ratelimit-remaining": "98"}
        client.post = lambda post_id: {
            "id": post_id, "text": "must not leak into metrics output",
            "channelId": "channel-1", "dueAt": "2026-08-13T01:33:00Z",
            "status": "sent", "metrics": [{"name": "views", "value": 42}],
            "metricsUpdatedAt": "2026-08-14T08:00:00Z",
        }

        result = _post_metrics(client, ["post-1"])

        self.assertTrue(result["ok"])
        self.assertEqual(42, result["posts"][0]["metrics"][0]["value"])
        self.assertNotIn("text", result["posts"][0])
        self.assertEqual("98", result["rate_limits"]["x-ratelimit-remaining"])

    # ── pre-dispatch duplicate guard ────────────────────────────────────────

    @patch.dict(os.environ, {"BUFFER_API_KEY": "test-token"}, clear=False)
    def test_duplicate_guard_blocks_with_zero_creation(self):
        package = _approved_buffer_package()
        target = package["posts"][0]
        queue_post = {
            "id": "existing-1", "status": "scheduled",
            "channelId": f"channel-{target['platform']}", "text": target["text"],
            "assets": [{"source": target["assets"][0]["url"]}],
        }
        client = BufferClient()
        client.channel = lambda service: {"id": f"channel-{service}", "service": service}
        client.queue_posts = lambda ids: [queue_post]
        client.available_capacity = lambda ids: {cid: None for cid in ids}
        client.create_post = lambda **kwargs: (_ for _ in ()).throw(
            AssertionError("guard must abort before create_post"))
        client.posting_limits = lambda ids: []

        result = dispatch(package, "live", client=client)

        self.assertFalse(result["ok"])
        self.assertEqual("blocked", result["duplicate_guard"])
        self.assertEqual(["existing-1"], result["existing_post_ids"])
        self.assertEqual(1, len(result["matches"]))
        self.assertEqual(target["item_id"], result["matches"][0]["item_id"])
        self.assertNotIn("delivery_receipts", result)
        self.assertNotIn("posts", result)

    @patch.dict(os.environ, {"BUFFER_API_KEY": "test-token"}, clear=False)
    def test_fresh_dispatch_allowed_when_queue_has_no_match(self):
        package = _approved_buffer_package()
        count = len(package["posts"])
        client = BufferClient()
        client.channel = lambda service: {"id": f"channel-{service}", "service": service}
        client.queue_posts = lambda ids: []
        client.available_capacity = lambda ids: {cid: None for cid in ids}
        created = iter([{"id": f"post-{i}", "status": "scheduled"} for i in range(count)])
        client.create_post = lambda **kwargs: next(created)
        client.posting_limits = lambda ids: []

        result = dispatch(package, "live", client=client)

        self.assertTrue(result["ok"])
        self.assertEqual(count, len(result["delivery_receipts"]))
        self.assertTrue(all(item["commitment_type"] == "scheduled"
                            for item in result["delivery_receipts"]))
        self.assertTrue(all(item["provider_post_id"] for item in result["delivery_receipts"]))
        self.assertTrue(all(item["verified"] for item in result["delivery_receipts"]))

    def test_fingerprint_normalization_ignores_whitespace_and_newlines(self):
        item = {"text": "First  paragraph\n\nSecond\tline", "creative_signature": "sig-1",
                "assets": [{"url": "https://cdn.example.com/a.png"}]}
        same = {"text": "First paragraph\nSecond line", "creative_signature": "sig-1",
                "assets": [{"source": "https://cdn.example.com/a.png"}]}
        other_media = {"text": "First paragraph\nSecond line", "creative_signature": "sig-1",
                       "assets": [{"source": "https://cdn.example.com/other.png"}]}
        self.assertEqual(content_fingerprint(item), content_fingerprint(same))
        self.assertTrue(_content_matches(item, same))
        self.assertFalse(_content_matches(item, other_media))

    # ── receipt commitment semantics ────────────────────────────────────────

    def test_commitment_type_accepts_only_scheduled_and_sent(self):
        self.assertEqual("scheduled", commitment_type("scheduled"))
        self.assertEqual("sent", commitment_type("sent"))
        self.assertIsNone(commitment_type("draft"))
        self.assertIsNone(commitment_type("needs_approval"))
        self.assertIsNone(commitment_type("error"))
        self.assertIsNone(commitment_type(None))

    @patch.dict(os.environ, {"BUFFER_API_KEY": "test-token"}, clear=False)
    def test_draft_result_is_ok_false_and_produces_no_receipt(self):
        package = _approved_buffer_package()
        count = len(package["posts"])
        client = BufferClient()
        client.channel = lambda service: {"id": f"channel-{service}", "service": service}
        client.queue_posts = lambda ids: []
        client.available_capacity = lambda ids: {cid: None for cid in ids}
        client.create_post = lambda **kwargs: {"id": "post-draft", "status": "draft"}
        client.posting_limits = lambda ids: []

        result = dispatch(package, "live", client=client)

        self.assertFalse(result["ok"])
        self.assertNotIn("delivery_receipts", result)
        self.assertEqual(count, len(result["created_posts"]))
        self.assertEqual(count, len(result["uncommitted"]))

    @patch.dict(os.environ, {"BUFFER_API_KEY": "test-token"}, clear=False)
    def test_sent_results_are_commitments_with_sent_commitment_type(self):
        package = _approved_buffer_package()
        count = len(package["posts"])
        client = BufferClient()
        client.channel = lambda service: {"id": f"channel-{service}", "service": service}
        client.queue_posts = lambda ids: []
        client.available_capacity = lambda ids: {cid: None for cid in ids}
        created = iter([{"id": f"post-{i}", "status": "sent"} for i in range(count)])
        client.create_post = lambda **kwargs: next(created)
        client.posting_limits = lambda ids: []

        result = dispatch(package, "live", client=client)

        self.assertTrue(result["ok"])
        self.assertTrue(all(item["commitment_type"] == "sent"
                            for item in result["delivery_receipts"]))

    @patch.dict(os.environ, {"BUFFER_API_KEY": "test-token"}, clear=False)
    def test_partial_commitment_is_ok_false_with_no_receipt(self):
        package = _approved_buffer_package()
        client = BufferClient()
        client.channel = lambda service: {"id": f"channel-{service}", "service": service}
        client.queue_posts = lambda ids: []
        client.available_capacity = lambda ids: {cid: None for cid in ids}
        statuses = iter(["scheduled"] * (len(package["posts"]) - 1) + ["draft"])
        client.create_post = lambda **kwargs: {"id": "post-x", "status": next(statuses)}
        client.posting_limits = lambda ids: []

        result = dispatch(package, "live", client=client)

        self.assertFalse(result["ok"])
        self.assertNotIn("delivery_receipts", result)
        self.assertEqual(1, len(result["uncommitted"]))

    def test_dry_run_dispatch_never_creates(self):
        result = dispatch({"campaign_manifest": {"phase": "approved"}}, "dry_run")
        self.assertFalse(result["ok"])
        self.assertIn("dry run", result["message"])

    # ── read-only queue surface ────────────────────────────────────────────

    @patch.dict(os.environ, {"BUFFER_API_KEY": "test-token"}, clear=False)
    def test_queue_posts_filters_to_scheduled_sent_draft(self):
        client = BufferClient()
        seen = {}

        def fake_graphql(query):
            seen["query"] = query
            return {"posts": {"edges": [
                {"node": {"id": "s1", "status": "scheduled", "text": "a"}},
                {"node": {"id": "s2", "status": "sent", "text": "b"}},
                {"node": {"id": "d1", "status": "draft", "text": "c"}},
                {"node": {"id": "n1", "status": "needs_approval", "text": "d"}},
            ]}}

        client.graphql = fake_graphql
        posts = client.queue_posts(["channel-1"])

        self.assertEqual({"s1", "s2", "d1"}, {post["id"] for post in posts})
        self.assertIn("channelIds", seen["query"])
        self.assertIn("sentAt", seen["query"])

    def test_queue_report_lists_posts_per_channel_without_writing(self):
        client = object.__new__(BufferClient)
        client.queue_posts = lambda ids: [
            {"id": "p1", "status": "scheduled", "channelId": "ch-1",
             "dueAt": "2026-08-17T10:00:00Z", "sentAt": None,
             "text": "One clear workflow", "assets": [{"source": "https://cdn.example.com/a.png"}]},
        ]
        client.last_rate_limits = {"x-ratelimit-remaining": "97"}

        report = _queue_report(client, ["ch-1"])

        self.assertTrue(report["ok"])
        self.assertEqual(1, report["count"])
        self.assertEqual("One clear workflow", report["channels"]["ch-1"][0]["text_excerpt"])
        self.assertEqual(["https://cdn.example.com/a.png"],
                         report["channels"]["ch-1"][0]["media_urls"])


class BufferMetricsRefreshTests(unittest.TestCase):
    """Read-only live engagement refresh used by funnel analysis (v1.3.0)."""

    @patch.dict(os.environ, {"BUFFER_API_KEY": "test-token"}, clear=False)
    def test_campaign_posts_selects_metrics_and_applies_window(self):
        client = BufferClient()
        seen = {}

        def fake_graphql(query):
            seen["query"] = query
            return {"posts": {"edges": [
                {"node": {"id": "p1", "status": "sent", "channelId": "ch-1",
                          "createdAt": "2026-08-17T08:00:00Z", "dueAt": "2026-08-16T09:00:00Z",
                          "metrics": [{"type": "views", "name": "Views", "value": 70}],
                          "metricsUpdatedAt": "2026-08-17T09:00:00Z"}},
                {"node": {"id": "p2", "status": "sent", "channelId": "ch-1",
                          "createdAt": "2026-08-10T08:00:00Z", "dueAt": "2026-08-10T09:00:00Z",
                          "metrics": [{"type": "likes", "name": "Likes", "value": 2}],
                          "metricsUpdatedAt": "2026-08-10T09:00:00Z"}},
                {"node": {"id": "d1", "status": "draft", "channelId": "ch-1",
                          "createdAt": "2026-08-17T07:00:00Z", "dueAt": None,
                          "metrics": [], "metricsUpdatedAt": None}},
            ]}}

        client.graphql = fake_graphql
        posts = client.campaign_posts(["channel-1"], since="2026-08-15T00:00:00Z")

        # p2 predates the window; p1 (sent) and d1 (draft) both fall inside it.
        self.assertEqual({"p1", "d1"}, {post["id"] for post in posts})
        self.assertIn("createdAt", seen["query"])
        self.assertIn("metrics { type name value unit } metricsUpdatedAt", seen["query"])
        # The reference queue read stays metric-free and untouched for the guard.
        queue = client.queue_posts(["channel-1"])
        self.assertEqual({"p1", "p2", "d1"}, {post["id"] for post in queue})
        self.assertNotIn("metricsUpdatedAt", seen["query"])
        self.assertNotIn("createdAt", seen["query"])

    @patch.dict(os.environ, {"BUFFER_API_KEY": "test-token"}, clear=False)
    def test_campaign_posts_walks_pages_and_deduplicates(self):
        """The metrics read pages past Buffer's newest-page cap (batch-01 fix)."""
        client = BufferClient()
        calls = []

        def fake_graphql(query):
            calls.append(query)
            if "after: \"cursor-1\"" in query:
                return {"posts": {"edges": [
                    {"node": {"id": "old-1", "status": "sent", "channelId": "ch-1",
                              "createdAt": "2026-08-12T20:00:00Z", "dueAt": None,
                              "metrics": [{"type": "views", "value": 65}],
                              "metricsUpdatedAt": "2026-08-17T05:00:00Z"}},
                ]}}
            return {"posts": {"pageInfo": {"hasNextPage": True, "endCursor": "cursor-1"},
                              "edges": [
                                  {"node": {"id": "new-1", "status": "sent", "channelId": "ch-1",
                                            "createdAt": "2026-08-17T08:00:00Z", "dueAt": None,
                                            "metrics": [], "metricsUpdatedAt": None}},
                                  # duplicate of a node that also appears on page 2
                                  {"node": {"id": "old-1", "status": "sent", "channelId": "ch-1",
                                            "createdAt": "2026-08-12T20:00:00Z", "dueAt": None,
                                            "metrics": [], "metricsUpdatedAt": None}},
                              ]}}

        client.graphql = fake_graphql
        posts = client.campaign_posts()

        self.assertEqual({"new-1", "old-1"}, {post["id"] for post in posts})
        self.assertEqual(2, len(posts))  # deduplicated across pages
        self.assertEqual(65, next(p["metrics"][0]["value"] for p in posts if p["id"] == "old-1"))
        self.assertIn("pageInfo { hasNextPage endCursor }", calls[0])
        self.assertIn("after: \"cursor-1\"", calls[1])

    @patch.dict(os.environ, {"BUFFER_API_KEY": "test-token"}, clear=False)
    def test_metrics_campaign_report_maps_buffer_native_reactions_and_comments(self):
        """Buffer's reactions/comments types populate likes/replies on the funnel keys."""
        client = object.__new__(BufferClient)
        client.last_rate_limits = {}
        client.campaign_posts = lambda ids, since=None, until=None: [
            {"id": "p1", "channelId": "ch-1", "channelService": "threads", "status": "sent",
             "createdAt": "2026-08-14T12:53:21Z", "dueAt": None,
             "sentAt": "2026-08-14T12:53:21Z",
             "metrics": [{"type": "views", "name": "Views", "value": 65},
                         {"type": "reactions", "name": "Reactions", "value": 2},
                         {"type": "comments", "name": "Comments", "value": 1},
                         {"type": "reposts", "name": "Reposts", "value": 0}],
             "metricsUpdatedAt": "2026-08-17T05:11:04Z"},
        ]
        now = datetime(2026, 8, 17, 12, 0, tzinfo=timezone.utc)

        report = _metrics_campaign_report(client, ["ch-1"], stale_after_hours=6, now=now)

        post = report["posts"][0]
        self.assertEqual(65, post["metrics"]["views"])
        self.assertEqual(2, post["metrics"]["likes"])
        self.assertEqual(1, post["metrics"]["replies"])
        self.assertEqual(0, post["metrics"]["reposts"])  # real platform-reported zero
        self.assertIsNone(post["metrics"]["shares"])
        self.assertIsNone(post["metrics"]["followers"])
        # Absent platform counts stay None (missing), never an invented zero.
        self.assertEqual(["shares", "followers"], post["missing_metrics"])

    @patch.dict(os.environ, {"BUFFER_API_KEY": "test-token"}, clear=False)
    def test_campaign_posts_window_uses_due_at_when_created_at_absent(self):
        client = BufferClient()
        client.graphql = lambda query: {"posts": {"edges": [
            {"node": {"id": "p1", "status": "sent", "createdAt": None,
                      "dueAt": "2026-08-16T09:00:00Z", "metrics": [], "metricsUpdatedAt": None}},
        ]}}
        self.assertEqual(["p1"], [post["id"]
                                  for post in client.campaign_posts(until="2026-08-17T00:00:00Z")])
        self.assertEqual([], client.campaign_posts(since="2026-08-17T00:00:00Z"))

    def test_metric_staleness_flags_fresh_stale_and_missing(self):
        now = datetime(2026, 8, 17, 12, 0, tzinfo=timezone.utc)
        self.assertEqual("fresh", metric_staleness("2026-08-17T10:00:00Z", 6, now=now))
        self.assertEqual("stale", metric_staleness("2026-08-17T05:00:00Z", 6, now=now))
        self.assertEqual("missing", metric_staleness(None, 6, now=now))

    def test_metrics_campaign_report_labels_missing_counts_not_zero(self):
        client = object.__new__(BufferClient)
        client.last_rate_limits = {"x-ratelimit-remaining": "96"}
        client.campaign_posts = lambda ids, since=None, until=None: [
            {"id": "p1", "channelId": "ch-1", "channelService": "threads", "status": "sent",
             "createdAt": "2026-08-17T08:00:00Z", "dueAt": None, "sentAt": "2026-08-17T08:00:00Z",
             "metrics": [{"type": "views", "name": "Views", "value": 60},
                         {"type": "likes", "name": "Likes", "value": 1}],
             "metricsUpdatedAt": "2026-08-17T09:00:00Z"},
        ]
        now = datetime(2026, 8, 17, 12, 0, tzinfo=timezone.utc)

        report = _metrics_campaign_report(client, ["ch-1"], stale_after_hours=6, now=now)

        self.assertTrue(report["ok"])
        self.assertEqual(1, report["count"])
        post = report["posts"][0]
        self.assertEqual(60, post["metrics"]["views"])
        self.assertEqual(1, post["metrics"]["likes"])
        self.assertIsNone(post["metrics"]["replies"])
        self.assertEqual(["replies", "reposts", "shares", "followers"],
                         post["missing_metrics"])
        self.assertEqual("fresh", post["staleness"])
        self.assertNotIn(0, post["metrics"].values())  # missing is None, never zero
        self.assertEqual("96", report["rate_limits"]["x-ratelimit-remaining"])

    @patch.dict(os.environ, {"BUFFER_API_KEY": "test-token"}, clear=False)
    def test_metrics_campaign_cli_is_read_only_and_reports_window(self):
        client = object.__new__(BufferClient)
        client.last_rate_limits = {}
        client.campaign_posts = lambda ids, since=None, until=None: []

        with patch("company.connections.buffer.BufferClient", return_value=client):
            with patch("sys.stdout", new_callable=io.StringIO) as out:
                code = main(["--metrics-campaign", "--since", "2026-08-01T00:00:00Z"])

        self.assertEqual(0, code)
        self.assertIn('"ok": true', out.getvalue())
        self.assertIn("2026-08-01T00:00:00Z", out.getvalue())

    def test_window_flags_are_rejected_without_metrics_campaign(self):
        with self.assertRaises(SystemExit):
            main(["--queue", "--since", "2026-08-01T00:00:00Z"])


if __name__ == "__main__":
    unittest.main()
