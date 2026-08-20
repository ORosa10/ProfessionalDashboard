import unittest

from sourcing.board_additional_adapters import extract_additional_links


class AdditionalBoardAdaptersTest(unittest.TestCase):
    def test_cv_library_detail(self):
        html = '<a href="/job/225472018/treasury-systems-transformation-manager?keyword=treasury">role</a>'
        self.assertEqual(
            extract_additional_links("cv-library-uk", html, 10),
            ["https://www.cv-library.co.uk/job/225472018/treasury-systems-transformation-manager"],
        )

    def test_jobup_detail(self):
        html = '<a href="/en/jobs/detail/7d30b8ff-2923-4fc0-8192-bd0468332fbc/">role</a>'
        self.assertEqual(
            extract_additional_links("jobup-ch", html, 10),
            ["https://www.jobup.ch/en/jobs/detail/7d30b8ff-2923-4fc0-8192-bd0468332fbc/"],
        )


if __name__ == "__main__":
    unittest.main()
