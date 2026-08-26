from __future__ import annotations

import unittest

from sourcing.g_data_quality import invalid_company_name, invalid_job_title


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


if __name__ == "__main__":
    unittest.main()
