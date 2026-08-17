# Workstreams A / B / C — status tracker

Kostra rozdělané práce na ProfessionalDashboard. Drž tato písmenka, ať je vždy jasné,
k čemu se vracíme. Aktualizovat při každé změně. (Cowork session nesdílejí paměť —
tohle + build-log jsou to, co přetrvá.)

Last updated: 2026-08-17

## A — Company discovery (hledání nových firem)
Co: scheduled task najde nové reálné firmy per kategorie a připojí je jako `rating="Unrated"`
do `company_universe_wave*.csv` (append-only, ATS/adaptér neřeší).
- Task: `company-discovery` — cron Po+Čt 07:00.
- Stav: ✅ BĚŽÍ, ověřeno ručně i automaticky. Přidáno 37 (2f7d9ee) + 28 (1d95170) = 65 firem.
- Otevřené: nic zásadního; sledovat, že plánované běhy dál procházejí.

## B — Ručně vkládané opportunity (stránka Add Opportunity)
Vstup: 2 pole (LinkedIn link + firemní stránka), tlačítko "Save for enrichment".
Ukládá do `data/user_submitted_opportunities.csv`. Zůstává na vlastní stránce (ne v Jobs inboxu).

### B1 — obohacení (profil firmy + profil pozice + mzdový market research)
- Task: `opportunity-enrichment` (denně 08:03), Fáze 1.
- Stav: ✅ BĚŽÍ, ověřeno (Evotec ručně + 6 pozic ranním během). Kvalita OK.

### B2 — vstup do kontextu (firma -> Universe + sourcing; rating -> targeting hypotéza)
- Task: `opportunity-enrichment`, Fáze 2. Interested/Maybe -> firma do Universe + `job_sources_<sektor>.csv`
  (task sám zjistí ATS adaptér); Pass -> negativní. Rating se připíše do hypotézy.
- Stav: ✅ POSTAVENO, ověřeno ručně (Evotec -> Universe + job_sources workday, commit f74c94d).
- Otevřené: automatická Fáze 2 zatím neproběhla naostro na reálném uživatelském ratingu.

## C — Kalibrace + shortlisty
- Skórovací pravidla vytažena z kódu do `data/calibration_rules.json` (calibrate_jobs je čte; ověřeno beze změny skóre).
- `calibrate_jobs` = jen HRUBÝ předfiltr, není headline.
- FIT je PRIMÁRNĚ SÉMANTICKÝ: reasoning od Claude per role (Strong/Moderate/Weak) v `data/semantic_fit.csv`,
  appka ho zobrazuje jako "Personal fit (semantic)" + "Fit" a řadí podle něj.
- Feedback k thesis: panel na stránce Jobs -> `data/targeting_feedback.csv`.
- Task: `calibration-refresh` — NA VYŽÁDÁNÍ (Run now / ping), plně automatický. Vstupy v pořadí priority:
  (1) targeting_feedback.csv, (2) rated user_submitted_opportunities.csv, (3) job_feedback.csv.
  Dělá: update rules + hypotéz -> regenerace shortlistů -> Fáze 2b generuje semantic fit.
- Stav: ✅ POSTAVENO a jednou odzkoušeno naostro: pravidla doladěna (treasury +12, nový markets/deriváty +12,
  compliance -12, real estate -9; 8f4e280), shortlisty přegenerovány, 57 semantic-fit reasoningů (6347ce2).

## D - Remote work (nový opportunity stream)
Stejný profil, fit i kalibrace jako Jobs (A/B/C), ale zdroj = veřejné remote boardy, NE firmy.
Company vrstva se přeskakuje. Scope: cokoliv (full-time i kontrakt), doladí se hodnocením.
- Sourcing: `sourcing/remote_pilot.py` + Action `.github/workflows/remote-sourcing.yml`
  (denně 05:30 UTC + workflow_dispatch). Tahá Remote OK / Remotive / We Work Remotely feedy,
  filtruje finanční/treasury/risk/investment termy, píše `data/jobs_remote_staging.csv`
  (schéma jako sektor staging), skóruje přes calibrate_jobs. Commituje PŘÍMO do main
  (čerstvý stream, žádná promotion vrstva).
- App: nová stránka **Opportunities -> Remote** (`render_remote` v jobs_ui.py) - review grid
  s Interested/Maybe/Pass + komentář a sémantický fit, bez company filtru. Feedback jde do
  sdíleného `job_feedback.csv`.
- Stav: POSTAVENO, zatím bez dat - naplní se prvním během Action (dispatch nebo ranní cron).
  OVĚŘIT po prvním běhu, že boardy vrací relevantní role a commit projde.
- Update: filtr utažen na finanční TITULY (popis dělal false-positives); D nově VYřazuje
  contract/interim (ty patří do E) -> D = jen trvalé remote role.
- Otevřené: sémantický fit pro remote/E role zatím negeneruje calibration-refresh (jen sektory) -
  přidat, až mají data.

## E - Projekty / Interim (nový opportunity stream)
Placená PROJEKTOVÁ / interim / kontraktní / freelance finanční práce pro Ondřeje osobně.
Osa = typ úvazku (na projekt/na dobu určitou), NE lokalita -> nepřekrývá se s D (D = trvalé remote).
Fit lens E = relevance k finanční doméně x osobní dodatelnost x DOSAŽITELNOST (má IČO, ale žádné
reference subjektu -> reference-heavy veřejné zakázky se sníží v pořadí, ne vyloučí).
- Sourcing: `sourcing/projects_pilot.py` (reuse fetcherů z remote_pilot; nechá jen project-type
  finanční role via `is_project_role`) + Action `.github/workflows/projects-sourcing.yml`
  (denně 05:45 + dispatch) -> `data/jobs_projects_staging.csv`, commit do main.
- App: stránka **Opportunities -> Projekty / Interim** (`render_projects`), sdílený review helper
  `_render_board_stream` (společný s Remote), bez company vrstvy, feedback do `job_feedback.csv`.
- Stav: POSTAVENO (kanál 1 = interim/kontrakt z boardů). Data po prvním běhu Action, OVĚŘIT kvalitu.
- Otevřené (kanál 2 = TENDERY): TED (EU open data) + Věstník (XML), CPV finanční kódy, s příznakem
  náročnosti referencí. Zatím NEpostaveno - dobrat zdroj (TED API vs Věstník) a přidat.
- Otevřené: E-specifický fit lens (dosažitelnost) zatím jen popsán; promítnout do semantic-fit generace.

## Scheduled tasks (souhrn)
- `company-discovery` — Po+Čt 07:00 (A)
- `opportunity-enrichment` — denně 08:03 (B1 + B2)
- `calibration-refresh` — manual / on-demand (C)
GitHub Actions (sourcing): sector-sourcing, ..., + `remote-sourcing` (D, denně 05:30), `projects-sourcing` (E, denně 05:45) — commit do main.
Pozn.: všechny commitují přes jeden fine-grained GitHub PAT uložený v promptu tasku (lokálně)
i ve Streamlit secrets (pro ukládání z appky). NEREVOKOVAT bez náhrady na obou místech.

## Další plánované streamy (zatím nespecifikováno)
- Možná **F = expert cally / advisory & NED** (placené hovory, GLG/Third Bridge apod.) - k dobrainstormování.

## Poznámky / další možné kroky
- B2 automatiku potvrdit na reálném ratingu (ohodnotit 1 z 6 čekajících pozic).
- Až přibude víc feedbacku (hlavně přímý thesis feedback), pustit `calibration-refresh` znovu.
