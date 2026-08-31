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
