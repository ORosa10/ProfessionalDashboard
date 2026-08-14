"""One-off generator: turn the rated Company Universe into job_sources_*.csv
files ready for the sourcing pilots.

Not part of the scheduled pipeline -- run manually whenever the Company
Universe changes enough to warrant regenerating source lists. Existing rows
in job_sources_pe.csv / job_sources_consulting.csv are preserved; this only
appends companies not already present. New sector files default every
company to adapter="generic" (the schema.org/JobPosting fallback that
already works broadly); dedicated adapters can be added per company later,
same as how Big Four adapters were tightened incrementally.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"

RATINGS = pd.read_csv(DATA / "company_ratings.csv").fillna("")
RATING_BY_ID = dict(zip(RATINGS["canonical_company_id"], RATINGS["rating"]))

# How often a company's career page actually gets re-checked once it's past
# its first (always-run) check -- A-rated companies weekly, B biweekly, C
# monthly, so we're not hammering low-priority companies' pages daily just
# because a high-priority sector shares the workflow. Enforced by
# sourcing/big4_pilot.py's due_for_check(), not by this script.
CADENCE_DAYS_BY_RATING = {"A": 7, "B": 14, "C": 30}

ALREADY_SOURCED: set[str] = set()
for existing in ("job_sources_pilot.csv", "job_sources_pe.csv", "job_sources_consulting.csv"):
    path = DATA / existing
    if path.exists():
        ALREADY_SOURCED |= set(pd.read_csv(path).fillna("")["canonical_company_id"])

COLUMNS = [
    "source_id", "canonical_company_id", "company", "market",
    "priority_locations", "seed_url", "adapter", "cadence_days", "enabled",
]

# (universe file, company_category filter or None for "take everything",
#  output filename or None to append into an existing file)
JOBS = [
    ("company_universe_wave2_consulting.csv", "Consulting", "job_sources_consulting.csv"),
    ("company_universe_wave2_investment.csv", "Private Equity & Asset Management", "job_sources_pe.csv"),
    ("company_universe_wave2_corporate.csv", "Corporate", "job_sources_corporate.csv"),
    ("company_universe_wave2_financial_services.csv", "Banking & Financial Services", "job_sources_financial_services.csv"),
    ("company_universe_wave2_holdings.csv", "Holding & Conglomerate", "job_sources_holdings.csv"),
    ("company_universe_wave3_investment.csv", "Investment Banking", "job_sources_investment_banking.csv"),
    ("company_universe_wave3_investment.csv", "Public Markets & Asset Management", "job_sources_public_markets.csv"),
    ("company_universe_wave3_investment.csv", "Specialist & Boutique Funds", "job_sources_specialist_funds.csv"),
    ("company_universe.csv", None, "job_sources_core.csv"),
]


def build_rows(universe_file: str, category: str | None) -> pd.DataFrame:
    df = pd.read_csv(DATA / universe_file).fillna("")
    if category is not None:
        df = df[df["company_category"] == category]
    df = df[df["career_url"].str.strip() != ""]
    df["rating"] = df["canonical_company_id"].map(RATING_BY_ID).fillna("")
    df = df[~df["rating"].isin(["Exclude", ""])]
    df = df[~df["canonical_company_id"].isin(ALREADY_SOURCED)]
    rows = pd.DataFrame({
        "source_id": df["canonical_company_id"] + "-global",
        "canonical_company_id": df["canonical_company_id"],
        "company": df["company"],
        "market": "Multi-region",
        "priority_locations": df["locations"],
        "seed_url": df["career_url"],
        "adapter": "generic",
        "cadence_days": df["rating"].map(CADENCE_DAYS_BY_RATING).fillna(14).astype(int),
        "enabled": True,
    })
    return rows.drop_duplicates(subset="canonical_company_id")


def main() -> None:
    seen_this_run: set[str] = set()
    for universe_file, category, output_file in JOBS:
        rows = build_rows(universe_file, category)
        rows = rows[~rows["canonical_company_id"].isin(seen_this_run)]
        seen_this_run |= set(rows["canonical_company_id"])
        out_path = DATA / output_file
        if out_path.exists():
            existing = pd.read_csv(out_path).fillna("")
            combined = pd.concat([existing, rows], ignore_index=True)
            combined = combined.drop_duplicates(subset="canonical_company_id")
        else:
            combined = rows
        combined = combined[COLUMNS]
        combined.to_csv(out_path, index=False)
        print(f"{output_file}: {len(combined)} total rows ({len(rows)} newly added)")


if __name__ == "__main__":
    main()
