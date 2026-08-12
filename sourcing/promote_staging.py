from __future__ import annotations

from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
LIVE_JOBS = ROOT / "data" / "jobs.csv"
STAGING_JOBS = ROOT / "data" / "jobs_staging.csv"
LIVE_RUNS = ROOT / "data" / "source_runs.csv"
STAGING_RUNS = ROOT / "data" / "source_runs_staging.csv"


def main() -> None:
    if not STAGING_JOBS.exists():
        raise SystemExit("No staging job snapshot exists.")
    jobs = pd.read_csv(STAGING_JOBS).fillna("")
    required = {"job_id", "company", "title", "job_url", "source_id"}
    missing = required.difference(jobs.columns)
    if missing:
        raise SystemExit(f"Staging snapshot is missing columns: {sorted(missing)}")
    if jobs["job_id"].duplicated().any():
        raise SystemExit("Staging snapshot contains duplicate job IDs.")
    if jobs["job_url"].eq("").any():
        raise SystemExit("Staging snapshot contains empty job URLs.")
    jobs.to_csv(LIVE_JOBS, index=False)

    if STAGING_RUNS.exists():
        pd.read_csv(STAGING_RUNS).fillna("").tail(2000).to_csv(LIVE_RUNS, index=False)
    print(f"Promoted {len(jobs)} verified jobs from staging to live.")


if __name__ == "__main__":
    main()
