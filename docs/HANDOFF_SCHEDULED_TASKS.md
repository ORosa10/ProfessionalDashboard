# Scheduled tasks (Cowork) — handoff

Doplněk k `docs/WORKSTREAMS.md`. Shrnuje naplánované Cowork úlohy, které tento
repo obsluhují, aby se na projekt dalo navázat i z jiné session / jiného stroje.

Last updated: 2026-09-22

Úlohy jsou definované lokálně u uživatele v
`C:\Users\OndřejRosický\Claude\Scheduled\<název>\SKILL.md` a spravují se přes
`list_scheduled_tasks` / `update_scheduled_task`. Zapisují do tohoto repa přes
fine-grained PAT (Contents: read/write) — token je v Streamlit secrets
`[github] token` a v promptech těchto úloh; do repa se NIKDY nepíše.

| Úloha | Rozvrh | Zapnuto | Co dělá |
|---|---|---|---|
| `company-discovery` | Po+Čt 07:00 | ANO | 3–6 nových reálných firem/kategorie → `data/company_universe_wave*.csv` jako `Unrated`, řádek do WORKSTREAMS.md (A), push |
| `opportunity-enrichment` | denně 08:13 | ANO | Fáze 1 obohatí nové submitted opportunities; Fáze 2 promítne Interested/Maybe do Universe + `job_sources_<sektor>.csv` + hypotéz; řádek do WORKSTREAMS.md (B), push |
| `calibration-refresh` | ručně (Run now) | ANO (manual) | Z ratingů/komentářů/`targeting_feedback.csv` aktualizuje `calibration_rules.json` + `*_TARGETING.md`, přegeneruje shortlisty a `semantic_fit.csv`; řádek do WORKSTREAMS.md (C), push |

**Pravidla, která tyto úlohy dodržují:**
- Jediný zdroj pravdy = tento repo (CSV/MD). Žádná DB.
- `calibration-refresh` jen mění pořadí, nikdy tvrdé vyloučení; drží ~20 % exploration.
- Kategorie „Big Four" (Deloitte, PwC, EY, KPMG) je fixní — nediskovuje se.
- Token jen v git remote URL, git výstup redigovaný přes `sed`, po pushi remote
  reset na `https://github.com/ORosa10/ProfessionalDashboard.git`.

**Navázání jinde:** přečti `docs/WORKSTREAMS.md` (pilíře A–H), pak tento soubor.
Kompletní master přehled všech projektů uživatele (napříč repy) je uložen
lokálně u uživatele mimo tento public repo (důvěrné projekty tam nepatří).
