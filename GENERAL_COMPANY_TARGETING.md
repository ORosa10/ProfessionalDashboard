# General Company Targeting Principles (cross-sector)

This company-level thesis is inferred from the current A/B/C/Exclude ratings in `data/company_ratings.csv` and the first full feedback round in `data/company_targeting_feedback.csv`. It is a **soft semantic ranking framework**, not a hard filter. A new company should be judged by similarity to the characteristics of positively rated companies, not merely by exact industry labels, size or brand recognition.

## What tends to rank up

- **Established, credible platforms with real financial complexity.** Companies where treasury, capital allocation, investments, financing, risk, markets, valuation or transaction work are meaningful activities rather than peripheral support functions.
- **International / multi-country businesses.** Cross-border operations, multiple currencies, capital-markets access and sophisticated group structures are positive because they create more relevant finance roles.
- **Companies with analytical finance depth.** Businesses where finance can plausibly touch markets, investment decisions, portfolio management, capital structure, valuation, risk or transactions.
- **Strong institutional quality.** Professional management, clear governance and a credible operating or investment model matter more than fame alone.
- **Europe-focused opportunity sets**, especially DACH, UK, Nordics and Switzerland. Czech opportunities remain valid, but a local-only Czech platform is generally less attractive when an otherwise similar international alternative exists.
- **Interesting market exposure is a plus, not an industry mandate.** Energy is attractive partly because commodities create useful market/risk exposure, but energy should not automatically outrank retail, industrials, consumer or other sectors with equally sophisticated finance functions.
- **Second-tier and mid-market companies are explicitly in scope.** Do not over-index on flagship employers. A company does not need to be a household name or mega-cap to rank highly if its business model creates meaningful treasury, markets, investment, financing, commodity, M&A or capital-allocation complexity. Smaller international businesses with professional finance teams can be especially attractive because relevant roles may be broader and more attainable.

## What tends to rank down

- **Company relevance that is mostly generic.** A famous company should not score highly just because it is large if the likely finance work is mainly routine reporting, accounting or generic support.
- **Platforms whose likely opportunity set is dominated by client relationship management, sales, distribution, pure operations or administrative finance** rather than analytical finance, markets or investments.
- **Opaque or highly idiosyncratic groups**, especially local conglomerates where governance, capital-allocation logic or the location of relevant finance work is unclear.
- **Real-estate-heavy investment platforms** are less attractive than private-markets firms with active company/deal/portfolio involvement.
- **Single negative examples are not rules.** An `Exclude` rating is evidence, not proof that every similar company must be excluded.

## Discovery mix: avoid flagship bias

Company discovery should deliberately span three layers rather than repeatedly returning only the largest employers:

1. **Established / flagship platforms (~50%)** — large, institutionally strong companies that clearly match the thesis.
2. **Second-tier / mid-market (~40%)** — less famous but professionally managed firms with enough international or financial complexity to support relevant roles.
3. **Exploration (~10%)** — smaller or less obvious companies that may still be attractive because of unusual market exposure, acquisitive growth, leverage, export/FX complexity, commodity exposure, project finance, active ownership or another reason that creates sophisticated finance work.

These percentages are guidance, not a hard quota. Company size should not be screened through a rigid EBITDA or revenue minimum. Roughly speaking, even businesses around tens of millions of EUR of EBITDA can be worth testing if the finance complexity is real; the business model and likely role content matter more than a specific threshold.

## Company relevance versus attainability

Do **not** confuse company attractiveness with how easy it is to get hired there. Some mega-funds, global investment managers and top investment banks are attractive companies but may be reach targets because of competition, seniority or work-life-balance trade-offs. That should appear later as an **attainability caution**, not as a lower semantic company score by default.

Likewise, smaller boutiques are not automatically weak. A smaller firm can rank well if the work is institutional, analytical and aligned; local/Czech boutiques are simply less preferred when the opportunity set is narrow or domestically focused.

## How to score a newly discovered company

For a new company from A or G, compare it semantically with the existing rated universe along several dimensions:

1. business / ownership model,
2. scale and institutional quality,
3. international and financial complexity,
4. likely depth of treasury / markets / investments / valuation / corporate-finance activity,
5. likely role mix: analytical finance versus reporting / operations / client-sales,
6. similarity to existing A-rated versus B/C/Exclude examples in the same sector,
7. any explicit sector feedback recorded by the user.

Return a **soft company relevance assessment** (for example Strong / Moderate / Weak with short reasoning). Do not hard-exclude a role because the company is unfamiliar or scores weakly: the job itself is still evaluated separately by C, and an unusually good role at an unfamiliar company can remain relevant.

## Relationship to C and H

- **A asks:** is this the kind of company worth watching?
- **C asks:** is this specific role a semantic fit?
- **H asks:** how attainable is the role in practice?

A therefore should not downrank an otherwise attractive company merely because it is highly competitive. Company relevance and attainability are separate signals.
