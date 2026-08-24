"""Change task change-8e1130b073 (goal-bbdb31c1b0) acceptance tests — proven-
pattern gates in compose.

The proven outbound pattern (strategy.md PROVEN PATTERN RULES 1-4, locked
2026-08-18): only researched owner-operator leads with firm-specific pain
and a per-lead hook are sendable (EN-1358 SDG Accountant, EN-1157 Sigma
Recruitment — both produced qualified replies). The anti-pattern is the
GCA bulk-framework cohort (EN-1419/1508/1834 + ~321 more): title "Named
framework contact", segment-generic verbatim pain, GCA CSV source — that
324-run produced 0 replies / 3 clicks at 51% opens.

Covered:
  - accepted: owner-operator title + firm-specific pain + per-lead hook
    composes (SDG pattern, Sigma pattern — regression);
  - rejected: "Named framework contact" title + segment-generic pain;
  - rejected: pain containing an RM#### framework identifier;
  - rejected: pain exactly matching a known segment-generic signature
    (normalized, punctuation/case-insensitive);
  - rejected: bulk-list source signature even when research looks complete;
  - kept: English STRICT skip reasons and the Persian template ladder
    (the gate guards the English STRICT path only);
  - batch path: bulk leads are skipped with an "unprepared" reason, never
    composed into the batch.

Hermetic: synthetic contacts only; no network, no real sends.
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from company.departments.outbound.workflows.email import compose  # noqa: E402

# Proven-pattern leads modeled on the real master rows (EN-1358, EN-1157).
SDG_ACCOUNTANT = {
    "lead_id": "EN-1358",
    "email": "sami@sdgaccountant.com",
    "company": "SDG Accountant",
    "contact_name": "Sami Ghaith",
    "title": "Founder & Managing Director",
    "segment": "accounting and bookkeeping",
    "country": "Canada",
    "language": "English",
    "send_recommendation": "Ready to personalized",
    "outreach_tier": "A",
    "email_status": "Publicly listed; not deliverability-verified",
    "personalization_hook": ("Reference Sami Ghaith's role as Founder and Managing "
                             "Director and one observable a cross-border tax practice "
                             "serving Canadian and US clients."),
    "pain_hypothesis": ("Compliance and advisory work runs on manual document "
                        "gathering and filing coordination per client."),
    "source": "Director web research 2026-08-12",
    "source_url": "https://accountingtoronto.ca/teams/sami-ghaith/",
}

SIGMA_RECRUITMENT = {
    "lead_id": "EN-1157",
    "email": "rhys@sigmarecruitment.co.uk",
    "company": "Sigma Recruitment",
    "contact_name": "Rhys Williams",
    "title": "Founder & Managing Director",
    "segment": "Recruitment & staffing",
    "country": "United Kingdom",
    "language": "English",
    "send_recommendation": "Ready to personalized",
    "outreach_tier": "A",
    "email_status": "Publicly listed; not deliverability-verified",
    "personalization_hook": ("Reference Rhys Williams's role as Founder & Managing "
                             "Director at Sigma Recruitment"),
    "pain_hypothesis": ("Engineering and manufacturing candidate shortlisting at "
                        "Sigma runs on manual consultant network sourcing per role."),
    "source": "Company website",
    "suggested_cta": "map the shortlist stage with you",
}

# Anti-pattern lead modeled on the real GCA bulk cohort (EN-1419).
GCA_BULK_LEAD = {
    "lead_id": "EN-1419",
    "email": "cheryl.denham@athona.com",
    "company": "ATHONA LIMITED",
    "contact_name": "Cheryl Denham",
    "title": "Named framework contact",
    "segment": "Recruitment & staffing",
    "country": "United Kingdom",
    "language": "English",
    "send_recommendation": "Ready to personalized",
    "outreach_tier": "A",
    "email_status": "Publicly listed; not deliverability-verified",
    "personalization_hook": ("Reference Cheryl Denham's role as a named framework "
                             "contact and one observable RM6281 Clinical & Healthcare "
                             "Staffing supplier in Medical Staffing | AHP/HSS/Emergency "
                             "| Nursing & Midwifery."),
    "pain_hypothesis": ("Clinical and healthcare staffing runs on manual candidate "
                        "sourcing, compliance handling and placement administration "
                        "per role."),
    "source": "GCA framework public supplier contacts 2026-08-12",
    "source_url": "https://www.gca.gov.uk/agreements/RM6281%3A2/lot-suppliers/csv",
}

GCA_GENERIC_PAIN = (
    "Clinical and healthcare staffing runs on manual candidate sourcing, "
    "compliance handling and placement administration per role."
)

ENGLISH_STRICT_REASON = (
    "unprepared: no parseable hook + pain research — prepare content before send"
)


class ProvenPatternAcceptedTests(unittest.TestCase):
    """The proven converting class must still compose (regression)."""

    def test_sdg_owner_operator_pattern_composes(self):
        subject, html, text, reason = compose.render_checked(SDG_ACCOUNTANT, seq=0)
        self.assertIsNone(reason)
        self.assertIn("SDG Accountant", subject)
        self.assertIn("Sami", text)
        self.assertIn("Compliance and advisory work", text)

    def test_sigma_owner_operator_pattern_composes(self):
        subject, html, text, reason = compose.render_checked(SIGMA_RECRUITMENT, seq=0)
        self.assertIsNone(reason)
        self.assertIn("Sigma Recruitment", subject)
        self.assertIn("Rhys", text)
        self.assertIn("shortlist", text.casefold())

    def test_accepted_leads_clear_the_proven_pattern_gate(self):
        for lead in (SDG_ACCOUNTANT, SIGMA_RECRUITMENT):
            self.assertIsNone(compose._proven_pattern_violation(lead), lead["lead_id"])

    def test_batch_keeps_accepted_leads(self):
        built = compose.build_batch_emails("B1", [SDG_ACCOUNTANT, SIGMA_RECRUITMENT], "h")
        self.assertEqual(len(built["emails"]), 2)
        self.assertEqual(built["skipped"], [])


class ProvenPatternRejectedTests(unittest.TestCase):
    """Bulk/framework anti-pattern leads are skipped 'unprepared', never sent."""

    def _assert_unprepared(self, lead):
        subject, html, text, reason = compose.render_checked(lead, seq=0)
        self.assertIsNone(subject, lead["lead_id"])
        self.assertIsNotNone(reason, lead["lead_id"])
        self.assertIn("unprepared", reason)
        return reason

    def test_named_framework_contact_title_rejected(self):
        # Real GCA row: list-signature title + segment-generic pain + bulk source.
        reason = self._assert_unprepared(GCA_BULK_LEAD)
        self.assertIn("title is a list/framework signature", reason)

    def test_title_markers_are_case_insensitive_and_cover_variants(self):
        good = dict(SDG_ACCOUNTANT, title="Founder & Managing Director")
        for marker in ("Named framework contact", "NAMED FRAMEWORK CONTACT",
                       "Framework contact", "Named contact", "Supplier contact",
                       "List contact", "Bulk contact"):
            lead = dict(good, lead_id=f"EN-{abs(hash(marker)) % 100000}",
                        title=marker,
                        personalization_hook=(
                            f"Reference Jane Doe's role as {marker} and one "
                            "observable fact about the company") )
            with self.subTest(marker=marker):
                reason = self._assert_unprepared(lead)
                self.assertIn("title is a list/framework signature", reason)

    def test_pain_with_framework_id_rejected(self):
        # Owner title + plausible pain, but the pain names an RM#### framework:
        # it is bulk-list data, not per-lead research.
        lead = dict(SDG_ACCOUNTANT, lead_id="EN-2000",
                    pain_hypothesis=(
                        "Clinical staffing at Acme runs on manual sourcing per role "
                        "under the RM6281 framework supplier list."))
        reason = self._assert_unprepared(lead)
        self.assertIn("pain_hypothesis is segment-generic", reason)

    def test_segment_generic_pain_exact_match_rejected_even_with_owner_title(self):
        # Owner title alone does not save a lead whose pain is the verbatim
        # segment-generic signature (the pain gate is independent of the title).
        lead = dict(SDG_ACCOUNTANT, lead_id="EN-2001",
                    pain_hypothesis=GCA_GENERIC_PAIN,
                    personalization_hook=(
                        "Reference Jane Doe's role as Founder and Managing Director "
                        "and one observable fact about the company"))
        reason = self._assert_unprepared(lead)
        self.assertIn("pain_hypothesis is segment-generic", reason)

    def test_segment_generic_pain_match_is_normalized(self):
        # Punctuation/case/whitespace variants normalize to the same signature.
        variants = (
            GCA_GENERIC_PAIN,
            GCA_GENERIC_PAIN.upper(),
            "Clinical and healthcare staffing runs on manual candidate sourcing; "
            "compliance handling and placement administration per role!!",
            "  clinical and healthcare staffing runs on manual candidate sourcing,"
            "compliance handling and placement administration per role.  ",
        )
        for i, pain in enumerate(variants):
            lead = dict(SDG_ACCOUNTANT, lead_id=f"EN-210{i}",
                        pain_hypothesis=pain)
            with self.subTest(i=i):
                self.assertIn(compose._normalize_pain(pain),
                              compose.SEGMENT_GENERIC_PAINS)
                self._assert_unprepared(lead)

    def test_second_gca_signature_rejected(self):
        # EN-1508's verbatim pain (supply teacher / support staff placement).
        pain = ("Supply teacher and support staff placement runs on manual "
                "candidate matching, school chasing and compliance tracking "
                "per booking.")
        lead = dict(SDG_ACCOUNTANT, lead_id="EN-2002", pain_hypothesis=pain)
        self.assertIn(compose._normalize_pain(pain), compose.SEGMENT_GENERIC_PAINS)
        self._assert_unprepared(lead)

    def test_bulk_source_rejected_even_with_complete_research(self):
        # RULE 1.2: a GCA framework export is not a sendable source even when
        # the row looks researched — source + URL carry the bulk signature.
        lead = dict(SDG_ACCOUNTANT, lead_id="EN-2003",
                    source="GCA framework public supplier contacts 2026-08-12",
                    source_url="https://www.gca.gov.uk/agreements/RM6281%3A2/lot-suppliers/csv")
        reason = self._assert_unprepared(lead)
        self.assertIn("source is an unresearched bulk supplier list", reason)

    def test_bulk_source_url_alone_rejected(self):
        # CSV/lot-suppliers URL marks the bulk export even if the source text
        # is terse.
        lead = dict(SDG_ACCOUNTANT, lead_id="EN-2004",
                    source="GCA list",
                    source_url="https://www.gca.gov.uk/agreements/RM6376%3A1/lot-suppliers/3")
        reason = self._assert_unprepared(lead)
        self.assertIn("source is an unresearched bulk supplier list", reason)

    def test_batch_skips_bulk_lead_with_reason(self):
        built = compose.build_batch_emails(
            "B1", [SDG_ACCOUNTANT, GCA_BULK_LEAD, SIGMA_RECRUITMENT], "h")
        self.assertEqual([e["lead_id"] for e in built["emails"]],
                         ["EN-1358", "EN-1157"])
        self.assertEqual([s["lead_id"] for s in built["skipped"]], ["EN-1419"])
        self.assertIn("unprepared", built["skipped"][0]["reason"])


class GateScopePreservationTests(unittest.TestCase):
    """English STRICT skip reasons and the Persian ladder are untouched."""

    def test_english_missing_hook_reason_unchanged(self):
        lead = dict(SDG_ACCOUNTANT, lead_id="EN-3000", personalization_hook="")
        subject, *_rest, reason = compose.render_checked(lead, seq=0)
        self.assertIsNone(subject)
        self.assertEqual(reason, ENGLISH_STRICT_REASON)

    def test_english_short_pain_reason_unchanged(self):
        lead = dict(SDG_ACCOUNTANT, lead_id="EN-3001",
                    pain_hypothesis="They have staffing work")
        subject, *_rest, reason = compose.render_checked(lead, seq=0)
        self.assertIsNone(subject)
        self.assertEqual(reason, ENGLISH_STRICT_REASON)

    def test_english_placeholder_pain_reason_unchanged(self):
        lead = dict(SDG_ACCOUNTANT, lead_id="EN-3002",
                    pain_hypothesis="The company likely has a staffing workflow")
        subject, *_rest, reason = compose.render_checked(lead, seq=0)
        self.assertIsNone(subject)
        self.assertEqual(reason, ENGLISH_STRICT_REASON)

    def test_persian_template_ladder_untouched(self):
        # A Persian lead with every anti-pattern field still composes via the
        # prepared Persian ladder — the gate guards the English STRICT path only.
        lead = {
            "lead_id": "FA-1",
            "email": "owner@acme-fa.com",
            "company": "Acme Persian",
            "contact_name": "علی رضایی",
            "title": "Named framework contact",
            "segment": "recruitment agency",
            "country": "United Kingdom",
            "language": "Persian",
            "send_recommendation": "Ready to personalized",
            "email_status": "Verified",
            "personalization_hook": ("Reference Ali's role as a named framework "
                                     "contact and one observable RM6281 supplier"),
            "pain_hypothesis": ("Clinical staffing runs on manual sourcing RM6281 "
                                "per role."),
            "source": "GCA framework public supplier contacts 2026-08-12",
        }
        subject, html, text, reason = compose.render_checked(lead, seq=0)
        self.assertIsNone(reason)
        self.assertIsNotNone(subject)
        self.assertIn("علی", text)


class GenericPainRegistryTests(unittest.TestCase):
    def test_registry_contains_forbidden_observations(self):
        # Every non-template FORBIDDEN_OBSERVATIONS sentence is a known
        # segment-generic signature in the registry.
        for obs in compose.FORBIDDEN_OBSERVATIONS:
            if "{" not in obs:
                self.assertIn(compose._normalize_pain(obs),
                              compose.SEGMENT_GENERIC_PAINS, obs)

    def test_registry_contains_gca_cohort_signatures(self):
        self.assertIn(
            compose._normalize_pain(GCA_GENERIC_PAIN), compose.SEGMENT_GENERIC_PAINS)
        self.assertIn(
            compose._normalize_pain(
                "Supply teacher and support staff placement runs on manual "
                "candidate matching, school chasing and compliance tracking "
                "per booking."),
            compose.SEGMENT_GENERIC_PAINS)

    def test_firm_specific_pains_are_not_in_the_registry(self):
        for lead in (SDG_ACCOUNTANT, SIGMA_RECRUITMENT):
            self.assertNotIn(compose._normalize_pain(lead["pain_hypothesis"]),
                             compose.SEGMENT_GENERIC_PAINS, lead["lead_id"])


if __name__ == "__main__":
    unittest.main()
