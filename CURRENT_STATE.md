# Current State

Updated: 2026-08-09

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
- first dedicated official-ATS adapters for EY target markets and Deloitte Germany, with verified individual vacancy URLs and parser regression tests
- placeholder sections for the future product areas
- dependency and deployment configuration

## Current priority

Turn the Jobs section into the first real end-to-end learning loop:

1. enable the repository-scoped token in Streamlit and collect `A / B / C / Exclude` feedback;
2. extend persistence from company ratings to Opportunities, Sources, SearchProfiles, and reviews;
3. connect the first genuine job source or career-page monitor;
4. ingest real opportunities into the Inbox;
5. collect `Interested` / `Maybe` / `Pass` feedback and pass reasons.

## Explicitly deferred

- sophisticated scoring before real user feedback exists
- hard exclusion of low-scored opportunities
- broad support for every sourcing engine
- production analytics and automation

## Deployment model

The app will run on Streamlit Community Cloud and track the GitHub repository. Code changes are deployed automatically from GitHub. The Streamlit filesystem is not treated as permanent storage: during v0, editable feedback is committed directly to dedicated CSV files in GitHub. An external database can be introduced later if the data model or write volume requires it.
