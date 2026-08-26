from __future__ import annotations

import unittest
from datetime import datetime, timezone

import pandas as pd

from sourcing.verify_live_j_links import apply_verification, classify_response, verify_pool


class VerifyLiveJLinksTests(unittest.TestCase):
    def test_404_and_410_are_dead(self) -> None:
        for status in (404, 410):
            result, evidence = classify_response(status, "https://example.com/jobs/123", "https://example.com/jobs/123", "")
            self.assertEqual(result, "dead")
            self.assertEqual(evidence, f"http_{status}")

    def test_expired_marker_is_dead_even_on_200(self) -> None:
        result, evidence = classify_response(
            200,
            "https://example.com/jobs/123",
            "https://example.com/jobs/123",
            "Thank you for your interest. This job is no longer available.",
        )
        self.assertEqual(result, "dead")
        self.assertTrue(evidence.startswith("expired_marker:"))

    def test_waf_and_server_failures_are_not_dead(self) -> None:
        for status in (403, 429, 500, 503):
            result, _ = classify_response(status, "https://example.com/jobs/123", "https://example.com/jobs/123", "")
            self.assertEqual(result, "verification_failed")

    def test_clean_200_is_live(self) -> None:
        result, evidence = classify_response(
            200,
            "https://example.com/jobs/123",
            "https://example.com/jobs/123",
            "Treasury Manager - Apply now",
        )
        self.assertEqual(result, "live")
        self.assertEqual(evidence, "http_200")

    def test_generic_redirect_is_warning_not_hard_dead(self) -> None:
        result, evidence = classify_response(
            200,
            "https://example.com/jobs/treasury-manager-123456",
            "https://example.com/jobs",
            "Careers at Example",
        )
        self.assertEqual(result, "likely_dead")
        self.assertEqual(evidence, "redirected_to_generic_careers")

    def test_recent_source_seen_skips_network_and_is_live(self) -> None:
        now = datetime.now(timezone.utc).isoformat()
        pool = pd.DataFrame([{
            "job_id": "j1",
            "company": "Example",
            "title": "Treasury Manager",
            "job_url": "https://example.com/jobs/1",
            "last_seen_at": now,
        }])
        normalized, verification = verify_pool(pool, pd.DataFrame(), source_recent_hours=48)
        self.assertEqual(len(normalized), 1)
        self.assertEqual(verification.iloc[0]["link_status"], "live")
        self.assertEqual(verification.iloc[0]["verification_evidence"], "source_seen_recently")

    def test_missing_url_is_unverifiable_not_dead(self) -> None:
        pool = pd.DataFrame([{
            "job_id": "j1",
            "company": "Example",
            "title": "Treasury Manager",
            "job_url": "",
            "last_seen_at": "",
        }])
        _, verification = verify_pool(pool, pd.DataFrame(), source_recent_hours=0, max_workers=1)
        self.assertEqual(verification.iloc[0]["link_status"], "verification_failed")
        self.assertEqual(verification.iloc[0]["verification_evidence"], "missing_job_url")

    def test_likely_dead_warning_stays_in_pool(self) -> None:
        pool = pd.DataFrame([
            {"job_id": "redirect", "company": "A", "title": "Treasury", "job_url": "https://a/jobs/123"},
        ])
        verification = pd.DataFrame([
            {"opportunity_id": "redirect", "link_status": "likely_dead", "last_verified_at": "2026-08-26T00:00:00+00:00", "verification_evidence": "redirected_to_generic_careers"},
        ])
        kept, excluded = apply_verification(pool, pd.DataFrame(), verification)
        self.assertEqual(kept["job_id"].tolist(), ["redirect"])
        self.assertEqual(kept.iloc[0]["link_status"], "likely_dead")
        self.assertTrue(excluded.empty)

    def test_only_confirmed_dead_is_removed(self) -> None:
        pool = pd.DataFrame([
            {"job_id": "dead", "company": "A", "title": "Treasury", "job_url": "https://a/job"},
            {"job_id": "waf", "company": "B", "title": "M&A", "job_url": "https://b/job"},
        ])
        verification = pd.DataFrame([
            {"opportunity_id": "dead", "link_status": "dead", "last_verified_at": "2026-08-26T00:00:00+00:00", "verification_evidence": "http_404"},
            {"opportunity_id": "waf", "link_status": "verification_failed", "last_verified_at": "2026-08-26T00:00:00+00:00", "verification_evidence": "http_403"},
        ])
        kept, excluded = apply_verification(pool, pd.DataFrame(), verification)
        self.assertEqual(kept["job_id"].tolist(), ["waf"])
        self.assertEqual(kept.iloc[0]["link_status"], "verification_failed")
        self.assertEqual(excluded.iloc[0]["excluded_reason"], "link_quality:http_404")


if __name__ == "__main__":
    unittest.main()
