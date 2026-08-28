"""Run every explicitly enabled A company-career source and publish coverage telemetry.

A source is not considered operational merely because it exists in a registry. This
runner records one outcome per due source: success, zero_jobs, error, or not_run.
"""
from __future__ import annotations

import argparse
import time
from pathlib import Path
from urllib.parse import urlparse

import pandas as pd

from sourcing import big4_pilot as common
from sourcing.consulting_pilot import discover_source as discover_consulting_source
from sourcing.pe_pilot import discover_source as discover_pe_source
from sourcing.sync_a_company_sources import MANAGED_SOURCE_FILES

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
OUT_PATH = DATA / "jobs_company_staging.csv"
RUNS_PATH = DATA / "source_runs_company_staging.csv"
COVERAGE_PATH = DATA / "company_source_coverage.csv"

SOURCE_COLUMNS = [
    "source_id", "canonical_company_id", "company", "market",
    "priority_locations", "seed_url", "adapter", "cadence_days", "enabled",
]
RUN_COLUMNS = [
    "run_at", "source_id", "canonical_company_id", "company", "market",
    "seed_url", "adapter", "source_file", "source_status", "pages_checked",
    "candidate_job_pages", "verified_jobs", "errors",
]
COVERAGE_COLUMNS = [
    "checked_at", "canonical_company_id", "company", "rating", "source_file",
    "source_id", "adapter", "career_url", "execution_status", "jobs_found",
    "last_run_at", "error", "next_due",
]


def _source_with_domain(source: pd.Series) -> pd.Series:
    result = source.copy()
    if not str(result.get("allowed_domains", "")).strip():
        result["allowed_domains"] = urlparse(str(result.get("seed_url", ""))).netloc
    return result


def discover_source(source: pd.Series, max_pages: int) -> tuple[list[dict], dict]:
    """Dispatch each configured source to the adapter it actually declares.

    The previous implementation routed most adapter types through the generic
    crawler. It also routed SuccessFactors through the PE runner, whose
    investment-role filter incorrectly removed corporate and banking vacancies.
    """
    adapter = str(source.get("adapter") or "generic").strip().lower()
    if adapter == "greenhouse":
        return discover_pe_source(source, max_pages)
    if adapter == "personio":
        return discover_pe_source(source, max_pages)
    if adapter == "successfactors":
        return common.discover_successfactors_sitemap_jobs(source, max_jobs=140)
    if adapter == "workday":
        return common.discover_workday_jobs(source, max_pages=min(max_pages, 20))
    if adapter == "smartrecruiters":
        return common.discover_smartrecruiters_jobs(source, max_jobs=140)
    if adapter == "phenom":
        return common.discover_phenom_jobs(source, max_pages=min(max_pages, 12))
    if adapter == "avature":
        return common.discover_avature_jobs(source, max_pages=min(max_pages, 20), max_jobs=140)
    if adapter == "jobylon":
        return common.discover_jobylon_jobs(source, max_jobs=140)
    return common.discover_jobs(_source_with_domain(source), max_pages=min(max_pages, 30))


def _load_sources() -> list[tuple[str, pd.DataFrame]]:
    result = []
    for filename in MANAGED_SOURCE_FILES:
        path = DATA / filename
        if not path.exists() or path.stat().st_size == 0:
            continue
        frame = pd.read_csv(path).fillna("")
        if not frame.empty:
            result.append((filename, frame.reindex(columns=SOURCE_COLUMNS, fill_value="")))
    return result


def _previous_jobs() -> pd.DataFrame:
    if not OUT_PATH.exists() or OUT_PATH.stat().st_size == 0:
        return pd.DataFrame()
    try:
        return pd.read_csv(OUT_PATH).fillna("")
    except (pd.errors.EmptyDataError, pd.errors.ParserError):
        return pd.DataFrame()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-pages", type=int, default=30)
    args = parser.parse_args()

    now = pd.Timestamp.now(tz="UTC").isoformat()
    jobs: list[dict] = []
    run_rows: list[dict] = []
    coverage: list[dict] = []
    previous = _previous_jobs()
    previous_by_source = {}
    if not previous.empty and "source_id" in previous.columns:
        previous_by_source = {
            source_id: group
            for source_id, group in previous.groupby("source_id", dropna=False)
        }

    for source_file, frame in _load_sources():
        enabled = frame[frame["enabled"].astype(str).str.lower().eq("true")]
        for _, source in enabled.iterrows():
            source_id = str(source.get("source_id", "")).strip()
            if not source_id:
                continue
            due = common.due_for_check(source, RUNS_PATH)
            if not due:
                old = previous_by_source.get(source_id, pd.DataFrame())
                last_seen = old["last_seen_at"].max() if not old.empty and "last_seen_at" in old.columns else ""
                coverage.append({
                    "checked_at": now, "canonical_company_id": source.get("canonical_company_id", ""),
                    "company": source.get("company", ""), "rating": "",
                    "source_file": source_file, "source_id": source_id,
                    "adapter": source.get("adapter", ""), "career_url": source.get("seed_url", ""),
                    "execution_status": "not_due", "jobs_found": len(old),
                    "last_run_at": "", "error": "", "next_due": last_seen,
                })
                continue

            started = pd.Timestamp.now(tz="UTC").isoformat()
            errors = []
            found = []
            try:
                found, run = discover_source(source, args.max_pages)
                errors = str(run.get("errors", "") or "")
                run_rows.append({
                    "run_at": run.get("run_at", started), "source_id": source_id,
                    "canonical_company_id": source.get("canonical_company_id", ""),
                    "company": source.get("company", ""), "market": source.get("market", ""),
                    "seed_url": source.get("seed_url", ""), "adapter": source.get("adapter", ""),
                    "source_file": source_file,
                    "source_status": "success" if found else ("error" if errors else "zero_jobs"),
                    "pages_checked": run.get("pages_checked", ""),
                    "candidate_job_pages": run.get("candidate_job_pages", ""),
                    "verified_jobs": len(found), "errors": errors,
                })
            except Exception as exc:
                errors = f"{type(exc).__name__}: {exc}"
                run_rows.append({
                    "run_at": started, "source_id": source_id,
                    "canonical_company_id": source.get("canonical_company_id", ""),
                    "company": source.get("company", ""), "market": source.get("market", ""),
                    "seed_url": source.get("seed_url", ""), "adapter": source.get("adapter", ""),
                    "source_file": source_file, "source_status": "error",
                    "pages_checked": "", "candidate_job_pages": "", "verified_jobs": 0,
                    "errors": errors,
                })
            jobs.extend(found)
            coverage.append({
                "checked_at": now, "canonical_company_id": source.get("canonical_company_id", ""),
                "company": source.get("company", ""), "rating": "",
                "source_file": source_file, "source_id": source_id,
                "adapter": source.get("adapter", ""), "career_url": source.get("seed_url", ""),
                "execution_status": "error" if errors else ("success" if found else "zero_jobs"),
                "jobs_found": len(found), "last_run_at": started, "error": errors,
                "next_due": "",
            })
            time.sleep(0.1)

    discovered = pd.DataFrame(jobs)
    if not discovered.empty:
        discovered = discovered.drop_duplicates("job_id", keep="first") if "job_id" in discovered.columns else discovered
    if not previous.empty and not discovered.empty:
        discovered = pd.concat([previous, discovered], ignore_index=True, sort=False)
        if "job_id" in discovered.columns:
            discovered = discovered.drop_duplicates("job_id", keep="last")
    elif not previous.empty:
        discovered = previous
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    discovered.to_csv(OUT_PATH, index=False)
    old_runs = pd.read_csv(RUNS_PATH).fillna("") if RUNS_PATH.exists() and RUNS_PATH.stat().st_size else pd.DataFrame()
    runs = pd.concat([old_runs, pd.DataFrame(run_rows)], ignore_index=True, sort=False).tail(5000)
    runs.reindex(columns=RUN_COLUMNS, fill_value="").to_csv(RUNS_PATH, index=False)
    pd.DataFrame(coverage).reindex(columns=COVERAGE_COLUMNS, fill_value="").to_csv(COVERAGE_PATH, index=False)
    print(f"Checked {len(coverage)} company sources; found {len(jobs)} new roles; stored {len(discovered)} roles.")


if __name__ == "__main__":
    main()
