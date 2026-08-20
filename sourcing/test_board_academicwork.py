import unittest

from sourcing.board_academicwork import extract_academicwork_links


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


if __name__ == "__main__":
    unittest.main()
