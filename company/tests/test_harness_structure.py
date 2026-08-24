import json
import re
import tempfile
import unittest
from pathlib import Path

from company.departments.outbound.workflows import social
from company.runtime.catalog import catalog
from company.runtime.loop import Runtime


ROOT = Path(__file__).resolve().parents[2]

TEMPLATE_ROOT = ROOT / "company/departments/design/templates"
REGISTRY_PATH = TEMPLATE_ROOT / "registry.json"
BOXICONS_CSS = ROOT / "company/departments/design/tools/vendor/boxicons/css/boxicons.min.css"


def render_context_tokens():
    """Every custom property a template may resolve: the semantic token files
    (source of truth), the render-context aliases in production.css, the
    shared motion layer, and the runtime-injected --path-len. A template's own
    :root declarations are added per-template in the test."""
    names = set()
    for css in (ROOT / "company/departments/design/tokens").glob("*.css"):
        names.update(re.findall(r"--[a-zA-Z0-9-]+", css.read_text()))
    for css in (
        ROOT / "company/departments/design/system/production.css",
        TEMPLATE_ROOT / "video/brand-motion.css",
    ):
        names.update(re.findall(r"--[a-zA-Z0-9-]+", css.read_text()))
    names.add("--path-len")  # set at runtime by the templates' tick()
    return names


class CatalogTests(unittest.TestCase):
    def test_catalog_has_one_loop_and_resolvable_composition(self):
        value = catalog()
        self.assertEqual(value["runtime"]["loop"],
                         ["GOAL", "OBSERVE", "DECIDE", "ACT", "EVALUATE"])
        departments = {item["id"]: item for item in value["departments"]}
        self.assertEqual({"outbound", "content", "design", "analytics", "seo"},
                         set(departments))
        agents = {item["id"] for item in value["agents"]}
        skills = {item["id"] for item in value["skills"]}
        for department in departments.values():
            for workflow in department["workflows"]:
                self.assertTrue(set(workflow["agents"]).issubset(agents))
                self.assertTrue(set(workflow["skills"]).issubset(skills))

    def test_lean_layout_has_one_authority_and_no_duplicate_layers(self):
        self.assertTrue((ROOT / "company/README.md").is_file())
        self.assertTrue((ROOT / "company/strategy/icp.md").is_file())
        self.assertFalse((ROOT / "company/engines").exists())
        self.assertFalse((ROOT / "company/tools").exists())
        self.assertFalse((ROOT / ".agents/Outbound").exists())
        self.assertFalse((ROOT / ".agents/Outreach").exists())
        commands = {path.stem for path in (ROOT / "company/init_templates/hosts/opencode/commands").glob("*.md")}
        self.assertEqual({"start", "stop", "status", "approve", "help"}, commands)

    def test_canonical_video_templates_stay_with_design(self):
        root = ROOT / "company/departments/design/templates/video"
        self.assertTrue((root / "scenario-b.html").is_file())
        self.assertTrue((root / "scenario-c.html").is_file())


class TemplateRegistryTests(unittest.TestCase):
    """Registry validation for the template archetype registry (change task
    change-6a6dd10b2c, design 3.4.0 → 3.5.0): every registered template file
    exists, is parseable HTML, uses only allowed boxicon classes (bx only,
    no bx-*-circle variants), and references only semantic tokens."""

    def setUp(self):
        self.registry = json.loads(REGISTRY_PATH.read_text())
        self.boxicons = BOXICONS_CSS.read_text()
        self.tokens = render_context_tokens()

    def test_registry_declares_minimum_counts_and_keeps_legacy_ids(self):
        self.assertEqual("1.0", self.registry["schema_version"])
        self.assertGreaterEqual(self.registry["counts"]["shorts_min"], 4)
        self.assertGreaterEqual(self.registry["counts"]["social_min"], 3)
        ids = [archetype["id"] for archetype in self.registry["archetypes"]]
        self.assertEqual(len(ids), len(set(ids)), "archetype ids must be unique")
        for legacy in ("scenario-b", "scenario-c", "harness-architecture"):
            self.assertIn(legacy, ids,
                          "legacy templates stay registered (never removed/renamed)")
        shorts = [a for a in self.registry["archetypes"] if a["kind"] == "shorts"]
        social = [a for a in self.registry["archetypes"] if a["kind"] == "social"]
        self.assertGreaterEqual(len(shorts), 4)
        self.assertGreaterEqual(len(social), 3)
        self.assertEqual(
            {"shorts", "social"}, {a["kind"] for a in self.registry["archetypes"]})

    def test_registry_points_at_an_existing_sourced_research_brief(self):
        brief = ROOT / self.registry["research_brief"]
        self.assertTrue(brief.is_file(), f"missing research brief: {brief}")
        text = brief.read_text()
        self.assertIn("https://", text, "research brief must cite URLs")
        self.assertIn("Sources", text)

    def test_every_registered_template_exists_and_is_parseable_html(self):
        for archetype in self.registry["archetypes"]:
            path = TEMPLATE_ROOT / archetype["file"]
            label = archetype["id"]
            self.assertTrue(path.is_file(), f"{label}: missing template {path}")
            source = path.read_text()
            self.assertRegex(source, r"(?i)<!doctype html>",
                             msg=f"{label}: must be a doctype HTML document")
            self.assertTrue(source.rstrip().endswith("</html>"),
                            f"{label}: must close with </html>")
            self.assertIn("<html", source, f"{label}: missing <html> root")
            for tag in ("style", "script"):
                self.assertEqual(
                    source.count(f"<{tag}"), source.count(f"</{tag}>"),
                    f"{label}: unbalanced <{tag}> tags")
            self.assertIn("data-theme", source, f"{label}: theme pin required")

    def test_registered_templates_use_only_boxicons_and_no_circle_variants(self):
        for archetype in self.registry["archetypes"]:
            path = TEMPLATE_ROOT / archetype["file"]
            label = archetype["id"]
            source = path.read_text()
            class_tokens = set()
            for group in re.findall(r'class="([^"]+)"', source):
                class_tokens.update(group.split())
            icon_tokens = {t for t in class_tokens if t.startswith("bx")}
            # Icon use is optional per archetype (single-fact is text-led);
            # the contract is: any icon class must be a real boxicon, never a
            # circle variant, and no foreign icon set may appear.
            for token in icon_tokens:
                if token == "bx":
                    continue  # the shared boxicons base class
                self.assertRegex(
                    token, r"^bx[l|s]?-",
                    f"{label}: non-boxicon class {token!r}")
                self.assertNotIn("circle", token,
                                 f"{label}: circle variant {token!r} is banned")
                self.assertIn(f".{token}", self.boxicons,
                              f"{label}: unknown boxicon {token!r}")
            for foreign in ("fa-", "lucide", "heroicon", "mdi-", "tabler-"):
                self.assertNotIn(foreign, source,
                                 f"{label}: foreign icon set prefix {foreign}")

    def test_registered_templates_reference_only_semantic_tokens(self):
        for archetype in self.registry["archetypes"]:
            path = TEMPLATE_ROOT / archetype["file"]
            label = archetype["id"]
            source = path.read_text()
            local = set(re.findall(r"(--[a-zA-Z0-9-]+)\s*:", source))
            referenced = set(re.findall(r"var\((--[a-zA-Z0-9-]+)\)", source))
            unknown = referenced - local - self.tokens
            self.assertEqual(set(), unknown,
                             f"{label}: non-token var() references: "
                             f"{sorted(unknown)}")

    def test_selection_rule_never_repeats_a_template_in_a_batch(self):
        rule = self.registry["selection_rule"]
        joined = rule["summary"] + " " + " ".join(rule["rules"])
        self.assertIn("No template is used twice within one batch", joined)
        self.assertIn("control", joined)
        self.assertIn("variant", joined)
        self.assertIn("item_id", joined)
        readme = (ROOT / "company/departments/design/README.md").read_text()
        self.assertIn("no batch repeats one template", readme.lower())
        skill = (ROOT / "company/departments/design/skills/video-creation/SKILL.md").read_text()
        self.assertIn("registry.json", skill)
        self.assertIn("No batch repeats one template", skill)


class SocialWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.prospect = {
            "lead_id": "lead-1", "name": "Alex Operator", "company": "Example Ops",
            "role": "COO", "channel": "linkedin",
            "profile_url": "https://linkedin.com/in/alex-operator", "icp_score": 88,
            "research_fact": "Expanded the staffing operation into Germany",
            "operational_consequence": "More cross-border candidate handoffs",
            "source_urls": ["https://example.com/news/germany"],
        }

    def test_social_prospect_requires_icp_research_and_sources(self):
        self.assertIsNotNone(social.normalize_prospect(self.prospect))
        self.assertIsNone(social.normalize_prospect({**self.prospect, "source_urls": []}))

    def test_dm_must_link_to_research_and_fit_channel(self):
        prospect = social.normalize_prospect(self.prospect)
        draft = {"lead_id": "lead-1", "channel": "linkedin",
                 "message": "The Germany expansion probably adds candidate handoffs. Is that routing still manual?"}
        self.assertIsNotNone(social.normalize_dm(draft, {"lead-1": prospect}))
        self.assertIsNone(social.normalize_dm({**draft, "message": "Generic AI pitch"}, {"lead-1": prospect}))

    def test_outbound_social_goal_requests_agent_then_evaluates_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime = Runtime(Path(tmp) / "company.sqlite")
            goal = runtime.create_goal(
                name="Research one social prospect", owner_id="outbound",
                metric="qualified_social_leads", operator="ge", target=1,
                deadline=None, config={"workflow": "social-lead-research", "required_count": 1},
                goal_id="goal-social-test", run_type="system_test",
                evidence_validity="technical_only")
            blocked = runtime.once(goal["id"])
            self.assertEqual(blocked["cycle"]["run_status"], "blocked")
            self.assertEqual(blocked["cycle"]["data"]["action_result"]["agent_id"], "social-researcher")
            open_orders = runtime.store.work_orders(status="open", goal_id=goal["id"])
            self.assertEqual(1, len(open_orders))
            self.assertEqual("social-researcher", open_orders[0]["employee_id"])
            self.assertEqual(["social_prospect"], open_orders[0]["accepts_evidence"])
            self.assertEqual(1, open_orders[0]["needed"])
            runtime.add_evidence(goal["id"], kind="social_prospect", source="social-researcher",
                                 payload=self.prospect, validity="technical_only")
            self.assertEqual([], runtime.store.work_orders(status="open", goal_id=goal["id"]))
            done = runtime.store.work_orders(status="done", goal_id=goal["id"])
            self.assertEqual(1, len(done))
            self.assertEqual(1, len(done[0]["result_evidence_ids"]))
            runtime.retry(goal["id"])
            completed = runtime.once(goal["id"])
            self.assertEqual(completed["goal"]["goal_status"], "achieved")
            self.assertEqual(completed["evaluation"]["metrics"]["qualified_social_leads"], 1)


if __name__ == "__main__":
    unittest.main()
