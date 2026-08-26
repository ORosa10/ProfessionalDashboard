from __future__ import annotations

import unittest
import pandas as pd

from sourcing.build_b_company_suggestions import build_suggestions


class BCompanySuggestionTests(unittest.TestCase):
    def test_manual_application_becomes_unrated_a_suggestion(self) -> None:
        submissions = pd.DataFrame([{
            "submission_id": "1", "submitted_at": "2026-08-26T10:00:00+00:00",
            "company": "Example Treasury AG", "canonical_company_id": "example-treasury",
            "country": "Germany", "title": "Treasury Analyst",
        }])
        out = build_suggestions(submissions)
        self.assertEqual(len(out), 1)
        row = out.iloc[0]
        self.assertEqual(row["suggested_company_id"], "example-treasury")
        self.assertEqual(row["suggested_rating"], "Unrated")
        self.assertEqual(row["source_streams"], "B")

    def test_research_can_fill_missing_company_identity(self) -> None:
        submissions = pd.DataFrame([{
            "submission_id": "1", "submitted_at": "2026-08-26T10:00:00+00:00",
            "company": "", "canonical_company_id": "", "country": "", "title": "",
        }])
        research = pd.DataFrame([{
            "submission_id": "1", "company": "Research Filled plc",
            "canonical_company_id": "research-filled", "country": "United Kingdom",
            "title": "Corporate Finance Analyst",
        }])
        out = build_suggestions(submissions, research)
        self.assertEqual(out.iloc[0]["suggested_company_id"], "research-filled")
        self.assertIn("Corporate Finance Analyst", out.iloc[0]["sample_titles"])


if __name__ == "__main__":
    unittest.main()
