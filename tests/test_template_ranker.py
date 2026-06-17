#!/usr/bin/env python3
"""test_template_ranker.py — Tests for the template ranking engine."""

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import template_ranker


SAMPLE_REGISTRY = {
    "version": 1,
    "platforms": {
        "x": {
            "categories": [
                {
                    "id": "listicle",
                    "name": "Listicle",
                    "defaults": {
                        "psych_triggers": ["greed", "curiosity"],
                        "anti_patterns": ["generic_advice"],
                        "body": "list",
                        "best_for": {
                            "archetypes": ["S4", "S8"],
                            "meaning_axes": ["leverage"],
                            "funnel_stages": ["TOFU"],
                            "icp_layers": ["L1"],
                        },
                    },
                    "templates": [
                        {
                            "id": "x-listicle-01",
                            "name": "7 free tools",
                            "hook": "7 free tools for {persona} to {result}: {list}",
                            "cta": "Bookmark this",
                        },
                        {
                            "id": "x-listicle-02",
                            "name": "Steal these N",
                            "hook": "Steal these {number} {assets} that {result}: {list}",
                            "cta": "RT for your network",
                        },
                    ],
                },
                {
                    "id": "story",
                    "name": "Story",
                    "defaults": {
                        "psych_triggers": ["hope", "fear"],
                        "anti_patterns": ["no_emotion"],
                        "body": "narrative",
                        "best_for": {
                            "archetypes": ["S4", "S5"],
                            "meaning_axes": ["human"],
                            "funnel_stages": ["TOFU", "MOFU"],
                            "icp_layers": ["L3"],
                        },
                    },
                    "templates": [
                        {
                            "id": "x-story-01",
                            "name": "I went from low to high",
                            "hook": "I went from {low} to {high} in {time}. Here's how:",
                            "cta": "Follow for the blueprint",
                        },
                    ],
                },
            ],
        },
    },
}


class TestSubstanceScore(unittest.TestCase):
    def test_substance_hook(self):
        t = {"hook": "This is a real hook with content", "cta": "Follow me"}
        score = template_ranker._substance_score(t)
        self.assertGreater(score, 0.5)

    def test_substance_slot_heavy(self):
        t = {"hook": "{a} {b} {c} {d} {e}", "cta": "{x}"}
        score = template_ranker._substance_score(t)
        self.assertLess(score, 0.5)

    def test_substance_empty_hook(self):
        t = {"hook": "", "cta": ""}
        score = template_ranker._substance_score(t)
        self.assertEqual(score, 0.0)


class TestArchetypeBreadth(unittest.TestCase):
    def test_full_coverage(self):
        t = {
            "best_for": {
                "archetypes": ["S1", "S2", "S3"],
                "meaning_axes": ["leverage", "systemic", "behavioral"],
                "funnel_stages": ["TOFU", "MOFU"],
                "icp_layers": ["L1", "L2"],
            }
        }
        score = template_ranker._archetype_breadth(t)
        self.assertGreater(score, 0.7)

    def test_empty(self):
        score = template_ranker._archetype_breadth({})
        self.assertEqual(score, 0.0)


class TestPsychMatch(unittest.TestCase):
    def test_no_triggers(self):
        self.assertEqual(template_ranker._psych_match_score({}), 0.0)

    def test_high_arousal(self):
        t = {"psych_triggers": ["fear", "curiosity"]}
        score = template_ranker._psych_match_score(t)
        self.assertGreater(score, 0.5)


class TestAntiDensity(unittest.TestCase):
    def test_no_anti(self):
        self.assertEqual(template_ranker._anti_density_penalty({}), 0.0)

    def test_some_anti(self):
        score = template_ranker._anti_density_penalty({"anti_patterns": ["x", "y", "z"]})
        self.assertGreater(score, 0.5)


class TestEngagementScore(unittest.TestCase):
    def test_no_data(self):
        score, n = template_ranker._engagement_score("x-listicle-01", {})
        self.assertEqual(score, 0.0)
        self.assertEqual(n, 0)

    def test_with_data(self):
        perf = {"x-listicle-01": {"posts": 10, "avg_rate": 0.05}}
        score, n = template_ranker._engagement_score("x-listicle-01", perf)
        self.assertEqual(n, 10)
        self.assertGreater(score, 0.0)


class TestScoreTemplate(unittest.TestCase):
    def test_returns_dict(self):
        t = {
            "id": "x-listicle-01",
            "name": "Test",
            "hook": "Real hook with content",
            "cta": "Follow me",
            "psych_triggers": ["greed"],
            "anti_patterns": ["generic"],
            "best_for": {
                "archetypes": ["S4"],
                "meaning_axes": ["leverage"],
                "funnel_stages": ["TOFU"],
                "icp_layers": ["L1"],
            },
        }
        result = template_ranker.score_template(t)
        self.assertIn("score", result)
        self.assertIn("components", result)
        self.assertGreater(result["score"], 0)

    def test_with_category_priors(self):
        t = {
            "id": "x-test",
            "name": "Test",
            "hook": "Real hook",
            "category": "ship_log",
        }
        priors = {"ship_log": {"multiplier": 1.5}}
        result = template_ranker.score_template(t, category_priors=priors)
        self.assertEqual(result["prior_multiplier"], 1.5)


class TestRankAll(unittest.TestCase):
    def test_returns_sorted(self):
        results = template_ranker.rank_all(SAMPLE_REGISTRY)
        self.assertEqual(len(results), 3)
        scores = [r["score"] for r in results]
        self.assertEqual(scores, sorted(scores, reverse=True))


class TestCurateTopN(unittest.TestCase):
    def test_keeps_top_n(self):
        ranked = template_ranker.rank_all(SAMPLE_REGISTRY)
        curated = template_ranker.curate_top_n(SAMPLE_REGISTRY, ranked, top_n=1)
        for plat_id, plat_data in curated.get("platforms", {}).items():
            for cat in plat_data.get("categories", []):
                n = len(cat.get("templates", []))
                self.assertLessEqual(n, 1)


class TestLoadSave(unittest.TestCase):
    def test_load_performance_missing(self):
        missing = Path("/tmp/does_not_exist_perf_xyz")
        perf = template_ranker.load_performance(missing)
        self.assertEqual(perf, {})


class TestCategoryPriorMultiplier(unittest.TestCase):
    def test_no_prior(self):
        self.assertEqual(
            template_ranker._category_prior_multiplier({"category": "x"}, {}),
            1.0,
        )

    def test_with_prior(self):
        result = template_ranker._category_prior_multiplier(
            {"category": "ship_log"},
            {"ship_log": {"multiplier": 1.4}},
        )
        self.assertEqual(result, 1.4)


if __name__ == "__main__":
    unittest.main(verbosity=2)
