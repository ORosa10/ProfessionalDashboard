import unittest

from sourcing.board_jobly_fi import extract_jobly_links


class JoblyAdapterTest(unittest.TestCase):
    def test_extracts_job_detail(self):
        html = '<a href="/en/job/cash-management-specialist-ssab-hameenlinna-2726180">role</a>'
        self.assertEqual(
            extract_jobly_links(html, 10),
            ["https://www.jobly.fi/en/job/cash-management-specialist-ssab-hameenlinna-2726180"],
        )


if __name__ == "__main__":
    unittest.main()
