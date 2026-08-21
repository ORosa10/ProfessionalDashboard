# Opportunity decision flow

This document is the operating model for the job-search dashboard.

## Core flow

### Automated opportunities

`A/C targeting guidance -> G sourcing -> A company context + C role fit/ranking -> J Apply Shortlist -> I Opportunity History -> H attainability`

G is a sourcing layer, not the final review queue. A and C also guide what G searches for, so the system is a feedback loop rather than a one-way pipeline.

### Manually added opportunities

`B Add Opportunity -> user rating -> A/C enrichment and fit -> I Opportunity History -> H attainability`

Once an opportunity is in I, its original source (B or G/J) is retained only as provenance. Application tracking is shared.

## A — Company relevance

A answers: **Is this an attractive company/context?**

Signals include company type, financial complexity, treasury/markets/investment exposure, capital allocation, financing, commodity exposure, ownership and the existing company thesis/feedback.

A helps G decide what to look for and supplies company context to J. It is not a hard exclusion gate.

## B — Manual Opportunity Intake

B is the user-supplied input path. The user pastes a job and rates it there. B then feeds the same A/C/history logic as automatically sourced opportunities.

## C — Role fit and shortlist intelligence

C answers: **Is this a good role for the user?**

C combines the stable targeting thesis, semantic fit and accumulated feedback. Its production purpose is to rank and reduce a large source universe to a small actionable set, not to create an endless calibration exercise.

C should preserve diversity across role families, employers and geographies rather than returning twenty near-identical jobs.

Calibration is a background maintenance function. Individual decisions do not rewrite C after every click; accumulated patterns can be used in periodic batches.

## G — Automated sourcing

G answers: **What relevant jobs are currently available?**

G searches country/job-board sources using guidance derived from A/C. It produces candidate jobs, which are then evaluated by A/C before reaching the user.

## J — Apply Shortlist

J is the user's main action page for automatically sourced jobs.

Target UX: approximately **20 best current opportunities**, diversified across plausible role families/companies/geographies.

For each job the user can:

- open the real job page,
- choose `Apply`, `Maybe` or `Skip`,
- optionally give separate company feedback and role feedback,
- add a short comment.

`Apply` and `Skip` leave the active shortlist after saving. `Maybe` can remain visible.

J feedback is stored immediately in I. Accumulated company/role patterns can later be fed back to A/C in calibration batches.

## I — Opportunity & Application History

I is the factual memory layer.

It stores decisions from both B and J together with the job/company context available at the time of decision. It also stores application stages and outcomes.

Application stages include:

`Not applied -> Applied -> 1st interview -> Case -> Final -> Offer`

and terminal outcomes such as:

`Rejected pre-screen / Lost after 1st / Lost after case / Withdrawn`.

I is data; it should not itself infer fit or attainability.

## H — Attainability

H answers: **How realistic is it that the user can obtain similar roles?**

H is inferred from actual application outcomes in I. It must remain separate from C semantic preference fit. A job can be highly attractive but difficult to obtain, or attainable but unattractive.

Do not overfit H to one or two applications; use repeated outcome evidence.

## Feedback loops

The long-run learning loop is:

`J/I company patterns -> periodic A calibration`

`J/I role patterns -> periodic C calibration`

`I application outcomes -> H attainability`

The primary product objective remains applications and offers, not calibration itself.
