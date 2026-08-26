# Start C Semantic Fit in ChatGPT Work

Use this as the startup instruction for the dedicated C Work workspace:

> Work on repository `ORosa10/ProfessionalDashboard`, branch `architecture-safe-migration`.
>
> Your only responsibility is Workstream C: semantic role fit between G and J.
>
> First read `docs/C_SEMANTIC_THESIS.md` and `docs/C_WORK_CONTRACT.md`. Treat them as authoritative and do not substitute keyword scoring or older targeting rules.
>
> Before recalibration, also inspect the current production factual learning file `data/c_learning_evidence.csv` on `main`. It is generated from canonical I's append-only decision/event history. Use repeated explicit role feedback and user comments only as evidence for a proposed, explicit thesis/calibration change; never silently change the thesis, never let Apply/Skip history override the actual responsibilities of an individual role, and never infer polarity for `comment_only` rows.
>
> For the first run, process the latest `c_work_recalibration_queue.csv` from the `architecture-replenishment-shadow` workflow artifact. Re-judge every row from scratch as Strong / Moderate / Weak using the actual role content. Previous fit/reasoning is audit context only and must not anchor the decision. If `needs_description_enrichment=true`, retrieve the actual vacancy content from `job_url` before judging when possible. Persist the resulting rows in a new timestamped CSV under `data/semantic_fit_reviews/` with exactly `opportunity_id,fit,reasoning,generated_at`.
>
> After the one-time recalibration is saved, process `c_work_queue.csv` the same way. Continue through unresolved roles without re-reviewing completed IDs. Keep reasoning to one concise sentence per role.
>
> Never use salary, language, geography, company rating, country target, link health or attainability to change C. Those belong downstream. Strong means the target work is genuinely central to day-to-day responsibilities.
>
> When new C judgments are saved, the repository pipeline will compile the latest verdicts; only Strong roles then proceed through Actionability / Quality toward J.
>
> J/I feedback can be used to propose explicit future edits to `docs/C_SEMANTIC_THESIS.md`, but never silently rewrite the thesis while reviewing roles.