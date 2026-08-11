# Jobs Radar operating instructions

The Jobs Radar turns the rated Company Universe into a rotating official-career-page monitor.

## Eligible companies

- Read `data/company_ratings.csv` and all `data/company_universe*.csv` files.
- Scan companies rated `A`, then `B`, then `C` as an exploration pool.
- Never scan `Exclude` or `Unrated` companies.
- Process a rotating batch of approximately 15 companies per run. Derive the batch from the current five-hour time slot and the stable, rating-first company ordering so that repeated runs cover the full universe without a mutable cursor.

## Target opportunity scope

- Countries: Czechia, Germany, Austria, Switzerland, United Kingdom, Finland, Norway, Denmark, and Sweden. Keep other unusually strong international opportunities only as exploration.
- Target cities include Prague, Munich, Berlin, Frankfurt, Hamburg, Vienna, Zurich, London and the main Nordic centres.
- Relevant families include treasury, FP&A, M&A, corporate finance, investment banking, transaction services, valuation, restructuring, public markets, asset management, private markets, portfolio analytics, risk, strategy, data and finance-focused business analysis.
- Prefer roles asking for roughly 3-7 years. Interpret seniority within each role family rather than relying only on the title.
- Avoid roles whose primary substance is sales, relationship management or client acquisition.
- Do not apply hard scoring yet. Store concise evidence and preserve exploration candidates.

## Source and data rules

- Use official company career pages or their official ATS pages as the source of truth.
- Store opportunities in `data/job_opportunities.csv` using its existing schema.
- Normalize countries, allow semicolon-separated multi-country opportunities, and keep cities separate.
- Deduplicate first by canonical company plus official requisition ID, then by normalized official URL.
- Preserve `discovered_at`; update `last_seen_at` when an opportunity is confirmed open.
- Mark a role `Closed` only after its official page is unavailable or clearly closed on two consecutive monitoring attempts. Do not delete historical rows.
- Set new roles to `review_status=New`; never overwrite user review decisions.
- Commit and push only when opportunity data actually changes. Never alter company ratings.

## Reporting

After each run, report companies checked, new roles, materially updated roles, possible closures, countries covered and any sources that failed.
