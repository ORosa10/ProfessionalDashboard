# General Targeting Principles v0.1

Updated: 2026-08-22  
Scope: cross-sector rules for Consulting, Private Markets, Banking, Investment Banking, Corporates and future employer categories

## How sector learning is combined

- Each employer sector keeps its **own targeting hypothesis** based on feedback from roles in that sector.
- A preference becomes part of the general profile only when it is supported by the personal baseline or repeats across multiple sectors.
- Sector-specific title ladders remain separate. An Analyst in private equity or investment banking cannot be treated like an Analyst in a corporate or consulting hierarchy.
- New sector feedback can refine the general profile, but must not silently overwrite the original evidence from another sector.

## General role profile

- Prefer work with meaningful **finance, investment, transaction, treasury, planning, risk or analytical decision-support content**.
- Judge the actual responsibilities and experience requirement before the title.
- Data and technology are attractive when they are tools used to solve finance or investment problems, rather than the entire profession being pure IT.
- Advisory and stakeholder interaction are acceptable. Roles primarily driven by sales targets, client acquisition or relationship selling are a lower priority.

## Seniority

- Roughly **3–7 years of required experience** is a directional target, not a hard interval.
- Plausible titles include Senior Analyst, Analyst on investment tracks, Associate, Senior Consultant and Specialist.
- Manager roles remain visible as reach candidates when their responsibilities are accessible.
- Penalize genuine internships, graduate schemes, assistant roles and clearly junior positions.
- Strongly downrank Senior Manager, Director, Head and equivalent leadership roles unless their stated requirements are unusually accessible.

## Geography and language

- Primary geography: Czechia; Germany, especially Munich, Berlin, Frankfurt and Hamburg; Vienna; Switzerland, especially Zurich/Zug; the Nordics; London and surrounding UK opportunities.
- English and Czech are fluent. German is approximately B2.
- **German is not an automatic blocker at ordinary working level.** Roles asking for B1/B2, good German, gute Deutschkenntnisse or ordinary working knowledge remain eligible for J.
- **German becomes an automatic feasibility pass only when the advert explicitly requires C1/C2, fluent / fließend, verhandlungssicher, native / muttersprachlich or equivalent near-native business proficiency.**
- For Norwegian, Swedish, Danish, Finnish and other non-English/Czech local languages, an **explicit mandatory / prerequisite / fluent requirement is an automatic feasibility pass before J**.
- A mere mention of a language, country or multilingual environment is not enough to filter a role. The requirement must be explicit.
- Language feasibility is separate from intrinsic semantic fit: a role can still be conceptually attractive while being removed from the actionable shortlist because its language requirement makes it non-actionable.

### Country sourcing mix

Use the following as **soft sourcing weights**, not hard quotas. They determine how much effort G spends in each market and how J tries to balance its TOP20. If a country cannot supply a sufficiently relevant actionable role, quality wins and the slot is filled by the next best role elsewhere.

| Country | Normalized sourcing weight | TOP20 target |
|---|---:|---:|
| Czechia | 9.09% | 2 |
| Germany | 18.18% | 4 |
| Austria | 13.64% | 3 |
| Switzerland | 13.64% | 3 |
| United Kingdom | 13.64% | 3 |
| Sweden | 9.09% | 2 |
| Norway | 4.55% | 1 |
| Denmark | 9.09% | 1 |
| Finland | 9.09% | 1 |

Operationally, G allocates country effort while accounting for the number of runnable job boards in each market, so a country with more technical adapters does not automatically dominate simply because it has more sources. C's semantic-fit queue uses the same country mix before quality-first fallback. J uses the TOP20 targets as a soft representation target.

## Signals that must remain separate

- **Intrinsic role interest:** whether the work itself is attractive.
- **Company interest:** the independent Company Universe rating.
- **Access:** familiarity, contacts, references and warm introductions.
- **Feasibility:** language, seniority, technical gaps, work authorization and other constraints.
- **Location economics:** compensation and cost-of-living viability.

These signals may change review order later, but one signal must not rewrite another. A strong contact cannot make an unattractive role intrinsically interesting, and a language gap does not mean the underlying work is unattractive.

## Exploration rule

- Keep roughly **20% exploration capacity** for adjacent, uncertain or unexpectedly titled roles.
- Low initial fit lowers review priority; it does not cause permanent exclusion.
- Scoring remains transparent and recoverable. It must not become a hidden gate before enough real feedback exists.

## Calibration update 2026-08-17 (from 128 ratings + 1 submitted opportunity)

- **Treasury / markets is the confirmed lane.** Treasury-themed roles were the only theme rated net-positive (Interested 16 vs Pass 9); reinforced by the Evotec Treasury Manager submission (Interested). Raised the treasury weight and, importantly, added a dedicated **markets / derivatives / FX / hedging / liquidity / interest-rate / commodities** positive that was previously not scored at all despite being a core personal signal.
- **Compliance/forensics strongly disliked** (Interested 2 vs Pass 16) - downrank deepened.
- **Real estate** added as a light caution (repeated Pass in comments + the earlier PE finding of Real Estate 3/3 Pass).
- **Seniority mismatch remains the top Pass reason** (comments: "junior" 13x, "too senior" 14x) - existing junior/Director+ cautions confirmed, left as-is.
- Held back on M&A / corporate-finance / analytics: their Pass rate looks driven by seniority/tax/compliance (already captured), not the theme itself, so their positive weights were left unchanged to avoid under-surfacing genuinely relevant transaction roles.
- No direct thesis feedback yet (targeting_feedback.csv empty); changes above are rating-driven and deliberately conservative (reorder only, no hard exclusions, exploration preserved).

## Cross-sector note 2026-08-17: pure IT / data roles

Rejecting **pure IT / data / analytics-engineering** roles now repeats across both Consulting (L.E.K. "Digital Data and AI - too technical and IT") and Corporate (five separate Pass comments: "too data and IT", "data science too IT"). This has crossed the threshold from sector-specific into the **general** profile: analytics/data/tech is attractive only as a tool for a finance/investment problem, never as the whole role. Encoded as a caution in calibration_rules.json.

## Cross-sector note 2026-08-17: investments/portfolio is a core positive; a data-quality gap

- **Investment / portfolio management / fixed income / asset management** roles were rated Interested across Banking, Public Markets and Specialist Funds but were previously unscored — now a positive in calibration_rules.json. This belongs in the general profile.
- **Deep code-heavy quant** is a mild negative even though modelling is positive (repeated: "too much in code", "too much quant", "depends how quantitative"). Quant is attractive as applied modelling, not as a software/quant-dev job.
- **Open data-quality item:** several Public Markets roles (Capital Group, Neuberger) could not be judged because their sourced descriptions were generic company boilerplate. Improve description extraction for those employers so the semantic fit has real text to reason over.

## Operational note 2026-08-21: language feasibility before J

- Workstream J is an actionable apply queue, so explicit language blockers are removed **before** C queue construction and before J ranking.
- The source row is preserved for auditability with status `Pass_language`; it is not deleted.
- This is a feasibility rule only. It must not retrain or distort semantic-fit preferences in C.
- German follows the B2 exception above; other mandatory local languages are passed when the requirement is explicit.
