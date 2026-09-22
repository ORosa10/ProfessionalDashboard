#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
company-discovery pro svět bez Claude (GitHub Actions + OpenAI API).
1:1 port stejnojmenné Cowork úlohy: najde nové REÁLNÉ firmy per kategorie a
připojí je jako `Unrated` do správného data/company_universe_wave*.csv.
BEZPEČNÉ: jen PŘIPISUJE (append), nikdy nemění existující řádky ani
company_ratings.csv / jobs*.csv. Commit řeší workflow.
"""
import csv
import datetime as dt
import glob
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from openai_client import ask_json  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
WORKSTREAMS = os.path.join(ROOT, "docs", "WORKSTREAMS.md")

WAVE_COLS = [
    "canonical_company_id", "company", "parent_company_id", "aliases_entities",
    "company_category", "region", "locations", "archetype", "why_test",
    "career_url", "source_strategy", "rating", "notes",
]

# kategorie -> cílový wave soubor (dle SKILL company-discovery)
CATEGORY_FILE = {
    "Consulting": "company_universe_wave2_consulting.csv",
    "Corporate": "company_universe_wave2_corporate.csv",
    "Banking & Financial Services": "company_universe_wave2_financial_services.csv",
    "Holding & Conglomerate": "company_universe_wave2_holdings.csv",
    "Private Equity & Private Markets": "company_universe_wave2_investment.csv",
    "Investment Banking": "company_universe_wave3_investment.csv",
    "Public Markets & Asset Management": "company_universe_wave3_investment.csv",
    "Specialist & Boutique Funds": "company_universe_wave3_investment.csv",
}

PROFILE = (
    "Pozitivní signály: treasury, financial & market risk, deriváty, valuation, "
    "liquidity, FX, úrokové sazby, komodity, finanční modelování/analytika, "
    "investiční role, corporate finance, people management. Mírně pozitivní: "
    "Python/R/SQL, Bloomberg/Refinitiv, CFA/FRM. Negativní: compliance/regulatoric, "
    "čistý sales, čisté IFRS/reporting. Jazyk: požadavek na plynulost/C1/native v "
    "jiném jazyce než angličtině je red flag (němčina 'velmi dobrá' ok). Cílové "
    "geografie: Česko, Německo, Rakousko, Švýcarsko, UK, Nordics (DK, SE, NO, FI)."
)


def load_existing_ids():
    ids = set()
    files = [os.path.join(DATA, "company_ratings.csv"),
             os.path.join(DATA, "company_universe.csv")]
    files += sorted(glob.glob(os.path.join(DATA, "company_universe_wave*.csv")))
    for fp in files:
        if not os.path.exists(fp):
            continue
        with open(fp, encoding="utf-8-sig", newline="") as f:
            for row in csv.DictReader(f):
                cid = (row.get("canonical_company_id") or "").strip().lower()
                if cid:
                    ids.add(cid)
    return ids


def targeting_context():
    bits = []
    for name in ("GENERAL_COMPANY_TARGETING.md", "COMPANY_TARGETING.md"):
        fp = os.path.join(ROOT, name)
        if os.path.exists(fp):
            with open(fp, encoding="utf-8") as f:
                bits.append(f"### {name}\n" + f.read()[:2000])
    return "\n\n".join(bits)[:4000]


def discover_for_category(cat, existing_ids, context):
    prompt = f"""Jsi sourcing analytik. Najdi 3 až 6 NOVÝCH, REÁLNÝCH firem v kategorii
"{cat}", které sedí na tento profil kandidáta a cílové geografie:

{PROFILE}

Kontext (targeting dokumenty uživatele):
{context}

Podmínky:
- Firma musí reálně existovat a mít přítomnost v cílových geografiích, ideálně s
  treasury/risk/valuation/investment funkcemi.
- Ověř ji přes web search; kde to jde, najdi její oficiální first-party careers URL.
  Když ji nenajdeš, nech career_url prázdné (nehádej).
- NEVYMÝŠLEJ firmy. Nevracej firmy, jejichž id už existuje (viz seznam níže).

Vrať JSON pole objektů s klíči:
canonical_company_id (lowercase-hyphen slug, unikátní), company, region
(jedna cílová geografie nebo "Multi-region"), locations, archetype (krátký popis),
why_test (jedna věta proč sedí), career_url, source_strategy (kde by se role
sourcovaly). NEuváděj rating (doplní se "Unrated").

Už existující id (NEPOUŽÍVAT znovu), zkráceně:
{", ".join(sorted(existing_ids))[:6000]}
"""
    try:
        items = ask_json(prompt, web_search=True, max_output_tokens=3000)
    except SystemExit:
        raise
    except Exception as e:  # noqa: BLE001
        print(f"  ! {cat}: chyba modelu ({e}) - přeskakuji")
        return []
    out = []
    for it in items if isinstance(items, list) else []:
        cid = (it.get("canonical_company_id") or "").strip().lower()
        if not cid or cid in existing_ids:
            continue
        existing_ids.add(cid)
        out.append({
            "canonical_company_id": cid,
            "company": it.get("company", "").strip(),
            "parent_company_id": "",
            "aliases_entities": "",
            "company_category": cat,
            "region": it.get("region", "").strip(),
            "locations": it.get("locations", "").strip(),
            "archetype": it.get("archetype", "").strip(),
            "why_test": it.get("why_test", "").strip(),
            "career_url": it.get("career_url", "").strip(),
            "source_strategy": it.get("source_strategy", "").strip(),
            "rating": "Unrated",
            "notes": "Added by gpt-company-discovery",
        })
    return out


def append_rows(fname, rows):
    fp = os.path.join(DATA, fname)
    exists = os.path.exists(fp)
    with open(fp, "a", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=WAVE_COLS)
        if not exists:
            w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in WAVE_COLS})


def update_workstreams(total, per_cat):
    if not os.path.exists(WORKSTREAMS) or total == 0:
        return
    today = dt.date.today().isoformat()
    cats = ", ".join(sorted(per_cat))
    bullet = f"- [{today}] A: added {total} companies across {cats} (gpt-discovery)\n"
    with open(WORKSTREAMS, encoding="utf-8") as f:
        lines = f.readlines()
    # najdi konec sekce "## A ..." = další "## " nebo konec souboru
    start = next((i for i, l in enumerate(lines) if l.startswith("## A ")), None)
    if start is None:
        return
    end = next((i for i in range(start + 1, len(lines)) if lines[i].startswith("## ")), len(lines))
    insert = end
    while insert - 1 > start and lines[insert - 1].strip() == "":
        insert -= 1
    lines.insert(insert, bullet)
    with open(WORKSTREAMS, "w", encoding="utf-8") as f:
        f.writelines(lines)


def main():
    existing = load_existing_ids()
    print(f"Existujících firem: {len(existing)}")
    context = targeting_context()
    by_file, per_cat, total = {}, {}, 0
    for cat in CATEGORY_FILE:
        rows = discover_for_category(cat, existing, context)
        if rows:
            by_file.setdefault(CATEGORY_FILE[cat], []).extend(rows)
            per_cat[cat] = len(rows)
            total += len(rows)
            print(f"  {cat}: +{len(rows)}")
    for fname, rows in by_file.items():
        append_rows(fname, rows)
    update_workstreams(total, per_cat)
    print(f"HOTOVO: přidáno {total} nových firem." if total else "Nic nového, žádná změna.")


if __name__ == "__main__":
    main()
