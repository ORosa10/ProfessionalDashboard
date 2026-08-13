# Private Equity Sector Hypothesis v0.1

Updated: 2026-08-13
Evidence base: first diverse PE calibration cohort, 20/20 reviewed roles (`data/pe_calibration_shortlist.csv`, feedback in `data/job_feedback.csv`)

This hypothesis applies primarily to **Private Equity / private-markets employers** (Partners Group, Ares Management, Ardian, Intermediate Capital Group, Mutares, Waterland and similar). It informs the general profile only where a signal repeats across sectors; it must not be copied mechanically to Consulting, Banking, Corporates or other sectors.

## Calibration result

- **2 Interested / 8 Maybe / 10 Pass.** Every role has a written comment.
- This is a much weaker hit rate than Consulting's first batch (14/10/26 out of 50). Two structural issues, not just role-content mismatch, explain most of the Pass/Maybe: seniority framing and a coverage gap in the role type actually wanted (see below).

## ⚠️ Critical sourcing gap: classic PE Investment Analyst roles (flagged 2026-08-13)

**This is the single most important open issue in PE sourcing right now.** "Investment Analyst" — a junior role embedded on the direct-investment team, doing deal sourcing/screening, LBO and financial modeling, and portfolio-company analysis — is the single most common, default entry/junior role type that exists across PE firms in general. It is not a niche lane; it is close to *the* standard way into the industry at this seniority.

This first 20-role calibration batch essentially did not cover it. Instead it skewed toward fund operations/finance/reporting roles (fund controller, fund launch/wind-down, IFRS reporting integration, group finance reporting) and toward Associate/Senior Associate/Manager-titled investment roles that were either too senior or required more experience than you currently have (~2 years). Not a single role in this batch was a straightforward, junior, direct-investment-team Investment Analyst position.

- This reads as a **sourcing-coverage gap, not a personal-fit rejection** — the keyword matching already includes "investment" and "analyst" (`sourcing/pe_pilot.py`'s `PE_ROLE_TERMS`), so the shortage is about which firms/postings were actually live and sampled at the time, not a term-matching bug.
- **Every future PE sourcing and calibration pass must deliberately search for and weight in "Investment Analyst," "Analyst, Private Equity," "Investment Team Analyst" or equivalent direct-investment-team titles**, clearly distinct from fund-operations/finance-function roles. Until this lane has real coverage and real feedback, the PE hypothesis should be treated as incomplete on its most important role type.

## PE lanes to prioritize

1. **Treasury / Fund Finance / CFO agenda**
   - 2 Interested from 2 direct examples (Treasury Manager at ICG; a Fund Finance / Secondaries & Primaries Analyst at Ardian read as "kinda treasury").
   - This is the strongest *confirmed* lane so far: treasury, fund finance, CFO-adjacent work, at accessible (non-VP/Manager) seniority.
   - Explicitly *not* about being close to the investment/deal team — it's the finance-function-inside-a-PE-firm angle, same instinct as the Consulting hypothesis's Treasury lane.
   - Important caveat: this is currently the strongest signal only because it's the lane with the most examples in this batch — it should not be read as stronger than classic Investment Analyst roles, which simply have zero data points yet (see gap above).

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

1. **Genuine "Investment Analyst" roles on direct-investment teams — deal analysis, financial modeling, portfolio monitoring — explicitly distinct from fund-operations/reporting roles. This is the top priority and the clearest gap to close before the next calibration round** (see the flagged gap above).
2. Treasury, fund finance and CFO-adjacent roles inside PE firms, at Analyst/junior-Associate level.
3. Roles stating roughly 1-3 years of required experience rather than 3-5+.
4. Continue excluding Real Estate, Investor Relations and Digital Infrastructure as standalone verticals.
5. One more lower-seniority Credit/Risk example would help resolve whether that lane is genuinely unattractive or just consistently over-leveled so far.
