"""Generic, config-driven sourcing pilot for any sector.

Reuses the same adapter code proven on Big Four / PE / Consulting
(sourcing/big4_pilot.py's Workday, SmartRecruiters, Phenom, SuccessFactors
and generic schema.org discovery, plus pe_pilot.py's Greenhouse adapter).
Every new sector defaults its companies to adapter="generic". When the career
URL clearly identifies a supported ATS, the adapter is upgraded automatically.
For genuinely custom pages, repeated *technical* generic failures can escalate
to the existing headless/LLM fallback. A successful zero-job scan never counts
as a technical failure.

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
from typing import Mapping
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
GENERIC_FAILURES_BEFORE_LLM = 3


def relevant_title(title: str) -> bool:
    """Same broad finance-lane vocabulary used across every pilot so far."""
    value = common.searchable(title)
    return (
        common.is_relevant_listing_title(title)
        and not any(term in value for term in EXCLUDED_ROLE_TERMS)
    )


def infer_adapter_from_url(url: str) -> str:
    """Return a supported ATS adapter only when the URL fingerprint is strong.

    This is intentionally conservative: a branded careers page may itself be
    backed by Phenom or another ATS without exposing that in the URL, so those
    stay generic until the generic scan proves technically unreliable.
    """
    raw = str(url or "").strip().lower()
    host = urlparse(raw).netloc.lower().split(":")[0]
    if "myworkdayjobs.com" in host:
        return "workday"
    if "greenhouse.io" in host:
        return "greenhouse"
    if "personio." in host:
        return "personio"
    if "smartrecruiters.com" in host:
        return "smartrecruiters"
    if "successfactors." in host:
        return "successfactors"
    return ""


def is_technical_failure(run_info: Mapping[str, object] | pd.Series) -> bool:
    """A technical failure is not the same thing as finding zero jobs.

    We only escalate when the adapter reported an actual error and verified no
    jobs. Therefore an error-free scan with zero relevant vacancies is healthy.
    """
    errors = str(run_info.get("errors", "") or "").strip()
    try:
        verified_jobs = int(float(str(run_info.get("verified_jobs", 0) or 0)))
    except (TypeError, ValueError):
        verified_jobs = 0
    return bool(errors) and verified_jobs == 0


def consecutive_technical_failures(history: pd.DataFrame, source_id: str) -> int:
    """Count the trailing technical-failure streak for one source.

    A successful run, including a successful zero-job run, resets the streak.
    If newer run data records an explicit non-generic adapter, that also ends
    the generic-failure streak.
    """
    if history.empty or "source_id" not in history.columns:
        return 0
    subset = history[history["source_id"].astype(str).eq(str(source_id))].copy()
    if subset.empty:
        return 0
    if "run_at" in subset.columns:
        subset = subset.sort_values("run_at")
    count = 0
    for _, row in subset.iloc[::-1].iterrows():
        adapter_used = str(row.get("adapter_used", "") or "").strip().lower()
        if adapter_used and adapter_used != "generic":
            break
        if is_technical_failure(row):
            count += 1
            continue
        break
    return count


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
    if adapter == "llm":
        from sourcing.llm_fallback import discover_jobs_llm

        return discover_jobs_llm(source)
    return common.discover_jobs(_source_with_domain(source), max_pages=min(max_pages, 30))


def run(sources_path: Path, jobs_path: Path, runs_path: Path, max_pages: int, source_ids: list[str]) -> None:
    common.ACTIVE_JOBS_OUTPUT_PATH = jobs_path
    all_sources = pd.read_csv(sources_path).fillna("")
    sources = all_sources[all_sources["enabled"].astype(str).str.lower().eq("true")].copy()
    if source_ids:
        sources = sources[sources["source_id"].isin(source_ids)]

    historical_runs = (
        pd.read_csv(runs_path).fillna("")
        if runs_path.exists() and runs_path.stat().st_size
        else pd.DataFrame()
    )

    all_jobs: list[dict] = []
    runs: list[dict] = []
    source_registry_changed = False

    for source_idx, source in sources.iterrows():
        if not common.due_for_check(source, runs_path):
            continue

        original_adapter = str(source.get("adapter") or "generic").strip().lower()
        effective_source = source.copy()
        inferred_adapter = ""
        fallback_reason = ""

        if original_adapter == "generic":
            inferred_adapter = infer_adapter_from_url(str(source.get("seed_url", "")))
            if inferred_adapter:
                effective_source["adapter"] = inferred_adapter
                all_sources.at[source_idx, "adapter"] = inferred_adapter
                source_registry_changed = True
                fallback_reason = f"url_fingerprint:{inferred_adapter}"

        jobs, run_info = discover_source(effective_source, max_pages)
        run_info["adapter_used"] = str(effective_source.get("adapter") or "generic").lower()
        run_info["fallback_reason"] = fallback_reason

        # Only custom/generic pages can escalate automatically to LLM. A clean
        # zero-job scan is healthy and therefore never reaches this branch.
        if (
            original_adapter == "generic"
            and not inferred_adapter
            and is_technical_failure(run_info)
            and consecutive_technical_failures(historical_runs, str(source.get("source_id", "")))
            >= GENERIC_FAILURES_BEFORE_LLM - 1
        ):
            llm_source = source.copy()
            llm_source["adapter"] = "llm"
            llm_jobs, llm_run = discover_source(llm_source, max_pages)
            llm_run["adapter_used"] = "llm"
            llm_run["fallback_reason"] = "after_3_consecutive_generic_technical_failures"
            if not is_technical_failure(llm_run):
                jobs = llm_jobs
                run_info = llm_run
                all_sources.at[source_idx, "adapter"] = "llm"
                source_registry_changed = True
            else:
                generic_error = str(run_info.get("errors", "") or "").strip()
                llm_error = str(llm_run.get("errors", "") or "").strip()
                run_info["fallback_reason"] = "llm_attempt_failed_after_3_generic_technical_failures"
                run_info["errors"] = " | ".join(
                    part for part in [generic_error, f"LLM fallback: {llm_error}" if llm_error else ""] if part
                )

        all_jobs.extend(jobs)
        runs.append(run_info)
        # Include this run in the in-memory history so the helper remains
        # correct even if a source registry ever contains repeated source IDs.
        historical_runs = pd.concat(
            [historical_runs, pd.DataFrame([run_info])], ignore_index=True, sort=False
        ).fillna("")
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

    if source_registry_changed:
        all_sources.to_csv(sources_path, index=False)

    run_df = pd.DataFrame(runs)
    if runs_path.exists() and runs_path.stat().st_size:
        run_df = pd.concat([pd.read_csv(runs_path).fillna(""), run_df], ignore_index=True, sort=False)
    run_df.fillna("").tail(2000).to_csv(runs_path, index=False)
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
