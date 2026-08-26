from __future__ import annotations

import unittest

from sourcing.g_query_profiles import ENGLISH_INTENT_QUERIES, queries_for_country


class GQueryProfilesTests(unittest.TestCase):
    def test_dach_and_nordics_get_english_intent_queries(self) -> None:
        base = ["treasury", "M&A"]
        for country in ["Germany", "Austria", "Switzerland", "Sweden", "Norway", "Denmark", "Finland"]:
            queries = queries_for_country(base, country)
            self.assertTrue(set(ENGLISH_INTENT_QUERIES).issubset(queries))
            self.assertEqual(queries[:2], base)

    def test_uk_and_czechia_keep_base_queries_only(self) -> None:
        base = ["treasury", "corporate finance"]
        self.assertEqual(queries_for_country(base, "United Kingdom"), base)
        self.assertEqual(queries_for_country(base, "Czechia"), base)

    def test_queries_are_deduplicated(self) -> None:
        queries = queries_for_country(["treasury", "treasury", "treasury english"], "Germany")
        self.assertEqual(queries.count("treasury"), 1)
        self.assertEqual(queries.count("treasury english"), 1)


if __name__ == "__main__":
    unittest.main()
