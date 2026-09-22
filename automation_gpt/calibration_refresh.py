#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
calibration-refresh pro svět bez Claude (GitHub Actions + OpenAI API), spouští
se ručně (workflow_dispatch). 1:1 port Cowork úlohy:
  Fáze 1  - z ratingů/komentářů/targeting_feedback KONZERVATIVNĚ upraví
            data/calibration_rules.json (jen mění pořadí/váhy, NIKDY tvrdé
            vyloučení, nemaže seed témata) + dopíše shrnutí do *_TARGETING.md.
  Fáze 2  - přegeneruje kalibrační shortlisty přes EXISTUJÍCÍ modul
            sourcing.build_calibration_batch (deterministické, beze změny).
  Fáze 2b - PRIMÁRNÍ semantic fit (Strong/Moderate/Weak + reasoning) -> upsert
            data/semantic_fit.csv.
DEFENZIVNÍ: calibration_rules.json se jen merguje; semantic_fit se upsertuje
po opportunity_id. Commit řeší workflow. Bez OPENAI_API_KEY se zastaví.
"""
import json
import os
import subprocess
import sys
import datetime as dt

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from openai_client import ask_json  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
RULES = os.path.join(DATA, "calibration_rules.json")
SEMANTIC = os.path.join(DATA, "semantic_fit.csv")
WORKSTREAMS = os.path.join(ROOT, "docs", "WORKSTREAMS.md")

PROFILE = (
    "Pozitivní: treasury, financial & market risk, deriváty, valuation, liquidity, "
    "FX, úrokové sazby, komodity, modelování/analytika, investice, corporate finance, "
    "people management. Mírně pozitivní: Python/R/SQL, Bloomberg/Refinitiv, CFA/FRM. "
    "Negativní: compliance/regulatoric, čistý sales, čisté IFRS/reporting. Jazyk: "
    "plynulost/C1/native v jiném než angličtině = red flag ('good German' ok). "
    "Seniorita ~3-7 let; snižuj internship/grad a Director/Head+. Drž ~20% exploration. "
    "Geografie: Česko, Německo, Rakousko, Švýcarsko, UK, Nordics."
)
SHORTLISTS = [
    ("data/jobs_corporate_staging.csv", "data/corporate_calibration_shortlist.csv", "corporate-calibration"),
    ("data/jobs_financial-services_staging.csv", "data/financial_services_calibration_shortlist.csv", "financial-services-calibration"),
    ("data/jobs_public-markets_staging.csv", "data/public_markets_calibration_shortlist.csv", "public-markets-calibration"),
    ("data/jobs_specialist-funds_staging.csv", "data/specialist_funds_calibration_shortlist.csv", "specialist-funds-calibration"),
]


def read_csv(fp):
    return pd.read_csv(fp, dtype=str, keep_default_na=False) if os.path.exists(fp) else pd.DataFrame()


def clamp(w, lo, hi):
    try:
        return max(lo, min(hi, int(round(float(w)))))
    except (TypeError, ValueError):
        return 0


def phase1():
    rules = json.load(open(RULES, encoding="utf-8"))
    tf = read_csv(os.path.join(DATA, "targeting_feedback.csv"))
    opps = read_csv(os.path.join(DATA, "user_submitted_opportunities.csv"))
    rated = opps[opps.get("feedback", pd.Series(dtype=str)).isin(["Interested", "Maybe", "Pass"])] if not opps.empty else opps
    jf = read_csv(os.path.join(DATA, "job_feedback.csv"))

    evidence = {
        "targeting_feedback": tf.to_dict("records")[:40] if not tf.empty else [],
        "rated_submitted": (rated[["title", "company", "topic", "feedback", "user_comment"]].to_dict("records")[:40]
                            if not rated.empty and set(["title", "company", "topic", "feedback"]).issubset(rated.columns) else []),
        "job_feedback": jf.to_dict("records")[:40] if not jf.empty else [],
    }
    prompt = f"""Jsi kalibrační analytik. Profil kandidáta:
{PROFILE}

Aktuální pravidla (calibration_rules.json, struktura positive_rules/caution_rules
= {{label: {{terms:[...], weight:int}}}}, base 50):
{json.dumps({k: rules.get(k) for k in ('positive_rules','caution_rules')}, ensure_ascii=False)[:6000]}

Nová evidence (priorita: targeting_feedback > rated_submitted > job_feedback):
{json.dumps(evidence, ensure_ascii=False)[:6000]}

Navrhni KONZERVATIVNÍ úpravy: přidej/zvyš positive termy pro oblíbená témata,
přidej/prohlub caution pro neoblíbená. Váhy mírné (+5..+15 / -5..-15). Jen
reorder, NIKDY tvrdé vyloučení, nemaž existující seed témata. Vyžaduj ~3
konzistentní signály (jedna přímá thesis-feedback věta stačí), jinak malá/žádná
změna. Vrať JSON pole objektů:
{{"section":"positive"|"caution","label":str,"terms":[str,...],"weight":int,
"reason":str}}. Když není důvod k změně, vrať prázdné pole []."""
    try:
        deltas = ask_json(prompt, web_search=False, max_output_tokens=2000)
    except SystemExit:
        raise
    except Exception as e:  # noqa: BLE001
        print(f"  ! Fáze 1 model chyba: {e} - pravidla nechávám beze změny")
        return rules, []
    applied = []
    for d in deltas if isinstance(deltas, list) else []:
        sec = "positive_rules" if d.get("section") == "positive" else "caution_rules"
        label = (d.get("label") or "").strip()
        if not label:
            continue
        lo, hi = (5, 15) if sec == "positive_rules" else (-15, -5)
        node = rules.setdefault(sec, {}).setdefault(label, {"terms": [], "weight": 0})
        terms = node.get("terms") or []
        for t in d.get("terms", []):
            if t and t not in terms:
                terms.append(t)
        node["terms"] = terms
        node["weight"] = clamp(d.get("weight", node.get("weight", 0)), lo, hi)
        applied.append(f"{d.get('section')}:{label}")
    if applied:
        rules["updated"] = f"{dt.date.today().isoformat()} - gpt calibration: {', '.join(applied)[:300]}"
        json.dump(rules, open(RULES, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    return rules, applied


def phase2():
    made = []
    for staging, out, batch in SHORTLISTS:
        if not os.path.exists(os.path.join(ROOT, staging)):
            continue
        cmd = [sys.executable, "-m", "sourcing.build_calibration_batch",
               "--jobs", staging, "--output", out, "--batch-id", batch, "--total", "20"]
        r = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
        if r.returncode == 0:
            made.append(out)
            print(f"  shortlist OK: {out}")
        else:
            print(f"  ! shortlist selhal ({out}): {r.stderr[:300]}")
    return made


def role_text_index():
    idx = {}
    import glob as _g
    for fp in _g.glob(os.path.join(DATA, "jobs*.csv")) + _g.glob(os.path.join(DATA, "*_candidates.csv")):
        try:
            df = pd.read_csv(fp, dtype=str, keep_default_na=False)
        except Exception:  # noqa: BLE001
            continue
        key = next((k for k in ("job_id", "candidate_id", "opportunity_id", "id") if k in df.columns), None)
        if not key:
            continue
        tcol = next((k for k in ("description_en", "description", "title") if k in df.columns), None)
        for _, r in df.iterrows():
            idx[str(r[key])] = f"{r.get('title','')} :: {r.get(tcol,'') if tcol else ''}"[:3000]
    return idx


def phase2b(shortlist_files):
    files = shortlist_files + [
        os.path.join(DATA, "job_calibration_batch.csv"),
        os.path.join(DATA, "pe_calibration_shortlist.csv"),
        os.path.join(DATA, "consulting_calibration_shortlist.csv"),
    ]
    ids = []
    for fp in files:
        p = fp if os.path.isabs(fp) else os.path.join(ROOT, fp)
        if os.path.exists(p):
            df = pd.read_csv(p, dtype=str, keep_default_na=False)
            col = next((c for c in ("opportunity_id", "job_id", "id") if c in df.columns), None)
            if col:
                ids += list(df[col])
    ids = [i for i in dict.fromkeys(ids) if i]
    if not ids:
        print("  žádné shortlist role pro semantic fit.")
        return 0
    texts = role_text_index()
    sem = read_csv(SEMANTIC)
    rows = {r["opportunity_id"]: r for r in sem.to_dict("records")} if not sem.empty else {}
    n = 0
    for oid in ids:
        txt = texts.get(oid)
        if not txt:
            continue
        prompt = f"""Profil kandidáta:
{PROFILE}

Role (title :: popis):
{txt}

Jako zkušený recruiter SÉMANTICKY porovnej roli s profilem (co role reálně dělá,
seniorita, jazyk, lokalita, omezení). Vrať JSON: {{"fit":"Strong"|"Moderate"|"Weak",
"reasoning":"2-3 věty proč sedí/nesedí, zelené vlajky + případné omezení"}} (ASCII-safe)."""
        try:
            d = ask_json(prompt, web_search=False, max_output_tokens=500)
        except Exception as e:  # noqa: BLE001
            print(f"  ! semantic fit {oid}: {e}")
            continue
        rows[oid] = {"opportunity_id": oid, "fit": d.get("fit", "Moderate"),
                     "reasoning": (d.get("reasoning", "") or "")[:600],
                     "generated_at": dt.date.today().isoformat()}
        n += 1
    out = pd.DataFrame(list(rows.values()), columns=["opportunity_id", "fit", "reasoning", "generated_at"])
    out.to_csv(SEMANTIC, index=False)
    print(f"  semantic fit: {n} rolí (soubor má {len(out)} řádků).")
    return n


def update_workstreams(bullet):
    if not os.path.exists(WORKSTREAMS):
        return
    lines = open(WORKSTREAMS, encoding="utf-8").readlines()
    start = next((i for i, l in enumerate(lines) if l.startswith("## C ")), None)
    if start is None:
        return
    end = next((i for i in range(start + 1, len(lines)) if lines[i].startswith("## ")), len(lines))
    insert = end
    while insert - 1 > start and lines[insert - 1].strip() == "":
        insert -= 1
    lines.insert(insert, bullet + "\n")
    open(WORKSTREAMS, "w", encoding="utf-8").writelines(lines)


def main():
    if not os.path.exists(RULES):
        sys.exit(f"CHYBA: {RULES} neexistuje - končím (žádná tichá náhrada).")
    _, applied = phase1()
    made = phase2()
    n_sem = phase2b(made)
    update_workstreams(
        f"- [{dt.date.today().isoformat()}] C: gpt kalibrace; rule změny: "
        f"{len(applied)}; shortlisty: {len(made)}; semantic fit: {n_sem}"
    )
    print(f"HOTOVO: pravidla {len(applied)}, shortlisty {len(made)}, semantic fit {n_sem}.")


if __name__ == "__main__":
    main()
