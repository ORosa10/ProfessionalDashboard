# General Company Targeting Principles (cross-sector)

This is the baseline company-level thesis inferred from the current A/B/C/Exclude ratings in `data/company_ratings.csv`. It is a **soft semantic ranking framework**, not a hard filter. A new company should be judged by similarity to the characteristics of positively rated companies, not merely by exact industry labels or brand recognition.

## What tends to rank up

- **Established, credible platforms with real financial complexity.** Large or institutionally credible companies where treasury, capital allocation, investments, financing, risk, markets or valuation are meaningful activities rather than peripheral support functions.
- **International / multi-country businesses.** Cross-border operations, multiple currencies, meaningful financing needs and sophisticated group structures are generally positive because they create more relevant finance roles.
- **Companies with analytical finance depth.** Businesses where the finance function can plausibly touch markets, investment decisions, portfolio management, capital structure, valuation, risk or transaction work.
- **Strong institutional quality.** Recognised governance, professional management, credible ownership and a clear operating or investment model matter more than fame alone.
- **Target geographies remain Europe-focused**, especially DACH, UK, Nordics, Switzerland and Czechia, while multi-region firms can still rank highly if the relevant teams sit in those markets.

## What tends to rank down

- **Company relevance that is mostly generic.** A well-known company should not score highly just because it is large or prestigious if the likely finance work is mainly routine reporting, accounting or generic corporate support.
- **Opaque or highly idiosyncratic groups** where it is difficult to understand the operating model, governance or where the relevant finance role would actually sit.
- **Platforms whose likely opportunity set is dominated by sales, pure operations, generic IT delivery or administrative finance** rather than analytical finance / markets / investment work.
- **Single negative examples are not rules.** An `Exclude` rating should be treated as evidence, not as proof that every similar company must be excluded.

## How to score a newly discovered company

For a new company from A or G, compare it semantically with the existing rated universe along several dimensions:

1. business / ownership model,
2. scale and institutional quality,
3. international and financial complexity,
4. likely depth of treasury / markets / investments / valuation / corporate-finance activity,
5. similarity to existing A-rated versus B/C/Exclude examples in the same sector.

Return a **soft company relevance assessment** (for example Strong / Moderate / Weak with short reasoning). Do not hard-exclude a role because the company is unfamiliar or scores weakly: the job itself is still evaluated separately by C, and an unusually good role at an unfamiliar company can remain relevant.

## Relationship to C

- **A asks:** is this the kind of company worth watching?
- **C asks:** is this specific role a semantic fit?

Company relevance should therefore be a secondary signal alongside role fit, not a replacement for it.
