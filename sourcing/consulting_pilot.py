from __future__ import annotations

import argparse
import time
from pathlib import Path
from urllib.parse import urlparse

import pandas as pd

from sourcing import big4_pilot as common
from sourcing.pe_pilot import (
    EXCLUDED_ROLE_TERMS,
    _source_with_domain,
    discover_greenhouse,
    target_location,
)


ROOT = Path(__file__).resolve().parents[1]
SOURCES_PATH = ROOT / "data" / "job_sources_consulting.csv"
JOBS_PATH = ROOT / "data" / "jobs_consulting_staging.csv"
RUNS_PATH = ROOT / "data" / "source_runs_consulting_staging.csv"


def relevant_consulting_title(title: str) -> bool:
    """Reuse the same finance-lane vocabulary CONSULTING_TARGETING.md was built from.

    common.ROLE_TERMS / is_relevant_listing_title already encode the Big Four
    calibration lanes (treasury, valuation, deals, restructuring, finance
    transformation, m&a, ...), so this stays consistent with that hypothesis
    instead of inventing a second, drifting vocabulary. Downranked lanes (tax,
    audit, ERP implementation, pure IT) are intentionally NOT hard-excluded
    here -- per product principle, low fit downranks review order but never
    deletes an exploration candidate. personal_fit scoring handles that later.
    """
    value = common.searchable(title)
    return (
        common.is_relevant_listing_title(title)
        and not any(term in value for term in EXCLUDED_ROLE_TERMS)
    )


def discover_source(source: pd.Series, max_pages: int) -> tuple[list[dict], dict]:
    adapter = str(source.get("adapter") or "generic").lower()
    if adapter == "greenhouse":
        return discover_greenhouse(source)
    if adapter == "workday":
        return common.discover_workday_jobs(source, max_pages=min(max_pages, 15))
    if adapter == "successfactors":
        host = urlparse(str(source.seed_url)).netloc.lower().split(":")[0]
        common.SUCCESSFACTORS_HOSTS = tuple(
            dict.fromkeys((*common.SUCCESSFACTORS_HOSTS, host))
        )
        return common.discover_successfactors_sitemap_jobs(source, max_jobs=120)
    if adapter == "smartrecruiters":
        return common.discover_smartrecruiters_jobs(source, max_jobs=160)
    if adapter == "phenom":
        return common.discover_phenom_jobs(source, max_pages=min(max_pages, 10))
    # "selectminds" has no dedicated adapter yet (Alvarez & Marsal, FTI
    # Consulting). Fall through to the generic schema.org/JobPosting scan,
    # same as "generic" and any future unrecognized adapter name -- consistent
    # with how pe_pilot.py handles unmatched adapters.
    return common.discover_jobs(_source_with_domain(source), max_pages=min(max_pages, 30))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-pages", type=int, default=30)
    parser.add_argument("--source-id", action="append", default=[])
    args = parser.parse_args()

    common.ACTIVE_JOBS_OUTPUT_PATH = JOBS_PATH
    sources = pd.read_csv(SOURCES_PATH).fillna("")
    sources = sources[sources["enabled"].astype(str).str.lower().eq("true")]
    if args.source_id:
        sources = sources[sources["source_id"].isin(args.source_id)]

    all_jobs: list[dict] = []
    runs: list[dict] = []
    for _, source in sources.iterrows():
        if not common.due_for_check(source, RUNS_PATH):
            continue
        jobs, run = discover_source(source, args.max_pages)
        all_jobs.extend(jobs)
        runs.append(run)
        time.sleep(0.15)

    discovered = pd.DataFrame(all_jobs)
    if not discovered.empty:
        discovered = discovered[
            discovered["title"].map(relevant_consulting_title)
            & discovered["location"].map(target_location)
        ]
        discovered = common.deduplicate_jobs(discovered)
    translated = common.translate_descriptions(discovered)
    merged = common.merge_jobs(translated, base_path=JOBS_PATH)
    JOBS_PATH.parent.mkdir(parents=True, exist_ok=True)
    merged.to_csv(JOBS_PATH, index=False)

    run_df = pd.DataFrame(runs)
    if RUNS_PATH.exists():
        run_df = pd.concat([pd.read_csv(RUNS_PATH).fillna(""), run_df], ignore_index=True)
    run_df.tail(2000).to_csv(RUNS_PATH, index=False)
    print(
        f"Checked {len(sources)} consulting-expansion sources; stored {len(merged)} "
        f"verified roles in separate consulting staging."
    )


if __name__ == "__main__":
    main()
