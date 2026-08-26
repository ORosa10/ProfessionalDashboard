# C → G Sourcing Learning Contract

## Purpose
C owns semantic role fit. G owns recall and sourcing. C may teach G which role
families deserve more search effort, but C feedback must never silently become
a hard exclusion rule in G.

## Source of truth
Structured guidance lives in `data/c_to_g_sourcing_guidance.csv` with columns:

- `guidance_id` — stable identifier.
- `status` — `Proposed`, `Active`, or `Retired`.
- `direction` — `prioritize` or `deprioritize`.
- `query_term` — concrete extra G search query when direction is `prioritize`.
- `role_family` — human-readable semantic family.
- `rationale` — concise evidence-based explanation.
- `evidence_count` — number of C examples supporting the pattern.
- `updated_at` — ISO timestamp.

## Production behavior
Only rows with `status=Active`, `direction=prioritize`, and a non-empty
`query_term` are consumed automatically. Their query terms are appended to G's
board search vocabulary and deduplicated. Existing G queries remain intact.

`deprioritize` guidance is deliberately **soft evidence only**. It is recorded
for future source-budget tuning but never removes vacancies or prevents them
reaching C. This protects recall and keeps semantic judgement inside C.

## C Work rules
- During QC/recalibration, recurring false positives or missing target families
  may be written as `Proposed` guidance.
- Do not activate a guidance row merely because of one ambiguous title.
- `Active` should represent an explicit, stable semantic conclusion consistent
  with `docs/C_SEMANTIC_THESIS.md`.
- Salary, language, geography, link health, company attractiveness and
  attainability never belong in this file.
- Free-text I comments are evidence, not automatic query instructions.
- Never mutate the C thesis silently in order to create G guidance.

## Examples
A repeated finding that direct `deal finance` roles are under-sourced can become
an Active `prioritize` row with `query_term=deal finance`.

A repeated finding that AI/software engineering inside CIB is semantically Weak
may be recorded as `deprioritize`, but G must not hard-filter all AI/data titles
because some finance roles legitimately use those tools.
