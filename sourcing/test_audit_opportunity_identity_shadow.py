from __future__ import annotations

import unittest

import pandas as pd

from sourcing.audit_opportunity_identity_shadow import audit_identity


class IdentityAuditTests(unittest.TestCase):
    def test_legal_suffix_and_gender_marker_match(self) -> None:
        candidates = pd.DataFrame([{
            "candidate_id": "c1", "job_id": "official-1", "company": "Deloitte",
            "title": "Manager M&A Advisory – Corporate Finance | Life Sciences & Healthcare",
            "country_bucket": "Switzerland", "source_streams": "company",
            "job_url": "https://apply.deloitte.ch/job/23732",
        }])
        reference = pd.DataFrame([{
            "job_id": "board-9", "company": "Deloitte AG",
            "title": "Manager M&A Advisory - Corporate Finance | Life Sciences & Healthcare",
            "market": "Switzerland",
        }])
        report, _ = audit_identity(candidates, reference)
        self.assertEqual(report.iloc[0]["match_status"], "high_confidence_identity_match")
        self.assertEqual(report.iloc[0]["matched_job_id"], "official-1")

    def test_same_job_id_with_wrong_title_is_conflict(self) -> None:
        candidates = pd.DataFrame([{
            "candidate_id": "c1", "job_id": "x", "company": "Danske Bank",
            "title": "sales specialist", "country_bucket": "Sweden",
            "source_streams": "board", "job_url": "https://example.com/credit",
        }])
        reference = pd.DataFrame([{
            "job_id": "x", "company": "Danske Bank",
            "title": "Credit Analyst - Wholesale Credit Risk Management",
            "market": "Sweden",
        }])
        report, _ = audit_identity(candidates, reference)
        self.assertEqual(report.iloc[0]["match_status"], "job_id_metadata_conflict")

    def test_potential_duplicates_are_reported_not_merged(self) -> None:
        candidates = pd.DataFrame([
            {"candidate_id": "a", "job_id": "1", "company": "Example AG", "title": "Treasury Manager (m/f/d)", "country_bucket": "Germany", "source_streams": "board", "job_url": "https://board/a"},
            {"candidate_id": "b", "job_id": "2", "company": "Example", "title": "Treasury Manager", "country_bucket": "Germany", "source_streams": "company", "job_url": "https://company/b"},
        ])
        _, duplicates = audit_identity(candidates, pd.DataFrame())
        self.assertEqual(len(duplicates), 1)
        self.assertEqual(int(duplicates.iloc[0]["candidate_count"]), 2)
        self.assertIn("board", duplicates.iloc[0]["source_streams"])
        self.assertIn("company", duplicates.iloc[0]["source_streams"])


if __name__ == "__main__":
    unittest.main()
