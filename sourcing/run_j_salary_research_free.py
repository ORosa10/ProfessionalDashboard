from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from sourcing.salary_research_free import (
    COUNTRY_CURRENCY,
    ROUND_TO,
    _expected_currency,
    _format_amount,
    _round,
    _text,
    research_salary,
)


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


def _modelled_salary(row: pd.Series) -> tuple[str, str]:
    """Always produce a usable market expectation when public evidence is absent."""
    title = _text(row.get("title")).lower()
    text = f"{title} {_text(row.get('role_family'))} {_text(row.get('description_en'))}".lower()
    country = _text(row.get("market")) or _text(row.get("country_bucket"))
    currency = _expected_currency(country, _text(row.get("location")))
    if not currency:
        currency = COUNTRY_CURRENCY.get(country.lower(), "EUR")

    bands = {
        "EUR": (55000, 80000), "CHF": (90000, 125000), "GBP": (55000, 80000),
        "SEK": (550000, 750000), "DKK": (550000, 800000), "CZK": (900000, 1350000),
    }
    low, high = bands.get(currency, bands["EUR"])

    if any(x in text for x in ["portfolio manager", "trader", "head of", "director", "vp ", "vice president"]):
        low, high = int(low * 1.65), int(high * 1.85)
    elif any(x in text for x in ["manager", "lead", "principal", "senior", "5+ years", "10 years"]):
        low, high = int(low * 1.35), int(high * 1.55)
    elif any(x in text for x in ["junior", "analyst", "specialist", "consultant"]):
        low, high = int(low * 0.90), int(high * 1.05)

    step = ROUND_TO.get(currency, 5000)
    low_i, high_i = _round(low, currency), _round(high, currency)
    if high_i <= low_i:
        high_i = low_i + step * 2
    formatted = f"{_format_amount(low_i, currency)}-{_format_amount(high_i, currency).replace(currency + ' ', '')} gross/year (modelled)"
    basis = (
        f"MODELLED MARKET ESTIMATE: no reliable role-specific public salary figure was found. "
        f"Range inferred from country ({country}), role family/title and apparent seniority; "
        f"use as an initial expectation and validate in recruiter screening."
    )
    return formatted, basis


def run(max_items: int = 20, force: bool = False) -> int:
    pool = _load(POOL_PATH, list(pd.read_csv(POOL_PATH, nrows=0).columns)) if POOL_PATH.exists() else pd.DataFrame()
    research = _load(RESEARCH_PATH, RESEARCH_COLUMNS)
    if pool.empty or "job_id" not in pool.columns:
        print("No J pool to research")
        return 0

    existing = research.drop_duplicates("job_id", keep="last").set_index("job_id") if not research.empty else pd.DataFrame()
    if not force and not research.empty:
        known = set(existing.index.astype(str))
        # Re-run earlier records that were incorrectly flattened to the generic
        # no-result label by a low-confidence run. Keep curated numeric ranges.
        retry_ids = {
            str(job_id)
            for job_id, record in existing.iterrows()
            if _text(record.get("salary_range")).lower().startswith("not found")
        }
        pending = pool[
            (~pool["job_id"].astype(str).isin(known))
            | pool["job_id"].astype(str).isin(retry_ids)
        ].copy()
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

        # Low-confidence runs still contain a usable numeric range. Only fall
        # back to a modelled expectation when the engine genuinely found no
        # salary figures at all; J should never be left without an expectation.
        if salary_range == "Needs ChatGPT review":
            salary_range, basis = _modelled_salary(row)
            status = "modelled"
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
