# Professional Dashboard — Workstreams handoff (A–G)

Kompletní, samostatný přehled rozdělané práce. Cíl: dát se na to navázat v jakékoli nové
session/kdekoli bez ztráty kontextu. Aktualizovat při každé změně.

Last updated: 2026-08-18

## Jak to navázat
- Repo: **ORosa10/ProfessionalDashboard** (public), Streamlit Community Cloud sleduje `main`, entry `app.py`.
- Persistence = tento repo (data v CSV) + Project "Job". Cowork session spolu NESDÍLEJÍ paměť → tento dokument + repo jsou to, co přetrvá.
- **GitHub token:** jeden fine-grained PAT je v (a) Streamlit secrets `[github] token` (ukládání z appky) a (b) promptech Cowork tasků (company-discovery, opportunity-enrichment, calibration-refresh — leží lokálně u uživatele v C:\Users\...\Claude\Scheduled). NEREVOKOVAT bez náhrady na obou místech.

## Architektura (3 výpočetní vrstvy)
1. **GitHub repo = jediný zdroj pravdy.** Žádná DB; všechno jsou CSV/MD v repu.
2. **Streamlit app = zobrazení + zadávání.** Čte/píše CSV přes GitHub API. ZÁMĚRNĚ bez AI (náklady).
3. **Motory nad tím:**
   - **GitHub Actions = deterministický sourcing** (scrapery, píší do staging větví / u D,E přímo main). Bez LLM (výjimka: Gemini free-tier fallback adaptér).
   - **Cowork scheduled/on-demand tasky = inteligence (Claude přes předplatné).** Discovery, enrichment, kalibrace. Běží mimo appku, sahají na stejné CSV.
- **Jediný zdroj pravdy pro cílení i skórování = `data/calibration_rules.json`** (učí ho C). Čte ho `calibrate_jobs` (skóre) i D/E targeting. Prose thesis docs (`*_TARGETING.md`) jsou lidská podoba téhož.

## Legenda pilířů (rozsah zamčen na A–G)
- **A** — Discovery firem
- **B** — Ručně vkládané opportunity (Add Opportunity)
- **C** — Kalibrace + shortlisty (jádro: pravidla, hypotézy, semantic fit)
- **D** — Remote (trvalé remote role z boardů)
- **E** — Projekty / Interim (projektová/kontraktní práce; tendery = TODO)
- **F** — Lidé / Network (LinkedIn kontakty → access signál)
- **G** — Country / board sweep (národní job boardy; company-agnostic)
(F jako "expert cally" zamítnuto — seniorita; F redefinováno na network. Dál se nerozšiřuje.)

---

## A — Discovery firem
Scheduled task najde nové reálné firmy per kategorie a připojí je jako `rating="Unrated"` do `company_universe_wave*.csv` (append-only).
- Task: **company-discovery** (cron Po+Čt 07:00).
- Stav: ✅ BĚŽÍ ručně i automaticky. Přidáno 37+28 = 65 firem.

## B — Ručně vkládané opportunity (stránka Add Opportunity)
Vstup: 2 pole (LinkedIn + firemní stránka), tlačítko "Save for enrichment" → `data/user_submitted_opportunities.csv`. Vlastní stránka (ne v Jobs inboxu).
- **B1 obohacení** (profil firmy + pozice + mzdový market research): task **opportunity-enrichment** (denně 08:03), Fáze 1. ✅
- **B2 do kontextu**: Fáze 2 — Interested/Maybe → firma do Universe + `job_sources_<sektor>.csv` (task sám zjistí ATS adaptér), rating → hypotéza. ✅ postaveno, ověřeno ručně (Evotec → Workday).
- Stav: 12 pozic "Enriched - ready to rate", 1 (Evotec) Interested/onboarded.
- **Otevřené (na uživateli):** ohodnotit těch 12. **Otevřené (na mně):** automatická Fáze 2 zatím neproběhla na reálném ratingu.

## C — Kalibrace + shortlisty (jádro)
- **`data/calibration_rules.json`** = učené skórovací pravidlo (positive/caution termy + váhy). `calibrate_jobs` (sourcing/big4_pilot.py) ho čte. Jen mění pořadí, NIKDY tvrdé vyloučení; drží ~20% exploration.
- **Sektorové thesis docs (6):** CONSULTING (+Big Four), PE, CORPORATE, FINANCIAL_SERVICES, PUBLIC_MARKETS, SPECIALIST_FUNDS + GENERAL. Zobrazují se na Jobs stránce (rozbalovací).
- **`data/semantic_fit.csv`** = PRIMÁRNÍ fit (reasoning Strong/Moderate/Weak od Claude). App ho ukazuje jako headline; keyword skóre je jen hrubý předfiltr.
- **`data/targeting_feedback.csv`** = přímý thesis feedback z panelu na Jobs (nejvyšší priorita vstupu do kalibrace). Zatím prázdný.
- Task: **calibration-refresh** (NA VYŽÁDÁNÍ / Run now). Vstupy dle priority: targeting_feedback → rated submitted opps → job_feedback. Dělá: update pravidel + hypotéz → regenerace shortlistů → semantic fit (Fáze 2b).
- Stav: všech 6 sektorů ohodnoceno (Big Four 50, PE 20, Consulting 20, Corporate 20, Banking 20, Public Markets 12, Specialist 6), thesis napsané, 2 díry v pravidlech zalepené (+caution IT/data; +positive investments/portfolio).
- **Otevřené (na uživateli):** napsat thesis feedback do panelu; pak spustit calibration-refresh. **Na mně:** semantic fit napojit i na D/E + submitted; Public Markets popisy jsou generický boilerplate (zlepšit extrakci); deep-code quant jako mírné mínus (zatím jen v docs).

## D — Remote (trvalé remote role)
Stejný profil/fit/kalibrace jako Jobs; zdroj = remote boardy; BEZ company vrstvy. Osa = trvalý úvazek (kontrakt → E).
- Kód: `sourcing/remote_pilot.py` + Action `remote-sourcing.yml` (denně 05:30, commit do main). Zdroje: Remote OK (finance title), Remotive (finance-legal kategorie), WWR (remote-management-and-finance feed, title filtr). Targeting z `calibration_rules.json`. App: stránka **Opportunities → Remote** (`render_remote`).
- Stav: ✅ čisté, ale NÍZKÝ OBJEM (dnes 2 role: FP&A analytici). Free boardy finance skoro nenesou — slabina zdrojů, ne kódu.

## E — Projekty / Interim
Projektová/kontraktní/freelance finanční práce pro uživatele osobně. Osa = typ úvazku (ne lokalita) → nepřekrývá se s D. Fit lens: relevance × osobní dodatelnost × dosažitelnost (má IČO, ale bez referencí subjektu → reference-heavy tendery dolů, ne vyloučit).
- Kód: `sourcing/projects_pilot.py` (reuse remote_pilot fetcherů, `is_project_role`) + Action `projects-sourcing.yml` (denně 05:45). App: stránka **Opportunities → Projekty / Interim** (`render_projects`, sdílený `_render_board_stream`).
- Stav: ✅ postaveno, 0 rolí dnes (contract+finance na těch boardech vzácné).
- **Otevřené:** kanál 2 = TENDERY (TED/Věstník, CPV finanční, s příznakem náročnosti referencí) — NEpostaveno, dobrat zdroj.

## F — Lidé / Network (access vrstva)
LinkedIn kontakty → napárování na firmy → access signál na příležitosti (blueprint AccessStrength, samostatný signál, jen boost pořadí).
- Kód: `people_ui.py` → stránka **Opportunities → Lidé / Network**. Ingest = nahrání LinkedIn **Connections CSV exportu** (Settings → Data privacy → Get a copy of your data → Connections). Žádný scraping. Parsuje export, fuzzy-páruje Company → canonical_company_id, ukládá do `data/connections.csv`, přehled "u které firmy koho znáš".
- Stav: ✅ postaveno a otestováno na syntetickém exportu. Čeká na reálný upload (0 kontaktů).
- **Otevřené (na uživateli):** nahrát LinkedIn export. **Na mně:** access boost do pořadí příležitostí + předvyplnění contact_strength na Companies (až budou kontakty).

## G — Country / board sweep
Company-AGNOSTIC sweep full-time rolí v cílových zemích z národních boardů — doplněk k firmocentrickému A. Nový ZDROJ pro Jobs pilíř (ne nový typ příležitosti). Targeting a pořadí z C.
- Registr: `data/job_boards.csv` nyní obsahuje 22 kandidátů včetně přidané oficiální německé Bundesagentur. Stav u každého zdroje rozlišuje `active`, `candidate` a technicky blokované zdroje.
- **První dva adaptéry ✅:** `sourcing/board_sweep.py` čte švédský Platsbanken přes oficiální JobSearch API a německou Bundesagentur přes serverově čitelné výsledky + plné schema.org `JobPosting` detaily.
- Výstup: `data/jobs_board_staging.csv`; samostatná review stránka **Opportunities → Country / Board Sweep**. Feedback se ukládá do společného `job_feedback.csv` a vstupuje do C. `calibration_rules.json` určuje transparentní hrubé pořadí; semantic fit doplní calibration-refresh.
- Action: `board-sourcing.yml` denně 06:00, zapisuje snapshot a `data/board_source_runs.csv` přímo do main.
- První živý technický test: 27 ověřených rolí (15 Sweden, 12 Germany), bez chyb zdrojů.
- **eFinancialCareers nelze použít jako bezobslužný první adaptér:** veřejná stránka vrací AWS Human Verification. Reed a Duunitori také blokují unattended přístup. Zůstávají evidované, ale nesmí se vykazovat jako fungující sourcing.
- Další rozšiřování: nejprve ověřit kvalitu G feedbackem, potom přidat jeden zdroj pro ČR a další stabilní národní/API zdroje. LinkedIn zůstává vynechán (auth zeď).

---

## Scheduled tasky (Cowork)
- **company-discovery** — Po+Čt 07:00 (A).
- **opportunity-enrichment** — denně 08:03 (B1 obohacení + B2 onboarding).
- **calibration-refresh** — na vyžádání / Run now (C: pravidla + hypotézy + shortlisty + semantic fit).

## GitHub Actions (deterministický sourcing)
- Firmocentrické: `job-sourcing` (Big Four), `pe-sourcing`, `consulting-sourcing`, `sector-sourcing` (matrix), `promote-staging`.
- Board-based (přímo main): `remote-sourcing` (D, 05:30), `projects-sourcing` (E, 05:45).

## Otevřené body (master list, jen dotažení A–G, žádné nové pilíře)
1. **B:** uživatel ohodnotí 12 vložených pozic; ověřit automatickou Fázi 2 na reálném ratingu.
2. **C:** uživatel napíše thesis feedback → spustit calibration-refresh; napojit semantic fit na D/E + submitted; zlepšit extrakci popisů (Public Markets boilerplate); zvážit deep-code-quant jako pravidlo.
3. **D/E:** nízký objem z free boardů — případně přidat lepší finanční zdroj; E kanál 2 = tendery (TED/Věstník).
4. **F:** uživatel nahraje LinkedIn export → dodělat access boost do pořadí příležitostí.
5. **G:** ohodnotit první Germany/Sweden board cohort; podle kvality doplnit český adaptér a další technicky stabilní země. Napojit G semantic fit při příštím calibration-refresh.

## Log klíčových rozhodnutí
- Rozsah zamčen na **6→7 pilířů A–G**; F = network (ne expert cally).
- **Fit je primárně SÉMANTICKÝ** (reasoning), keyword skóre jen hrubý předfiltr.
- **`calibration_rules.json` = jediný zdroj pravdy** pro skórování (C) i targeting (D/E, budoucí G).
- Sourcing = Actions/deterministický (bez placeného LLM; Gemini free fallback); inteligence = Cowork tasky (předplatné).
- D vs E dělení podle **typu úvazku** (trvalé → D, projektové → E), ne lokality.
- **LinkedIn se nescrapuje** (F = CSV export; G bez LinkedInu).
- Žádné tvrdé vylučování rolí — kalibrace jen mění pořadí, drží exploration.
