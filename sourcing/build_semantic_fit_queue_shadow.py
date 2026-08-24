"""Build a non-production C review queue from the shadow G candidate pool.

The script deliberately does NOT apply language, geography/employability, salary,
link-health or attainability rules. Those belong to actionability/H, not C. The
only operational status filter here is that an explicitly non-open vacancy is
not worth sending for new semantic review.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from sourcing.build_semantic_fit_queue import (
    _company_maps,
    _load_company_universe,
    _norm,
    _role_family,
    _target_slots,
)


QUEUE_COLUMNS = [
    "opportunity_id", "candidate_id", "title", "company", "canonical_company_id",
    "company_category", "company_rating", "market", "country_bucket", "location",
    "job_url", "date_posted", "last_seen_at", "source_id", "source_streams",
    "source_count", "calibration_score", "calibration_note", "matched_terms",
    "role_family", "company_context", "description_for_fit",
]


def _read(path: Path) -> pd.DataFrame:
    if not path.exists() or path.stat().st_size == 0:
        return pd.DataFrame()
    try:
        return pd.read_csv(path).fillna("")
    except (pd.errors.EmptyDataError, pd.errors.ParserError):
        return pd.DataFrame()


def build_shadow_queue(
    candidates: pd.DataFrame,
    semantic: pd.DataFrame,
    history: pd.DataFrame,
    limit: int = 160,
) -> pd.DataFrame:
    if candidates.empty:
        return pd.DataFrame(columns=QUEUE_COLUMNS)

    jobs = candidates.fillna("").copy()
    for col in [
        "candidate_id", "job_id", "title", "company", "canonical_company_id",
        "market", "country_bucket", "location", "job_url", "date_posted",
        "last_seen_at", "source_id", "source_streams", "source_count",
        "calibration_score", "calibration_note", "matched_terms", "description",
        "description_en", "status",
    ]:
        if col not in jobs.columns:
            jobs[col] = ""

    # Explicitly closed/blocked source rows should not consume new C review time.
    # Blank/unknown status is retained in shadow mode rather than silently lost.
    jobs = jobs[~jobs["status"].astype(str).str.lower().isin({"closed", "expired", "removed"})].copy()
    jobs["opportunity_id"] = jobs.apply(
        lambda row: str(row.get("job_id", "")).strip() or str(row.get("candidate_id", "")).strip(),
        axis=1,
    )
    jobs = jobs[jobs["opportunity_id"].ne("")].drop_duplicates("opportunity_id", keep="first")

    already: set[str] = set()
    if not semantic.empty and "opportunity_id" in semantic.columns:
        already.update(str(x).strip() for x in semantic["opportunity_id"] if str(x).strip())
    if not history.empty and {"opportunity_id", "action"}.issubset(history.columns):
        done = history[history["action"].astype(str).isin(["Apply", "Skip", "Pass"])]
        already.update(str(x).strip() for x in done["opportunity_id"] if str(x).strip())
    jobs = jobs[~jobs["opportunity_id"].isin(already)].copy()
    if jobs.empty:
        return pd.DataFrame(columns=QUEUE_COLUMNS)

    universe = _load_company_universe()
    exact, aliases = _company_maps(universe)

    def lookup(company: object) -> dict:
        key = _norm(company)
        return exact.get(key) or aliases.get(key) or {}

    found = jobs["company"].map(lookup)
    mapped_id = pd.Series([str(x.get("canonical_company_id", "")) for x in found], index=jobs.index)
    jobs["canonical_company_id"] = jobs["canonical_company_id"].where(jobs["canonical_company_id"].ne(""), mapped_id)
    jobs["company_category"] = [str(x.get("company_category", "")) for x in found]
    jobs["company_rating"] = [str(x.get("rating", "") or "Unrated") for x in found]
    jobs["company_context"] = [
        " · ".join(part for part in [str(x.get("archetype", "")), str(x.get("why_test", ""))] if part)
        for x in found
    ]
    jobs["description_for_fit"] = jobs.apply(
        lambda row: str(row.get("description_en", "") or row.get("description", ""))[:5000],
        axis=1,
    )
    jobs["role_family"] = jobs.apply(
        lambda row: _role_family(row.get("title", ""), row.get("description_for_fit", "")),
        axis=1,
    )
    jobs["calibration_score"] = pd.to_numeric(jobs["calibration_score"], errors="coerce").fillna(0)
    jobs["_posted"] = pd.to_datetime(jobs["date_posted"], errors="coerce", utc=True)
    jobs["_seen"] = pd.to_datetime(jobs["last_seen_at"], errors="coerce", utc=True)
    jobs = jobs.sort_values(
        ["calibration_score", "_posted", "_seen"],
        ascending=[False, False, False],
        na_position="last",
    )

    # Country allocation is only C-review workload balancing. It does not alter
    # semantic judgement and never lowers the pool below the available quality.
    targets = _target_slots(limit)
    chosen: list[int] = []
    for country, target in targets.items():
        if target <= 0:
            continue
        subset = jobs[jobs["country_bucket"].astype(str).eq(country)]
        for idx in subset.index[:target]:
            if idx not in chosen:
                chosen.append(idx)

    if len(chosen) < min(limit, len(jobs)):
        for idx in jobs.index:
            if idx not in chosen:
                chosen.append(idx)
            if len(chosen) >= limit:
                break

    queue = jobs.loc[chosen[:limit]].copy()
    return queue.reindex(columns=QUEUE_COLUMNS, fill_value="").reset_index(drop=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a non-production C review queue from shadow G")
    parser.add_argument("--candidates", required=True)
    parser.add_argument("--semantic", required=True)
    parser.add_argument("--history", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--limit", type=int, default=160)
    args = parser.parse_args()

    queue = build_shadow_queue(
        _read(Path(args.candidates)),
        _read(Path(args.semantic)),
        _read(Path(args.history)),
        args.limit,
    )
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    queue.to_csv(out, index=False)
    print(f"shadow C queue wrote {len(queue)} pending roles to {out}")


if __name__ == "__main__":
    main()
