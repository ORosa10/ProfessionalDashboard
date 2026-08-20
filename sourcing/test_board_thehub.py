import unittest

from sourcing.board_thehub import extract_thehub_links


class TheHubAdapterTest(unittest.TestCase):
    def test_extracts_job_detail(self):
        html = '<a href="/jobs/6a31e3a212a93079279f918a">Market & Liquidity Risk Specialist</a>'
        self.assertEqual(
            extract_thehub_links(html, 10),
            ["https://thehub.io/jobs/6a31e3a212a93079279f918a"],
        )


if __name__ == "__main__":
    unittest.main()
