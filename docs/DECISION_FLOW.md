# Opportunity decision flow

This document is the operating model for the job-search dashboard.

## Core flow

### Automated opportunities

`A/C targeting guidance -> G sourcing -> language/actionability gate -> A company context + C semantic role fit -> J Apply Shortlist -> I Opportunity History -> H attainability`

G is a sourcing layer, not the final review queue. A and C also guide what G searches for, so the system is a feedback loop rather than a one-way pipeline.

Semantic judgement in C is performed in chat on demand and written back to `data/semantic_fit.csv`. GitHub Actions prepare and refresh deterministic sourcing data; they do not invent semantic fit.

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

C is semantic-first. It uses the stable targeting thesis and the actual responsibilities/seniority of the job. Legacy technical/calibration scores may help G organise a broad source universe, but they must not determine J ordering or substitute for semantic judgement.

Semantic outputs are `Strong`, `Moderate` or `Weak` with written reasoning. The intended interpretation is:

- `Strong`: genuinely attractive role-content fit and eligible for J subject to feasibility checks.
- `Moderate`: adjacent / mixed fit; can enter J only when it has been explicitly reviewed and judged actionable.
- `Weak`: not suitable for J.
- Unreviewed roles never enter J.

C should preserve diversity across role families, employers and geographies, but diversity must not lower the quality threshold.

Calibration is a background maintenance function. Individual decisions do not rewrite C after every click; accumulated patterns can be used in periodic batches.

## G — Automated sourcing

G answers: **What relevant jobs are currently available?**

G searches the configured country/job-board sources in `data/job_boards.csv`; LinkedIn is not part of the automated G sourcing flow. G should search broadly enough to create a large candidate pool, then continue searching when the semantic pipeline has not produced enough fitting opportunities.

The operational objective is not to stop after the first 20 source matches. A normal cycle can contain roughly 150–300 finance candidates across the target markets, after which actionability and C semantic review reduce the pool.

Country sourcing effort follows `data/country_sourcing_weights.json` as a soft target. Current normalized weights are approximately:

- Czechia 9.1%
- Germany 18.2%
- Austria 13.6%
- Switzerland 13.6%
- United Kingdom 13.6%
- Sweden 9.1%
- Norway 4.5%
- Denmark 9.1%
- Finland 9.1%

These weights guide search effort rather than creating hard quotas. If one market is sparse, quality roles from other markets may fill the gap.

### Actionability / language gate

Feasibility is separate from semantic interest.

- English and Czech are acceptable.
- German B1/B2, good German or ordinary working knowledge remain eligible.
- German is a hard blocker only when C1/C2, fluent/fließend, verhandlungssicher, native/muttersprachlich or equivalent advanced fluency is explicitly required.
- Explicit mandatory Norwegian, Swedish, Danish, Finnish or other unsupported local-language requirements are hard blockers.
- Preferred / nice-to-have language requirements are not blockers.

Hard-blocked roles must not consume C research capacity or J slots and must not be treated as negative user-preference feedback.

## J — Apply Shortlist

J is the user's main action page for automatically sourced jobs. It is an **apply queue**, not a second sourcing board.

Target UX: **up to 20 best current actionable opportunities**. Twenty is a capacity target, not a fill requirement. If only 8 roles pass the semantic/actionability threshold, J should show 8 while G continues searching for more; it must never fill the remaining slots with weak or unreviewed jobs.

Eligibility rules:

- Strong semantic fit: eligible subject to feasibility.
- Moderate semantic fit: only when explicitly curated/reviewed as actionable.
- Weak semantic fit: never shown.
- No semantic fit: never shown.
- Company `Exclude`: never shown.
- Technical `calibration_score` is not displayed and does not rank J.

Country representation uses the agreed soft TOP20 mix:

`CZ 2 / DE 4 / AT 3 / CH 3 / UK 3 / SE 2 / NO 1 / DK 1 / FI 1`

This is secondary to quality: country targets cannot force weak roles into J.

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
