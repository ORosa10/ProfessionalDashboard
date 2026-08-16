# Manual job sourcing task: Holding & Conglomerate sector

## Context

This is a personal Streamlit job-search dashboard repo (`ORosa10/ProfessionalDashboard`) for Ondřej, a finance/treasury/risk professional looking for roles in Czechia, Germany, Austria, Switzerland, UK, and the Nordics.

The repo automatically sources job postings from company career pages using deterministic adapters (Workday, SuccessFactors, SmartRecruiters, Personio APIs — these work reliably). For companies whose career page doesn't match any of those platforms (JS-rendered custom sites), there's a fallback meant to use a headless browser + free Gemini API via GitHub Actions — but Gemini's free tier keeps hitting rate-limit/quota errors, so it isn't working reliably right now.

Rather than keep fighting that automation, this ONE sector (Holding & Conglomerate — 8 companies, all currently on the broken `llm` adapter, 0 jobs found so far) is being done as a **manual pass**: browse each career page yourself, read the actual current job listings, and commit results directly to GitHub.

## Your task

For each of the 8 companies below, visit the `seed_url` (their careers page) and identify real, currently-listed job openings that are plausibly relevant to **finance, investment, treasury, risk, accounting, strategy, corporate development, or related business/analytical roles**. Ignore engineering/IT/sales/retail/manual-labor/internal-HR postings. If a page requires clicking through to a job board or has pagination, follow the relevant link. If a page genuinely shows no matching current openings, that's a valid, honest outcome — **do not invent postings**.

### Companies (source_id, canonical_company_id, company, market, priority_locations, seed_url)

1. `csg-global`, `csg`, Czechoslovak Group, Multi-region, "Prague; Czech Republic; European portfolio", https://czechoslovakgroup.com/en/career
2. `cpi-property-group-global`, `cpi-property-group`, CPI Property Group, Multi-region, "Prague; Berlin; Vienna; CEE", https://www.cpipg.com/careers
3. `investor-ab-global`, `investor-ab`, Investor AB, Multi-region, "Stockholm; Nordic portfolio", https://www.investorab.com/career/
4. `industrivarden-global`, `industrivarden`, Industrivärden, Multi-region, "Stockholm; Nordic portfolio", https://www.industrivarden.se/en-gb/career/
5. `kinnevik-global`, `kinnevik`, Kinnevik, Multi-region, "Stockholm; London; European portfolio", https://www.kinnevik.com/careers
6. `exor-global`, `exor`, Exor, Multi-region, "Amsterdam; London; European portfolio", https://www.exor.com/pages/exor/careers
7. `porsche-se-global`, `porsche-se`, Porsche Automobil Holding, Multi-region, "Stuttgart; European portfolio", https://www.porsche-se.com/en/company/career
8. `ap-moller-holding-global`, `ap-moller-holding`, A.P. Moller Holding, Multi-region, "Copenhagen; global portfolio", https://apmoller.com/careers/

## CSV schema

Target file: `data/jobs_holdings_staging.csv` on branch `holdings-sourcing-staging`. It currently has only a header row (no data rows yet). For every job you find, produce one row with **exactly** these columns, in this order:

```
job_id,canonical_company_id,company,title,description,description_en,translation_status,market,location,priority_locations,job_url,source_url,source_id,date_posted,discovered_at,last_seen_at,relevance_score,matched_terms,verification,status,alternate_job_urls,duplicate_count,calibration_score,calibration_note
```

Column notes:
- `job_id`: any short unique-looking hex/slug string per job (doesn't need to be cryptographic, just unique within your output)
- `description` / `description_en`: a short 1–3 sentence summary in your own words if enough detail is visible; blank (`""`) is fine if the page only shows a title/location
- `translation_status`: `original-en` if the posting is in English, otherwise blank
- `location`: the specific city/office shown for that posting if visible, else blank
- `priority_locations`: copy verbatim from the company list above for that company
- `job_url`: the direct URL to that specific job posting if findable, else reuse the `seed_url`
- `source_url`: always the `seed_url` for that company
- `source_id` / `canonical_company_id` / `company` / `market`: copy verbatim from the company list above
- `date_posted`: blank if not visible
- `discovered_at` / `last_seen_at`: current UTC timestamp in ISO format, e.g. `2026-08-16T00:00:00.000000+00:00` — use one consistent timestamp for the whole batch
- `relevance_score` / `matched_terms`: leave blank
- `verification`: exactly `Manually reviewed via Claude (Haiku) browsing, <today's date>`
- `status`: `Open`
- `alternate_job_urls` / `duplicate_count` / `calibration_score` / `calibration_note`: leave blank

## What to do with the results

1. Clone the repo (or work in a fresh checkout): `git clone https://github.com/ORosa10/ProfessionalDashboard`
2. Check out the existing branch: `git fetch origin holdings-sourcing-staging && git checkout holdings-sourcing-staging`
3. Append your new job rows to `data/jobs_holdings_staging.csv` (keep the existing header, add rows after it, properly quote any field containing a comma).
4. Do **not** touch any other file in the repo, and do **not** touch `data/source_runs_holdings_staging.csv`.
5. Commit with git author name `professional-dashboard-bot` / email `professional-dashboard-bot@users.noreply.github.com`, message like: `Manually source Holdings jobs via Claude Haiku browsing (Gemini free-tier fallback unreliable)`.
6. Push to the **same branch** (not `main`): `git push origin HEAD:refs/heads/holdings-sourcing-staging`. If it's rejected because the remote moved, fetch + rebase/merge first — do not force-push.
7. Use whatever GitHub write access this chat/session has been given (repo access granted by Ondřej) to authenticate the push.

## Constraints

- Do not invent or guess job postings — only report what you actually see on each page. Zero rows for a company is a fine, honest outcome.
- This is a one-time manual supplement to the broken automated pipeline for just this one sector, as a test. Do not attempt to fix the Gemini/Playwright adapter code itself — that's being handled separately in the main session.

## When done

Report: how many jobs found per company (or "0, page showed no relevant postings"), and confirm whether the git push succeeded (or what error was hit).
