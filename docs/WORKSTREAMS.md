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

## Scheduled tasks (souhrn)
- `company-discovery` — Po+Čt 07:00 (A)
- `opportunity-enrichment` — denně 08:03 (B1 + B2)
- `calibration-refresh` — manual / on-demand (C)
Pozn.: všechny commitují přes jeden fine-grained GitHub PAT uložený v promptu tasku (lokálně)
i ve Streamlit secrets (pro ukládání z appky). NEREVOKOVAT bez náhrady na obou místech.

## Poznámky / další možné kroky
- B2 automatiku potvrdit na reálném ratingu (ohodnotit 1 z 6 čekajících pozic).
- Až přibude víc feedbacku (hlavně přímý thesis feedback), pustit `calibration-refresh` znovu.
