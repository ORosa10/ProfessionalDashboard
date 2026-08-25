# C Work — Semantic Fit Operating Contract

## Mission

Continuously drain the unresolved G opportunity backlog by assigning a high-quality semantic-fit judgment in C.

```text
G unresolved opportunities
        ↓
C Work semantic judgment
        ↓
Strong / Moderate / Weak
        ↓
Strong only → downstream Actionability / Quality → J
```

C Work is the semantic evaluator. It is not a sourcing engine, actionability filter, ranking engine or application tracker.

## Authoritative thesis

Before every run, read `docs/C_SEMANTIC_THESIS.md` and treat it as the single authoritative C decision policy.

Do not derive C policy from old calibration scores, keyword weights, geography rules, company ratings or actionability logic.

## One-time v2 recalibration

The current C thesis is materially stricter than the historical judgments that seeded J. Therefore the first C Work rollout must review `c_work_recalibration_queue.csv` once before steady-state processing.

That file contains currently active G opportunities that already have a C judgment. Re-judge them from scratch using the current thesis. The previous fit/reasoning fields are audit context only and must not anchor the new verdict.

Save the recalibration results as a new file under `data/semantic_fit_reviews/`. The canonical compiler keeps the newest judgment per `opportunity_id`.

After this one-time sweep, normal runs should process only `c_work_queue.csv` and must not repeatedly re-review completed IDs unless a later explicit thesis recalibration is declared.

## Steady-state input

Primary input is `c_work_queue.csv` from the architecture replenishment workflow.

Each unresolved role provides:
- `opportunity_id`
- `title`
- `company`
- `job_url`
- `description_for_fit`
- `description_chars`
- `needs_description_enrichment`

Use the full role description whenever available.

If `needs_description_enrichment=true`, or the supplied text is clearly generic company boilerplate rather than the vacancy responsibilities, use `job_url` only to retrieve the actual role content before judging C. Do not research salary, language feasibility, company quality or other downstream signals.

If the real description still cannot be obtained, return `Moderate` with reasoning beginning `INSUFFICIENT_DESCRIPTION:` unless the title/content makes the role unambiguously Weak. Do not invent a Strong rating from a title alone.

## Required output

Return exactly one row per reviewed opportunity with these columns:

```text
opportunity_id,fit,reasoning,generated_at
```

Allowed `fit` values only:
- `Strong`
- `Moderate`
- `Weak`

`reasoning` should be one concise sentence explaining the actual role-content judgment. Do not discuss salary, language, geography, company attractiveness, link health or attainability.

## Review method

For every role:

1. Read the actual responsibilities, not just the title.
2. Identify what the person would spend most of the week doing.
3. Compare those core duties with `docs/C_SEMANTIC_THESIS.md`.
4. Decide Strong / Moderate / Weak independently of other roles in the queue.
5. Write one short semantic reason.
6. Continue through the queue; if Work execution limits stop the run, the next run continues from remaining unresolved IDs rather than re-reviewing completed IDs.

## Speed rules

- Do not write essays.
- Do not produce scores out of 100.
- Do not compare candidates against one another.
- Do not spend time researching downstream actionability signals.
- Obvious Weak roles may be decided quickly from clear responsibilities.
- Ambiguous finance-adjacent roles deserve the deeper semantic read.
- Only open the vacancy URL when the supplied description is insufficient or clearly boilerplate.
- Queue order is review priority only and must never influence the fit label.

## Quality guardrails

- A relevant keyword is not enough for Strong.
- Strong requires target work to be central to day-to-day responsibilities.
- M&A mentioned incidentally inside FP&A/business partnering stays Moderate unless transaction work is genuinely core.
- Markets-adjacent credit/control/reporting work stays Moderate/Weak unless practical markets/hedging/investment content is central.
- Pure quant/code-heavy modelling is not promoted simply because it is mathematically sophisticated.
- Company rating and brand are invisible to the semantic verdict.
- Language and years-of-experience requirements are downstream unless seniority materially changes the actual work into management rather than target execution.

## Persistence

Reviewed rows are appended as a new CSV under:

`data/semantic_fit_reviews/`

The replenishment workflow compiles `data/semantic_fit.csv` plus all review files and keeps the latest judgment per `opportunity_id`.

Do not overwrite historic review files. Use a new timestamped Work review file for each save.

## Feedback loop

J/I feedback is evidence for future thesis changes, not a direct override of individual C judgments.

When repeated role-content feedback shows a stable pattern, propose a specific versioned edit to `docs/C_SEMANTIC_THESIS.md`. Do not silently mutate the thesis during normal role review.
