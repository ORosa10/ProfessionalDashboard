from __future__ import annotations

import unittest

import pandas as pd

from sourcing.g_data_quality import audit_g_frame, normalise_vacancy_url
from sourcing.validate_g_outputs import build_report


class GDataQualityTests(unittest.TestCase):
    def test_url_normalisation_removes_tracking(self):
        self.assertEqual(normalise_vacancy_url("HTTPS://Example.com/job/1/?utm_source=x#top"), "https://example.com/job/1")

    def test_thin_role_is_flagged_but_not_deleted(self):
        report = audit_g_frame(pd.DataFrame([{"job_id": "j1", "title": "Treasury Analyst", "company": "Example", "job_url": "https://x/1", "description": "short"}]))
        self.assertEqual(len(report), 1)
        self.assertIn("thin_description", report.iloc[0]["quality_flags"])
        self.assertEqual(report.iloc[0]["quality_status"], "review")

    def test_duplicate_url_is_reported_across_lanes(self):
        frame = pd.DataFrame([
            {"job_id": "j1", "title": "Treasury Analyst", "company": "A", "job_url": "https://x/1"},
            {"job_id": "j2", "title": "Treasury Analyst", "company": "A", "job_url": "https://x/1?utm_source=x"},
        ])
        report = build_report([("jobs_a.csv", frame)])
        self.assertIn("duplicate_vacancy_url", report.iloc[1]["quality_flags"])


if __name__ == "__main__":
    unittest.main()
