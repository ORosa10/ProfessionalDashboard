import unittest

from sourcing.board_html_adapters import extract_html_search_links


class BoardHtmlAdaptersTest(unittest.TestCase):
    def test_jobs_cz_extracts_rpd_detail(self):
        html = '''
        <a href="/prace/?q=treasury">filter</a>
        <a class="job-card" href="/rpd/2000999999/?searchId=abc">Treasury Analyst</a>
        '''
        self.assertEqual(
            extract_html_search_links("jobs-cz", html, 10),
            ["https://www.jobs.cz/rpd/2000999999/?searchId=abc"],
        )

    def test_stepstone_extracts_vacancy_detail(self):
        html = '''
        <a href="/jobs/treasury">filter</a>
        <a href="/stellenangebote--Treasury-Expert-Wien-Example--992643-inline.html">role</a>
        '''
        self.assertEqual(
            extract_html_search_links("stepstone-at", html, 10),
            ["https://www.stepstone.at/stellenangebote--Treasury-Expert-Wien-Example--992643-inline.html"],
        )

    def test_jobbsafari_extracts_job_detail(self):
        html = '''
        <a href="/lediga-jobb?sok=treasury">search</a>
        <a href="/jobb/treasury-analyst-sasrb-20169129">Treasury Analyst</a>
        '''
        self.assertEqual(
            extract_html_search_links("jobbsafari-se", html, 10),
            ["https://jobbsafari.se/jobb/treasury-analyst-sasrb-20169129"],
        )


if __name__ == "__main__":
    unittest.main()
