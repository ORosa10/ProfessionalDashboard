# Private Equity Sector Hypothesis v0.1

Updated: 2026-08-13
Evidence base: first diverse PE calibration cohort, 20/20 reviewed roles (`data/pe_calibration_shortlist.csv`, feedback in `data/job_feedback.csv`)

This hypothesis applies primarily to **Private Equity / private-markets employers** (Partners Group, Ares Management, Ardian, Intermediate Capital Group, Mutares, Waterland and similar). It informs the general profile only where a signal repeats across sectors; it must not be copied mechanically to Consulting, Banking, Corporates or other sectors.

## Calibration result

- **2 Interested / 8 Maybe / 10 Pass.** Every role has a written comment.
- This is a much weaker hit rate than Consulting's first batch (14/10/26 out of 50). Two structural issues, not just role-content mismatch, explain most of the Pass/Maybe: seniority framing and a coverage gap in the role type actually wanted (see below).

## PE lanes to prioritize

1. **Treasury / Fund Finance / CFO agenda**
   - 2 Interested from 2 direct examples (Treasury Manager at ICG; a Fund Finance / Secondaries & Primaries Analyst at Ardian read as "kinda treasury").
   - This is the strongest confirmed lane so far: treasury, fund finance, CFO-adjacent work, at accessible (non-VP/Manager) seniority.
   - Explicitly *not* about being close to the investment/deal team — it's the finance-function-inside-a-PE-firm angle, same instinct as the Consulting hypothesis's Treasury lane.

2. **Classic PE Investment Analyst roles — under-covered, needs deliberate sourcing (flagged 2026-08-13)**
   - This batch skewed heavily toward fund operations/finance/reporting roles (fund controller, fund launch/wind-down, IFRS reporting integration, group finance reporting) and toward Associate/Senior Associate/Manager-titled investment roles that were too senior or required more experience than you have (~2 years) — not toward genuine junior **Investment Analyst** roles on a direct-investment team (deal sourcing, LBO/financial modeling, portfolio company analysis).
   - This looks like a sourcing-coverage gap rather than a personal-fit rejection: the underlying keyword matching already includes "investment" and "analyst" (`sourcing/pe_pilot.py`'s `PE_ROLE_TERMS`), so the shortage is about which firms/postings were live and sampled, not a term-matching bug.
   - Next sourcing/calibration pass should deliberately look for and weight in "Investment Analyst," "Analyst, Private Equity," "Investment Team Analyst" or equivalent titles at the direct-investment-team level, distinct from fund-operations/finance-function roles.

## PE lanes to downrank

- **Real Estate** — 3 for 3 Pass (Associate Real Estate Asset Management, Fund Finance Manager Real Estate Debt, Analyst Real Estate Secondaries). Consistent, clear signal: no interest or experience in real estate as an asset class, regardless of seniority or function.
- **Digital Infrastructure** — Pass, no experience and limited interest as a standalone vertical.
- **Credit / quantitative risk at senior level** — VP Credit Analysis and Quantitative Risk Manager were both too senior and outside direct experience; unclear yet whether credit itself is unattractive or whether it was purely the seniority/VP framing — needs another data point at a lower seniority before concluding either way.
- **Investor Relations** — explicit Pass ("no investor relations").
- **Niche verticals unrelated to core finance** — Sports Media & Entertainment Associate was "interesting angle" but landed Maybe/borderline because the PE-relevance of the role itself was unclear, not because sports is uninteresting.

## PE seniority interpretation

- **Associate is borderline, not automatically fine.** Several Associate-titled roles were marked Maybe specifically because the description implied 3-5 years while your actual experience is closer to 2 — description-stated experience matters more than the title band itself.
- **Manager, Senior Associate/Manager, VP and equivalent are consistently too senior** for this stage — this was the single most repeated Pass reason across the batch (Investment Manager, Quantitative Risk Manager, VP Credit Analysis, Manager/Senior Manager Group Finance Reporting, (Senior) Investment Manager DACH).
- **Junior/Analyst-titled roles were dismissed for content, not seniority** (Junior Asset Class Analyst was "not that interesting" on role content, not on level) — so Analyst-level itself is not the problem, the *type* of analyst role was.

## What the next PE search should emphasize

- Treasury, fund finance and CFO-adjacent roles inside PE firms, at Analyst/junior-Associate level.
- Genuine **Investment Analyst** roles on direct-investment teams — deal analysis, financial modeling, portfolio monitoring — explicitly distinct from fund-operations/reporting roles. This is the clearest gap to close before the next calibration round.
- Roles stating roughly 1-3 years of required experience rather than 3-5+.
- Continue excluding Real Estate, Investor Relations and Digital Infrastructure as standalone verticals.
- One more lower-seniority Credit/Risk example would help resolve whether that lane is genuinely unattractive or just consistently over-leveled so far.
