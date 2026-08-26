from __future__ import annotations

import unittest

import pandas as pd

from company_targeting_ui import _discovered_universe_row


class CompanyTargetingPromotionTests(unittest.TestCase):
    def test_explicit_rating_promotes_clean_universe_row(self) -> None:
        suggestion = pd.Series({
            "suggested_company_id": "example-energy",
            "company": "Example Energy AG",
            "countries": "Germany; Austria",
            "sample_titles": "Treasury Manager | Market Risk Analyst",
        })
        row = _discovered_universe_row(suggestion, "A")
        self.assertEqual(row["canonical_company_id"], "example-energy")
        self.assertEqual(row["company"], "Example Energy AG")
        self.assertEqual(row["region"], "Germany")
        self.assertEqual(row["rating"], "A")
        self.assertEqual(row["company_category"], "Unclassified / G discovered")
        self.assertIn("Treasury Manager", row["why_test"])


if __name__ == "__main__":
    unittest.main()
