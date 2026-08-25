"""Read-only audit of sector sourcing before/after title/location filtering.

This tool never writes a live staging file. It is used to answer two migration
questions:
1. why a source can report verified job pages but still produce zero stored roles;
2. whether current `adapter=llm` holdings pages have any useful deterministic
   `generic` discovery path before considering an LLM dependency.

The second mode explicitly replaces `llm` with `generic` in-memory only. It never
calls Gemini and never changes job_sources_*.csv.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from sourcing import sector_pilot
from sourcing.pe_pilot import target_location


JOB_COLUMNS = [
    "source_id", "company", "configured_adapter", "effective_adapter", "title",
    "location", "job_url", "title_relevant", "location_target", "kept",
    "rejection_reason",
]
RUN_COLUMNS = [
    "source_id", "company", "configured_adapter", "effective_adapter",
    "pages_checked", "candidate_job_pages", "verified_jobs_before_sector_filter",
    "kept_after_sector_filter", "errors",
]


def classify_job(job: dict) -> dict[str, object]:
    title = str(job.get("title", "") or "")
    location = str(job.get("location", "") or "")
    title_ok = bool(sector_pilot.relevant_title(title))
    location_ok = bool(target_location(location))
    reasons: list[str] = []
    if not title_ok:
        reasons.append("title_filter")
    if not location_ok:
        reasons.append("location_filter")
    return {
        "title_relevant": title_ok,
        "location_target": location_ok,
        "kept": title_ok and location_ok,
        "rejection_reason": "; ".join(reasons),
    }


def audit_sources(
    sources: pd.DataFrame,
    *,
    max_pages: int = 12,
    source_ids: set[str] | None = None,
    force_generic_for_llm: bool = False,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    if sources.empty:
        return pd.DataFrame(columns=JOB_COLUMNS), pd.DataFrame(columns=RUN_COLUMNS)
    frame = sources.fillna("").copy()
    if "enabled" in frame.columns:
        frame = frame[frame["enabled"].astype(str).str.lower().eq("true")]
    if source_ids:
        frame = frame[frame["source_id"].astype(str).isin(source_ids)]

    jobs_out: list[dict[str, object]] = []
    runs_out: list[dict[str, object]] = []
    for _, original in frame.iterrows():
        source = original.copy()
        configured = str(source.get("adapter", "generic") or "generic").lower()
        effective = configured
        if force_generic_for_llm and configured == "llm":
            source["adapter"] = "generic"
            effective = "generic_shadow_replacement"

        try:
            jobs, run = sector_pilot.discover_source(source, max_pages=max_pages)
        except Exception as exc:
            jobs = []
            run = {
                "pages_checked": 0,
                "candidate_job_pages": 0,
                "verified_jobs": 0,
                "errors": f"audit exception: {type(exc).__name__}: {exc}",
            }

        kept_count = 0
        for job in jobs:
            classified = classify_job(job)
            kept_count += int(bool(classified["kept"]))
            jobs_out.append({
                "source_id": str(original.get("source_id", "")),
                "company": str(original.get("company", "")),
                "configured_adapter": configured,
                "effective_adapter": effective,
                "title": str(job.get("title", "")),
                "location": str(job.get("location", "")),
                "job_url": str(job.get("job_url", "")),
                **classified,
            })
        runs_out.append({
            "source_id": str(original.get("source_id", "")),
            "company": str(original.get("company", "")),
            "configured_adapter": configured,
            "effective_adapter": effective,
            "pages_checked": int(run.get("pages_checked", 0) or 0),
            "candidate_job_pages": int(run.get("candidate_job_pages", 0) or 0),
            "verified_jobs_before_sector_filter": int(run.get("verified_jobs", len(jobs)) or 0),
            "kept_after_sector_filter": kept_count,
            "errors": str(run.get("errors", "") or ""),
        })

    return (
        pd.DataFrame(jobs_out).reindex(columns=JOB_COLUMNS, fill_value=""),
        pd.DataFrame(runs_out).reindex(columns=RUN_COLUMNS, fill_value=""),
    )


def _read(path: Path) -> pd.DataFrame:
    if not path.exists() or path.stat().st_size == 0:
        return pd.DataFrame()
    return pd.read_csv(path).fillna("")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sources", required=True)
    parser.add_argument("--source-id", action="append", default=[])
    parser.add_argument("--max-pages", type=int, default=12)
    parser.add_argument("--force-generic-for-llm", action="store_true")
    parser.add_argument("--jobs-out", required=True)
    parser.add_argument("--runs-out", required=True)
    args = parser.parse_args()

    jobs, runs = audit_sources(
        _read(Path(args.sources)),
        max_pages=args.max_pages,
        source_ids=set(args.source_id),
        force_generic_for_llm=args.force_generic_for_llm,
    )
    jobs_path = Path(args.jobs_out)
    runs_path = Path(args.runs_out)
    jobs_path.parent.mkdir(parents=True, exist_ok=True)
    runs_path.parent.mkdir(parents=True, exist_ok=True)
    jobs.to_csv(jobs_path, index=False)
    runs.to_csv(runs_path, index=False)
    print(runs.to_string(index=False) if len(runs) else "No audited sources")
    if len(jobs):
        print("\nFilter reasons:")
        print(jobs["rejection_reason"].replace("", "kept").value_counts().to_string())


if __name__ == "__main__":
    main()
