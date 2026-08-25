from __future__ import annotations

import unittest

import pandas as pd

from sourcing.build_discovered_employers_shadow import build_discovered_employers


class DiscoveredEmployersShadowTests(unittest.TestCase):
    def test_known_canonical_company_is_not_emitted(self) -> None:
        universe = pd.DataFrame([{"canonical_company_id": "known", "company": "Known AG", "aliases_entities": "Known"}])
        candidates = pd.DataFrame([{"company": "Known AG", "canonical_company_id": "known", "title": "Treasury", "source_streams": "company"}])
        result = build_discovered_employers(candidates, pd.DataFrame(), [universe])
        self.assertTrue(result.empty)

    def test_company_variant_is_alias_candidate_not_new_preference(self) -> None:
        universe = pd.DataFrame([{"canonical_company_id": "sparkasse-ooe", "company": "Sparkasse OÖ Investment GmbH", "aliases_entities": ""}])
        candidates = pd.DataFrame([{
            "company": "Sparkasse OÖ Investment", "canonical_company_id": "", "title": "Risk Manager",
            "source_streams": "board", "country_bucket": "Austria", "job_url": "https://example.com/job",
        }])
        result = build_discovered_employers(candidates, pd.DataFrame(), [universe])
        self.assertEqual(len(result), 1)
        row = result.iloc[0]
        self.assertEqual(row["discovery_status"], "possible_alias_of_existing")
        self.assertEqual(row["possible_existing_company_id"], "sparkasse-ooe")
        self.assertEqual(row["suggested_initial_rating"], "Unrated")

    def test_new_company_is_unrated_and_aggregates_g_and_b_observations(self) -> None:
        candidates = pd.DataFrame([{
            "company": "NewCo Ltd", "canonical_company_id": "", "title": "Treasury Analyst",
            "source_streams": "board", "country_bucket": "United Kingdom", "job_url": "https://newco.com/job/1",
        }])
        submissions = pd.DataFrame([{
            "company": "NewCo", "canonical_company_id": "", "title": "Treasury Manager",
            "country": "United Kingdom", "job_url": "https://newco.com/job/2",
        }])
        result = build_discovered_employers(candidates, submissions, [pd.DataFrame()])
        self.assertEqual(len(result), 1)
        row = result.iloc[0]
        self.assertEqual(row["discovery_status"], "new_company_candidate")
        self.assertEqual(int(row["observation_count"]), 2)
        self.assertIn("board", row["source_streams"])
        self.assertIn("B", row["source_streams"])
        self.assertEqual(row["suggested_initial_rating"], "Unrated")


if __name__ == "__main__":
    unittest.main()
