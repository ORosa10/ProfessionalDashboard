# Current State

Updated: 2026-08-09

## Current phase

Foundation / v0 app shell.

## What exists

- GitHub repository and Streamlit-ready project structure
- consolidated product blueprint
- first navigable application shell with Jobs and Companies grouped under Opportunities
- SearchProfile workflow designed; no personal profile data is stored in the public repository
- researched Company Universe v0.1 prepared for user rating
- placeholder sections for the future product areas
- dependency and deployment configuration

## Current priority

Turn the Jobs section into the first real end-to-end learning loop:

1. collect `A / B / C / Exclude` feedback on the initial Company Universe;
2. persist Opportunities, Companies, Sources, SearchProfiles, company ratings, and reviews;
3. connect the first genuine job source or career-page monitor;
4. ingest real opportunities into the Inbox;
5. collect `Interested` / `Maybe` / `Pass` feedback and pass reasons.

## Explicitly deferred

- sophisticated scoring before real user feedback exists
- hard exclusion of low-scored opportunities
- broad support for every sourcing engine
- production analytics and automation

## Deployment model

The app will run on Streamlit Community Cloud and track the GitHub repository. Code changes are deployed automatically from GitHub. Durable production persistence must use an external database; the Streamlit app filesystem must not be treated as permanent storage.
