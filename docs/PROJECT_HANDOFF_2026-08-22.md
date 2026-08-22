# ProfessionalDashboard — Project Handoff

Updated: 2026-08-22

This file is the canonical handoff for the current state of the job-search project. It exists so a new ChatGPT thread can continue without reconstructing the full prior conversation.

## User profile and role preference

- Current / recent experience: Investment Analyst at Rockaway Capital; prior Treasury Specialist / PwC Treasury Advisory; earlier Komerční banka investment-banking sales in FX and money markets; earlier Deloitte audit/data internship.
- Education / credentials: Charles University IES MSc Economics & Finance, magna cum laude; Erasmus University of Helsinki; CFA; FRM.
- Core strengths: treasury, financial markets, FX, IRS, derivatives, valuation, liquidity, financial risk, hedge accounting, financial modelling, R, Alteryx, Bloomberg, Refinitiv.
- Strongest preference: analytical finance roles tied to markets, treasury, investments, risk, financing or transactions.
- Lower preference: pure reporting/control/compliance, relationship sales, client coverage, organisational transformation, pure IT/data engineering, deep quant-dev/software roles.
- Geography: Czechia, Germany, Austria, Switzerland, UK/London, Sweden, Norway, Denmark, Finland.
- Abroad compensation should be judged by savings / real economics, not merely Prague-equivalent gross salary.

## Architecture

GitHub repo: `ORosa10/ProfessionalDashboard`, branch `main`.
Streamlit entry: `app.py`.
GitHub is the source of truth; no database.
Streamlit handles UI/data entry and reads/writes repo via GitHub API.
GitHub Actions handle deterministic sourcing/preparation.
Semantic research/judgement is done in ChatGPT on demand, not with a recurring ChatGPT automation.

### Workstreams

- A = Company discovery/relevance.
- B = Manual Opportunity Intake.
- C = Semantic fit / calibrated role judgement.
- D = Remote.
- E = Projects/Interim.
- F = People/Network, low priority.
- G = Country / job-board sourcing engine.
- H = Attainability inference from actual application outcomes.
- I = Opportunity & Application History, factual lifecycle store.
- J = Apply Shortlist / Job Decisions / Action Queue.

### Decision flow

Machine sourced:
`A + C -> G -> A/C enrichment -> J -> I -> H`

Manual opportunity:
`B -> targeting/enrichment -> I -> H`

Feedback:
`J/I -> periodic batch calibration -> A and C`

Important distinction: C is an engine / semantic judgement layer. J is the user's actual working page where Apply / Maybe / Skip decisions happen.

## A — Company relevance

A is effectively complete enough for production. Do not spend time expanding the company universe unless a sourcing gap appears.

Company principles:
- financial complexity > fame/size;
- mid-market / second-tier is attractive;
- strong signals: treasury, commodities, markets, financing, investing, M&A;
- avoid relationship/client-coverage-heavy banking roles;
- PE: investing + portfolio involvement; not real estate/support-only;
- public markets/AM: investment work, not wealth/client portfolio servicing.

## B — Manual intake

`add_opportunity_ui.py` exists and writes `data/user_submitted_opportunities.csv`.
Manual jobs can be rated immediately in B. Do not force a duplicate rating later in J/C.

## C — Semantic fit

Semantic calibration itself is considered done. Do not restart calibration from scratch.

Core files:
- `data/calibration_rules.json`
- `data/semantic_fit.csv`
- targeting markdown files (`GENERAL_TARGETING.md`, sector-specific targeting docs)

`data/semantic_fit.csv` schema is based on:
`opportunity_id, fit, reasoning, generated_at`
where fit is Strong / Moderate / Weak.

Semantic fit should reflect the actual responsibilities and user's profile, not a crude keyword score.

## G — Sourcing

G uses our defined job-board adapters / sources. Do NOT use LinkedIn as an alternative sourcing path unless explicitly requested.

Important existing source examples:
- Czechia: MPSV open data, Jobs.cz, Prace.cz, Cocuma.
- Germany: Bundesagentur Jobsuche, Stellenanzeigen.de.
- Austria: karriere.at, willhaben.
- Switzerland: JobWinner, NZZ Jobs.
- UK: DWP Find a Job, JobServe.
- Sweden: Platsbanken / JobSearch API, Jobbland, LedigaJobb.
- Norway: Jobbsafari, NAV/Arbeidsplassen where working.
- Denmark: JobDanmark, Academic Work, Djøf Jobunivers.
- Finland: Barona, Academic Work.

Manual-fallback / blocked sources should remain compliant with their access terms; do not try to bypass explicit blocks or prohibitions.

## Language feasibility rule

This is a hard actionability filter before C/J, separate from semantic fit.

- English and Czech are fine.
- German is approximately B2 and is NOT a blanket blocker.
- German B1/B2, "good German", ordinary working knowledge etc. remain eligible.
- German becomes a hard feasibility pass only when explicitly requiring C1/C2, fluent / fließend, verhandlungssicher, native / muttersprachlich or equivalent near-native business proficiency.
- Norwegian, Swedish, Danish, Finnish and other unsupported local languages: explicit mandatory / prerequisite / fluent requirement = hard pass before J.
- Preferred / nice-to-have local language is NOT a blocker.
- Mere appearance of a language word is not enough; requirement must be explicit.
- Auto language passes must not contaminate A/C preference feedback.

## Country sourcing weights

User requested country weights based on market size and realistic opportunity.
Stored in `data/country_sourcing_weights.json` and documented in `GENERAL_TARGETING.md`.

Normalized soft sourcing weights:
- Czechia 9.09%
- Germany 18.18%
- Austria 13.64%
- Switzerland 13.64%
- United Kingdom 13.64%
- Sweden 9.09%
- Norway 4.55%
- Denmark 9.09%
- Finland 9.09%

Soft TOP20 country target:
- Czechia 2
- Germany 4
- Austria 3
- Switzerland 3
- United Kingdom 3
- Sweden 2
- Norway 1
- Denmark 1
- Finland 1

These are soft targets, not quotas. Quality wins. If a market lacks good roles, fill from elsewhere.

Implemented commits:
- `956a2c36e3331c3e1c56a21950bd2333956eb0f5` — Add country sourcing target mix
- `9d141708997ab97272e27fe0623460d74fd68c01` — Weight G sourcing by target country mix
- `995e8a3dcdbd1992e667ea34b7f7a65c11128dc6` — Balance C queue by country targets
- `5ac0619a19407b2f2a0cf4bbd8484e68f8fedbe2` — Apply soft country mix to J shortlist
- `0389c7ce66b78dbf0054c62f54344f6445346885` — Document country sourcing target mix

Do not add role-family/segment weights yet. User explicitly wants to wait and observe natural sourcing first.

## J — Apply Shortlist

J is the final actionable apply queue, not a second sourcing board and not a dump of top technical scores.

Important recent bug:
An earlier J version filled 20 slots even with obviously irrelevant roles such as IAM, Databricks, data architect, infrastructure engineer, mechanical PM, AI QA, automation engineer, AI agent developer and finance PhD roles. This was wrong.

User explicitly objected because most of those were clearly outside semantic fit.

Correct J principles now:
- Strong semantic fit can enter J.
- Moderate only if explicitly curated / genuinely adjacent and worth applying to.
- Weak never enters J.
- Unreviewed / no semantic fit never enters J.
- Company rating `Exclude` should keep a role out.
- J does not have to contain exactly 20 roles. If only 8 genuinely good roles exist, show 8 rather than 8 good + 12 garbage.
- `calibration_score` must not rank or visibly drive J.
- J ordering is semantic-first; country mix is secondary and soft.
- Apply / Skip leaves J after saving; Maybe can stay.

Latest semantic-first J fix:
- `c7954783bdec8fce43c6a993e779e920974ead45` — Make J semantic-first and quality-gated

The old screenshot that showed `score 55` represented an old deployed version and should not be treated as the desired behaviour.

## First curated J batch / caution

A first manually curated file `data/j_curated_shortlist.csv` was created. It contained some genuinely strong roles but was too concentrated in AT/DE and still did not solve the core issue of getting 20 genuinely fitting roles.

Examples of strong/interesting roles from that batch:
- NovaTaste Austria — Senior Expert Treasury & Corporate Finance
- KPMG Zurich — Senior Consultant Treasury Transformation Advisory
- GoodMills — Corporate Development Specialist
- PwC Austria — Capital Advisory & Restructuring
- Deloitte Austria — M&A Restructuring
- BDO Austria — Corporate Finance / derivatives valuation
- ING Germany — Market & Liquidity Risk
- Stegra Sweden — Treasury Analyst / Treasury Front Office
- Avaron Sweden — Senior Treasury Specialist
- TEKsystems London — Corporate Treasury Analyst (Moderate due regulatory/prudential-heavy content)

Do not treat the old curated batch as final. It is only a starting pool.

## Specific role judgement from the bad 20-role queue

User stated that in the following list, only the first two looked useful, and the rest were largely garbage for J:
- Investment Banking Analyst
- Corporate Treasury Analyst
- Apotek 1 Business Controller
- Manager, Strategic Finance
- Project Controller
- Finance Transformation Lead
- Identity & Access Management Operations Analyst
- Technical Support & Business Analyst
- Databricks Lead Engineer
- Senior Data Architect
- Finance PhD
- Infrastructure Engineer
- Mechanical Project/Contract Manager
- Content Designer
- Generic Banking Project Manager
- AI QA Tester
- Prudential Regulatory Reporting
- Automation Engineer
- Finance PhD duplicate
- AI Agent Developer

Further nuance:
- Investment Banking Analyst at Arctic Securities was intrinsically Strong but had a mandatory Nordic-language requirement, so it should not be actionable in J.
- Corporate Treasury Analyst in London was the clearest actionable role from that particular batch.

## Current core objective

This is where the next chat should resume.

User's expectation is that finding 20 fitting roles across 9 European markets is realistic. Their rough expectation is that there may be ~150-200 plausible relevant roles in the wider pool.

The correct operational loop is:

`G sources broadly (target 150-300 finance candidates across our own job boards)`
`-> language/actionability filter`
`-> C semantic review`
`-> J gets the best up-to-20 genuinely fitting roles`

If J does not have enough fitting roles, the answer is: SEARCH MORE IN G. Do not lower the J quality bar and do not fill with Weak/unreviewed roles.

## Immediate next task

Do a sourcing sprint, not more architecture work.

1. Expand / improve G finance search queries and depth across our own configured job boards.
2. Use the agreed country weights to determine search effort.
3. Target a broad pool of roughly 150-300 plausible finance candidates.
4. Apply the explicit language feasibility filter before wasting semantic review effort.
5. Perform semantic judgement based on the existing calibrated targeting thesis.
6. Keep only Strong and genuinely useful Moderate roles for the actionable pool.
7. Populate J with up to 20 genuinely fitting roles, ideally 20.
8. Do NOT use LinkedIn for this sourcing sprint.
9. Do NOT add role-family/segment weights yet.
10. Do NOT create ChatGPT scheduled automations for semantic research.

The user approved this sourcing sprint with: "ano do toho".

## Product philosophy

The main KPI is not source count, calibration count or having exactly 20 visible cards. It is: surface genuinely relevant jobs that the user can realistically consider applying to, get decisions into I, and eventually learn attainability from real outcomes in H.
