import json
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError

from company.connections import connection, connections
from company.departments.analytics.posthog import (
    FUNNEL_EVENTS, LEAD_SUCCESS_EVENTS, PostHogClient, PostHogError,
    consume_batch_evidence, posthog_token,
)
from company.departments.design.department import accept_design_order, validate_design_order
from company.departments.seo.keywords import build_opportunities
from company.runtime.catalog import catalog
from company.runtime.models import Department, GoalContext, Goal
from company.runtime.registry import departments
from company.tests.test_campaign_handoff_contract import campaign_manifest


class GrowthDepartmentTests(unittest.TestCase):
    def test_five_departments_are_discovered_from_their_own_folders(self):
        installed = departments()
        self.assertEqual({"outbound", "content", "design", "analytics", "seo"},
                         set(installed))
        self.assertTrue(all(isinstance(item, Department) for item in installed.values()))

    def test_catalog_exposes_only_universal_building_blocks(self):
        value = catalog()
        self.assertNotIn("tools", value)
        self.assertNotIn("control_engines", value)
        self.assertEqual("interpreter", value["runtime"]["department_runtime"])
        self.assertEqual({"attio", "buffer", "cal-booking", "posthog", "search-console", "website", "web-research",
                          "email-delivery"},
                         {item["id"] for item in value["connections"]})
        known_connections = {item["id"] for item in value["connections"]}
        referenced = {
            connection_id
            for department in value["departments"]
            for workflow in department["workflows"]
            for connection_id in workflow["connections"]
        }
        self.assertLessEqual(referenced, known_connections)
        lego = {item["id"] for item in value["departments"] if item.get("lego")}
        self.assertTrue({"content", "design", "analytics", "seo"}.issubset(lego))

    def test_representative_departments_share_frozen_lego_contract(self):
        value = catalog()
        representatives = {
            item["id"]: item for item in value["departments"]
            if item["id"] in {"content", "analytics", "outbound"}
        }
        self.assertEqual({"content", "analytics", "outbound"}, set(representatives))
        package_fields = {
            "id", "version", "description", "agent_ids", "workflow_agents",
            "evidence_metrics", "metrics", "config_schema", "workflows",
            "package_defects", "lego",
        }
        workflow_fields = {
            "id", "description", "steps", "agents", "skills", "approvals",
            "evidence", "connections", "graph",
        }
        step_fields = {
            "id", "kind", "employee_id", "produces", "requires", "skill_ids",
            "connection_ids",
        }
        for department in representatives.values():
            self.assertEqual([], department["package_defects"])
            self.assertTrue(department["lego"])
            self.assertEqual(package_fields, set(department))
            self.assertTrue(department["metrics"])
            self.assertTrue(department["evidence_metrics"])
            self.assertTrue(department["workflows"])
            for workflow in department["workflows"]:
                self.assertEqual(workflow_fields, set(workflow))
                self.assertTrue(workflow["steps"])
                self.assertTrue(workflow["agents"])
                self.assertTrue(workflow["evidence"])
                for step in workflow["graph"]:
                    self.assertEqual(step_fields, set(step))
                    self.assertIn(step["kind"], {"employee", "approval", "connection", "machine"})

    def test_department_requests_agent_then_evaluates_typed_evidence(self):
        goal = Goal("g", "graphics", "design", "approved_designs", "ge", 1,
                    None, None, "active", {"workflow": "social-visual"})
        department = departments()["design"]
        ctx = GoalContext(goal, {"evidence": []}, (), lambda _: None)
        decision = department.decide(ctx, department.observe(ctx).payload)
        self.assertEqual("request_agent", decision.payload["action"])
        self.assertEqual("designer", decision.payload["agent_id"])
        self.assertEqual(["approved_design"], decision.payload["accepted_evidence_kinds"])
        self.assertEqual(["spielos-ui"], decision.payload["skill_ids"])
        self.assertEqual("social-visual", decision.payload["workflow_id"])
        ctx = GoalContext(goal, {"evidence": [{"kind": "approved_design"}]}, (), lambda _: None)
        decision = department.decide(ctx, department.observe(ctx).payload)
        self.assertEqual("evaluate", decision.payload["action"])

    def test_content_publish_is_approval_gated_then_uses_direct_buffer_connection(self):
        goal = Goal("g", "publish", "content", "published_items", "ge", 1,
                    None, None, "active",
                    {"workflow": "publish", "connection": "buffer", "execution_mode": "dry_run"})
        evidence = [{"kind": "content_package", "payload": {"channel_id": "channel", "text": "hello"}}]
        department = departments()["content"]
        waiting = GoalContext(goal, {"evidence": evidence}, (), lambda _: None)
        observation = department.observe(waiting).payload
        decision = department.decide(waiting, observation)
        self.assertEqual("request_approval", decision.payload["action"])
        self.assertEqual("awaiting_approval", department.act(waiting, decision.payload).run_status.value)
        approved = GoalContext(goal, {"evidence": evidence}, (), lambda _: "approved")
        advanced = department.act(approved, decision.payload)
        self.assertEqual("DECIDE", advanced.next_stage.value)
        next_decision = department.decide(approved, department.observe(approved).payload)
        self.assertEqual("connection_dispatch", next_decision.payload["action"])
        # Connection dispatch also requires approval before direct delivery.
        self.assertEqual("awaiting_approval",
                         department.act(waiting, next_decision.payload).run_status.value)
        result = department.act(approved, next_decision.payload)
        self.assertEqual("blocked", result.run_status.value)
        self.assertEqual("Buffer dispatch is a dry run; no post was created",
                         result.payload["connection_request"]["message"])


class ConnectionContractTests(unittest.TestCase):
    def test_interactive_connections_are_host_first_except_direct_buffer_delivery(self):
        for connection_id in ("posthog", "search-console", "website", "web-research"):
            item = connection(connection_id)
            self.assertEqual(("codex", "opencode"), item.hosts)
            self.assertFalse(item.unattended)
            self.assertEqual((), item.required_environment)
        item = connection("buffer")
        self.assertEqual(("direct",), item.hosts)
        self.assertTrue(item.unattended)
        self.assertEqual(("BUFFER_API_KEY",), item.required_environment)

    def test_only_email_delivery_requires_unattended_direct_credentials(self):
        item = connections()["email-delivery"]
        self.assertTrue(item.unattended)
        self.assertEqual(("direct",), item.hosts)
        self.assertEqual(("EMAIL_PROVIDER",), item.required_environment)


class DesignContractTests(unittest.TestCase):
    def test_presets_cover_landscape_square_portrait_and_story(self):
        path = Path(__file__).parents[1] / "departments/design/presets.json"
        presets = json.loads(path.read_text())
        ratios = {(value["width"] > value["height"], value["width"] == value["height"],
                   value["width"] < value["height"]) for value in presets.values()}
        self.assertIn((True, False, False), ratios)
        self.assertIn((False, True, False), ratios)
        self.assertIn((False, False, True), ratios)

    def test_campaign_video_templates_are_restored_batch1_flat_with_still_thumbnail_titles(self):
        root = Path(__file__).parents[2]
        sources = "\n".join((root / path).read_text() for path in (
            "company/departments/design/templates/video/scenario-b.html",
            "company/departments/design/templates/video/scenario-c.html",
        ))
        # Owner order 2026-08-13: revert the contrast/placement experiment.
        # Templates are batch-1 flat again: no campaign scene machinery, no
        # visual.* contract fields, no stale legacy fixed scene copy.
        for stale in ("Employees using AI separately", "Repeated prompts, copied context",
                      "One assistant doing everything", "Hire a role", "AI directs"):
            self.assertNotIn(stale, sources)
        for field in ("visual.headline", "visual.supporting_text", "visual.component",
                      "visual.icon", "visual.labels"):
            self.assertNotIn(field, sources)
        for machinery in ("campaign-scene", "campaign-label", "__applyCampaignRendition",
                          "spoken_display_alignment"):
            self.assertNotIn(machinery, sources)
        for marker in ("hook-main", "cta-url", "spielos.xyz/services",
                       "thumb-title", "__setStillTitle"):
            self.assertIn(marker, sources)
        tts = (root / "company/departments/design/tools/tts-gemini.js").read_text()
        self.assertNotIn("SpielOS (pronounced", tts)
        self.assertIn('[/SpielOS/g, "Shpeel O S"]', tts)
        self.assertIn('spoken_display_alignment === "url-pronunciation"', tts)
        self.assertIn('displayed === "spielos.xyz/services"', tts)
        self.assertIn('spoken === "go to spielos dot xyz slash services."', tts)

    def test_keyword_research_marks_unmeasured_demand_unknown(self):
        values = build_opportunities(["AI department", "company harness"],
            [{"keys": ["company harness software"], "impressions": 40, "clicks": 3}])
        self.assertEqual("unknown", values[0]["demand_status"])
        self.assertIsNone(values[0]["impressions"])
        self.assertEqual("measured", values[1]["demand_status"])


class DesignRotationGateTests(unittest.TestCase):
    """Mechanical archetype rotation enforcement at the design gate (v3.4.0)."""

    def test_design_gate_rejects_a_design_order_with_repeated_archetypes(self):
        manifest = campaign_manifest()
        # YouTube draws from eight registered shorts archetypes for a batch of
        # five, so every template_id must be unique: repeating scenario-b on
        # items 01 and 02 violates "no batch repeats".
        manifest["items"][0]["renditions"]["youtube"]["design"]["template_id"] = "scenario-b"
        manifest["items"][1]["renditions"]["youtube"]["design"]["template_id"] = "scenario-b"
        errors = validate_design_order(manifest)
        self.assertTrue(any("no batch repeats for youtube" in error for error in errors))
        with self.assertRaisesRegex(ValueError, "no batch repeats for youtube"):
            accept_design_order(manifest)

    def test_design_gate_rejects_a_design_order_with_unbalanced_cells(self):
        manifest = campaign_manifest()
        # Threads draws from six registered social archetypes for five items,
        # so every template_id must be unique under the current registry:
        # repeating testimonial-pull-quote on items 02 and 04 violates
        # "no batch repeats" AND collapses the variant cell (items 02/04) to a
        # single archetype family — the cell is starved and the order must be
        # rejected.
        rotation = ["harness-architecture", "testimonial-pull-quote", "single-fact",
                    "testimonial-pull-quote", "list-checklist"]
        for item, template_id in zip(manifest["items"], rotation):
            item["renditions"]["threads"]["design"]["template_id"] = template_id
        errors = validate_design_order(manifest)
        self.assertTrue(any("unbalanced experiment cells" in error and "threads" in error
                            for error in errors))
        with self.assertRaisesRegex(ValueError, "unbalanced experiment cells"):
            accept_design_order(manifest)

    def test_design_gate_accepts_a_valid_round_robin_batch(self):
        manifest = campaign_manifest()
        # The shared fixture rotation repeats harness-architecture on items 01
        # and 05. That bounded round-robin repeat was legal when only four
        # social archetypes were registered, but the registry now offers six
        # selectable social archetypes (design 3.4.0), so a five-item batch
        # must use five unique template_ids. Rotate through five distinct
        # registered social archetypes that also keep both experiment cells
        # balanced: control (items 01/03/05) sees three families and variant
        # (items 02/04) sees two. The youtube shorts rotation (five of eight
        # registered) is already valid as-built.
        rotation = ["harness-architecture", "single-fact", "list-checklist",
                    "testimonial-pull-quote", "department-map"]
        for item, template_id in zip(manifest["items"], rotation):
            item["renditions"]["threads"]["design"]["template_id"] = template_id
        self.assertEqual([], validate_design_order(manifest))
        accepted = accept_design_order(manifest)
        self.assertEqual("designed", accepted["phase"])
        self.assertEqual(5, len(accepted["items"]))


class PostHogWarehouseTests(unittest.TestCase):
    """Read-only PostHog warehouse wiring (v1.4.0 funnel envelope)."""

    def test_posthog_token_is_never_hardcoded_in_source(self):
        source = Path(__file__).parents[1] / "departments/analytics/posthog.py"
        self.assertNotIn("phc_1osIFVXYDFr7Z00RN5gRaF4kRfZ1safm9c7NswRfKpm",
                         source.read_text())

    @patch.dict("os.environ", {"POSTHOG_PERSONAL_API_KEY": "phx_test"}, clear=False)
    def test_posthog_token_reads_from_environment_or_env_file(self):
        self.assertEqual("phx_test", posthog_token())

    @patch.dict("os.environ", {"POSTHOG_PERSONAL_API_KEY": "phx_test"}, clear=False)
    def test_posthog_client_hits_eu_project_scoped_query_route_with_bearer_key(self):
        captured = {}

        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def read(self):
                return json.dumps({
                    "columns": ["event", "c"],
                    "rows": [["cta_clicked", 112]],
                    "types": ["string", "UInt64"], "query_id": "q1",
                }).encode("utf-8")

        def fake_urlopen(request, timeout=30):
            captured["url"] = request.full_url
            captured["method"] = request.get_method()
            captured["auth"] = next(
                (value for name, value in request.header_items()
                 if name.lower() == "authorization"), None)
            captured["body"] = json.loads(request.data.decode("utf-8"))
            return FakeResponse()

        client = PostHogClient()
        with patch("company.departments.analytics.posthog.urlopen",
                   side_effect=fake_urlopen):
            rows = client.rows("select event, count() as c from events group by event")

        self.assertEqual("https://eu.posthog.com/api/projects/92369/query/", captured["url"])
        self.assertEqual("POST", captured["method"])
        self.assertEqual("Bearer phx_test", captured["auth"])
        self.assertEqual("HogQLQuery", captured["body"]["query"]["kind"])
        self.assertEqual([{"event": "cta_clicked", "c": 112}], rows["rows"])
        self.assertEqual("q1", rows["query_id"])

    @patch.dict("os.environ", {"POSTHOG_PERSONAL_API_KEY": "phx_test"}, clear=False)
    def test_posthog_client_parses_live_results_list_of_lists_shape(self):
        """The project-scoped Query API returns results as [[name, count], ...]."""
        captured = {}

        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def read(self):
                return json.dumps({
                    "columns": ["event", "c"],
                    "results": [["cta_clicked", 112], ["click_contact", 19]],
                    "types": ["string", "UInt64"],
                }).encode("utf-8")

        def fake_urlopen(request, timeout=30):
            captured["url"] = request.full_url
            captured["body"] = json.loads(request.data.decode("utf-8"))
            return FakeResponse()

        client = PostHogClient()
        with patch("company.departments.analytics.posthog.urlopen",
                   side_effect=fake_urlopen):
            rows = client.rows(
                "select event, count() as c from events group by event order by c desc limit 10")
            counts = client.event_counts()

        self.assertEqual("https://eu.posthog.com/api/projects/92369/query/",
                         captured["url"])
        self.assertEqual([{"event": "cta_clicked", "c": 112},
                          {"event": "click_contact", "c": 19}], rows["rows"])
        self.assertEqual({"cta_clicked": 112, "click_contact": 19},
                         counts["events"])

    @patch.dict("os.environ", {"POSTHOG_PERSONAL_API_KEY": "phx_test"}, clear=False)
    def test_posthog_client_project_id_is_configurable(self):
        client = PostHogClient(project_id=4242)
        self.assertEqual("https://eu.posthog.com/api/projects/4242/query/", client.api_url)
        default = PostHogClient()
        self.assertEqual(92369, default.project_id)

    @patch.dict("os.environ", {"POSTHOG_PERSONAL_API_KEY": "phx_test"}, clear=False)
    def test_event_counts_labels_missing_events_never_zero(self):
        client = PostHogClient()
        client.rows = lambda hogql, timeout=30: {
            "query_id": "q1", "columns": ["event", "c"],
            "rows": [{"event": "cta_clicked", "c": 3}],
        }

        result = client.event_counts()

        self.assertTrue(result["ok"])
        self.assertEqual({"cta_clicked": 3}, result["events"])
        self.assertNotIn("cta_clicked", result["missing_events"])
        # Retired loader names are never invented as zero: absent = missing.
        self.assertIn("content_landing", result["missing_events"])
        self.assertIn("lead_form_success", result["missing_events"])
        self.assertIsNone(result["events"].get("lead_form_success"))
        self.assertEqual(sorted(set(FUNNEL_EVENTS) - {"cta_clicked"}),
                         result["missing_events"])

    @patch.dict("os.environ", {"POSTHOG_PERSONAL_API_KEY": "phx_test"}, clear=False)
    def test_warehouse_http_error_raises_safe_read_only_error(self):
        client = PostHogClient()

        def boom(request, timeout=30):
            raise HTTPError("https://eu.posthog.com/api/projects/92369/query/",
                            401, "Unauthorized", {}, None)

        with patch("company.departments.analytics.posthog.urlopen",
                   side_effect=boom):
            with self.assertRaisesRegex(PostHogError, "HTTP 401"):
                client.query("select 1")


class FunnelConsumptionTests(unittest.TestCase):
    """funnel-analysis consumes refreshed Buffer + PostHog warehouse per batch."""

    @staticmethod
    def _refresh(posts):
        return {"ok": True, "count": len(posts),
                "window": {"stale_after_hours": 6.0},
                "posts": posts, "rate_limits": {}}

    def test_consume_batch_evidence_joins_buffer_and_posthog_on_join_keys(self):
        receipts = [
            {"item_id": "batch-01-item-01", "platform": "threads",
             "content_id": "batch-01-item-01-threads",
             "creative_signature": "sig-t", "provider_post_id": "post-1"},
            {"item_id": "batch-01-item-01", "platform": "youtube",
             "content_id": "batch-01-item-01-youtube",
             "creative_signature": "sig-y", "provider_post_id": "post-2"},
        ]
        refresh = self._refresh([
            {"post_id": "post-1", "status": "sent", "channel_service": "threads",
             "metrics": {"views": 60, "likes": 1, "replies": 0, "reposts": None,
                         "shares": None, "followers": 1},
             "metrics_updated_at": "2026-08-17T09:00:00Z", "staleness": "fresh",
             "missing_metrics": ["reposts", "shares"]},
            {"post_id": "post-2", "status": "sent", "channel_service": "youtube",
             "metrics": {"views": 70, "likes": 2, "replies": 0, "reposts": None,
                         "shares": None, "followers": None},
             "metrics_updated_at": "2026-08-17T09:00:00Z", "staleness": "fresh",
             "missing_metrics": ["reposts", "shares", "followers"]},
        ])
        events = {"events": {"cta_clicked": 1,
                             "agent_briefing_form_success": 1,
                             "waitlist_form_success": 1},
                  "missing_events": ["content_landing", "lead_form_success"]}

        evidence = consume_batch_evidence(
            campaign_id="content-leads-20260812", batch_id="batch-01",
            delivery_receipts=receipts, buffer_refresh=refresh,
            posthog_events=events,
            evidence_window={"since": "2026-08-17T00:00:00Z",
                             "until": "2026-08-18T00:00:00Z"})

        self.assertEqual(
            ["campaign_id", "batch_id", "item_id", "content_id", "creative_signature"],
            evidence["join_keys"])
        self.assertEqual(130, evidence["funnel"]["platform_views"]["value"])
        self.assertFalse(evidence["funnel"]["platform_views"]["missing"])
        # content_landing is the retired loader name: never captured live, so
        # the attention stage is missing (not zero) and the rates stay absent.
        self.assertTrue(evidence["funnel"]["content_landings"]["missing"])
        self.assertIsNone(evidence["funnel"]["content_landings"]["value"])
        self.assertEqual(1, evidence["funnel"]["service_cta_clicks"]["value"])
        # lead_form_success was never captured in this window, so the leads
        # stage is missing (None), not an invented count — schema 1.5.0 keeps
        # the live lead form events as the only lead-success names.
        self.assertTrue(evidence["funnel"]["leads"]["missing"])
        self.assertIsNone(evidence["funnel"]["leads"]["value"])
        self.assertIn("no lead_form_success event captured",
                      evidence["funnel"]["leads"]["missing_reason"])
        self.assertIsNone(evidence["funnel"]["ctr"])
        self.assertIsNone(evidence["funnel"]["service_intent_rate"])
        self.assertIsNone(evidence["funnel"]["lead_conversion_rate"])
        self.assertTrue(evidence["technical_only"])
        self.assertIn("Missing counts are labeled missing, never zero",
                      evidence["honesty_rules"])
        self.assertEqual("buffer_refresh", evidence["funnel"]["platform_views"]["source"])
        self.assertEqual("posthog_warehouse", evidence["funnel"]["leads"]["source"])
        # Live lead events are the only lead_funnel members and none were
        # captured in this window; retired loader names (agent-brief, waitlist,
        # click_contact/install) live in posthog_warehouse.events, never inside
        # lead_funnel (schema 1.5.0). The read source is the EU project-scoped
        # route.
        self.assertEqual("https://eu.posthog.com/api/projects/92369/query/",
                         evidence["posthog_warehouse"]["read_source"])
        self.assertIsNone(evidence["posthog_warehouse"]["lead_funnel"]["lead_form_success"])
        self.assertIsNone(evidence["posthog_warehouse"]["lead_funnel"]["lead_form_view"])
        self.assertNotIn("click_contact", evidence["posthog_warehouse"]["lead_funnel"])
        self.assertNotIn("click_install", evidence["posthog_warehouse"]["lead_funnel"])
        self.assertNotIn("agent_briefing_form_success",
                         evidence["posthog_warehouse"]["lead_funnel"])
        self.assertNotIn("waitlist_form_success",
                         evidence["posthog_warehouse"]["lead_funnel"])
        self.assertEqual(1, evidence["posthog_warehouse"]["events"]["agent_briefing_form_success"])
        self.assertEqual(1, evidence["posthog_warehouse"]["events"]["waitlist_form_success"])

    def test_consume_batch_evidence_never_invents_zero_counts(self):
        receipts = [
            {"item_id": "batch-01-item-01", "platform": "threads",
             "content_id": "batch-01-item-01-threads",
             "creative_signature": "sig-t", "provider_post_id": "post-1"},
        ]
        refresh = self._refresh([
            {"post_id": "post-1", "status": "sent", "channel_service": "threads",
             "metrics": {"views": None, "likes": None, "replies": None,
                         "reposts": None, "shares": None, "followers": None},
             "metrics_updated_at": None, "staleness": "missing",
             "missing_metrics": ["views", "likes", "replies", "reposts",
                                 "shares", "followers"]},
        ])
        events = {"events": {}, "missing_events": sorted(FUNNEL_EVENTS)}

        evidence = consume_batch_evidence(
            campaign_id="content-leads-20260812", batch_id="batch-01",
            delivery_receipts=receipts, buffer_refresh=refresh,
            posthog_events=events)

        funnel = evidence["funnel"]
        self.assertTrue(funnel["platform_views"]["missing"])
        self.assertIsNone(funnel["platform_views"]["value"])
        self.assertTrue(funnel["content_landings"]["missing"])
        self.assertTrue(funnel["service_cta_clicks"]["missing"])
        self.assertTrue(funnel["leads"]["missing"])
        self.assertIsNone(funnel["leads"]["value"])
        self.assertIsNone(funnel["ctr"])
        self.assertEqual(sorted(FUNNEL_EVENTS),
                         evidence["posthog_warehouse"]["missing_events"])
        # Live lead events are missing (None), never an invented zero.
        for key in LEAD_SUCCESS_EVENTS:
            self.assertIsNone(evidence["posthog_warehouse"]["lead_funnel"][key])
        self.assertIn("batch-01-item-01-threads:views",
                      evidence["buffer_refresh"]["missing_metric_labels"])
        self.assertEqual({"batch-01-item-01-threads": "missing"},
                         evidence["buffer_refresh"]["staleness_by_rendition"])

    def test_consume_batch_evidence_marks_stale_refreshes(self):
        receipts = [
            {"item_id": "batch-01-item-01", "platform": "youtube",
             "content_id": "batch-01-item-01-youtube",
             "creative_signature": "sig-y", "provider_post_id": "post-2"},
        ]
        refresh = self._refresh([
            {"post_id": "post-2", "status": "sent", "channel_service": "youtube",
             "metrics": {"views": 23, "likes": None, "replies": None,
                         "reposts": None, "shares": None, "followers": None},
             "metrics_updated_at": "2026-08-13T08:00:00Z", "staleness": "stale",
             "missing_metrics": ["likes", "replies", "reposts", "shares",
                                 "followers"]},
        ])
        events = {"events": {"content_landing": 2}, "missing_events": ["cta_clicked",
                                                                      "lead_form_success"]}

        evidence = consume_batch_evidence(
            campaign_id="content-leads-20260812", batch_id="batch-01",
            delivery_receipts=receipts, buffer_refresh=refresh,
            posthog_events=events)

        self.assertEqual(["post-2"], evidence["buffer_refresh"]["stale_post_ids"])
        self.assertEqual("stale",
                         evidence["buffer_refresh"]["staleness_by_rendition"]["batch-01-item-01-youtube"])


class TemplateBreakdownTests(unittest.TestCase):
    """consume_batch_evidence carries the per-template funnel dimension (v1.5.0)."""

    @staticmethod
    def _refresh(posts):
        return {"ok": True, "count": len(posts),
                "window": {"stale_after_hours": 6.0},
                "posts": posts, "rate_limits": {}}

    @staticmethod
    def _manifest_with_templates():
        items = []
        for sequence in (1, 2):
            item_id = f"batch-09-item-{sequence:02d}"
            renditions = {}
            for platform, template_id in (("threads", "harness-architecture"),
                                          ("youtube", "scenario-b")):
                renditions[platform] = {
                    "platform": platform,
                    "content_id": f"{item_id}-{platform}",
                    "design": {"template_id": template_id},
                }
            items.append({"item_id": item_id, "sequence": sequence, "renditions": renditions})
        return {"campaign_id": "content-leads-20260812", "batch_id": "batch-09", "items": items}

    @staticmethod
    def _receipts(manifest, views_spec):
        receipts = []
        for item in manifest["items"]:
            for platform in ("threads", "youtube"):
                content_id = item["renditions"][platform]["content_id"]
                receipts.append({
                    "item_id": item["item_id"], "platform": platform,
                    "content_id": content_id, "creative_signature": "sig",
                    "provider_post_id": f"post-{content_id}",
                })
        posts = []
        for content_id, views in views_spec.items():
            posts.append({
                "post_id": f"post-{content_id}", "status": "sent",
                "channel_service": "threads" if content_id.endswith("-threads") else "youtube",
                "metrics": {"views": views, "likes": None, "replies": None,
                            "reposts": None, "shares": None, "followers": None},
                "metrics_updated_at": "2026-08-18T09:00:00Z", "staleness": "fresh",
                "missing_metrics": ["likes", "replies", "reposts", "shares", "followers"],
            })
        return receipts, posts

    def test_consume_batch_evidence_emits_per_template_platform_views(self):
        manifest = self._manifest_with_templates()
        receipts, posts = self._receipts(manifest, {
            "batch-09-item-01-threads": 60, "batch-09-item-02-threads": 30,
            "batch-09-item-01-youtube": 70, "batch-09-item-02-youtube": 40,
        })
        events = {"events": {"cta_clicked": 3},
                  "missing_events": sorted(set(FUNNEL_EVENTS) - {"cta_clicked"})}
        evidence = consume_batch_evidence(
            manifest=manifest, delivery_receipts=receipts,
            buffer_refresh=self._refresh(posts), posthog_events=events,
            evidence_window={"since": "2026-08-18T00:00:00Z",
                             "until": "2026-08-19T00:00:00Z"})

        self.assertEqual("1.5.0", evidence["schema_version"])
        breakdown = evidence["template_breakdown"]
        by_template = {(entry["template_id"], entry["platform"]): entry
                       for entry in breakdown["per_template"]}
        threads = by_template[("harness-architecture", "threads")]
        self.assertFalse(threads["missing"])
        self.assertEqual(2, threads["posts"])
        self.assertEqual(90, threads["views"])
        youtube = by_template[("scenario-b", "youtube")]
        self.assertFalse(youtube["missing"])
        self.assertEqual(110, youtube["views"])
        # Every registered archetype of the platform kind is enumerated, even
        # the ones with no per-post row in this batch — labeled missing, never
        # an invented zero.
        self.assertIn(("question-hook", "youtube"), by_template)
        absent = by_template[("question-hook", "youtube")]
        self.assertTrue(absent["missing"])
        self.assertIsNone(absent["views"])
        self.assertEqual(0, absent["posts"])
        self.assertIn("no per-post row", absent["missing_reason"])
        # All eight shorts and six social archetypes are reported.
        self.assertEqual(14, len(breakdown["per_template"]))
        # Website events are batch-level only; the block says so instead of
        # inventing per-template attribution.
        self.assertIn("batch-level only", breakdown["website_events"])
        self.assertIn("never attributed per template without per-post tracking",
                      breakdown["website_events"])

    def test_consume_batch_evidence_labels_missing_per_template_views(self):
        manifest = self._manifest_with_templates()
        receipts, posts = self._receipts(manifest, {
            "batch-09-item-01-threads": None, "batch-09-item-02-threads": 30,
            "batch-09-item-01-youtube": 70, "batch-09-item-02-youtube": 40,
        })
        events = {"events": {}, "missing_events": sorted(FUNNEL_EVENTS)}
        evidence = consume_batch_evidence(
            manifest=manifest, delivery_receipts=receipts,
            buffer_refresh=self._refresh(posts), posthog_events=events)

        by_template = {(entry["template_id"], entry["platform"]): entry
                       for entry in evidence["template_breakdown"]["per_template"]}
        # One row in the group has no measured views -> the whole template/
        # platform views stay missing, never a partial sum or a zero.
        threads = by_template[("harness-architecture", "threads")]
        self.assertTrue(threads["missing"])
        self.assertIsNone(threads["views"])
        self.assertEqual(2, threads["posts"])
        self.assertIn("batch-09-item-01-threads", threads["missing_reason"])
        # The fully measured template/platform stays measured.
        youtube = by_template[("scenario-b", "youtube")]
        self.assertFalse(youtube["missing"])
        self.assertEqual(110, youtube["views"])

    def test_consume_batch_evidence_without_manifest_labels_template_dimension_missing(self):
        receipts = [
            {"item_id": "batch-01-item-01", "platform": "threads",
             "content_id": "batch-01-item-01-threads",
             "creative_signature": "sig-t", "provider_post_id": "post-1"},
        ]
        posts = [{
            "post_id": "post-1", "status": "sent", "channel_service": "threads",
            "metrics": {"views": 12, "likes": None, "replies": None,
                        "reposts": None, "shares": None, "followers": None},
            "metrics_updated_at": "2026-08-18T09:00:00Z", "staleness": "fresh",
            "missing_metrics": ["likes", "replies", "reposts", "shares", "followers"],
        }]
        events = {"events": {}, "missing_events": sorted(FUNNEL_EVENTS)}
        evidence = consume_batch_evidence(
            campaign_id="content-leads-20260812", batch_id="batch-09",
            delivery_receipts=receipts, buffer_refresh=self._refresh(posts),
            posthog_events=events)

        per_template = evidence["template_breakdown"]["per_template"]
        self.assertEqual(2, len(per_template))
        for entry in per_template:
            self.assertIsNone(entry["template_id"])
            self.assertTrue(entry["missing"])
            self.assertIsNone(entry["views"])
            self.assertIn("manifest design orders absent", entry["missing_reason"])


if __name__ == "__main__":
    unittest.main()
