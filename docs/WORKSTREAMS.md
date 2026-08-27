# Professional Dashboard — Workstreams handoff (A–H)

Kompletní, samostatný přehled rozdělané práce. Cíl: dát se na to navázat v jakékoli nové
session/kdekoli bez ztráty kontextu. Aktualizovat při každé změně.

Last updated: 2026-08-19

## Jak to navázat
- Repo: **ORosa10/ProfessionalDashboard** (public), Streamlit Community Cloud sleduje `main`, entry `app.py`.
- Persistence = tento repo (data v CSV) + Project "Job". Cowork session spolu NESDÍLEJÍ paměť → tento dokument + repo jsou to, co přetrvá.
- **GitHub token:** jeden fine-grained PAT je v (a) Streamlit secrets `[github] token` (ukládání z appky) a (b) promptech Cowork tasků (company-discovery, opportunity-enrichment, calibration-refresh — leží lokálně u uživatele v C:\Users\...\Claude\Scheduled). NEREVOKOVAT bez náhrady na obou místech.

## Architektura (3 výpočetní vrstvy)
1. **GitHub repo = jediný zdroj pravdy.** Žádná DB; všechno jsou CSV/MD v repu.
2. **Streamlit app = zobrazení + zadávání.** Čte/píše CSV přes GitHub API. ZÁMĚRNĚ bez AI (náklady).
3. **Motory nad tím:**
   - **GitHub Actions = deterministický sourcing** (scrapery, píší do staging větví / u D,E,G přímo main). Bez LLM (výjimka: Gemini free-tier fallback adaptér).
   - **Cowork scheduled/on-demand tasky = inteligence (Claude přes předplatné).** Discovery, enrichment, kalibrace. Běží mimo appku, sahají na stejné CSV.
- **Jediný zdroj pravdy pro cílení i skórování rolí = `data/calibration_rules.json`** (učí ho C). Čte ho `calibrate_jobs` (skóre) i D/E/G targeting. Prose thesis docs (`*_TARGETING.md`) jsou lidská podoba téhož.

## Legenda pilířů (rozsah A–H)
- **A** — Discovery + relevance firem
- **B** — Ručně vkládané opportunity (Add Opportunity)
- **C** — Kalibrace + shortlisty (jádro: pravidla, hypotézy, semantic fit rolí)
- **D** — Remote (trvalé remote role z boardů)
- **E** — Projekty / Interim (projektová/kontraktní práce; tendery = TODO)
- **F** — Lidé / Network (LinkedIn kontakty → access signál)
- **G** — Country / board sweep (discovery engine; vstup do A + C, ne samostatný review pilíř)
- **H** — Application outcomes / Market feedback (co se stalo po aplikaci → attainability)
(F jako "expert cally" zamítnuto — seniorita; F redefinováno na network.)

---

## A — Discovery + relevance firem
A udržuje universe firem a jejich relevanci vůči uživatelské company thesis.
- Scheduled task **company-discovery** (cron Po+Čt 07:00) hledá nové reálné firmy per kategorie a připojuje je do `company_universe_wave*.csv`.
- Nová firma nemusí být ručně hodnocena uživatelem, aby šla dál. Systém má umět vytvořit **automatický company relevance assessment** podle semantické podobnosti s firmami, které už uživatel hodnotil, a podle příslušné company thesis.
- Výstup nemá být binární hard filter. Firma může mít např. vyšší / střední / nižší company relevance; neznámá nebo slabší firma nesmí automaticky skrýt výbornou roli.
- Pokud už firma v A existuje, G/B/C reuse její existující profil a signály místo vytváření duplicity.
- Stav: ✅ company discovery běží ručně i automaticky. **Otevřené (na systému):** formalizovat a uložit automatické semantické company relevance skóre/reasoning, které lze použít i pro firmy objevené přes G.
- [2026-08-24] A: added 42 companies across Consulting, Corporate, Banking & Financial Services, Holding & Conglomerate, Private Equity & Private Markets, Investment Banking, Public Markets & Asset Management, Specialist & Boutique Funds
- [2026-08-27] A: added 35 companies across Consulting, Corporate, Banking & Financial Services, Holding & Conglomerate, Private Equity & Private Markets, Investment Banking, Public Markets & Asset Management, Specialist & Boutique Funds

## B — Ručně vkládané opportunity (stránka Add Opportunity)
Vstup: LinkedIn/job link + firemní stránka → `data/user_submitted_opportunities.csv`. Vlastní stránka (ne v Jobs inboxu).
- **B1 obohacení** (profil firmy + pozice + mzdový market research): task **opportunity-enrichment** (denně 08:03), Fáze 1. ✅
- **B2 do kontextu**: Fáze 2 — Interested/Maybe → firma do Universe + `job_sources_<sektor>.csv` (task sám zjistí ATS adaptér), rating → hypotéza. ✅ postaveno, ověřeno ručně (Evotec → Workday).
- **Aktuální uživatelský workflow:** pro pozitivní role stačí rating `Interested`; důvod lze ve většině případů inferovat z role/profile textu. Uživatel už začal doplňovat ratingy i outcome typu `Lost` pro role, kde reálně neprošel.
- **Otevřené (na systému):** automatická Fáze 2 musí spolehlivě zpracovat nové reálné ratingy; nové outcome signály `Lost` se nemají míchat do preference fitu, ale přejdou do H.
- [2026-08-24] B: enriched 5 (StepStone Group, Albedis/Basel, ING Frankfurt, ETL International, W&W Informatik), onboarded 0 companies to sourcing (no newly rated submissions).
- [2026-08-26] B: enriched 1 (BCG Consultant - Market & Commodity Trading and Risk / Energy Trading), onboarded 1 company to sourcing (Boston Consulting Group, Interested; already in universe + job_sources_consulting).

## C — Kalibrace + shortlisty (jádro)
- **`data/calibration_rules.json`** = učené skórovací pravidlo (positive/caution termy + váhy). `calibrate_jobs` ho čte. Jen mění pořadí, NIKDY tvrdé vyloučení; drží exploration.
- **Sektorové thesis docs** = lidská formulace targeting logiky.
- **`data/semantic_fit.csv`** = PRIMÁRNÍ preference/content fit role (reasoning Strong/Moderate/Weak od Claude). App ho ukazuje jako headline; keyword skóre je jen hrubý předfiltr.
- **`data/targeting_feedback.csv`** = přímý thesis feedback z panelu na Jobs.
- Task: **calibration-refresh** (NA VYŽÁDÁNÍ / Run now). Vstupy dle priority: targeting_feedback → rated submitted opps → job_feedback. Dělá: update pravidel + hypotéz → regenerace shortlistů → semantic fit.
- Stav: všech 6 sektorů historicky ohodnoceno, thesis napsané, pravidla už jednou kalibrována.
- **G integrace:** role nalezené přes G nemají dostávat zvláštní ruční G-rating. Po company assessmentu v A se samotný job vyhodnotí stejným C semantic-fit frameworkem jako ostatní Jobs. Relevantní G role se pak zobrazí v normálním Jobs review s informací o source boardu.
- **Otevřené (na uživateli):** thesis feedback jen pokud se objeví skutečný pattern; není nutné ho vyrábět uměle. **Na systému:** semantic fit napojit i na D/E/G + submitted; zlepšit Public Markets popisy; deep-code quant případně převést z docs do mírného caution pravidla.

## D — Remote (trvalé remote role)
Stejný profil/fit/kalibrace jako Jobs; zdroj = remote boardy; BEZ company vrstvy. Osa = trvalý úvazek (kontrakt → E).
- Kód: `sourcing/remote_pilot.py` + Action `remote-sourcing.yml` (denně 05:30, commit do main).
- Stav: ✅ funguje, ale nízký objem relevantních finance rolí na free remote boardech.

## E — Projekty / Interim
Projektová/kontraktní/freelance finanční práce pro uživatele osobně. Fit lens: relevance × osobní dodatelnost × dosažitelnost.
- Kód: `sourcing/projects_pilot.py` + Action `projects-sourcing.yml` (denně 05:45).
- Stav: ✅ kanál z boardů postaven.
- **Otevřené:** kanál 2 = TENDERY (TED/Věstník, CPV finanční, s příznakem náročnosti referencí) — NEpostaveno.

## F — Lidé / Network (access vrstva)
LinkedIn kontakty → napárování na firmy → access signál na příležitosti. Samostatný signál, jen boost pořadí, nepřepisuje fit.
- Kód: `people_ui.py` → stránka **Opportunities → Lidé / Network**. Ingest = LinkedIn **Connections CSV export**.
- Stav: ✅ postaveno a otestováno na syntetickém exportu. Čeká na reálný upload.
- **Otevřené (na uživateli):** nahrát LinkedIn export. **Na systému:** access boost do pořadí příležitostí + předvyplnění `contact_strength` na Companies.

## G — Country / board sweep
G je **discovery engine**, ne samostatný uživatelský review workflow. Prohledává národní job boardy mimo známý company universe, aby našel nové firmy a role, které firmocentrické A nemusí zachytit.
- Registr `data/job_boards.csv`; první aktivní adaptéry = švédský Platsbanken + německá Bundesagentur.
- Action `board-sourcing.yml` denně 06:00; technický staging zůstává `data/jobs_board_staging.csv`.
- První živý test: 27 ověřených rolí (15 Sweden, 12 Germany), bez chyb zdrojů.
- eFinancialCareers/Reed/Duunitori jsou unattended blokované a nesmí se tvářit jako funkční sourcing.

### Cílový pipeline G → A → C
1. **G najde job + firmu** na country boardu.
2. **A vyhodnotí firmu:** pokud už existuje v universe, reuse existující profil/signály; pokud je nová, automaticky ji obohatí a dá jí **semantické company relevance skóre/reasoning podle podobnosti s již hodnocenými firmami a podle company thesis**.
3. Company relevance je **soft signal, ne hard filter**. Nízké skóre firmy může roli posunout níž, ale nesmí samo o sobě vyřadit job s výborným content fit.
4. **C vyhodnotí samotnou roli** stejným Semantic fit frameworkem jako ostatní Jobs.
5. Relevantní výsledky se propíšou do **normálního Jobs inboxu/review**, pouze s označením zdroje (`Platsbanken`, `Bundesagentur`, budoucí CZ board apod.). Uživatel nemá hodnotit samostatnou pseudofirmu ani celý G cohort jen proto, že přišel z boardu.

- **Otevřené (na systému):** implementovat A company-semantic assessment pro nové G firmy; napojit G role na C semantic fit; sloučit relevantní G výsledky do standardního Jobs review; potom podle kvality přidat český adaptér a další stabilní zdroje.
- **Otevřené (na uživateli):** žádný samostatný G cohort review. Uživatel hodnotí až role, které projdou běžným A+C rankingem a objeví se v Jobs.

## H — Application outcomes / Market feedback
Samostatná validační vrstva nad reálnými aplikacemi. C odpovídá **„co se uživateli líbí / co je obsahově fit“**; H odpovídá **„kam ho trh reálně pustí dál a kde ne“**.

### Co sledovat
- `Applied`
- `Rejected pre-screen`
- `Lost after 1st round`
- `Lost after case`
- `Final round`
- `Offer`
- `Withdrawn`
- případně stručný známý důvod / poznámku; pokud důvod nevíme, nehádat ho jako fakt.

### Co se z H má učit
Outcome se má analyzovat proti dimenzím, které už známe z job profilu: seniorita, požadované roky zkušeností, role family, sektor, jazyk, lokalita/relocation, požadované přímé zkušenosti a compensation band. Cílem je odhalovat opakující se patterny, např. zda uživatel reachuje příliš vysoko senioritou, zda je bottleneck jazyk, direct buy-side experience apod.

### Klíčové pravidlo
Jednotlivý `Lost` **není** důkaz, že typ role je mimo reach. H nesmí po 1–2 neúspěších agresivně snižovat targeting. Teprve opakující se pattern napříč dostatečným počtem aplikací má měnit úsudek.

### Výstup: Attainability score
Vedle **Semantic fit** přidat samostatné **Attainability** hodnocení:
- Semantic fit = jak moc je role obsahově / preferenčně pro uživatele.
- Attainability = jak realistické je ji získat vzhledem k senioritě, zkušenosti, jazyku, lokalitě, sektoru, compensation a empirickým outcomes.

Attainability nesmí nahrazovat Semantic fit ani role tvrdě vyřazovat; má být druhý, transparentní signál. U rolí s vysokým semantic fit, ale nízkou attainability má dashboard ukázat, že jde o **reach** — ne ji skrýt.

### Aktuální stav
- Uživatel už začal doplňovat `Lost` přímo u ručně vložených opportunities (např. jako kombinovaný uživatelský signál `Interested Lost`). To je první reálný vstup pro H.
- **Otevřené (na systému):** navrhnout čisté datové schéma pro outcomes (oddělit preference rating od application stage/outcome), UI pro jednoduchou aktualizaci stage a první verzi Attainability score / reasoning.
- **Otevřené (na uživateli):** průběžně jen aktualizovat outcome u skutečných aplikací; případný známý důvod rejectionu doplnit stručně, pokud ho má.

---

## Scheduled tasky (Cowork)
- **company-discovery** — Po+Čt 07:00 (A).
- **opportunity-enrichment** — denně 08:03 (B1 obohacení + B2 onboarding).
- **calibration-refresh** — na vyžádání / Run now (C: pravidla + hypotézy + shortlisty + semantic fit).

## GitHub Actions (deterministický sourcing)
- Firmocentrické: `job-sourcing`, `pe-sourcing`, `consulting-sourcing`, `sector-sourcing`, `promote-staging`.
- Board-based: `remote-sourcing` (D), `projects-sourcing` (E), `board-sourcing` (G discovery → A+C).

## Otevřené body — master list
1. **A/G:** postavit automatické semantické company relevance hodnocení pro firmy nalezené přes G podle podobnosti s již hodnocenými firmami + company thesis; bez hard filtru.
2. **B:** ratingy už jsou průběžně doplňované; ověřit automatickou Fázi 2 na nových reálných `Interested` ratingách a oddělit application outcome od preference feedbacku.
3. **C/G:** napojit G role na standardní C semantic fit a relevantní výsledky sloučit do normálního Jobs inboxu; případný skutečný thesis feedback → calibration-refresh; zlepšit Public Markets extrakci; zvážit deep-code-quant caution.
4. **D/E:** nízký objem free boardů; E kanál 2 = tendery (TED/Věstník).
5. **F:** uživatel nahraje LinkedIn Connections export → poté access boost.
6. **G:** po integraci A+C přidat CZ a další stabilní adaptéry; samostatný Germany/Sweden cohort review se ruší.
7. **H:** postavit outcome datový model + UI; převést existující `Lost` signály do H; následně první transparentní **Attainability score vedle Semantic fit** a postupně jej kalibrovat podle skutečných application outcomes.

## Co je teď konkrétně na uživateli
1. **F:** nahrát LinkedIn Connections CSV export.
2. **H:** u skutečných aplikací průběžně evidovat outcome (`Lost`, další kolo, offer atd.); pokud je znám konkrétní důvod neúspěchu, stručně ho přidat.
3. **C:** thesis feedback jen tehdy, když se při používání objeví jasný pattern; pak spustit calibration-refresh.

**G už není samostatný úkol na uživateli.** Country-board výsledky má nejprve zpracovat A+C a uživatel bude hodnotit pouze relevantní role v běžném Jobs workflow.

## Log klíčových rozhodnutí
- Rozsah je nyní **A–H**; H není další sourcing kanál, ale outcome/market-validation vrstva.
- **G je discovery engine, ne samostatný review stream:** `G → A company relevance → C role semantic fit → Jobs inbox`.
- Nové G firmy se mají hodnotit **semanticky podle podobnosti s již hodnocenými firmami a podle company thesis**, nikoli ručně jednu po druhé.
- **Company relevance je soft signal, nikdy hard filter.** Výborný job u méně známé firmy musí zůstat viditelný.
- **Fit role je primárně SÉMANTICKÝ** (preference/content fit), keyword skóre jen hrubý předfiltr.
- **Attainability je samostatný druhý signál** vedle Semantic fit; nesmí role skrývat ani přepisovat preference fit.
- `Lost` a jiné outcomes se nesmí míchat do `Interested/Maybe/Pass`; preference a market outcome jsou dvě rozdílné osy.
- Jednotlivý rejection není dostatečný pro snížení attainability; rozhodují opakující se empirické patterny.
- `calibration_rules.json` = zdroj pravdy pro role targeting/skórování C/D/E/G; H je oddělená empirická validační vrstva.
- Sourcing = Actions/deterministický; inteligence = Cowork tasky.
- D vs E dělení podle typu úvazku, ne lokality.
- LinkedIn se nescrapuje (F = CSV export; G bez LinkedInu).
- Žádné tvrdé vylučování rolí — kalibrace i attainability mění pořadí/interpretaci, ne dostupnost role.
- [2026-08-27] B: enriched 1 (Nobia Group - Group Treasurer, Aarhus/Tilst DK; Corporate), onboarded 0 companies to sourcing (no newly rated submissions; 1 LinkedIn-only row unidentifiable, left for retry).
