from __future__ import annotations

import unittest

import pandas as pd

from sourcing.build_a_discovered_companies_shadow import build_a_suggestions


class BuildADiscoveredCompaniesShadowTests(unittest.TestCase):
    def test_known_company_is_not_suggested(self) -> None:
        candidates = pd.DataFrame([
            {"company": "Known Co", "title": "Treasury Analyst", "country_bucket": "Germany", "source_streams": "board"},
            {"company": "New Co", "title": "M&A Analyst", "country_bucket": "Germany", "source_streams": "board"},
        ])
        universe = pd.DataFrame([
            {"company": "Known Co", "aliases_entities": "Known Company"},
        ])
        result = build_a_suggestions(candidates, universe)
        self.assertEqual(result["company"].tolist(), ["New Co"])
        self.assertEqual(result.iloc[0]["suggested_rating"], "Unrated")

    def test_repeated_sightings_are_grouped_without_rating_inference(self) -> None:
        candidates = pd.DataFrame([
            {"company": "New Co", "title": "Treasury Analyst", "country_bucket": "Germany", "source_streams": "board", "last_seen_at": "2026-08-25T08:00:00Z"},
            {"company": "New Co", "title": "Corporate Finance Analyst", "country_bucket": "Austria", "source_streams": "company", "last_seen_at": "2026-08-25T09:00:00Z"},
        ])
        result = build_a_suggestions(candidates, pd.DataFrame(columns=["company", "aliases_entities"]))
        self.assertEqual(len(result), 1)
        row = result.iloc[0]
        self.assertEqual(int(row["role_count"]), 2)
        self.assertEqual(row["countries"], "Austria; Germany")
        self.assertEqual(row["source_streams"], "board; company")
        self.assertEqual(row["suggested_rating"], "Unrated")


if __name__ == "__main__":
    unittest.main()
