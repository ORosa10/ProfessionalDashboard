import unittest

from sourcing.board_academicwork import _relevant, extract_academicwork_links


class AcademicWorkAdapterTest(unittest.TestCase):
    def test_denmark_detail_link(self):
        html = '<a href="/en/jobs/j/financial-controller-copenhagen/ABC123">role</a>'
        self.assertEqual(
            extract_academicwork_links("academicwork-dk", html, 10),
            ["https://www.academicwork.dk/en/jobs/j/financial-controller-copenhagen/ABC123"],
        )

    def test_finland_detail_link(self):
        html = '<a href="/en/jobs/j/cash-management-specialist-ssab-hameenlinna/1HFLWI">role</a>'
        self.assertEqual(
            extract_academicwork_links("academicwork-fi", html, 10),
            ["https://www.academicwork.fi/en/jobs/j/cash-management-specialist-ssab-hameenlinna/1HFLWI"],
        )

    def test_engineering_role_is_not_rescued_by_finance_in_description(self):
        self.assertFalse(
            _relevant(
                "Embedded Linux Developer (Audio)",
                "Join a finance-sector client and support risk applications.",
            )
        )

    def test_finance_title_remains_candidate(self):
        self.assertTrue(_relevant("Cash Management Specialist", "generic description"))
        self.assertTrue(_relevant("Financial Controller", "generic description"))


if __name__ == "__main__":
    unittest.main()
