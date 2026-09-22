#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
opportunity-enrichment pro svět bez Claude (GitHub Actions + OpenAI API).
1:1 port Cowork úlohy. Denně:
  Fáze 1 - obohatí nové vložené pozice (review_status == "Needs enrichment"
           nebo prázdný company_profile).
  Fáze 2 - ohodnocené (Interested/Maybe) promítne do kontextu: firma -> Universe
           + job_sources_<sektor>, rating -> hypotéza; Pass -> "Rated - noted".
DEFENZIVNÍ: úpravy v user_submitted_opportunities.csv jsou po submission_id
(žádné mazání řádků), do universe/job_sources/TARGETING se jen PŘIPISUJE.
Commit řeší workflow. Bez OPENAI_API_KEY se zastaví (žádná tichá náhrada).
"""
import csv
import datetime as dt
import glob
import os
import sys

import pandas as pd
import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from openai_client import ask, ask_json  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
OPPS = os.path.join(DATA, "user_submitted_opportunities.csv")
WORKSTREAMS = os.path.join(ROOT, "docs", "WORKSTREAMS.md")

CATEGORIES = [
    "Big Four", "Consulting", "Corporate", "Banking & Financial Services",
    "Holding & Conglomerate", "Private Equity & Private Markets",
    "Investment Banking", "Public Markets & Asset Management",
    "Specialist & Boutique Funds",
]
JOB_SOURCES = {
    "Consulting": "job_sources_consulting.csv",
    "Corporate": "job_sources_corporate.csv",
    "Banking & Financial Services": "job_sources_financial_services.csv",
    "Holding & Conglomerate": "job_sources_holdings.csv",
    "Private Equity & Private Markets": "job_sources_pe.csv",
    "Investment Banking": "job_sources_investment_banking.csv",
    "Public Markets & Asset Management": "job_sources_public_markets.csv",
    "Specialist & Boutique Funds": "job_sources_specialist_funds.csv",
}
UNIVERSE_WAVE = {
    "Consulting": ("company_universe_wave2_consulting.csv", "Consulting"),
    "Corporate": ("company_universe_wave2_corporate.csv", "Corporate"),
    "Banking & Financial Services": ("company_universe_wave2_financial_services.csv", "Banking & Financial Services"),
    "Holding & Conglomerate": ("company_universe_wave2_holdings.csv", "Holding & Conglomerate"),
    "Private Equity & Private Markets": ("company_universe_wave2_investment.csv", "Private Equity & Asset Management"),
    "Investment Banking": ("company_universe_wave3_investment.csv", "Investment Banking"),
    "Public Markets & Asset Management": ("company_universe_wave3_investment.csv", "Public Markets & Asset Management"),
    "Specialist & Boutique Funds": ("company_universe_wave3_investment.csv", "Specialist & Boutique Funds"),
}
TARGETING = {
    "Consulting": "CONSULTING_TARGETING.md",
    "Private Equity & Private Markets": "PE_TARGETING.md",
    "Corporate": "CORPORATE_TARGETING.md",
    "Banking & Financial Services": "FINANCIAL_SERVICES_TARGETING.md",
    "Public Markets & Asset Management": "PUBLIC_MARKETS_TARGETING.md",
    "Specialist & Boutique Funds": "SPECIALIST_FUNDS_TARGETING.md",
}
WAVE_COLS = [
    "canonical_company_id", "company", "parent_company_id", "aliases_entities",
    "company_category", "region", "locations", "archetype", "why_test",
    "career_url", "source_strategy", "rating", "notes",
]
JS_COLS = ["source_id", "canonical_company_id", "company", "market",
           "priority_locations", "seed_url", "adapter", "cadence_days", "enabled"]

PROFILE = (
    "Pozitivní: treasury, financial & market risk, deriváty, valuation, liquidity, "
    "FX, úrokové sazby, komodity, modelování/analytika, investice, corporate finance, "
    "people management. Mírně pozitivní: Python/R/SQL, Bloomberg/Refinitiv, CFA/FRM. "
    "Negativní: compliance/regulatoric, čistý sales, čisté IFRS/reporting. Jazyk: "
    "plynulost/C1/native v jiném než angličtině = red flag ('good German' ok). "
    "Geografie: Česko, Německo, Rakousko, Švýcarsko, UK, Nordics. Úspora ~500 000 CZK/rok."
)


def fetch_url(url):
    if not url:
        return ""
    try:
        r = requests.get(url, timeout=30, headers={"User-Agent": "Mozilla/5.0"})
        if r.ok:
            return r.text[:8000]
    except Exception:  # noqa: BLE001
        pass
    return ""


def slug(s):
    import re
    return re.sub(r"[^a-z0-9]+", "-", (s or "").lower()).strip("-")


def existing_universe_ids():
    ids = set()
    for fp in glob.glob(os.path.join(DATA, "company_universe*.csv")):
        try:
            df = pd.read_csv(fp, dtype=str, keep_default_na=False)
            ids.update(df.get("canonical_company_id", pd.Series([], dtype=str)).str.lower())
        except Exception:  # noqa: BLE001
            pass
    return {i for i in ids if i}


def append_row(fname, cols, row):
    fp = os.path.join(DATA, fname)
    exists = os.path.exists(fp)
    with open(fp, "a", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        if not exists:
            w.writeheader()
        w.writerow({k: row.get(k, "") for k in cols})


def append_targeting(cat, bullet):
    name = TARGETING.get(cat, "GENERAL_TARGETING.md")
    fp = os.path.join(ROOT, name)
    with open(fp, "a", encoding="utf-8") as f:
        f.write(("" if not os.path.exists(fp) else "") + bullet + "\n")


def update_workstreams(section_letter, bullet):
    if not os.path.exists(WORKSTREAMS):
        return
    with open(WORKSTREAMS, encoding="utf-8") as f:
        lines = f.readlines()
    start = next((i for i, l in enumerate(lines) if l.startswith(f"## {section_letter} ")), None)
    if start is None:
        return
    end = next((i for i in range(start + 1, len(lines)) if lines[i].startswith("## ")), len(lines))
    insert = end
    while insert - 1 > start and lines[insert - 1].strip() == "":
        insert -= 1
    lines.insert(insert, bullet if bullet.endswith("\n") else bullet + "\n")
    with open(WORKSTREAMS, "w", encoding="utf-8") as f:
        f.writelines(lines)


def phase1(df):
    mask = (df["review_status"] == "Needs enrichment") | (df["company_profile"].fillna("").str.strip() == "")
    todo = df[mask]
    n = 0
    for idx, row in todo.iterrows():
        page = fetch_url(row.get("company_url", "")) or fetch_url(row.get("job_url", ""))
        prompt = f"""Obohať tuto pracovní příležitost pro kandidáta s profilem:
{PROFILE}

Vstupy:
- title: {row.get('title','')}
- company: {row.get('company','')}
- company_url: {row.get('company_url','')}
- job_url: {row.get('job_url','')}
- linkedin_url: {row.get('linkedin_url','')}
- text stránky (zkráceně): {page[:4000]}

Když je text prázdný nebo je odkaz na LinkedIn (login-gated), použij web search.
Vrať JSON objekt s klíči (ASCII-safe, stručně):
title, company, location, country, canonical_company_id (lowercase-hyphen slug),
company_category (přesně jedno z: {", ".join(CATEGORIES)}; default Corporate když
nejasné), topic, role_summary_en (1-3 věty), company_profile (2-4 věty),
role_profile (co role dělá + seniorita + jazyk + on-site + explicitní FIT vs.
profil se zelenými/červenými vlajkami), salary_research (PRIMÁRNÍ tržní rozpětí +
"co si říct" z reálných zdrojů; SEKUNDÁRNÍ jedna věta vs. cíl ~500k CZK/rok pro
dané město), salary_range (KRÁTKÉ rozpětí pro sloupec, např. "EUR 80-100k base")."""
        try:
            d = ask_json(prompt, web_search=True, max_output_tokens=1500)
        except SystemExit:
            raise
        except Exception as e:  # noqa: BLE001
            print(f"  ! enrich submission {row.get('submission_id')}: {e} - přeskakuji")
            continue
        cat = d.get("company_category", "Corporate")
        if cat not in CATEGORIES:
            cat = "Corporate"
        for k in ("title", "company", "location", "country", "topic", "role_summary_en",
                  "company_profile", "role_profile", "salary_research", "salary_range"):
            if d.get(k):
                df.at[idx, k] = str(d[k])
        df.at[idx, "canonical_company_id"] = d.get("canonical_company_id") or slug(d.get("company", row.get("company", "")))
        df.at[idx, "company_category"] = cat
        df.at[idx, "targeting_scope"] = cat
        df.at[idx, "review_status"] = "Enriched - ready to rate"
        n += 1
        print(f"  enriched: {df.at[idx,'company']} ({cat})")
    return n


def identify_adapter(company, career_url):
    prompt = f"""Firma: {company}. Careers URL: {career_url or '(neznámé)'}.
Zjisti (web search) jejich ATS a vrať JSON: {{"adapter": one of workday|successfactors|
smartrecruiters|greenhouse|phenom|personio|llm, "seed_url": "co nejlepší seed URL
kariérních stránek nebo prázdné"}}. Když si nejsi jistý, adapter="llm"."""
    try:
        d = ask_json(prompt, web_search=True, max_output_tokens=400)
        ad = d.get("adapter", "llm")
        return (ad if ad in {"workday", "successfactors", "smartrecruiters", "greenhouse", "phenom", "personio", "llm"} else "llm",
                d.get("seed_url", ""))
    except Exception:  # noqa: BLE001
        return "llm", ""


def phase2(df, uni_ids):
    onboarded = 0
    js_existing = {}
    for cat, fn in JOB_SOURCES.items():
        fp = os.path.join(DATA, fn)
        if os.path.exists(fp):
            try:
                js_existing[fn] = set(pd.read_csv(fp, dtype=str, keep_default_na=False)["canonical_company_id"].str.lower())
            except Exception:  # noqa: BLE001
                js_existing[fn] = set()
    for idx, row in df.iterrows():
        fb = (row.get("feedback") or "").strip()
        rs = (row.get("review_status") or "").strip()
        if fb not in ("Interested", "Maybe", "Pass") or rs in ("Onboarded to sourcing", "Rated - noted"):
            continue
        cat = row.get("company_category") or "Corporate"
        cid = (row.get("canonical_company_id") or slug(row.get("company", ""))).lower()
        company = row.get("company", "")
        if fb in ("Interested", "Maybe") and cat != "Big Four":
            wave, label = UNIVERSE_WAVE.get(cat, ("company_universe_wave2_corporate.csv", "Corporate"))
            if cid and cid not in uni_ids:
                append_row(wave, WAVE_COLS, {
                    "canonical_company_id": cid, "company": company,
                    "company_category": label, "region": row.get("country", ""),
                    "locations": row.get("location", ""), "archetype": "",
                    "why_test": (row.get("role_summary_en", "") or "")[:200],
                    "career_url": row.get("company_url", ""), "rating": "Unrated",
                    "notes": "Added from an Interested user-submitted opportunity",
                })
                uni_ids.add(cid)
            fn = JOB_SOURCES.get(cat)
            if fn and cid and cid not in js_existing.get(fn, set()):
                adapter, seed = identify_adapter(company, row.get("company_url", ""))
                append_row(fn, JS_COLS, {
                    "source_id": f"{cid}-global", "canonical_company_id": cid,
                    "company": company, "market": row.get("country", "") or "Multi-region",
                    "priority_locations": row.get("location", ""), "seed_url": seed,
                    "adapter": adapter, "cadence_days": "14", "enabled": "True",
                })
                js_existing.setdefault(fn, set()).add(cid)
            df.at[idx, "review_status"] = "Onboarded to sourcing"
            onboarded += 1
        elif fb == "Pass":
            df.at[idx, "review_status"] = "Rated - noted"
        today = dt.date.today().isoformat()
        tag = "Pass" if fb == "Pass" else "Interested"
        append_targeting(cat, f"- [{today}] User example ({tag}): {row.get('title','')} @ {company} - theme {row.get('topic','')}")
    return onboarded


def main():
    if not os.path.exists(OPPS):
        sys.exit(f"CHYBA: {OPPS} neexistuje - končím (žádná tichá náhrada).")
    df = pd.read_csv(OPPS, dtype=str, keep_default_na=False)
    n1 = phase1(df)
    uni_ids = existing_universe_ids()
    n2 = phase2(df, uni_ids)
    if n1 or n2:
        df.to_csv(OPPS, index=False)
        update_workstreams("B", f"- [{dt.date.today().isoformat()}] B: enriched {n1}, onboarded {n2} companies to sourcing (gpt)")
    print(f"HOTOVO: enriched {n1}, onboarded {n2}." if (n1 or n2) else "Nic ke zpracování.")


if __name__ == "__main__":
    main()
