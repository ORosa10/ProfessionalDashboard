import unittest

from sourcing.board_nav_no import _absolute_api_url, _relevant_title


class NavAdapterTest(unittest.TestCase):
    def test_relative_feed_url(self):
        self.assertEqual(
            _absolute_api_url("/api/v1/feedentry/abc"),
            "https://pam-stilling-feed.nav.no/api/v1/feedentry/abc",
        )

    def test_finance_title_filter(self):
        self.assertTrue(_relevant_title("Senior Treasury Analyst"))
        self.assertTrue(_relevant_title("Finansiell risikoanalytiker"))
        self.assertFalse(_relevant_title("Barnehagelærer"))


if __name__ == "__main__":
    unittest.main()
