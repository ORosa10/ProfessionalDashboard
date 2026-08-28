"""Merge independent A-company sourcing shard checkpoints."""
from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
JOBS_PATH = DATA / "jobs_company_staging.csv"
RUNS_PATH = DATA / "source_runs_company_staging.csv"
COVERAGE_PATH = DATA / "company_source_coverage.csv"


def _read_many(root: Path, filename: str) -> pd.DataFrame:
    frames = []
    for path in sorted(root.glob(f"*/{filename}")):
        if path.exists() and path.stat().st_size:
            try:
                frames.append(pd.read_csv(path).fillna(""))
            except (pd.errors.EmptyDataError, pd.errors.ParserError):
                continue
    return pd.concat(frames, ignore_index=True, sort=False) if frames else pd.DataFrame()


def _read_existing(path: Path) -> pd.DataFrame:
    if not path.exists() or not path.stat().st_size:
        return pd.DataFrame()
    try:
        return pd.read_csv(path).fillna("")
    except (pd.errors.EmptyDataError, pd.errors.ParserError):
        return pd.DataFrame()


def _merge_jobs(new: pd.DataFrame, old: pd.DataFrame) -> pd.DataFrame:
    combined = pd.concat([old, new], ignore_index=True, sort=False)
    if combined.empty:
        return combined
    if "job_id" in combined.columns:
        combined = combined.drop_duplicates("job_id", keep="last")
    return combined


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--shards-dir", required=True)
    args = parser.parse_args()

    shards = Path(args.shards_dir)
    jobs = _merge_jobs(_read_many(shards, "jobs.csv"), _read_existing(JOBS_PATH))
    runs = _read_many(shards, "runs.csv")
    old_runs = _read_existing(RUNS_PATH)
    runs = pd.concat([old_runs, runs], ignore_index=True, sort=False).tail(5000)
    coverage = _read_many(shards, "coverage.csv")

    DATA.mkdir(parents=True, exist_ok=True)
    jobs.to_csv(JOBS_PATH, index=False)
    runs.to_csv(RUNS_PATH, index=False)
    coverage.to_csv(COVERAGE_PATH, index=False)

    statuses = coverage["execution_status"].value_counts().to_dict() if not coverage.empty else {}
    print(
        f"Merged {len(coverage)} company results; stored {len(jobs)} roles; "
        f"statuses={statuses}"
    )
    if coverage.empty:
        raise SystemExit("No shard checkpoints were produced")
    if coverage["source_id"].astype(str).str.strip().eq("").any():
        raise SystemExit("Coverage contains a row without source_id")


if __name__ == "__main__":
    main()
