import hashlib
import json
import subprocess
import unittest
from pathlib import Path

from company.departments.analytics.department import campaign_funnel_report
from company.departments.campaign_contract import (
    LINK_IN_BIO,
    SCHEMA_VERSION,
    SPIELOS_REMINDER,
    apply_delivery_receipts,
    apply_funnel_report,
    apply_render_report,
    approve_rendered_campaign,
    creative_signature,
    publication_package,
    record_optimization_decision,
    validate_campaign,
)
from company.departments.design.department import accept_design_order, render_report, validate_design_order


ROOT = Path(__file__).resolve().parents[2]


def promoted_filename_cases():
    """Evaluate the promotion script's canonical filename builder over
    representative renderer basenames and return the built names.

    Mirrors the batch-02/03 Threads PNG naming from render-design.js
    (`{content_id}-{size_preset}-{W}x{H}.png`) and the YouTube `video.mp4`
    fallback, plus degenerate basenames that carry the content_id mid-string.
    """
    node_script = r"""
    import { publicAssetFilename } from './company/departments/design/tools/promote-campaign-assets.mjs';
    const cases = [
      ['batch-03-item-04-threads', '.spielos/artifacts/content-growth-20260812/batch-03/threads/batch-03-item-04-threads-threads-portrait-1080x1350.png'],
      ['batch-03-item-04-youtube', '.spielos/artifacts/content-growth-20260812/batch-03/youtube-shorts/batch-03-item-04/video.mp4'],
      ['batch-02-item-01-threads', '.spielos/artifacts/content-growth-20260812/batch-02/threads/batch-02-item-01-threads-threads-portrait-1080x1350.png'],
      ['batch-02-item-01-youtube', '.spielos/artifacts/content-growth-20260812/batch-02/youtube-shorts/batch-02-item-01/video.mp4'],
      ['plain-item-threads', '/tmp/render/video.mp4'],
      ['mid-string-id', '/tmp/render/prefix-mid-string-id-suffix.png'],
    ];
    const names = cases.map(([contentId, localPath]) => ({
      content_id: contentId,
      basename: localPath.split('/').pop(),
      name: publicAssetFilename(contentId, localPath),
    }));
    process.stdout.write(JSON.stringify(names));
    """
    result = subprocess.run(
        ["node", "--input-type=module", "-e", node_script],
        cwd=ROOT, capture_output=True, text=True,
    )
    if result.returncode != 0:
        raise AssertionError(f"promoted filename check failed: {result.stderr}")
    return json.loads(result.stdout)


HOOK_TEXT = "AI answers are useful. But repeated work still needs a usable workflow."
URL_TEXT = "go to spielos dot xyz slash services."

# Per-archetype scene order (mirrors registry.json scene_control.scenes and
# tts-gemini.js SCENE_ORDER). New Shorts archetypes reuse this table so the
# manifest stays archetype-exact under the 1.1 narration contract.
SHORTS_SCENE_ORDER = {
    "scenario-b": ["hook", "pain", "promise", "pillars", "director", "cta"],
    "scenario-c": ["hook", "build", "live", "director", "cta"],
    "contrast-text": ["hook", "claim", "proof", "resolve", "cta"],
    "storyboard": ["problem", "turn", "result", "cta"],
    "data-card": ["stat", "claim", "proof", "cta"],
}

SECONDARY_LINES = {
    "pain": "Context disappears when work moves by hand.",
    "promise": "One supervised workflow keeps the context.",
    "pillars": "Roles, standards, evals, and workflows stay attached.",
    "director": "Set the goal once. You judge the result.",
    "build": "Define the roles, context, standards, and workflows.",
    "live": "Now it runs with the review visible.",
    "claim": "Answers are cheap; an owned operation is the work.",
    "proof": "Supervised workflows beat chatbots that forget.",
    "resolve": "Roles, context, and review stay with the work.",
    "problem": "Work moves between tools by hand.",
    "turn": "One workflow carries the context.",
    "result": "It runs and you judge the outcome.",
    "stat": "Most repeated work never gets reviewed.",
    "question": "Who owns the AI result?",
    "stakes": "Unreviewed output looks right until it isn't.",
    "band": "Your process can run itself with supervision.",
    "goal": "Set the direction once and check against it.",
    "watch": "It watches, decides, and catches mistakes early.",
    "run": "It runs and shows the honest result.",
    "beat": "Your work lives on one live card.",
}


def _scene_intent(index, total):
    if index == total - 1:
        return "command/falling"  # CTA
    if index == 0:
        return "question/rising"  # hook
    return "statement/falling"


def _scene_visual(scene_id, text):
    """Controlled visual fields: headline == spoken text, cta uses the
    url-pronunciation alignment, every controlled scene carries 1-4 labels."""
    if scene_id == "cta":
        return {
            "eyebrow": "SpielOS · supervised AI workflows",
            "headline": "spielos.xyz/services",
            "supporting_text": "Book a free discovery call.",
            "component": "cta",
            "icon": "bx-check-square",
            "labels": ["AI agent implementation"],
            "spoken_display_alignment": "url-pronunciation",
        }
    return {
        "eyebrow": "SpielOS · supervised AI workflows",
        "headline": text,
        "supporting_text": "The decision and the review stay visible.",
        "component": "statement",
        "icon": "bx-check-square",
        "labels": ["Roles", "Context", "Evals"],
    }


def _youtube_narration(template_id, sequence):
    """One whole story (script) split after the fact into the archetype's
    scenes, each with a delivery intent — scene_control_version 1.1."""
    scene_ids = SHORTS_SCENE_ORDER[template_id]
    texts = []
    scenes = []
    for index, scene_id in enumerate(scene_ids):
        if index == 0:
            text = HOOK_TEXT
        elif scene_id == "cta":
            text = URL_TEXT
        else:
            text = SECONDARY_LINES.get(scene_id, f"{scene_id} line {sequence}.")
        scenes.append({
            "id": scene_id,
            "text": text,
            "intent": _scene_intent(index, len(scene_ids)),
            "visual": _scene_visual(scene_id, text),
        })
        texts.append(text)
    return {"scene_control_version": "1.1", "script": " ".join(texts), "scenes": scenes}


def campaign_manifest():
    campaign_id = "content-leads-20260812"
    # Valid archetype rotation enforced by the design gate: youtube picks five
    # unique shorts archetypes of the eight registered; threads picks five
    # distinct social archetypes of the six registered. Both pass
    # no-batch-repeats, round-robin balance, and bounded cell balance.
    threads_rotation = ("harness-architecture", "single-fact", "list-checklist",
                        "testimonial-pull-quote", "department-map")
    youtube_rotation = ("scenario-b", "scenario-c", "contrast-text",
                        "storyboard", "data-card")
    items = []
    for sequence in range(1, 6):
        item_id = f"batch-01-item-{sequence:02d}"
        renditions = {}
        for platform, asset_type, preset in (
            ("threads", "image", "threads-portrait"),
            ("youtube", "video", "youtube-shorts"),
        ):
            content_id = f"{item_id}-{platform}"
            destination = (
                f"https://spielos.xyz/services/?utm_source={platform}&utm_medium=social"
                f"&utm_campaign={campaign_id}&utm_content={content_id}"
            )
            template_id = (threads_rotation if platform == "threads" else youtube_rotation)[sequence - 1]
            design = {
                "template_id": template_id,
                "theme": ["gruvbox-dark", "gruvbox-light", "blue-dark", "monochrome-dark", "black-gold-dark"][sequence - 1],
                "size_preset": preset,
                "eyebrow": "SpielOS · supervised AI workflows",
                # The designed title must equal the locked hook narration
                # (contract: hook == complete designed title).
                "title_lines": ["AI answers are useful.", "But repeated work still needs a usable workflow."],
                "accent_line": 1,
                "supporting_text": "The title, hierarchy, and message share one campaign source.",
                "station_labels": ["Strategy", "Design", "Publish", "Measure", "Decide"],
            }
            rendition = {
                "platform": platform, "content_id": content_id,
                "copy": (
                    f"{HOOK_TEXT}\n\n"
                    f"Map the missing workflow:\n{destination}"
                    if platform == "threads" else
                    f"{HOOK_TEXT}\n\n{LINK_IN_BIO}"
                ) + (f"\n\n{SPIELOS_REMINDER}" if sequence == 5 else ""),
                "destination": destination,
                "link_placement": "caption" if platform == "threads" else "bio",
                "design": design,
            }
            if platform == "youtube":
                rendition["narration"] = _youtube_narration(template_id, sequence)
            renditions[platform] = rendition
        item = {
            "sequence": sequence, "item_id": item_id,
            "one_idea": f"One operating proof {sequence}",
            "brief": {
                "reader": "Owner of an established service business",
                "customer_moment": "Staff move repeated customer work between disconnected tools by hand.",
                "one_idea": f"One operating proof {sequence}",
                "desired_result": "Move the work faster without losing customer context.",
                "intent": "value",
                "spielos_relevance": "Supervised workflows turn repeated customer work into owned operations.",
                "proof": "The work can be mapped from intake to result.",
            },
            "hook": {"id": f"context-hook-{sequence}", "text": HOOK_TEXT},
            "cta": {"id": f"services-cta-{sequence}", "text": "Map the missing workflow."},
            "narrative_type": "spielos-reminder" if sequence == 5 else "customer-insight",
            "renditions": renditions,
        }
        if sequence == 5:
            item["reminder"] = {
                "text": SPIELOS_REMINDER,
                "proof": "The company uses SpielOS to operate its own repeatable work.",
            }
        items.append(item)
    return {
        "schema_version": SCHEMA_VERSION, "phase": "strategy",
        "campaign_id": campaign_id, "batch_id": "content-leads-20260812-batch-01",
        "batch_number": 1, "batch_size": 5,
        "daily_targets": {"threads": 50, "youtube": 50},
        "objective": {"qualified_visits_per_day": 200, "leads_per_day": 10,
                      "lead_conversion_rate": 0.05},
        "strategy": {
            "references": {
                "icp": "company/strategy/icp.md",
                "positioning": "company/strategy/positioning.md",
                "voice": "company/strategy/voice.md",
            },
            "hypothesis": "Context-first creative will attract more qualified service intent.",
            "controlled_variables": {"offer": "services", "batch_size": 5},
            "changed_variables": ["hook"],
        },
        "experiment": {
            "id": "context-hook-test-01", "test_type": "single-variable",
            "scope": "cross-channel-creative", "variables": ["hook"],
            "cells": [
                {"id": "control-hook", "role": "control", "values": {"hook": "direct-context"}},
                {"id": "variant-hook", "role": "variant", "values": {"hook": "problem-context"}},
            ],
            "assignment": {"method": "balanced", "unit": "content_id"},
            "primary_metric": "ctr", "guardrails": ["lead_conversion_rate"],
            "minimum_evidence_per_cell": 100,
            "analysis_method": "difference-in-rates",
        },
        "measurement": {"join_keys": ["campaign_id", "batch_id", "item_id", "content_id", "creative_signature"]},
        "items": items, "handoffs": [],
    }


def factorial_manifest():
    manifest = campaign_manifest()
    manifest["strategy"]["changed_variables"] = ["hook", "cta"]
    manifest["experiment"].update({
        "id": "hook-cta-factorial-01", "test_type": "factorial",
        "variables": ["hook", "cta"],
        "cells": [
            {"id": "control-both", "role": "control",
             "values": {"hook": "direct", "cta": "services"}},
            {"id": "variant-hook", "role": "variant",
             "values": {"hook": "problem", "cta": "services"}},
            {"id": "variant-cta", "role": "variant",
             "values": {"hook": "direct", "cta": "audit"}},
            {"id": "variant-both", "role": "variant",
             "values": {"hook": "problem", "cta": "audit"}},
        ],
    })
    return manifest


def measured_campaign(manifest, sample_size=250, effects=None):
    designed = accept_design_order(manifest)
    assets = [
        {"item_id": item["item_id"], "platform": platform,
         "type": "image" if platform == "threads" else "video",
         "local_path": "asset", "sha256": f"sha-{item['item_id']}-{platform}",
         "render_report_id": f"render-{item['item_id']}-{platform}"}
        for item in designed["items"] for platform in ("threads", "youtube")
    ]
    rendered = apply_render_report(designed, render_report(designed, assets))
    approvals = [
        {"item_id": item["item_id"], "platform": platform, "status": "approved",
         "approval_id": f"approval-{item['item_id']}-{platform}",
         "public_url": f"https://cdn.spielos.xyz/{item['item_id']}-{platform}.asset"}
        for item in rendered["items"] for platform in ("threads", "youtube")
    ]
    approved = approve_rendered_campaign(rendered, approvals)
    package = publication_package(approved)
    receipts = [
        {**{key: post[key] for key in ("campaign_id", "batch_id", "item_id", "content_id", "creative_signature", "platform", "approval_id")},
         "provider_post_id": f"buffer-{post['content_id']}", "verified": True, "status": "scheduled"}
        for post in package["posts"]
    ]
    delivered = apply_delivery_receipts(approved, receipts)
    report = campaign_funnel_report(delivered, {
        "content_ids": [post["content_id"] for post in package["posts"]],
        "evidence_complete": True, "evidence_window": "24h",
        "platform_views": sample_size * len(manifest["experiment"]["cells"]),
        "content_landings": 200, "service_cta_clicks": 40, "leads": 10,
        "experiment_cells": [
            {"cell_id": cell["id"], "sample_size": sample_size}
            for cell in manifest["experiment"]["cells"]
        ],
        "effects": effects or [],
    })
    return apply_funnel_report(delivered, report)


class CampaignHandoffContractTests(unittest.TestCase):
    def test_one_artifact_survives_the_complete_campaign_to_lead_journey(self):
        strategy = campaign_manifest()
        self.assertEqual(validate_campaign(strategy, "strategy"), [])

        designed = accept_design_order(strategy)
        assets = [
            {"item_id": item["item_id"], "platform": platform,
             "type": "image" if platform == "threads" else "video",
             "local_path": f".spielos/artifacts/{item['item_id']}-{platform}",
             "sha256": f"sha-{item['item_id']}-{platform}",
             "render_report_id": f"render-{item['item_id']}-{platform}"}
            for item in designed["items"] for platform in ("threads", "youtube")
        ]
        rendered = apply_render_report(designed, render_report(designed, assets))

        approvals = [
            {"item_id": item["item_id"], "platform": platform, "status": "approved",
             "approval_id": f"approval-{item['item_id']}-{platform}",
             "public_url": f"https://cdn.spielos.xyz/{item['item_id']}-{platform}.{'png' if platform == 'threads' else 'mp4'}"}
            for item in rendered["items"] for platform in ("threads", "youtube")
        ]
        approved = approve_rendered_campaign(rendered, approvals)
        package = publication_package(approved)
        self.assertEqual(len(package["posts"]), 10)
        self.assertTrue(all(post["approval_id"] for post in package["posts"]))

        receipts = [
            {**{key: post[key] for key in ("campaign_id", "batch_id", "item_id", "content_id", "creative_signature", "platform", "approval_id")},
             "provider_post_id": f"buffer-{post['content_id']}", "verified": True, "status": "scheduled"}
            for post in package["posts"]
        ]
        delivered = apply_delivery_receipts(approved, receipts)
        content_ids = [post["content_id"] for post in package["posts"]]
        report = campaign_funnel_report(delivered, {
            "content_ids": content_ids, "evidence_complete": True,
            "evidence_window": "24h", "platform_views": 4000,
            "content_landings": 200, "service_cta_clicks": 40, "leads": 10,
            "experiment_cells": [
                {"cell_id": "control-hook", "sample_size": 2000},
                {"cell_id": "variant-hook", "sample_size": 2000},
            ],
            "effects": [{"variables": ["hook"], "supported": True, "effect_size": 0.01}],
        })
        measured = apply_funnel_report(delivered, report)
        evaluated = record_optimization_decision(measured, {
            "evidence_window": "24h", "verdict": "keep context; test a clearer CTA",
            "test_type": "single-variable", "scope": "cross-channel-creative",
            "changed_variables": ["cta"],
            "next_batch_hypothesis": "A concrete workflow-audit CTA will increase service intent.",
        })
        self.assertEqual(validate_campaign(evaluated, "evaluated"), [])
        self.assertEqual(evaluated["campaign_id"], strategy["campaign_id"])
        self.assertEqual([handoff["to"] for handoff in evaluated["handoffs"]],
                         ["designed", "rendered", "approved", "delivered", "measured", "evaluated"])
        self.assertEqual(report["ctr"], 0.05)
        self.assertEqual(report["lead_conversion_rate"], 0.05)

    def test_funnel_report_forwards_the_template_breakdown(self):
        strategy = campaign_manifest()
        designed = accept_design_order(strategy)
        assets = [
            {"item_id": item["item_id"], "platform": platform,
             "type": "image" if platform == "threads" else "video",
             "local_path": "asset", "sha256": "sha", "render_report_id": "render"}
            for item in designed["items"] for platform in ("threads", "youtube")
        ]
        rendered = apply_render_report(designed, render_report(designed, assets))
        approvals = [
            {"item_id": item["item_id"], "platform": platform, "status": "approved",
             "approval_id": f"approval-{item['item_id']}-{platform}",
             "public_url": f"https://cdn.spielos.xyz/{item['item_id']}-{platform}.asset"}
            for item in rendered["items"] for platform in ("threads", "youtube")
        ]
        approved = approve_rendered_campaign(rendered, approvals)
        package = publication_package(approved)
        receipts = [
            {**{key: post[key] for key in ("campaign_id", "batch_id", "item_id", "content_id", "creative_signature", "platform", "approval_id")},
             "provider_post_id": f"buffer-{post['content_id']}", "verified": True, "status": "scheduled"}
            for post in package["posts"]
        ]
        delivered = apply_delivery_receipts(approved, receipts)
        breakdown = {
            "basis": "manifest item design orders joined to per-post Buffer rows",
            "website_events": "batch-level only: never per-template attribution without per-post tracking",
            "per_template": [{"template_id": "scenario-b", "platform": "youtube",
                              "posts": 2, "views": 13, "missing": False}],
        }
        report = campaign_funnel_report(delivered, {
            "content_ids": [post["content_id"] for post in package["posts"]],
            "evidence_complete": True, "evidence_window": "24h",
            "platform_views": 2000, "content_landings": 100,
            "service_cta_clicks": 20, "leads": 5,
            "template_breakdown": breakdown,
            "experiment_cells": [
                {"cell_id": "control-hook", "sample_size": 1000},
                {"cell_id": "variant-hook", "sample_size": 1000},
            ],
            "effects": [],
        })
        # The analytics handoff forwards the breakdown unchanged (passthrough;
        # canonical funnel math untouched) and the measured Artifact keeps it.
        self.assertEqual(breakdown, report["template_breakdown"])
        self.assertEqual(0.05, report["ctr"])
        measured = apply_funnel_report(delivered, report)
        self.assertEqual(validate_campaign(measured, "measured"), [])
        self.assertEqual(breakdown, measured["measurement"]["report"]["template_breakdown"])

    def test_promoted_public_urls_never_repeat_the_content_id_segment(self):
        # (a) The promotion script's canonical filename builder must never
        # repeat the content_id segment — the batch-02/03 regression where
        # Threads PNG basenames that already start with `{content_id}-` were
        # prefixed again, producing doubled URLs that broke Buffer media fetch.
        for case in promoted_filename_cases():
            content_id = case["content_id"]
            basename = case["basename"]
            name = case["name"]
            self.assertNotIn(f"{content_id}-{content_id}", name,
                             f"doubled content_id segment for {basename}")
            if content_id in basename:
                self.assertEqual(name, basename,
                                 "basename already carrying the content_id must stay canonical")
            else:
                self.assertEqual(name, f"{content_id}-{basename}",
                                 "identity-less basenames get a single clean prefix")
            self.assertLessEqual(name.count(content_id), 1)

    def _approved_manifest(self, batch: str) -> dict:
        """Load an approved batch manifest from local run artifacts.

        Artifacts live under gitignored `.spielos/artifacts/`; the batch-02/03
        manifests were archived to `_archive/fresh-start-20260819/`. Callers
        must skip when the local artifact is absent (fresh clones).
        """
        for rel in (f".spielos/artifacts/content-growth-20260812/{batch}/campaign-approved.json",
                    f".spielos/artifacts/content-growth-20260812/_archive/fresh-start-20260819/{batch}/campaign-approved.json"):
            path = ROOT / rel
            if path.is_file():
                return json.loads(path.read_text())
        self.skipTest(f"local artifact not present: {batch}/campaign-approved.json")

    @unittest.skipUnless(
        any((Path(__file__).resolve().parents[2] / rel).is_file() for rel in (
            ".spielos/artifacts/content-growth-20260812/batch-02/campaign-approved.json",
            ".spielos/artifacts/content-growth-20260812/_archive/fresh-start-20260819/batch-02/campaign-approved.json")),
        "owner-local artifact batch-02/campaign-approved.json not present")
    def test_approved_batch_manifests_announce_deployed_public_urls(self):
        # Approved batch-02/03 manifests: every announced public_url
        # contains exactly one content_id segment and the announced URL points
        # at the deployed public file, byte-for-byte.
        for batch in ("batch-02", "batch-03"):
            manifest = self._approved_manifest(batch)
            self.assertEqual(manifest["phase"], "approved")
            for item in manifest["items"]:
                for platform, rendition in item["renditions"].items():
                    content_id = rendition["content_id"]
                    url = rendition["asset"]["public_url"]
                    label = f"{batch}/{item['item_id']}/{platform}"
                    self.assertEqual(url.count(content_id), 1,
                                     f"{label}: public_url must contain exactly one content_id segment: {url}")
                    relative = url.replace("https://spielos.xyz", "", 1).lstrip("/")
                    deployed = ROOT / "public" / relative
                    self.assertTrue(deployed.is_file(),
                                    f"{label}: announced URL has no deployed file: {url}")
                    self.assertEqual(deployed.name, url.rsplit("/", 1)[-1])
                    self.assertEqual(
                        hashlib.sha256(deployed.read_bytes()).hexdigest(),
                        rendition["asset"]["sha256"],
                        f"{label}: deployed file does not match the approved manifest checksum")

    def test_identity_or_approval_drift_is_rejected(self):
        designed = accept_design_order(campaign_manifest())
        assets = [
            {"item_id": item["item_id"], "platform": platform,
             "type": "image" if platform == "threads" else "video",
             "local_path": "asset", "sha256": "sha", "render_report_id": "render"}
            for item in designed["items"] for platform in ("threads", "youtube")
        ]
        report = render_report(designed, assets)
        report["campaign_id"] = "wrong-campaign"
        with self.assertRaisesRegex(ValueError, "identity"):
            apply_render_report(designed, report)

    def test_video_templates_are_batch1_flat_with_a_still_only_thumbnail_title(self):
        template_source = "\n".join(
            (ROOT / path).read_text() for path in (
                "company/departments/design/templates/video/scenario-b.html",
                "company/departments/design/templates/video/scenario-c.html",
            )
        )
        # Batch-1 flat composition: no campaign-scene mounts, no panel/scrim
        # contrast cards, no campaign-label pills around the title.
        for stale in ("campaign-scene", "campaign-label", "__applyCampaignRendition",
                      "visual.headline", "visual.supporting_text", "spoken_display_alignment"):
            self.assertNotIn(stale, template_source)
        for marker in ("hook-main", "cta-url", "spielos.xyz/services"):
            self.assertIn(marker, template_source)
        # Optional Shorts thumbnail title renders ONLY on the still frame.
        for marker in ("thumb-title", "__setStillTitle"):
            self.assertIn(marker, template_source)
        renderer_source = (ROOT / "company/departments/design/tools/render-video.js").read_text()
        self.assertIn("--still", renderer_source)
        self.assertIn("campaignThumbnailTitle", renderer_source)

    def test_creative_identity_is_derived_not_entered_by_a_department(self):
        manifest = campaign_manifest()
        item = manifest["items"][0]
        design = item["renditions"]["threads"]["design"]
        first = creative_signature(manifest["campaign_id"], item["item_id"], "threads", design)
        design["title_lines"] = ["A different title line."]
        second = creative_signature(manifest["campaign_id"], item["item_id"], "threads", design)
        self.assertNotEqual(first, second)

    def test_factorial_contract_declares_cells_assignment_metrics_and_analysis(self):
        manifest = factorial_manifest()
        self.assertEqual(validate_campaign(manifest, "strategy"), [])
        manifest["experiment"]["cells"][1]["values"].pop("cta")
        errors = validate_campaign(manifest, "strategy")
        self.assertTrue(any("every variable" in error for error in errors))

    def test_multi_change_requires_supported_independent_or_interaction_effects(self):
        manifest = factorial_manifest()
        measured = measured_campaign(manifest, effects=[
            {"variables": ["hook"], "supported": True, "effect_size": 0.02},
            {"variables": ["cta"], "supported": True, "effect_size": 0.01},
        ])
        decision = {
            "evidence_window": "24h", "verdict": "test both supported effects",
            "test_type": "factorial", "scope": "cross-channel-creative",
            "changed_variables": ["hook", "cta"],
            "next_batch_hypothesis": "Combining the independently supported hook and CTA will improve CTR.",
        }
        evaluated = record_optimization_decision(measured, decision)
        self.assertEqual(validate_campaign(evaluated, "evaluated"), [])
        unsupported = measured_campaign(factorial_manifest(), effects=[
            {"variables": ["hook"], "supported": True, "effect_size": 0.02},
            {"variables": ["cta"], "supported": False, "effect_size": 0.0},
        ])
        with self.assertRaisesRegex(ValueError, "independent or interaction"):
            record_optimization_decision(unsupported, decision)

    def test_sparse_evidence_narrows_next_test_to_one_variable(self):
        measured = measured_campaign(factorial_manifest(), sample_size=20, effects=[])
        with self.assertRaisesRegex(ValueError, "sparse evidence"):
            record_optimization_decision(measured, {
                "evidence_window": "24h", "verdict": "not enough evidence",
                "test_type": "factorial", "scope": "cross-channel-creative",
                "changed_variables": ["hook", "cta"],
                "next_batch_hypothesis": "Premature multi-change test.",
            })

    def test_website_cro_is_identifiable_and_retains_separate_approval(self):
        manifest = campaign_manifest()
        manifest["experiment"].update({"scope": "website-cro",
                                       "assignment": {"method": "randomized", "unit": "session"}})
        errors = validate_campaign(manifest, "strategy")
        self.assertTrue(any("separate website-mutation approval" in error for error in errors))
        manifest["experiment"]["separate_approval_required"] = True
        self.assertEqual(validate_campaign(manifest, "strategy"), [])

    def test_public_copy_rejects_internal_language_and_literal_line_breaks(self):
        manifest = campaign_manifest()
        manifest["items"][0]["renditions"]["threads"]["copy"] = (
            r"I stopped the first batch.\n\nThe review gate caught it."
        )
        errors = validate_campaign(manifest, "strategy")
        self.assertTrue(any("real line breaks" in error for error in errors))
        self.assertTrue(any("internal production language: batch" in error for error in errors))
        self.assertTrue(any("internal production language: review gate" in error for error in errors))

    def test_youtube_uses_bio_and_only_fifth_item_uses_the_reminder(self):
        manifest = campaign_manifest()
        youtube = manifest["items"][0]["renditions"]["youtube"]
        youtube["copy"] += " https://spielos.xyz/services/?utm_source=youtube"
        manifest["items"][0]["renditions"]["threads"]["copy"] += f"\n\n{SPIELOS_REMINDER}"
        manifest["items"][4]["renditions"]["youtube"]["copy"] = LINK_IN_BIO
        errors = validate_campaign(manifest, "strategy")
        self.assertTrue(any("YouTube Shorts copy must not contain a URL" in error for error in errors))
        self.assertTrue(any("must not include the fifth-item" in error for error in errors))
        self.assertTrue(any("must end with the fifth-item" in error for error in errors))

    def test_youtube_thumbnail_title_is_optional_bounded_and_public_only(self):
        manifest = campaign_manifest()
        youtube = manifest["items"][0]["renditions"]["youtube"]
        # Absent title stays valid (optional).
        self.assertEqual(validate_campaign(manifest, "strategy"), [])
        # A 2-3 word title is the intended use and passes.
        youtube["design"]["thumbnail_title"] = "AI works alone"
        self.assertEqual(validate_campaign(manifest, "strategy"), [])
        # Up to five words is allowed.
        youtube["design"]["thumbnail_title"] = "one two three four five"
        self.assertEqual(validate_campaign(manifest, "strategy"), [])
        # Six words are rejected.
        youtube["design"]["thumbnail_title"] = "one two three four five six"
        errors = validate_campaign(manifest, "strategy")
        self.assertTrue(any("thumbnail_title must be 1-5 words" in error for error in errors))
        # URLs and UTM parameters are rejected.
        youtube["design"]["thumbnail_title"] = "see spielos.xyz"
        errors = validate_campaign(manifest, "strategy")
        self.assertTrue(any("must not contain a URL or UTM parameters" in error for error in errors))
        # Internal production language is rejected.
        youtube["design"]["thumbnail_title"] = "batch review"
        errors = validate_campaign(manifest, "strategy")
        self.assertTrue(any("thumbnail_title exposes internal production language: batch" in error for error in errors))
        # The field is a YouTube-only design field: Threads ignores it.
        threads = manifest["items"][0]["renditions"]["threads"]
        threads["design"]["thumbnail_title"] = "not validated here"
        youtube["design"]["thumbnail_title"] = "AI works alone"
        self.assertEqual(validate_campaign(manifest, "strategy"), [])

    def test_schema_1_2_brief_and_narration_contract_passes(self):
        """Schema 1.2 manifest: brief intent + spielos_relevance, and a
        whole-story narration (scene_control_version 1.1) validate clean."""
        manifest = campaign_manifest()
        self.assertEqual("1.2", SCHEMA_VERSION)
        self.assertEqual(manifest["schema_version"], "1.2")
        self.assertEqual(validate_campaign(manifest, "strategy"), [])
        for item in manifest["items"]:
            self.assertIn(item["brief"]["intent"], {"value", "proof", "conversion"})
            self.assertTrue(item["brief"]["spielos_relevance"].strip())
        narration = manifest["items"][0]["renditions"]["youtube"]["narration"]
        self.assertEqual("1.1", narration["scene_control_version"])
        self.assertTrue(narration["script"].strip())
        for scene in narration["scenes"]:
            self.assertIn(scene["intent"], {"question/rising", "statement/falling", "command/falling"})
            if scene["id"] == "cta":
                # url-pronunciation alignment: the CTA is spoken as the URL
                # phrase while the displayed headline stays the short URL.
                self.assertEqual("url-pronunciation", scene["visual"]["spoken_display_alignment"])
                self.assertEqual("spielos.xyz/services", scene["visual"]["headline"])
                self.assertEqual("go to spielos dot xyz slash services.", scene["text"])
            else:
                self.assertEqual(scene["text"], scene["visual"]["headline"])

    def test_schema_1_2_missing_brief_fields_fail(self):
        """Missing intent or spielos_relevance on a schema-1.2 brief fails."""
        manifest = campaign_manifest()
        brief = manifest["items"][0]["brief"]
        brief.pop("intent", None)
        brief["spielos_relevance"] = "   "
        errors = validate_campaign(manifest, "strategy")
        self.assertTrue(any("brief.intent must be one of" in error for error in errors))
        self.assertTrue(any("brief.spielos_relevance is required" in error for error in errors))

    def test_schema_1_2_missing_narration_contract_fails(self):
        """scene_control_version 1.1 requires the whole narration script and a
        registered delivery intent on every scene."""
        manifest = campaign_manifest()
        narration = manifest["items"][0]["renditions"]["youtube"]["narration"]
        narration.pop("script", None)
        narration["scenes"][1]["intent"] = "whimsical"
        errors = validate_campaign(manifest, "strategy")
        self.assertTrue(any("narration.script is required" in error for error in errors))
        self.assertTrue(any("scene 2.intent must be one of" in error for error in errors))

    def test_design_order_rejects_batch_repeats_across_eight_shorts_archetypes(self):
        """The registry registers eight Shorts archetypes, so a five-item batch
        must use five distinct ones; repeating one is rejected upstream."""
        registry = json.loads(
            (ROOT / "company/departments/design/templates/registry.json").read_text())
        shorts = [entry["id"] for entry in registry["archetypes"] if entry["kind"] == "shorts"]
        self.assertEqual(8, len(shorts))
        manifest = campaign_manifest()
        self.assertEqual([], validate_design_order(manifest))
        manifest["items"][1]["renditions"]["youtube"]["design"]["template_id"] = "scenario-b"
        manifest["items"][3]["renditions"]["youtube"]["design"]["template_id"] = "scenario-b"
        errors = validate_design_order(manifest)
        self.assertTrue(any("no batch repeats" in error and "scenario-b" in error
                            for error in errors))

if __name__ == "__main__":
    unittest.main()
