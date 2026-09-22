# Handoff pro GPT — ProfessionalDashboard (nábor)

> **▶ START ZDE (GPT):** Tři „inteligentní" úlohy, které dřív dělal Claude v
> Coworku (discovery firem, obohacení pozic, kalibrace), jsou teď přepsané jako
> **GitHub Actions volající OpenAI API**. Běží samy v repu, bez Claude.
> **Jediný předpoklad:** přidat repo secret **`OPENAI_API_KEY`**.

Last updated: 2026-09-22

## Nastavení (jednorázově)
GitHub → Settings → Secrets and variables → Actions:
- **Secret `OPENAI_API_KEY`** = tvůj OpenAI API klíč (Claude ho nikdy nevidí).
- (volitelně) **Variable `OPENAI_MODEL`** = model (default `gpt-4o`).

Bez klíče se úloha zastaví s jasnou hláškou (žádná tichá náhrada).

## Co kde je
```
automation_gpt/openai_client.py         sdílený klient OpenAI Responses API (+web search)
automation_gpt/company_discovery.py     A: nové Unrated firmy -> company_universe_wave*.csv
automation_gpt/opportunity_enrichment.py B: obohacení + onboarding do sourcingu
automation_gpt/calibration_refresh.py   C: pravidla + shortlisty + semantic fit
.github/workflows/gpt-company-discovery.yml     cron Po+Čt 05:00 UTC
.github/workflows/gpt-opportunity-enrichment.yml cron denně 06:00 UTC
.github/workflows/gpt-calibration-refresh.yml    RUČNĚ (Run workflow)
```
Zdroj pravdy zůstává tento repo (CSV/MD). Deterministický sourcing (existující
Actions) i Streamlit appka běží beze změny.

## Tři úlohy (1:1 dle původních Cowork promptů)
- **A — `gpt-company-discovery`** (Po+Čt): přes web search najde 3–6 nových
  reálných firem per kategorie, dedup proti všem existujícím `canonical_company_id`,
  a **připíše** je jako `Unrated` do správného `data/company_universe_wave*.csv`
  + řádek do `docs/WORKSTREAMS.md` (sekce A). Append-only, nikdy nemění
  `company_ratings.csv` ani `jobs*`. „Big Four" se nediskovuje.
- **B — `gpt-opportunity-enrichment`** (denně): Fáze 1 obohatí nové vložené
  pozice v `data/user_submitted_opportunities.csv` (profil firmy/role + mzdový
  research + `salary_range`), Fáze 2 promítne Interested/Maybe do Universe +
  `job_sources_<sektor>.csv` (model zjistí ATS adaptér) a dopíše hypotézu do
  `*_TARGETING.md`; Pass = „Rated - noted". Úpravy CSV jsou po `submission_id`.
- **C — `gpt-calibration-refresh`** (ručně): konzervativně upraví
  `data/calibration_rules.json` (jen merge/pořadí, nikdy tvrdé vyloučení,
  nemaže seed témata), přegeneruje shortlisty přes **existující**
  `sourcing.build_calibration_batch` a upsertuje `data/semantic_fit.csv`
  (Strong/Moderate/Weak + reasoning). Drží ~20 % exploration.

## Doporučení pro první běh (protože úlohy B/C mění živá data)
Původní tři úlohy taky běžely samy, ale zdravý postup: po nastavení klíče
spusť každou nejdřív **ručně** (Actions → vyber workflow → Run workflow),
zkontroluj commit/diff, a teprve pak nech běžet dle cronu. Discovery (A) je
append-only, takže bezpečná; B a C mění existující CSV — proto ta kontrola.
Kvalita výstupu závisí na modelu (na rozdíl od Claude v Coworku) — po pár bězích
si to případně dolaď v promptech uvnitř skriptů.

## Pozn. k dřívějšímu tokenu
Původní Cowork prompty používaly fine-grained PAT (v Streamlit secrets +
lokálně u tebe). Tyto Actions ho NEPOTŘEBUJÍ — commitují přes vestavěný
`GITHUB_TOKEN`. Jediné nové tajemství je `OPENAI_API_KEY`.
