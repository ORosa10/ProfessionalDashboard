import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from bs4 import BeautifulSoup

import pandas as pd

from sourcing.big4_pilot import (
    _smartrecruiters_company,
    avature_posting_from_soup,
    calibrate_jobs,
    deduplicate_jobs,
    extract_job_postings,
    extract_phenom_records,
    focus_role_description,
    is_real_job_title,
    is_relevant_listing_title,
    is_successfactors_job_url,
    merge_jobs,
    stable_job_id,
    _workday_config,
    _workday_target_location_ids,
    extract_jobylon_records,
)


class BigFourPilotTest(unittest.TestCase):
    def test_rejects_talent_community_false_positive(self):
        self.assertFalse(is_real_job_title("Interest in EY?"))
        self.assertFalse(is_real_job_title("Join our talent community"))
        self.assertFalse(is_real_job_title("Åpen søknad til Technology & Consulting"))
        self.assertTrue(is_real_job_title("Senior Consultant Corporate Finance"))

    def test_focuses_description_on_role_content(self):
        raw = (
            "At EY, we're all in to shape your future with confidence. "
            "Your impact You will build financial models and advise on transactions. "
            "What we offer A global benefits programme."
        )
        focused = focus_role_description(raw)
        self.assertEqual(
            focused,
            "Your impact You will build financial models and advise on transactions.",
        )

    def test_merges_same_role_across_locations(self):
        jobs = pd.DataFrame([
            {
                "job_id": "one", "canonical_company_id": "ey", "company": "EY",
                "title": "Senior Consultant Finance (m/f/d)", "location": "Berlin · DE",
                "market": "Germany", "priority_locations": "Berlin", "job_url": "https://a",
                "date_posted": "2026-08-10",
            },
            {
                "job_id": "two", "canonical_company_id": "ey", "company": "EY",
                "title": "Senior Consultant Finance (w/m/d)", "location": "Munich · DE",
                "market": "Germany", "priority_locations": "Munich", "job_url": "https://b",
                "date_posted": "2026-08-09",
            },
        ])
        result = deduplicate_jobs(jobs)
        self.assertEqual(len(result), 1)
        self.assertIn("Berlin", result.iloc[0]["location"])
        self.assertIn("Munich", result.iloc[0]["location"])
        self.assertEqual(result.iloc[0]["duplicate_count"], 2)

    def test_feedback_calibration_ranks_relevant_finance_above_junior_tax(self):
        jobs = pd.DataFrame([
            {"title": "Senior Consultant Corporate Finance", "description_en": "M&A valuation work"},
            {"title": "Graduate Tax Assistant", "description_en": "Entry level tax compliance"},
        ])
        result = calibrate_jobs(jobs)
        self.assertGreater(
            result.iloc[0]["calibration_score"], result.iloc[1]["calibration_score"]
        )

    def test_successfactors_detail_url_requires_numeric_vacancy_id(self):
        self.assertTrue(
            is_successfactors_job_url(
                "https://careers.ey.com/ey/job/Berlin-Finance-Manager/123456/"
            )
        )
        self.assertTrue(
            is_successfactors_job_url(
                "https://jobs.kpmg.de/job/Finance-Consultant/12164-de_DE/"
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

    def test_extracts_server_rendered_phenom_results(self):
        html = '<script>phApp.ddo = {"eagerLoadRefineSearch":{"totalHits":1,"data":{"jobs":[{"jobId":"42","title":"Finance Consultant"}]}}};</script>'
        records, total = extract_phenom_records(html)
        self.assertEqual(total, 1)
        self.assertEqual(records[0]["jobId"], "42")

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

    def test_extracts_deloitte_avature_detail(self):
        soup = BeautifulSoup(
            """
            <h1>Senior Consultant Corporate Finance</h1>
            <article class="article article--details">
              <h2>Basic information</h2>
              <div class="article__content__view__field">
                <span class="article__content__view__field__label">City</span>
                <span class="article__content__view__field__value">Zurich</span>
              </div>
            </article>
            <article class="article article--details">
              <h2>Job description</h2>
              <div class="article__content__view">
                Advise clients on M&amp;A transactions and build valuation models.
              </div>
            </article>
            """,
            "html.parser",
        )
        source = pd.Series({"market": "Switzerland"})
        posting = avature_posting_from_soup(
            soup,
            "https://apply.deloitte.ch/CHCareers/JobDetail/Corporate-Finance/23953",
            source,
        )
        self.assertEqual(posting["identifier"]["value"], "23953")
        self.assertEqual(posting["jobLocation"]["address"], "Zurich, Switzerland")
        self.assertIn("valuation models", posting["description"])

    def test_smartrecruiters_company_slug_and_broad_discovery(self):
        self.assertEqual(
            _smartrecruiters_company(
                "https://careers.smartrecruiters.com/DeloitteNordic?oga=true"
            ),
            "DeloitteNordic",
        )
        self.assertTrue(is_relevant_listing_title("Senior Consultant M&A Finance"))
        self.assertFalse(is_relevant_listing_title("Office Receptionist"))
        self.assertFalse(is_relevant_listing_title("Talent Acquisition Specialist"))

    def test_stable_id_matches_posting_identity(self):
        source = pd.Series({"canonical_company_id": "pwc"})
        self.assertEqual(stable_job_id(source, "REQ-42"), stable_job_id(source, "REQ-42"))
        self.assertNotEqual(stable_job_id(source, "REQ-42"), stable_job_id(source, "REQ-43"))

    def test_merge_can_build_on_separate_staging_snapshot(self):
        columns = [
            "job_id", "canonical_company_id", "company", "title", "description",
            "description_en", "translation_status", "market", "location",
            "priority_locations", "job_url", "source_url", "source_id", "date_posted",
            "discovered_at", "last_seen_at", "relevance_score", "matched_terms",
            "verification", "status", "alternate_job_urls", "duplicate_count",
            "calibration_score", "calibration_note",
        ]
        with TemporaryDirectory() as temp_dir:
            staging = Path(temp_dir) / "jobs_staging.csv"
            old = pd.DataFrame(
                [{
                    "job_id": "staged-one", "canonical_company_id": "pwc", "company": "PwC",
                    "title": "Senior Consultant Finance", "job_url": "https://example/one",
                    "verification": "official ATS vacancy detail", "status": "Open",
                }]
            ).reindex(columns=columns, fill_value="")
            old.to_csv(staging, index=False)
            new = pd.DataFrame(
                [{
                    "job_id": "staged-two", "canonical_company_id": "kpmg", "company": "KPMG",
                    "title": "Manager Treasury", "job_url": "https://example/two",
                    "verification": "official ATS vacancy detail", "status": "Open",
                }]
            )
            merged = merge_jobs(new, base_path=staging)
            self.assertEqual(set(merged["job_id"]), {"staged-one", "staged-two"})

    def test_workday_configuration_and_location_selection(self):
        _, site, api_root = _workday_config(
            "https://pwc.wd3.myworkdayjobs.com/en-US/Global_Experienced_Careers"
        )
        self.assertEqual(site, "Global_Experienced_Careers")
        self.assertTrue(api_root.endswith("/wday/cxs/pwc/Global_Experienced_Careers"))
        payload = {
            "facets": [{
                "facetParameter": "locationMainGroup",
                "values": [{
                    "descriptor": "Austria",
                    "values": [{
                        "facetParameter": "locations",
                        "values": [
                            {"id": "vienna-id", "descriptor": "Vienna"},
                            {"id": "graz-id", "descriptor": "Graz"},
                        ],
                    }],
                }],
            }]
        }
        source = pd.Series({"priority_locations": "Vienna"})
        self.assertEqual(_workday_target_location_ids(payload, source), ["vienna-id"])

    def test_extracts_jobylon_embedded_records(self):
        source = """[
            { id: '370097', url: '/jobs/370097-finance/',
              title: 'Manager \\u2013 Finance Transformation',
              locations_text: 'Stockholm', published_date: 'July 3, 2026' },
        ]"""
        records = extract_jobylon_records(source)
        self.assertEqual(records[0]["id"], "370097")
        self.assertIn("Finance Transformation", records[0]["title"])


if __name__ == "__main__":
    unittest.main()
