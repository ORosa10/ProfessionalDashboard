# Big Four Jobs Radar pilot

The current Jobs Radar is intentionally limited to Deloitte, PwC, EY, and KPMG. Do not expand it to other rated companies until the user explicitly confirms that the pilot has been calibrated.

## Pilot scope

- Companies: Deloitte, PwC, EY, and KPMG only.
- Markets: Czechia, Germany, Austria, Switzerland, United Kingdom, Finland, Norway, Denmark, and Sweden.
- Run the pilot once daily through the existing GitHub Actions workflow, plus explicit test runs after sourcing-code changes.
- Use `data/job_sources_pilot.csv` and the existing `sourcing/big4_pilot.py` framework. Improve company or market adapters incrementally instead of creating a second parallel scraper.

## Target opportunity scope

- Do not store opportunities outside the pilot countries.
- Target cities include Prague, Munich, Berlin, Frankfurt, Hamburg, Vienna, Zurich, London and the main Nordic centres.
- Relevant families include treasury, FP&A, M&A, corporate finance, investment banking, transaction services, valuation, restructuring, public markets, asset management, private markets, portfolio analytics, risk, strategy, data and finance-focused business analysis.
- Prefer roles asking for roughly 3-7 years. Interpret seniority within each role family rather than relying only on the title.
- Avoid roles whose primary substance is sales, relationship management or client acquisition.
- Do not apply hard scoring yet. Store concise evidence and preserve exploration candidates.

## Source and data rules

- Use official company career pages or their official ATS pages as the source of truth.
- Store verified opportunities in `data/jobs.csv` using the existing pilot schema.
- Normalize country/market and location. Split Nordic vacancies into Finland, Norway, Denmark, or Sweden whenever the official vacancy location allows it.
- Deduplicate by canonical company plus official requisition ID, then by normalized official vacancy URL.
- Preserve `discovered_at`; update `last_seen_at` when an opportunity is confirmed open.
- Mark a role `Closed` only after its official page is unavailable or clearly closed on two consecutive monitoring attempts. Do not delete historical rows.
- A career landing page, search-results page, or generic business page is not a vacancy. Store only individually verified live roles with a visible official job link.
- Commit and push only when verified opportunity data or source diagnostics materially change. Never alter company ratings.

## Reporting

After each run, report Big Four companies and markets checked, verified new roles, rejected false positives, possible closures, source failures, and the next adapter improvement.
