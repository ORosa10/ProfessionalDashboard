from __future__ import annotations

import unittest

import pandas as pd

from sourcing.j_soft_ranking import add_soft_rank_columns, looks_german_advert, seniority_soft_penalty


class JSoftRankingTests(unittest.TestCase):
    def test_german_advert_detected_but_not_english_dach_advert(self) -> None:
        german = "Wir suchen eine Person mit Erfahrung im Bereich Treasury. Ihre Aufgaben umfassen die Steuerung der Liquidität und die Zusammenarbeit mit Banken für unser Unternehmen."
        english = "We are looking for a treasury specialist with experience in liquidity, FX hedging and banking relationships in an international team."
        self.assertTrue(looks_german_advert(german))
        self.assertFalse(looks_german_advert(english))

        frame = pd.DataFrame([
            {"title": "Treasury Specialist", "country_bucket": "Germany", "description": german},
            {"title": "Treasury Specialist", "country_bucket": "Germany", "description": english},
        ])
        ranked = add_soft_rank_columns(frame)
        self.assertEqual(ranked.iloc[0]["_language_soft"], 1)
        self.assertEqual(ranked.iloc[1]["_language_soft"], 0)

    def test_seniority_is_soft_not_exclusion(self) -> None:
        self.assertEqual(seniority_soft_penalty("Investment Banking Senior Analyst"), 0)
        self.assertEqual(seniority_soft_penalty("Treasury Specialist"), 0)
        self.assertEqual(seniority_soft_penalty("Senior Consultant M&A"), 1)
        self.assertEqual(seniority_soft_penalty("Treasury Manager"), 1)
        self.assertEqual(seniority_soft_penalty("Treasury Lead"), 2)

    def test_sehr_gute_deutschkenntnisse_is_only_part_of_advert_language_signal(self) -> None:
        text = "Wir suchen Verstärkung für unser Treasury Team. Sie bringen sehr gute Deutschkenntnisse mit und arbeiten mit Banken sowie internen Bereichen zusammen."
        self.assertTrue(looks_german_advert(text))
        # This module only ranks; it never marks a role non-actionable.
        row = add_soft_rank_columns(pd.DataFrame([{
            "title": "Treasury Specialist", "country_bucket": "Germany", "description": text,
        }])).iloc[0]
        self.assertEqual(row["_language_soft"], 1)


if __name__ == "__main__":
    unittest.main()
