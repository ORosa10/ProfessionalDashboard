"""Audit Big Four source coverage before publishing a review pool.

The audit is deliberately separate from relevance filtering. A source that
returns zero jobs or errors is not treated as checked; it is surfaced for
repair instead of silently shrinking the inventory.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
FIRMS = ("Deloitte", "EY", "KPMG", "PwC")
MARKETS = (
    "Czechia", "Germany", "Austria", "Switzerland", "United Kingdom",
    "Sweden", "Norway", "Denmark", "Finland",
)
NORDIC = {"Sweden", "Norway", "Denmark", "Finland"}


def _market_matches(source_market: str, market: str) -> bool:
    if source_market == market:
        return True
    return source_market == "Nordics" and market in NORDIC


def build_audit(sources: pd.DataFrame, runs: pd.DataFrame) -> pd.DataFrame:
    sources = sources.fillna("")
    runs = runs.fillna("")
    rows: list[dict[str, object]] = []
    for company in FIRMS:
        for market in MARKETS:
            candidates = sources[
                sources["company"].eq(company)
                & sources["market"].map(lambda value: _market_matches(str(value), market))
                & sources["enabled"].astype(str).str.lower().eq("true")
            ]
            if candidates.empty:
                rows.append({
                    "company": company, "market": market, "source_id": "",
                    "seed_url": "", "status": "missing", "last_run": "",
                    "verified_jobs": 0, "errors": "No enabled source configured",
                })
                continue
            source_ids = list(dict.fromkeys(candidates["source_id"].astype(str)))
            source_rows = []
            for source_id in source_ids:
                source = candidates[candidates["source_id"].eq(source_id)].iloc[0]
                source_runs = runs[runs["source_id"].eq(source_id)].copy()
                if source_runs.empty:
                    status, verified, errors, last_run = "not_run", 0, "", ""
                else:
                    source_runs["_run_at"] = pd.to_datetime(source_runs["run_at"], errors="coerce", utc=True)
                    latest = source_runs.sort_values("_run_at").iloc[-1]
                    verified = int(float(latest.get("verified_jobs", 0) or 0))
                    errors = str(latest.get("errors", "") or "")
                    last_run = str(latest.get("run_at", "") or "")
                    status = "error" if errors else "verified" if verified else "zero"
                source_rows.append((source, status, verified, errors, last_run))
            # One row per firm-country cell. Shared or duplicated Nordic feeds
            # are represented in source_id and the worst source status wins.
            rank = {"error": 3, "zero": 2, "not_run": 1, "verified": 0}
            source, status, verified, errors, last_run = max(
                source_rows, key=lambda item: (rank[item[1]], -item[2])
            )
            rows.append({
                "company": company, "market": market,
                "source_id": ";".join(source_ids),
                "seed_url": ";".join(dict.fromkeys(str(item[0]["seed_url"]) for item in source_rows)),
                "status": status, "last_run": last_run,
                "verified_jobs": verified,
                "errors": errors if status == "error" else "",
            })
    return pd.DataFrame(rows)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sources", default="data/job_sources_pilot.csv")
    parser.add_argument("--runs", default="data/source_runs.csv")
    parser.add_argument("--output", default="data/big4_source_audit.csv")
    args = parser.parse_args()
    sources = pd.read_csv(ROOT / args.sources)
    runs = pd.read_csv(ROOT / args.runs) if (ROOT / args.runs).exists() else pd.DataFrame()
    audit = build_audit(sources, runs)
    audit.to_csv(ROOT / args.output, index=False)
    print(audit["status"].value_counts().to_string())
    print(f"Wrote {len(audit)} firm-country audit rows to {args.output}")


if __name__ == "__main__":
    main()


---AUDIT---
company,market,source_id,seed_url,status,last_run,verified_jobs,errors
Deloitte,Czechia,deloitte-cz,https://apply.deloittece.com/en_US/careers/SearchJobs/?jobOffset=0&jobRecordsPerPage=10&listFilterMode=1,verified,2026-08-12T19:08:59.841861+00:00,1,
Deloitte,Germany,deloitte-de,https://jobs.deloitte.de/search/?q=finance&locationsearch=Germany,verified,2026-08-12T19:10:39.314655+00:00,12,
Deloitte,Austria,deloitte-at,https://careers.smartrecruiters.com/DeloitteAT/deloitte-jobs,verified,2026-08-12T19:11:08.632660+00:00,23,
Deloitte,Switzerland,deloitte-ch,https://apply.deloitte.ch/CHCareers/SearchJobs/,verified,2026-08-12T19:11:15.935639+00:00,35,
Deloitte,United Kingdom,deloitte-uk,https://apply.deloitte.co.uk/UKCareers/SearchJobs/,verified,2026-08-12T19:12:18.711567+00:00,140,
Deloitte,Sweden,deloitte-nordics,https://careers.smartrecruiters.com/DeloitteNordic?oga=true,verified,2026-08-12T19:17:34.609223+00:00,23,
Deloitte,Norway,deloitte-nordics,https://careers.smartrecruiters.com/DeloitteNordic?oga=true,verified,2026-08-12T19:17:34.609223+00:00,23,
Deloitte,Denmark,deloitte-nordics,https://careers.smartrecruiters.com/DeloitteNordic?oga=true,verified,2026-08-12T19:17:34.609223+00:00,23,
Deloitte,Finland,deloitte-nordics,https://careers.smartrecruiters.com/DeloitteNordic?oga=true,verified,2026-08-12T19:17:34.609223+00:00,23,
EY,Czechia,ey-cz,https://careers.ey.com/ey/search/?q=finance&locationsearch=Czech%20Republic,verified,2026-08-12T14:44:38.750094+00:00,11,
EY,Germany,ey-de,https://careers.ey.com/ey/search/?q=finance&locationsearch=Germany,verified,2026-08-12T14:45:48.526761+00:00,25,
EY,Austria,ey-at,https://careers.ey.com/ey/search/?q=finance&locationsearch=Austria,verified,2026-08-12T14:46:57.802342+00:00,13,
EY,Switzerland,ey-ch,https://careers.ey.com/ey/search/?q=finance&locationsearch=Switzerland,verified,2026-08-12T14:48:06.657823+00:00,25,
EY,United Kingdom,ey-uk,https://careers.ey.com/ey/search/?q=finance&locationsearch=United%20Kingdom,verified,2026-08-12T14:49:15.881820+00:00,25,
EY,Sweden,ey-se;ey-dk;ey-no;ey-fi,https://careers.ey.com/ey/search/?q=finance&locationsearch=Sweden;https://careers.ey.com/ey/search/?q=finance&locationsearch=Denmark;https://careers.ey.com/ey/search/?q=finance&locationsearch=Norway;https://careers.ey.com/ey/search/?q=finance&locationsearch=Finland,error,2026-08-12T14:53:48.857597+00:00,3,https://careers.ey.com/ey?locale=zh_CN: ReadTimeout
EY,Norway,ey-se;ey-dk;ey-no;ey-fi,https://careers.ey.com/ey/search/?q=finance&locationsearch=Sweden;https://careers.ey.com/ey/search/?q=finance&locationsearch=Denmark;https://careers.ey.com/ey/search/?q=finance&locationsearch=Norway;https://careers.ey.com/ey/search/?q=finance&locationsearch=Finland,error,2026-08-12T14:53:48.857597+00:00,3,https://careers.ey.com/ey?locale=zh_CN: ReadTimeout
EY,Denmark,ey-se;ey-dk;ey-no;ey-fi,https://careers.ey.com/ey/search/?q=finance&locationsearch=Sweden;https://careers.ey.com/ey/search/?q=finance&locationsearch=Denmark;https://careers.ey.com/ey/search/?q=finance&locationsearch=Norway;https://careers.ey.com/ey/search/?q=finance&locationsearch=Finland,error,2026-08-12T14:53:48.857597+00:00,3,https://careers.ey.com/ey?locale=zh_CN: ReadTimeout
EY,Finland,ey-se;ey-dk;ey-no;ey-fi,https://careers.ey.com/ey/search/?q=finance&locationsearch=Sweden;https://careers.ey.com/ey/search/?q=finance&locationsearch=Denmark;https://careers.ey.com/ey/search/?q=finance&locationsearch=Norway;https://careers.ey.com/ey/search/?q=finance&locationsearch=Finland,error,2026-08-12T14:53:48.857597+00:00,3,https://careers.ey.com/ey?locale=zh_CN: ReadTimeout
KPMG,Czechia,kpmg-cz,https://kpmg.jobs.cz/,zero,2026-08-12T14:56:53.637063+00:00,0,
KPMG,Germany,kpmg-de,https://jobs.kpmg.de/?currentPage=1&keyword=finance&pageSize=25,verified,2026-08-12T14:56:54.817054+00:00,93,
KPMG,Austria,kpmg-at,https://bewerbung.kpmg.at/go/Alle-Stellen/9402055/,error,2026-08-12T14:57:16.414031+00:00,0,https://kpmg.com/at/en/home/careers.html: HTTPError
KPMG,Switzerland,kpmg-ch,https://jobs.kpmg.ch/index.cfm?seq=4&sprCd=en&wlgo=1,zero,2026-08-12T14:57:17.298576+00:00,0,
KPMG,United Kingdom,kpmg-uk,https://www.kpmgcareers.co.uk/search/vacancies/?intakeType=Experienced,zero,2026-08-12T14:57:19.066845+00:00,0,
KPMG,Sweden,kpmg-nordics,https://cdn.jobylon.com/jobs/companies/1532/embed/v2/?page_size=100,error,2026-08-12T14:57:20.281290+00:00,0,https://kpmg.com/xx/en/home/careers.html: HTTPError
KPMG,Norway,kpmg-nordics,https://cdn.jobylon.com/jobs/companies/1532/embed/v2/?page_size=100,error,2026-08-12T14:57:20.281290+00:00,0,https://kpmg.com/xx/en/home/careers.html: HTTPError
KPMG,Denmark,kpmg-nordics,https://cdn.jobylon.com/jobs/companies/1532/embed/v2/?page_size=100,error,2026-08-12T14:57:20.281290+00:00,0,https://kpmg.com/xx/en/home/careers.html: HTTPError
KPMG,Finland,kpmg-nordics,https://cdn.jobylon.com/jobs/companies/1532/embed/v2/?page_size=100,error,2026-08-12T14:57:20.281290+00:00,0,https://kpmg.com/xx/en/home/careers.html: HTTPError
PwC,Czechia,pwc-cz,https://jobs-cee.pwc.com/cz/cz/search-results?keywords=finance,zero,2026-08-12T14:40:17.834772+00:00,0,
PwC,Germany,pwc-de,https://jobs.pwc.de/de/de/search-results?keywords=finance,verified,2026-08-12T14:40:23.605221+00:00,98,
PwC,Austria,pwc-at,https://pwc.wd3.myworkdayjobs.com/en-US/Global_Experienced_Careers,zero,2026-08-12T14:42:40.633619+00:00,0,
PwC,Switzerland,pwc-ch,https://pwc.wd3.myworkdayjobs.com/en-US/Global_Experienced_Careers,error,2026-08-12T14:42:49.574128+00:00,0,https://www.pwc.ch/en/careers.html: HTTPError
PwC,United Kingdom,pwc-uk,https://jobs.pwc.co.uk/uk/en/search-results?keywords=finance,verified,2026-08-12T14:42:50.262928+00:00,97,
PwC,Sweden,pwc-nordics,https://pwc.wd3.myworkdayjobs.com/en-US/Global_Experienced_Careers,zero,2026-08-12T14:44:34.419863+00:00,0,
PwC,Norway,pwc-nordics,https://pwc.wd3.myworkdayjobs.com/en-US/Global_Experienced_Careers,zero,2026-08-12T14:44:34.419863+00:00,0,
PwC,Denmark,pwc-nordics,https://pwc.wd3.myworkdayjobs.com/en-US/Global_Experienced_Careers,zero,2026-08-12T14:44:34.419863+00:00,0,
PwC,Finland,pwc-nordics,https://pwc.wd3.myworkdayjobs.com/en-US/Global_Experienced_Careers,zero,2026-08-12T14:44:34.419863+00:00,0,

