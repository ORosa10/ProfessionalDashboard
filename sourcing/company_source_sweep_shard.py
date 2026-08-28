"""Run one shard of the A-company sourcing sweep.

The existing discovery adapters are reused, but execution is split into independent
shards so a slow or broken source cannot erase the results of the other companies.
Each source result is checkpointed after completion.
"""
from __future__ import annotations

import argparse
import signal
from pathlib import Path

import pandas as pd

from sourcing.company_source_sweep import (
    COVERAGE_COLUMNS,
    RUN_COLUMNS,
    _load_sources,
    discover_source,
)
from sourcing import big4_pilot as common

DEFAULT_TIMEOUT_SECONDS = 110


class SourceTimeout(Exception):
    pass


def _timeout_handler(signum: int, frame: object) -> None:
    raise SourceTimeout("source exceeded per-company timeout")


def _run_source(source: pd.Series, max_pages: int, timeout_seconds: int) -> tuple[list[dict], dict, str]:
    previous_handler = signal.signal(signal.SIGALRM, _timeout_handler)
    signal.alarm(timeout_seconds)
    try:
        found, run = discover_source(source, max_pages)
        errors = str(run.get("errors", "") or "")
        status = "success" if found else ("error" if errors else "zero_jobs")
        return found, run, status
    except SourceTimeout as exc:
        return [], {"errors": str(exc)}, "timeout"
    except Exception as exc:
        return [], {"errors": f"{type(exc).__name__}: {exc}"}, "error"
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, previous_handler)


def _write_checkpoint(out_dir: Path, jobs: list[dict], runs: list[dict], coverage: list[dict]) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(jobs).to_csv(out_dir / "jobs.csv", index=False)
    pd.DataFrame(runs).reindex(columns=RUN_COLUMNS, fill_value="").to_csv(out_dir / "runs.csv", index=False)
    pd.DataFrame(coverage).reindex(columns=COVERAGE_COLUMNS, fill_value="").to_csv(
        out_dir / "coverage.csv", index=False
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--shard-index", type=int, required=True)
    parser.add_argument("--shards", type=int, required=True)
    parser.add_argument("--max-pages", type=int, default=30)
    parser.add_argument("--timeout-seconds", type=int, default=DEFAULT_TIMEOUT_SECONDS)
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()

    if args.shard_index < 0 or args.shard_index >= args.shards:
        raise SystemExit("shard-index must be between 0 and shards-1")

    sources = []
    for source_file, frame in _load_sources():
        enabled = frame[frame["enabled"].astype(str).str.lower().eq("true")].copy()
        enabled["_source_file"] = source_file
        sources.append(enabled)
    all_sources = pd.concat(sources, ignore_index=True) if sources else pd.DataFrame()
    if not all_sources.empty:
        all_sources = all_sources.iloc[args.shard_index :: args.shards].copy()

    jobs: list[dict] = []
    runs: list[dict] = []
    coverage: list[dict] = []
    now = pd.Timestamp.now(tz="UTC").isoformat()

    for _, source in all_sources.iterrows():
        source_id = str(source.get("source_id", "")).strip()
        if not source_id:
            continue
        source_file = str(source.get("_source_file", ""))
        started = pd.Timestamp.now(tz="UTC").isoformat()
        found, run, status = _run_source(source, args.max_pages, args.timeout_seconds)
        errors = str(run.get("errors", "") or "")
        runs.append({
            "run_at": run.get("run_at", started),
            "source_id": source_id,
            "canonical_company_id": source.get("canonical_company_id", ""),
            "company": source.get("company", ""),
            "market": source.get("market", ""),
            "seed_url": source.get("seed_url", ""),
            "adapter": source.get("adapter", ""),
            "source_file": source_file,
            "source_status": status,
            "pages_checked": run.get("pages_checked", ""),
            "candidate_job_pages": run.get("candidate_job_pages", ""),
            "verified_jobs": len(found),
            "errors": errors,
        })
        jobs.extend(found)
        coverage.append({
            "checked_at": now,
            "canonical_company_id": source.get("canonical_company_id", ""),
            "company": source.get("company", ""),
            "rating": "",
            "source_file": source_file,
            "source_id": source_id,
            "adapter": source.get("adapter", ""),
            "career_url": source.get("seed_url", ""),
            "execution_status": status,
            "jobs_found": len(found),
            "last_run_at": started,
            "error": errors,
            "next_due": "",
        })
        _write_checkpoint(Path(args.output_dir), jobs, runs, coverage)

    _write_checkpoint(Path(args.output_dir), jobs, runs, coverage)
    print(
        f"Shard {args.shard_index}/{args.shards}: checked {len(coverage)} sources; "
        f"found {len(jobs)} roles; statuses="
        + str(pd.Series([r["source_status"] for r in runs]).value_counts().to_dict())
    )


if __name__ == "__main__":
    main()
