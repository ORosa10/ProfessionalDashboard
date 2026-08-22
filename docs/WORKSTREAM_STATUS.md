# Workstream status A–J

Updated: 2026-08-22

This file is the compact persistent project context. `docs/DECISION_FLOW.md` contains the detailed operating model.

## A — Company relevance

Status: mature / maintenance.

Purpose: company attractiveness and context. Company relevance is informative, not a hard role gate. Company feedback is accumulated and recalibrated in batches.

## B — Manual Opportunity Intake

Status: working.

Purpose: manual job/opportunity entry. The user rates the opportunity directly in B; downstream pages must not force a duplicate preference decision.

## C — Semantic role fit

Status: calibrated; production semantic review is active.

Purpose: judge the actual job responsibilities against the targeting thesis. Semantic judgement is done in chat and written back to the repository. C is semantic-first, not score-first.

Outputs:
- Strong = genuine fit and potentially actionable.
- Moderate = mixed/adjacent; only explicitly reviewed actionable roles may enter J.
- Weak = never enters J.
- Unreviewed = never enters J.

Technical/calibration scores may assist broad G candidate organisation but do not rank or display in J.

## D — Remote

Status: secondary / low priority.

Purpose: remote-opportunity exploration. Do not divert effort from the core G -> C -> J application pipeline.

## E — Projects / Interim

Status: secondary / sparse.

Purpose: project/interim opportunities. Maintain but do not prioritise over permanent-role sourcing unless evidence changes.

## F — People / Network

Status: deferred / nice-to-have.

Purpose: contacts and networking layer. Not a blocker for the core sourcing/application workflow.

## G — Automated sourcing

Status: active; current focus is search depth and quality.

Purpose: continuously create a sufficiently large current finance-role pool from the configured country/job-board sources. LinkedIn is not part of the automated G flow.

Current operational principle:
- Search broadly across the nine target markets.
- A normal source pool can be ~150–300 finance candidates.
- Do not stop because 20 raw jobs were found.
- If C/J cannot produce 20 quality actionable roles, G searches deeper / expands relevant queries rather than lowering the J threshold.
- Country search effort follows `data/country_sourcing_weights.json` as a soft allocation.
- Explicit language blockers are feasibility exclusions, not negative preference feedback.

Current country mix:
- CZ 9.1%
- DE 18.2%
- AT 13.6%
- CH 13.6%
- UK 13.6%
- SE 9.1%
- NO 4.5%
- DK 9.1%
- FI 9.1%

Role-family weights are intentionally NOT configured yet; observe actual sourcing and decision data first.

## H — Attainability

Status: early / data-limited.

Purpose: infer realistic chance of obtaining similar roles from actual application outcomes in I. Keep separate from C preference fit and avoid overfitting to a few applications.

## I — Opportunity & Application History

Status: working factual history layer.

Purpose: shared lifecycle/outcome memory for both B and G/J opportunities. I stores facts and decisions; it does not infer preference or attainability by itself.

## J — Apply Shortlist

Status: active; semantic quality gate implemented.

Purpose: final action queue, not a sourcing board.

Rules:
- Capacity target is up to 20 roles.
- Never fill to 20 with garbage.
- Strong semantic fit is eligible subject to feasibility.
- Moderate requires explicit review/curation as actionable.
- Weak and unreviewed jobs never appear.
- Technical `calibration_score` is not displayed and does not rank J.
- Country targets are soft and secondary to quality.
- Apply/Skip leave the queue; Maybe can remain.

Current curated batch after the 2026-08-22 sourcing correction: 20 roles, 19 Strong and 1 explicitly reviewed Moderate before any further language/availability exclusions.

## Current priority

1. Keep sourcing deeper in G using the configured job-board sources.
2. Verify language/actionability and current vacancy status.
3. Perform C semantic review on promising candidates.
4. Maintain roughly 20 genuinely actionable fitting roles in J.
5. Record real Apply/Maybe/Skip decisions in I and use accumulated batches later for A/C calibration and H attainability.
