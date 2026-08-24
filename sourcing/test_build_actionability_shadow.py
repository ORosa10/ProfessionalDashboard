from __future__ import annotations

import unittest

import pandas as pd

from sourcing.build_actionability_shadow import evaluate_actionability


POLICY = {
    "target_geographies": ["Germany", "Austria", "Switzerland", "United Kingdom", "Czechia", "Sweden", "Norway", "Denmark", "Finland"],
    "hard_blockers": {
        "explicit_vacancy_status": ["Closed", "Expired", "Removed"],
        "confirmed_dead_link": ["404", "410", "dead"],
    },
    "warnings_not_blockers": {
        "old_posting_days": 45,
        "stale_last_seen_days": 7,
    },
}


class ActionabilityShadowTests(unittest.TestCase):
    def _evaluate(self, row: dict) -> pd.Series:
        base = {
            "candidate_id": "cand",
            "job_id": "job",
            "company": "Example",
            "title": "Treasury Analyst",
            "country_bucket": "Germany",
            "market": "Germany",
            "location": "Frankfurt",
            "status": "Open",
            "job_url": "https://example.com/job",
            "description_en": "",
            "last_seen_at": "2026-08-24",
            "date_posted": "2026-08-20",
        }
        base.update(row)
        result = evaluate_actionability(pd.DataFrame([base]), pd.DataFrame(), POLICY, as_of="2026-08-24")
        return result.iloc[0]

    def test_german_c1_is_blocker_b2_is_not(self) -> None:
        blocked = self._evaluate({"description_en": "German C1 is required."})
        self.assertFalse(bool(blocked["actionable"]))
        self.assertIn("German C1", blocked["language_blocker"])

        allowed = self._evaluate({"description_en": "German B2 is required."})
        self.assertTrue(bool(allowed["actionable"]))

    def test_mandatory_nordic_language_blocks_preferred_does_not(self) -> None:
        blocked = self._evaluate({"description_en": "Fluent Norwegian is required."})
        self.assertFalse(bool(blocked["actionable"]))
        self.assertIn("Mandatory Norwegian", blocked["language_blocker"])

        allowed = self._evaluate({"description_en": "Norwegian is an advantage but not required."})
        self.assertTrue(bool(allowed["actionable"]))

    def test_explicit_outside_target_geography_blocks(self) -> None:
        row = self._evaluate({"country_bucket": "Poland", "market": "Poland", "location": "Warsaw, Poland"})
        self.assertFalse(bool(row["actionable"]))
        self.assertIn("geography:Poland", row["blockers"])

    def test_structured_outside_iso_code_blocks_but_prose_in_does_not(self) -> None:
        outside = self._evaluate({"country_bucket": "Other / Unresolved", "market": "Multi-region", "location": "Warsaw, Europe, PL"})
        self.assertFalse(bool(outside["actionable"]))
        self.assertIn("geography:PL", outside["blockers"])

        prose = self._evaluate({"country_bucket": "Other / Unresolved", "market": "Remote", "location": "Remote in Europe"})
        self.assertTrue(bool(prose["actionable"]))
        self.assertIn("geography:needs_resolution", prose["warnings"])

    def test_unresolved_geography_warns_but_does_not_block(self) -> None:
        row = self._evaluate({"country_bucket": "Other / Unresolved", "market": "Multi-region", "location": ""})
        self.assertTrue(bool(row["actionable"]))
        self.assertIn("geography:needs_resolution", row["warnings"])

    def test_missing_or_confirmed_dead_link_blocks(self) -> None:
        missing = self._evaluate({"job_url": ""})
        self.assertFalse(bool(missing["actionable"]))
        self.assertIn("link:missing_job_url", missing["blockers"])

        dead = self._evaluate({"link_health": "404"})
        self.assertFalse(bool(dead["actionable"]))
        self.assertIn("link:404", dead["blockers"])

    def test_unknown_work_authorization_is_warning_only(self) -> None:
        row = self._evaluate({"description_en": "Candidates must already have the right to work in Germany; no visa sponsorship."})
        self.assertTrue(bool(row["actionable"]))
        self.assertIn("work_authorization:manual_check", row["warnings"])

    def test_semantic_fit_is_carried_as_context_not_changed(self) -> None:
        candidates = pd.DataFrame([{
            "candidate_id": "c1", "job_id": "x", "company": "A", "title": "Risk",
            "country_bucket": "Germany", "market": "Germany", "location": "Frankfurt",
            "status": "Open", "job_url": "https://example.com/x",
        }])
        semantic = pd.DataFrame([{"opportunity_id": "x", "fit": "Strong"}])
        result = evaluate_actionability(candidates, semantic, POLICY, as_of="2026-08-24")
        self.assertEqual(result.iloc[0]["semantic_fit"], "Strong")


if __name__ == "__main__":
    unittest.main()
