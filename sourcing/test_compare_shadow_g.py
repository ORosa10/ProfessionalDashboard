from __future__ import annotations

import unittest

import pandas as pd

from sourcing.compare_shadow_g import compare_reference, country_supply


class ShadowComparisonTests(unittest.TestCase):
    def test_reference_match_prefers_job_id_and_reports_missing(self) -> None:
        shadow = pd.DataFrame([
            {
                "candidate_id": "cand1",
                "job_id": "job1",
                "company": "A",
                "title": "Treasury Analyst",
                "job_url": "https://example.com/job/1",
                "source_streams": "corporate",
                "country_bucket": "Germany",
            }
        ])
        reference = pd.DataFrame([
            {
                "job_id": "job1",
                "company": "A",
                "title": "Treasury Analyst",
                "job_url": "https://different.example/job/1",
                "semantic_fit": "Strong",
                "curated_rank": 1,
            },
            {
                "job_id": "job2",
                "company": "B",
                "title": "Risk Analyst",
                "job_url": "https://example.com/job/2",
                "semantic_fit": "Strong",
                "curated_rank": 2,
            },
        ])
        report = compare_reference(shadow, reference)
        by_id = report.set_index("job_id")
        self.assertTrue(bool(by_id.loc["job1", "found_in_shadow"]))
        self.assertEqual(by_id.loc["job1", "shadow_source_streams"], "corporate")
        self.assertFalse(bool(by_id.loc["job2", "found_in_shadow"]))

    def test_reference_can_match_normalised_url(self) -> None:
        shadow = pd.DataFrame([
            {
                "candidate_id": "cand1",
                "job_id": "new-id",
                "company": "A",
                "title": "Treasury Analyst",
                "job_url": "https://example.com/job/1?jobId=55",
                "source_streams": "board",
            }
        ])
        reference = pd.DataFrame([
            {
                "job_id": "old-id",
                "company": "A",
                "title": "Treasury Analyst",
                "job_url": "https://example.com/job/1?jobId=55&utm_source=x",
            }
        ])
        report = compare_reference(shadow, reference)
        self.assertTrue(bool(report.iloc[0]["found_in_shadow"]))

    def test_country_supply_is_diagnostic_not_quality_fill(self) -> None:
        shadow = pd.DataFrame({
            "country_bucket": ["Germany", "Germany", "United Kingdom"],
        })
        report = country_supply(shadow, {"Germany": 2, "United Kingdom": 3})
        by_country = report.set_index("country")
        self.assertEqual(by_country.loc["Germany", "raw_supply_status"], "OK")
        self.assertEqual(int(by_country.loc["United Kingdom", "raw_gap"]), 2)
        self.assertEqual(by_country.loc["United Kingdom", "raw_supply_status"], "RAW DEFICIT")


if __name__ == "__main__":
    unittest.main()
