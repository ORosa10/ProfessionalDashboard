# ProfessionalDashboard — Canonical A–J Workstream Context

This document is the current conceptual source of truth for the job-search architecture. It is intentionally about responsibilities and data flow, not implementation details.

## Core flow

```text
A company context ─────┐
C role/search thesis ──┤
Country targeting ─────┤
                       ▼
                       G
                       │ candidates
                       ▼
                       C
                       │ Strong only
                       ▼
              Actionability / Quality
                       │
                       ▼
                       J
                       │ decisions + feedback
                       ▼
               backend decision history
                       │
             Apply ────┴──→ I
                           │ stages/outcomes
                           ▼
                           H
```

Feedback from J routes to A/C learning even for Skip/Maybe. The backend history can retain all decisions, but visible I must contain only actual applications.

## A — Company Intelligence / Company Relevance

Purpose: decide whether an employer is worth following, independently from whether a specific vacancy is a fit.

Rules:
- explicit user A/B/C/Exclude is highest authority and is never overwritten automatically;
- historical evidence may create suggestions only;
- G may discover new employers and propose them to A as Unrated/Suggested;
- A context may influence sourcing/ranking context, but it must not turn a semantically weak role into Strong.

Outstanding architecture:
- ingest discovered employers from G safely;
- use J/I feedback as learning evidence without overwriting explicit ratings;
- surface H context without making H authoritative over A.

## B — Manual Add

User rule: anything manually added in B is a role the user is interested in and has already applied to.

Therefore:
- B = Interested + Applied;
- B bypasses J;
- B → I directly with application stage Applied;
- salary research still runs automatically using free/public research;
- any B vacancy must never re-enter J, even through another source, URL or ID.

Dedup priority for B exclusion:
1. canonical/normalised vacancy URL and known aliases;
2. mapped source/job IDs;
3. conservative company + normalised title (+ location when needed) fallback.

## C — Semantic Role Fit

Purpose: evaluate the actual content of each role from G using the full role description and the accumulated job-search context.

Output:
- Strong
- Moderate
- Weak
- short semantic reasoning

C is about role-content fit only. It must not be changed by geography, salary, link health, language, company attractiveness or H.

Target interpretation:
- Strong: real target work, e.g. corporate treasury/markets execution, deal finance/M&A execution, corporate development with real transactions, investment decision-making, practical market/liquidity/financial risk linked to markets/hedging, transaction valuation/modelling;
- Moderate: relevant but secondary, e.g. pure quant/model development, generic FP&A/business partnering, portfolio monitoring, generic controlling, credit-heavy roles, investment-adjacent operations;
- Weak: reporting/compliance/ops, finance transformation, IT/data engineering, sales/outreach, non-finance roles, or clearly wrong seniority/content.

Important distinction:
- C asks: “Is this truly target role content?”
- J asks: “Of the Strong roles, which are best to apply to now?”

Every relevant G role should eventually receive a C judgment. Processing can be batched (e.g. 100–160 roles at a time), but batch size is only an implementation constraint, not a filter. Previously judged roles should not be judged again unless the vacancy materially changes or explicit recalibration is required.

Canonical target store: `data/semantic_fit.csv`.

## D — Remote lane

Purpose: source remote opportunities as a secondary lane.

Flow: D → G/canonical candidate pool → C.

Actionability rules still apply, especially remote employability. Remote US/Canada-only is a blocker; Europe/EMEA/worldwide is normally acceptable; vague Remote is a warning.

## E — Projects / Interim lane

Purpose: source project/interim opportunities as a secondary lane.

Flow: E → G/canonical candidate pool → C.

It does not have a separate semantic truth; C remains authoritative for role fit.

## F — Network Access

Purpose: add network/access context to companies and opportunities.

Flow: F → A/context.

Privacy constraint: the repository is public. Raw LinkedIn names, profile URLs or private network data must not be persisted to the public repo. Before F goes live, storage must be private or only aggregate/non-identifying outputs may be persisted.

## G — Sourcing Engine

Purpose: one logical sourcing engine that continuously gathers opportunities from all source lanes.

Inputs include:
- A/company universe;
- country targeting;
- company career pages;
- country/job boards;
- Corporate;
- Financial Services;
- Holdings;
- Investment Banking;
- Public Markets / Asset Management;
- Specialist Funds;
- PE;
- Consulting;
- D remote;
- E projects/interim.

G outputs vacancy candidates to C. G sends employer identity/discovery to A, not role-fit conclusions.

Target state: all G streams merge into one canonical candidate pool before C. Separate staging branches are implementation detail only and must not fragment the logical pipeline.

## H — Attainability

Purpose: estimate the realistic chance of getting similar roles based on actual application outcomes.

Only factual application stages/outcomes from I count as H evidence. Preference actions such as Skip/Maybe are not attainability outcomes.

H is soft context only. It must never override C semantic fit, A explicit company ratings or hard actionability rules.

## I — Application Tracker

Purpose: track only actual applications and their outcomes.

Sources:
- B manual add → Applied directly;
- J Apply → Applied.

Visible I should contain only actual application processes, e.g.:
- Applied
- 1st interview
- Case
- Final
- Offer
- Rejected
- Withdrawn

Maybe, Skip, New and comment-only J records remain in backend history for learning but must not appear in visible I.

I stage/outcome updates are the factual downstream evidence for H.

## J — Apply Shortlist

Purpose: a fresh decision queue of new automatically sourced roles.

J should contain only Strong + actionable roles after exclusions and ranking.

User decisions:
- Apply → I;
- Maybe → backend history / learning, not visible I;
- Skip → backend history / learning, not visible I.

J feedback (company feedback, role feedback, comments) feeds A/C learning. Any role with substantive prior review — including comment-only feedback — should not recycle into a fresh J batch.

Regular-J guardrails:
- exclude B/manual-applied vacancies by canonical identity;
- exclude already reviewed history;
- A=Exclude is a separate gate;
- hard actionability blockers are removed;
- Big Four is normally routed to a separate batch, not used as filler in regular J;
- Big Four may have explicit per-opportunity exceptions only when intentionally approved;
- use soft diversification so J does not become dominated by pure quant or one role family;
- country targets are soft quality-guided targets, not quotas that force Moderate/Weak/blocker roles into J.

## Actionability / Quality layer

This layer is separate from C.

Typical hard blockers:
- explicit fluent/C1/C2/native-like German, unless an opportunity-level exception exists;
- mandatory/fluent Nordic local language;
- explicit outside-target geography unless remote employability works;
- remote US/Canada-only;
- closed/expired/removed vacancy;
- missing or confirmed dead job URL.

Typical warnings:
- salary unknown;
- seniority stretch;
- H low/unknown;
- stale posting;
- vague/broad remote or geographic wording.

Known opportunity-level exception:
- PwC Zürich Senior Associate — Treasury Strategy & Technology may pass despite fluent-German wording because the user explicitly approved it as an exceptional fit.

## Big Four policy

Big Four is a separate application/review lane by default. PwC, Deloitte, KPMG and EY should not consume regular-J slots merely because they publish many relevant roles.

Preferred workflow:
- collect relevant Big Four roles across countries;
- review them periodically as one batch;
- compare and potentially apply to several together.

C should still judge Big Four roles normally; separation happens at J/distribution level, not by artificially penalising C.

## Country targeting

Current sourcing weights:
- CZ 2
- DE 4
- AT 3
- CH 3
- UK 3
- SE 2
- NO 1
- DK 1
- FI 1

Principle: quality wins. If a country cannot provide sufficiently relevant/actionable Strong roles, show the deficit and redistribute rather than filling with weaker candidates.

## Learning loop

Preferred loop:

```text
G new roles
  ↓
C semantic judgment
  ↓
Strong + Actionability
  ↓
J
  ├─ Apply → I → H
  ├─ Maybe → A/C learning
  └─ Skip  → A/C learning

B manual application → I directly → H
```

Explicit user feedback should have more authority than inferred historical patterns. Comment-only feedback is valid learning evidence but should not silently mutate factual application state.

## Current implementation principle

The live dashboard must remain usable while migration continues. New architecture should first run in shadow, reconcile with latest live `main`, pass tests/diagnostics, and only then cut over incrementally. Do not introduce new metered/pay-as-you-go services without explicit user approval.
