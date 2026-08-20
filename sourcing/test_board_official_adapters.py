import unittest

from sourcing.board_official_adapters import extract_findajob_links


class OfficialBoardAdaptersTest(unittest.TestCase):
    def test_findajob_extracts_detail(self):
        html = '<a href="/details/17934138">Treasury Accounting Manager</a>'
        self.assertEqual(
            extract_findajob_links(html, 10),
            ["https://findajob.dwp.gov.uk/details/17934138"],
        )


if __name__ == "__main__":
    unittest.main()
