"""Generic, config-driven sourcing pilot for any sector.

Reuses the same adapter code proven on Big Four / PE / Consulting
(sourcing/big4_pilot.py's Workday, SmartRecruiters, Phenom, SuccessFactors
and generic schema.org discovery, plus pe_pilot.py's Greenhouse adapter).
Every new sector defaults its companies to adapter="generic" -- dedicated
adapters can be swapped in per company later by editing that company's
"adapter" column in its job_sources_*.csv, no code change required unless
the platform itself isn't supported yet.

Usage:
    python -m sourcing.sector_pilot --sources data/job_sources_corporate.csv \
        --jobs-out data/jobs_corporate_staging.csv \
        --runs-out data/source_runs_corporate_staging.csv \
        --max-pages 40
"""
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
    discover_personio,
    target_location,
)

ROOT = Path(__file__).resolve().parents[1]


def relevant_title(title: str) -> bool:
    """Same broad finance-lane vocabulary used across every pilot so far
    (common.ROLE_TERMS / is_relevant_listing_title), so a new sector starts
    from the same, already-calibrated-adjacent hypothesis rather than a
    fresh, drifting one. Nothing here hard-excludes by content lane -- only
    obviously irrelevant listings (intern, HR, assistant roles, ...) are
    dropped; everything else is left for personal_fit scoring to rank.
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
    if adapter == "personio":
        return discover_personio(source)
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
    # "generic" and any unrecognized/not-yet-built adapter name: fall back to
    # the generic schema.org/JobPosting scan of the company's own career
    # page. This is what almost every new-sector row uses today.
    return common.discover_jobs(_source_with_domain(source), max_pages=min(max_pages, 30))


def run(sources_path: Path, jobs_path: Path, runs_path: Path, max_pages: int, source_ids: list[str]) -> None:
    common.ACTIVE_JOBS_OUTPUT_PATH = jobs_path
    sources = pd.read_csv(sources_path).fillna("")
    sources = sources[sources["enabled"].astype(str).str.lower().eq("true")]
    if source_ids:
        sources = sources[sources["source_id"].isin(source_ids)]

    all_jobs: list[dict] = []
    runs: list[dict] = []
    for _, source in sources.iterrows():
        jobs, run_info = discover_source(source, max_pages)
        all_jobs.extend(jobs)
        runs.append(run_info)
        time.sleep(0.15)

    discovered = pd.DataFrame(all_jobs)
    if not discovered.empty:
        discovered = discovered[
            discovered["title"].map(relevant_title)
            & discovered["location"].map(target_location)
        ]
        discovered = common.deduplicate_jobs(discovered)
    translated = common.translate_descriptions(discovered)
    merged = common.merge_jobs(translated, base_path=jobs_path)
    jobs_path.parent.mkdir(parents=True, exist_ok=True)
    merged.to_csv(jobs_path, index=False)

    run_df = pd.DataFrame(runs)
    if runs_path.exists():
        run_df = pd.concat([pd.read_csv(runs_path).fillna(""), run_df], ignore_index=True)
    run_df.tail(2000).to_csv(runs_path, index=False)
    print(
        f"Checked {len(sources)} sources in {sources_path.name}; "
        f"stored {len(merged)} verified roles in {jobs_path.name}."
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sources", required=True, type=Path)
    parser.add_argument("--jobs-out", required=True, type=Path)
    parser.add_argument("--runs-out", required=True, type=Path)
    parser.add_argument("--max-pages", type=int, default=30)
    parser.add_argument("--source-id", action="append", default=[])
    args = parser.parse_args()
    run(args.sources, args.jobs_out, args.runs_out, args.max_pages, args.source_id)


if __name__ == "__main__":
    main()
