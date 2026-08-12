# Current State

Updated: 2026-08-12

## Current phase

Foundation / v0 app shell.

## What exists

- GitHub repository and Streamlit-ready project structure
- consolidated product blueprint
- first navigable application shell with Jobs and Companies grouped under Opportunities
- SearchProfile workflow designed; no personal profile data is stored in the public repository
- researched Company Universe v0.4 with 261 canonical employers across consulting, banking, investment banking, public markets, private markets, specialist funds, corporates, and holdings
- eight-category company taxonomy that keeps public markets, private markets, specialist funds, and investment banking distinct without over-segmenting the universe
- rating-progress metrics and source metadata prepared for staged career-page monitoring
- structured contact-strength feedback for known contacts, warm introductions, and strong referrals
- direct Streamlit-to-GitHub persistence for company ratings and notes
- company ratings currently capture intrinsic interest in the firm and its work; contacts and later feasibility signals remain separate prioritization layers
- first live Jobs Inbox with company and country/market filters
- Big Four-only sourcing pilot for Deloitte, PwC, EY, and KPMG, scheduled daily through GitHub Actions; broader rated-company monitoring remains intentionally deferred until the pilot is calibrated
- official-ATS adapters for EY target markets, Deloitte Germany, PwC Germany/UK, and KPMG Germany, with verified individual vacancy URLs and parser regression tests
- 410 verified open Big Four roles in the current snapshot (102 EY, 12 Deloitte, 91 KPMG, 205 PwC), with PwC pagination fixed and every role carrying an English description
- editable job feedback with `Interested / Maybe / Pass`, recurring reason comments, and direct GitHub persistence; the first 50-role Big Four cohort is fully reviewed (14 Interested, 10 Maybe, 26 Pass, with 50 comments)
- feedback-informed review ordering that remains transparent and exploratory rather than hard-excluding low-ranked roles
- `JOB_TARGETING.md` v0.1 turns the first cohort into a reviewable sourcing hypothesis: transactions/M&A, treasury, analytical FP&A and finance-linked strategy/data are prioritized, while tax, audit, pure IT, ERP implementation and non-financial risk are downranked
- role-focused English descriptions with employer boilerplate removed, plus logical deduplication of the same role advertised across multiple cities
- separate PE/private-markets cohort: 21 A-rated sources checked, 25 verified candidates retained, and a diverse 20-role follow-up calibration shortlist available as its own Jobs review set
- placeholder sections for the future product areas
- dependency and deployment configuration

## Current priority

Turn the Jobs section into the first real end-to-end learning loop:

1. finish rating the current Big Four opportunity set;
2. use repeated feedback themes to refine descriptions, deduplication, and review ordering;
3. complete dedicated adapters for remaining Big Four country portals;
4. validate closure detection before removing any stale vacancy from the open inbox;
5. keep PE research and adapter development in a separate staging dataset while Big Four feedback is collected, then publish only a curated PE calibration shortlist rather than the full raw result set.

The next product layer is defined but not yet implemented: separate company `IntrinsicInterest`, `Familiarity`, and `AccessStrength` signals, plus versioned country/city economics that estimate minimum viable compensation and add a recoverable `Financially viable / Below threshold / Unknown` opportunity filter.

## Explicitly deferred

- sophisticated or opaque scoring; current ordering uses only transparent rules derived from real feedback
- hard exclusion of low-scored opportunities
- broad support for every sourcing engine
- production analytics and automation

## Deployment model

The app will run on Streamlit Community Cloud and track the GitHub repository. Code changes are deployed automatically from GitHub. The Streamlit filesystem is not treated as permanent storage: during v0, editable feedback is committed directly to dedicated CSV files in GitHub. An external database can be introduced later if the data model or write volume requires it.
