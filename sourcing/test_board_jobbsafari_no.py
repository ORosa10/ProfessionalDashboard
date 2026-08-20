import unittest

from sourcing.board_jobbsafari_no import extract_links


class JobbsafariNorwayTest(unittest.TestCase):
    def test_extracts_public_job_detail(self):
        html = '<a href="/jobb/treasury-manager-example-456780">Treasury Manager</a>'
        self.assertEqual(
            extract_links(html, 10),
            ["https://jobbsafari.no/jobb/treasury-manager-example-456780"],
        )


if __name__ == "__main__":
    unittest.main()
