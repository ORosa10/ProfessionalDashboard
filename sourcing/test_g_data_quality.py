from __future__ import annotations

import unittest

from sourcing.g_data_quality import any_finance_marker, finance_marker_present, invalid_company_name, invalid_job_title


class GDataQualityTests(unittest.TestCase):
    def test_invalid_company_placeholders(self) -> None:
        for value in [
            "Employer not stated",
            "LINKEDIN",
            "Poslat nabídku na e-mail",
            "Nabídka Pracovní nabídka O nás Volná místa 4",
            "Navštivte naše sociální sítě a poznejte Trinity Bank ještě blíž",
            "Práce v oboru",
        ]:
            self.assertTrue(invalid_company_name(value), value)
        self.assertFalse(invalid_company_name("Example Energy AG"))

    def test_search_result_titles_are_not_jobs(self) -> None:
        self.assertTrue(invalid_job_title("105 Jobs für deine Suche"))
        self.assertTrue(invalid_job_title("1’148 Jobs für deine Suche"))
        self.assertFalse(invalid_job_title("Treasury Analyst"))

    def test_valuation_does_not_match_evaluation(self) -> None:
        self.assertFalse(finance_marker_present("AI Evaluation Engineer", "valuation"))
        self.assertTrue(finance_marker_present("Transaction Valuation Analyst", "valuation"))
        self.assertTrue(finance_marker_present("Valuations Associate", "valuation"))

    def test_compound_finance_stems_remain_supported(self) -> None:
        self.assertTrue(finance_marker_present("Finanzanalyst", "finanz"))
        self.assertTrue(any_finance_marker("Senior finansanalytiker", ["finans", "treasury"]))


if __name__ == "__main__":
    unittest.main()
