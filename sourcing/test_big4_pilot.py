import unittest

from bs4 import BeautifulSoup

from sourcing.big4_pilot import extract_job_postings, is_successfactors_job_url


class BigFourPilotTest(unittest.TestCase):
    def test_successfactors_detail_url_requires_numeric_vacancy_id(self):
        self.assertTrue(
            is_successfactors_job_url(
                "https://careers.ey.com/ey/job/Berlin-Finance-Manager/123456/"
            )
        )
        self.assertFalse(is_successfactors_job_url("https://careers.ey.com/ey/search/"))

    def test_extracts_jobposting_microdata(self):
        soup = BeautifulSoup(
            """
            <div itemscope itemtype="http://schema.org/JobPosting">
              <span itemprop="title">Senior Consultant Corporate Finance</span>
              <span itemprop="description">Advising clients on transactions and valuation.</span>
              <meta itemprop="datePosted" content="2026-08-10">
              <span itemprop="jobLocation">
                <span itemprop="address">
                  <meta itemprop="addressLocality" content="Frankfurt">
                  <meta itemprop="addressCountry" content="DE">
                </span>
              </span>
            </div>
            """,
            "html.parser",
        )
        postings = extract_job_postings(soup)
        self.assertEqual(postings[0]["title"], "Senior Consultant Corporate Finance")
        self.assertEqual(
            postings[0]["description"],
            "Advising clients on transactions and valuation.",
        )
        self.assertEqual(postings[0]["_verification"], "schema.org/JobPosting microdata")

    def test_ats_fallback_requires_detail_url_and_visible_location(self):
        soup = BeautifulSoup(
            """
            <meta property="og:title" content="Manager Finance Analytics">
            <div class="jobDisplayShell">
              <div class="jobLocation">mehrere Standorte, DE</div>
              <div class="jobdescription">Build finance analytics solutions.</div>
            </div>
            """,
            "html.parser",
        )
        postings = extract_job_postings(
            soup,
            "https://jobs.deloitte.de/job/Manager-Finance-Analytics/987654/",
        )
        self.assertEqual(postings[0]["_verification"], "official ATS vacancy detail")
        self.assertEqual(postings[0]["jobLocation"]["address"], "mehrere Standorte, DE")
        self.assertEqual(postings[0]["description"], "Build finance analytics solutions.")


if __name__ == "__main__":
    unittest.main()
