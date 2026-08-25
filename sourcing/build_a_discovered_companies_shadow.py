"""Build read-only A employer suggestions from the unified G candidate pool.

This is deliberately conservative:
- it never writes company ratings;
- it never overwrites a known company;
- it groups repeated employer sightings from G into one suggestion;
- the output is context for A, not a role-fit or Apply decision.
"""
from __future__ import annotations

import argparse
import re
from pathlib import Path

import pandas as pd

from sourcing.build_semantic_fit_queue import _load_company_universe, _norm

OUTPUT_COLUMNS = [
    "suggested_company_id", "company", "role_count", "countries", "source_streams",
    "sample_titles", "first_seen_at", "last_seen_at", "suggested_rating", "evidence_source",
]


def _read(path: Path) -> pd.DataFrame:
    if not path.exists() or path.stat().st_size == 0:
        return pd.DataFrame()
    try:
        return pd.read_csv(path).fillna("")
    except (pd.errors.EmptyDataError, pd.errors.ParserError):
        return pd.DataFrame()


def _slug(value: object) -> str:
    text = re.sub(r"[^a-z0-9]+", "-", str(value or "").lower()).strip("-")
    return text or "discovered-company"


def build_a_suggestions(candidates: pd.DataFrame, universe: pd.DataFrame | None = None) -> pd.DataFrame:
    if candidates.empty:
        return pd.DataFrame(columns=OUTPUT_COLUMNS)

    known = _load_company_universe() if universe is None else universe.fillna("")
    known_names: set[str] = set()
    if not known.empty:
        for _, row in known.iterrows():
            for value in [row.get("company", ""), *str(row.get("aliases_entities", "")).split(";")]:
                key = _norm(value)
                if key:
                    known_names.add(key)

    jobs = candidates.fillna("").copy()
    for col in ["company", "title", "country_bucket", "market", "source_streams", "date_posted", "last_seen_at"]:
        if col not in jobs.columns:
            jobs[col] = ""
    jobs = jobs[jobs["company"].astype(str).str.strip().ne("")].copy()
    jobs["_company_key"] = jobs["company"].map(_norm)
    jobs = jobs[~jobs["_company_key"].isin(known_names)].copy()
    if jobs.empty:
        return pd.DataFrame(columns=OUTPUT_COLUMNS)

    rows: list[dict[str, object]] = []
    for _, group in jobs.groupby("_company_key", sort=False):
        company = str(group.iloc[0]["company"]).strip()
        countries = sorted({str(x).strip() for x in group["country_bucket"] if str(x).strip()})
        if not countries:
            countries = sorted({str(x).strip() for x in group["market"] if str(x).strip()})
        streams: set[str] = set()
        for value in group["source_streams"]:
            streams.update(x.strip() for x in str(value).split(";") if x.strip())
        titles = []
        for value in group["title"]:
            title = str(value).strip()
            if title and title not in titles:
                titles.append(title)
            if len(titles) >= 4:
                break
        posted = pd.to_datetime(group["date_posted"], errors="coerce", utc=True)
        seen = pd.to_datetime(group["last_seen_at"], errors="coerce", utc=True)
        first = posted.min()
        last = seen.max()
        rows.append({
            "suggested_company_id": _slug(company),
            "company": company,
            "role_count": int(len(group)),
            "countries": "; ".join(countries),
            "source_streams": "; ".join(sorted(streams)),
            "sample_titles": " | ".join(titles),
            "first_seen_at": "" if pd.isna(first) else first.isoformat(),
            "last_seen_at": "" if pd.isna(last) else last.isoformat(),
            "suggested_rating": "Unrated",
            "evidence_source": "G discovered employer",
        })

    out = pd.DataFrame(rows).reindex(columns=OUTPUT_COLUMNS, fill_value="")
    out = out.sort_values(["role_count", "last_seen_at", "company"], ascending=[False, False, True])
    return out.reset_index(drop=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build shadow A employer suggestions from G")
    parser.add_argument("--candidates", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    result = build_a_suggestions(_read(Path(args.candidates)))
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    result.to_csv(out, index=False)
    print(f"shadow A: {len(result)} discovered employer suggestions")


if __name__ == "__main__":
    main()
