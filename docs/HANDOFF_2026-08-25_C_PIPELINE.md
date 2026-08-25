# Handoff — C semantic pipeline / A–J architecture

Date: 2026-08-25

This is the restart point for a fresh ChatGPT conversation. The canonical conceptual definitions of A–J are in `docs/WORKSTREAM_CONTEXT.md`. Read that file first; this handoff records the implementation state and the decisions made in the long working chat that ended here.

## User-level decisions now considered final

- Do not build J by manually searching for “another 20 jobs” in chat.
- G must replenish source pools continuously; C must judge the roles coming from G; J must be generated from the resulting Strong + actionable pool.
- Every relevant G role should eventually receive a C semantic judgment. Batch size such as 160 is only an internal processing limit, not a filter or discard rule.
- C may be performed by ChatGPT reasoning in batches. The preferred future operating model is a dedicated ChatGPT Work / agent workflow for C, with the canonical context and repository attached.
- C judges role-content fit only: Strong / Moderate / Weak + short reasoning.
- Strong should mean genuinely desirable target work, not merely “the user could do this job”. Pure quant/model-development, generic FP&A/business partnering, monitoring/control and similar finance-adjacent roles should generally be Moderate rather than automatically Strong.
- Big Four is a separate application/review lane. PwC, Deloitte, KPMG and EY should not normally consume regular-J slots; C still evaluates their roles normally.
- B manual add means the user has already applied. B bypasses J and goes directly to I as Applied.
- I visible UI contains actual applications only. New / Maybe / Skip / comment-only J records remain in backend history for learning so historical rejections are retained.
- Any substantive prior J review, including comment-only feedback, prevents the vacancy from recycling into a fresh regular J batch.
- B/manual-applied vacancies must never re-enter J even under another source URL/ID; dedupe must use canonical vacancy identity, not only `opportunity_id`.
- No new metered/pay-as-you-go service unless explicitly approved.

## Current pipeline state

Migration branch: `architecture-safe-migration`
Draft PR: #3 `WIP: safe core architecture migration`

A new shadow replenishment workflow now runs the intended logical pipeline:

`all G source lanes -> canonical G candidate pool -> A employer suggestions -> canonical C / C queue -> actionability -> B/history/Big4 guardrails -> auto J`

First successful unified run showed:

- G canonical candidates: 1,860
- A discovered-employer suggestions: 363
- C initial pending queue: 160 (hard processing batch limit, not total pending population)
- Big Four routed out of regular J: ~1,026 candidates after alias hardening
- previously reviewed history excluded from regular J: 35

The main historical bottleneck was not lack of sourcing. G already had many candidates distributed across multiple staging branches, while only a small subset had canonical C judgments. Live J was therefore being assembled from a tiny pre-judged pool.

## C batch 1 completed

The first real 160-role C batch was processed with ChatGPT semantic reasoning and persisted to `data/semantic_fit.csv` on the migration branch.

Batch result:

- Strong: 41
- Moderate: 38
- Weak: 81

The migration-branch canonical C store then contained 253 judged roles total (existing + this batch).

Several older overly-broad Strong judgments were also recalibrated downward where the latest J feedback showed they were not true target roles (examples: pure quant, generic business partnering, overly senior UK manager-type roles, tech-heavy M&A/advisory).

## C loop bug found and fixed

The first rerun after batch 1 initially ignored the new C judgments because the replenishment workflow was reading `data/semantic_fit.csv` from `main` instead of the evolving migration-branch state.

That was fixed in `.github/workflows/architecture-replenishment-shadow.yml`: C semantic state now comes from the checked-out migration/PR branch, while live decision history and B submissions still come from `main`.

After the fix the workflow correctly reported:

- semantic state: 253 existing C rows
- new pending C queue: another 160 previously unjudged roles

This proves the intended batching loop works: process 160 -> persist -> rerun -> next 160 appears.

## J result after stricter C calibration

After batch 1 and stricter semantic calibration, auto J shrank to only 6 Strong + actionable regular-J roles.

This is currently considered a healthy diagnostic rather than a failure: the system stopped forcing weak or merely technically compatible jobs into Strong/J. More C batches must be processed before judging the quality/coverage of auto J.

Current remaining C state at chat end:

- next C batch of 160 has been generated/downloaded
- batch 2 has NOT yet been fully semantically processed/persisted
- continue processing C batches until the current G backlog is substantially judged
- after each batch, rerun replenishment and inspect auto J

## Big Four and regular-J guardrails

Regular-J shadow guardrails now include:

- Big Four separate batch
- hardened Big Four recognition for variants such as `Deloitte AG`, `KPMG AG`, etc.
- manual-B already-applied exclusion
- reviewed-history exclusion including comment-only feedback

The user explicitly wants Big Four reviewed periodically as a separate broad batch rather than fed one-by-one into normal J.

## I / application tracker state

The intended and now implemented visible semantics are:

- B -> Applied directly
- J Apply -> Applied
- visible I = actual application processes only
- Skip / Maybe / New / comment-only remain in `opportunity_history.csv` backend for learning but are not shown as applications

Do not delete historical declined/reviewed roles; they are useful learning data.

## C as ChatGPT Work / agent — intended design

The user proposed making C a dedicated ChatGPT Work chat/agent. This is directionally approved.

Desired operating pattern:

1. Work reads `docs/WORKSTREAM_CONTEXT.md` plus current C/job-search context.
2. Work retrieves the next `c_queue` batch from the repo/artifact.
3. For every row, evaluate the full role content using the accumulated context.
4. Output `Strong / Moderate / Weak + concise reasoning` in the canonical schema.
5. Write/merge results into `data/semantic_fit.csv` on the migration branch (or later the canonical production branch after cutover).
6. Trigger/re-run replenishment so the next C batch appears and J is regenerated.
7. Repeat until backlog is processed; after that only newly discovered/changed G roles need judgment.

Do not replace this reasoning with a simplistic keyword score. Deterministic heuristics can pre-screen obvious junk, but true C classifications should remain contextual semantic judgments.

## Immediate next steps for a fresh chat

1. Read `docs/WORKSTREAM_CONTEXT.md` and this handoff.
2. Decide/implement the dedicated Work-agent setup for C, including model choice and usage strategy.
3. Continue with C batch 2 (currently pending 160 roles), persist it, and rerun replenishment.
4. Repeat enough C batches to build a meaningful Strong pool.
5. Inspect generated J quality; do not manually search for replacement jobs to make it reach 20.
6. Once shadow quality is good, reconcile the migration branch with latest `main` and cut over incrementally.

Live dashboard usability remains the priority during migration.
