# C Work — Semantic Fit Operating Contract

## Mission

Continuously drain the unresolved G opportunity backlog by assigning a high-quality semantic-fit judgment in C.

Pipeline responsibility:

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

## Input

Primary input is the generated Work queue `c_work_queue.csv` from the architecture replenishment workflow.

Each unresolved role should provide at minimum:
- `opportunity_id`
- `title`
- `company`
- `job_url`
- `description_for_fit`

Use the full role description whenever available. If the description is missing or clearly generic company boilerplate, do not invent a fit judgment from the title alone. Return `Moderate` with reasoning beginning `INSUFFICIENT_DESCRIPTION:` unless the title itself makes the role unambiguously Weak.

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
6. Continue until the unresolved queue is exhausted or Work execution limits are reached; on the next run continue from remaining unresolved IDs rather than re-reviewing completed IDs.

## Speed rules

- Do not write essays.
- Do not produce scores out of 100.
- Do not compare candidates against one another.
- Do not spend time researching salary, language or company quality.
- Do not re-review an `opportunity_id` already present in canonical C state unless explicitly requested for recalibration.
- Obvious Weak roles may be decided quickly from clear responsibilities; ambiguous finance-adjacent roles deserve the deeper semantic read.
- The queue order is review priority only and must never influence the fit label.

## Quality guardrails

- A relevant keyword is not enough for Strong.
- A Strong label requires target work to be central to day-to-day responsibilities.
- M&A mentioned incidentally inside FP&A/business partnering stays Moderate unless transaction work is genuinely core.
- Markets-adjacent credit/control/reporting work stays Moderate/Weak unless practical markets/hedging/investment content is central.
- Pure quant/code-heavy modelling is not promoted simply because it is mathematically sophisticated.
- Company rating and brand are invisible to the semantic verdict.
- Language and seniority requirements are downstream unless seniority materially changes the actual work into management rather than target execution.

## Persistence

Reviewed rows are appended as a new CSV under:

`data/semantic_fit_reviews/`

The replenishment workflow compiles `data/semantic_fit.csv` plus all review files and keeps the latest judgment per `opportunity_id`.

Do not overwrite historic review files. Use a new timestamped Work review file for each save.

## Feedback loop

J/I feedback is evidence for future thesis changes, not a direct override of individual C judgments.

When repeated role-content feedback shows a stable pattern, propose a specific edit to `docs/C_SEMANTIC_THESIS.md`. Do not silently mutate the thesis during normal role review.
