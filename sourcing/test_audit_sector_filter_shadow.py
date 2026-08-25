from __future__ import annotations

import unittest

from sourcing.audit_sector_filter_shadow import classify_job


class SectorFilterAuditTests(unittest.TestCase):
    def test_finance_title_target_location_kept(self) -> None:
        row = classify_job({"title": "Investment Banking Analyst", "location": "London, United Kingdom"})
        self.assertTrue(row["title_relevant"])
        self.assertTrue(row["location_target"])
        self.assertTrue(row["kept"])
        self.assertEqual(row["rejection_reason"], "")

    def test_non_finance_title_is_explained(self) -> None:
        row = classify_job({"title": "Software Engineer", "location": "London"})
        self.assertFalse(row["title_relevant"])
        self.assertTrue(row["location_target"])
        self.assertFalse(row["kept"])
        self.assertEqual(row["rejection_reason"], "title_filter")

    def test_outside_location_is_explained(self) -> None:
        row = classify_job({"title": "Corporate Finance Analyst", "location": "New York, United States"})
        self.assertTrue(row["title_relevant"])
        self.assertFalse(row["location_target"])
        self.assertFalse(row["kept"])
        self.assertEqual(row["rejection_reason"], "location_filter")

    def test_both_filters_are_visible(self) -> None:
        row = classify_job({"title": "Software Engineer", "location": "New York"})
        self.assertEqual(row["rejection_reason"], "title_filter; location_filter")


if __name__ == "__main__":
    unittest.main()
