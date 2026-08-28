from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from sourcing.salary_research_free import _text, research_salary


ROOT = Path(__file__).resolve().parents[1]
POOL_PATH = ROOT / "data" / "j_eligible_pool.csv"
RESEARCH_PATH = ROOT / "data" / "j_salary_research.csv"
RESEARCH_COLUMNS = ["job_id", "salary_range", "salary_basis", "research_date"]


def _load(path, columns):
    if not path.exists() or path.stat().st_size == 0:
        return pd.DataFrame(columns=columns)
    try:
        return pd.read_csv(path).fillna("").reindex(columns=columns, fill_value="")
    except pd.errors.EmptyDataError:
        return pd.DataFrame(columns=columns)


def _research_row(row: pd.Series) -> pd.Series:
    # Keep the shared research engine independent from the J-specific schema.
    return pd.Series(
        {
            "title": _text(row.get("title")),
            "company": _text(row.get("company")),
            "location": _text(row.get("location")),
            "country": _text(row.get("market")) or _text(row.get("country_bucket")),
        }
    )


def run(max_items: int = 20, force: bool = False) -> int:
    pool = _load(POOL_PATH, list(pd.read_csv(POOL_PATH, nrows=0).columns)) if POOL_PATH.exists() else pd.DataFrame()
    research = _load(RESEARCH_PATH, RESEARCH_COLUMNS)
    if pool.empty or "job_id" not in pool.columns:
        print("No J pool to research")
        return 0

    existing = research.drop_duplicates("job_id", keep="last").set_index("job_id") if not research.empty else pd.DataFrame()
    if not force and not research.empty:
        known = set(existing.index.astype(str))
        pending = pool[~pool["job_id"].astype(str).isin(known)].copy()
    else:
        pending = pool.copy()
    pending = pending.head(max_items)
    if pending.empty:
        print("No pending J salary research")
        return 0

    records = {str(r["job_id"]): r.to_dict() for _, r in research.iterrows()}
    today = datetime.now(timezone.utc).date().isoformat()
    processed = 0
    for _, row in pending.iterrows():
        job_id = _text(row.get("job_id"))
        try:
            salary_range, basis, status = research_salary(_research_row(row))
        except Exception as exc:
            salary_range = "Not found in public sources"
            basis = f"Salary research failed: {type(exc).__name__}: {exc}"
            status = "failed"

        # Do not expose an internal review label as if it were a salary figure.
        if status != "done":
            salary_range = "Not found in public sources"
        records[job_id] = {
            "job_id": job_id,
            "salary_range": salary_range,
            "salary_basis": basis,
            "research_date": today,
        }
        processed += 1
        print(f"SALARY {job_id}: {salary_range} ({status})")

    pd.DataFrame(records.values()).reindex(columns=RESEARCH_COLUMNS).to_csv(RESEARCH_PATH, index=False)
    return processed


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-items", type=int, default=20)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    print(f"Processed {run(args.max_items, args.force)} J salary record(s)")


if __name__ == "__main__":
    main()

