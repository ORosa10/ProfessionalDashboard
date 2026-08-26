"""Build A company suggestions from manual B applications.

B is application intake. Discovering a company through B should make that
employer visible to A, but must never assign an A/B/C/Exclude rating.
"""
from __future__ import annotations

import argparse
import re
from pathlib import Path

import pandas as pd

from sourcing.g_data_quality import invalid_company_name, invalid_job_title

ROOT = Path(__file__).resolve().parents[1]
SUBMISSIONS = ROOT / "data" / "user_submitted_opportunities.csv"
RESEARCH = ROOT / "data" / "user_submitted_opportunity_research.csv"
OUT = ROOT / "data" / "a_b_discovered_companies.csv"

OUT_COLUMNS = [
    "suggested_company_id", "company", "role_count", "countries", "source_streams",
    "sample_titles", "first_seen_at", "last_seen_at", "suggested_rating", "evidence_source",
]


def _clean(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _slug(value: object) -> str:
    text = re.sub(r"[^a-z0-9]+", "-", _clean(value).lower()).strip("-")
    return text or "b-discovered-company"


def _overlay_research(submissions: pd.DataFrame, research: pd.DataFrame) -> pd.DataFrame:
    out = submissions.fillna("").copy()
    if out.empty or research.empty or "submission_id" not in out.columns or "submission_id" not in research.columns:
        return out
    latest = research.fillna("").drop_duplicates("submission_id", keep="last").set_index("submission_id")
    for col in ["company", "canonical_company_id", "country", "title", "location"]:
        if col not in latest.columns:
            continue
        if col not in out.columns:
            out[col] = ""
        mapped = out["submission_id"].map(latest[col]).fillna("")
        out[col] = mapped.where(mapped.astype(str).str.strip().ne(""), out[col].fillna(""))
    return out


def build_suggestions(submissions: pd.DataFrame, research: pd.DataFrame | None = None) -> pd.DataFrame:
    if submissions.empty:
        return pd.DataFrame(columns=OUT_COLUMNS)
    frame = _overlay_research(submissions, research if research is not None else pd.DataFrame())
    for col in ["submission_id", "submitted_at", "company", "canonical_company_id", "country", "title"]:
        if col not in frame.columns:
            frame[col] = ""
    frame = frame.fillna("")
    frame["company"] = frame["company"].map(_clean)
    frame["title"] = frame["title"].map(_clean)
    frame = frame[frame["company"].ne("") & ~frame["company"].map(invalid_company_name)].copy()
    if frame.empty:
        return pd.DataFrame(columns=OUT_COLUMNS)
    frame["suggested_company_id"] = frame.apply(
        lambda row: _clean(row.get("canonical_company_id", "")) or _slug(row.get("company", "")), axis=1
    )
    rows: list[dict[str, object]] = []
    for company_id, group in frame.groupby("suggested_company_id", sort=False):
        group = group.copy()
        titles = []
        for value in group["title"]:
            title = _clean(value)
            if title and not invalid_job_title(title) and title not in titles:
                titles.append(title)
        if not titles:
            titles = ["Manual application"]
        countries = []
        for value in group["country"]:
            country = _clean(value)
            if country and country not in countries:
                countries.append(country)
        timestamps = [_clean(x) for x in group["submitted_at"] if _clean(x)]
        rows.append({
            "suggested_company_id": company_id,
            "company": _clean(group.iloc[-1]["company"]),
            "role_count": int(group["submission_id"].astype(str).nunique()),
            "countries": "; ".join(countries),
            "source_streams": "B",
            "sample_titles": " | ".join(titles[:5]),
            "first_seen_at": min(timestamps) if timestamps else "",
            "last_seen_at": max(timestamps) if timestamps else "",
            "suggested_rating": "Unrated",
            "evidence_source": "B manual application",
        })
    return pd.DataFrame(rows).reindex(columns=OUT_COLUMNS, fill_value="").sort_values(
        ["last_seen_at", "company"], ascending=[False, True]
    ).reset_index(drop=True)


def _read_csv(path: Path) -> pd.DataFrame:
    if not path.exists() or not path.stat().st_size:
        return pd.DataFrame()
    try:
        return pd.read_csv(path).fillna("")
    except (pd.errors.EmptyDataError, pd.errors.ParserError):
        return pd.DataFrame()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--submissions", default=str(SUBMISSIONS))
    parser.add_argument("--research", default=str(RESEARCH))
    parser.add_argument("--out", default=str(OUT))
    args = parser.parse_args()
    result = build_suggestions(_read_csv(Path(args.submissions)), _read_csv(Path(args.research)))
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    result.to_csv(out, index=False)
    print(f"wrote {len(result)} B-discovered company suggestions to {out}")


if __name__ == "__main__":
    main()
