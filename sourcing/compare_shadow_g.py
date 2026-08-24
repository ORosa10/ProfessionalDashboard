"""Read-only comparison helpers for the shadow G migration.

This module never feeds production. It answers two migration-safety questions:
1. Which roles currently visible in the curated/live J reference are absent from
   the shadow G source snapshot?
2. Does raw G supply cover the configured country targets before semantic and
   actionability filters are even applied?

A raw-country deficit is therefore a definite sourcing-coverage warning. Raw
supply above target is not proof that J can fill the quota; C/actionability still
need to be applied later.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from sourcing.aggregate_candidates_shadow import _normalise_url


REFERENCE_COLUMNS = [
    "job_id", "company", "title", "market", "location", "semantic_fit",
    "curated_rank", "job_url", "found_in_shadow", "shadow_candidate_id",
    "shadow_source_streams",
]

COUNTRY_COLUMNS = [
    "country", "configured_target", "raw_shadow_candidates", "raw_gap",
    "raw_supply_status",
]


def _read_csv(path: Path) -> pd.DataFrame:
    if not path.exists() or path.stat().st_size == 0:
        return pd.DataFrame()
    try:
        return pd.read_csv(path).fillna("")
    except (pd.errors.EmptyDataError, pd.errors.ParserError):
        return pd.DataFrame()


def compare_reference(shadow: pd.DataFrame, reference: pd.DataFrame) -> pd.DataFrame:
    if reference.empty:
        return pd.DataFrame(columns=REFERENCE_COLUMNS)

    shadow = shadow.fillna("").copy()
    reference = reference.fillna("").copy()
    for col in ["candidate_id", "job_id", "job_url", "source_streams"]:
        if col not in shadow.columns:
            shadow[col] = ""
    for col in REFERENCE_COLUMNS:
        if col not in reference.columns:
            reference[col] = ""

    by_job_id = {
        str(row["job_id"]).strip(): row
        for _, row in shadow.iterrows()
        if str(row.get("job_id", "")).strip()
    }
    by_url = {
        _normalise_url(row.get("job_url", "")): row
        for _, row in shadow.iterrows()
        if _normalise_url(row.get("job_url", ""))
    }

    rows = []
    for _, ref in reference.iterrows():
        match = None
        job_id = str(ref.get("job_id", "")).strip()
        url = _normalise_url(ref.get("job_url", ""))
        if job_id and job_id in by_job_id:
            match = by_job_id[job_id]
        elif url and url in by_url:
            match = by_url[url]

        rec = {col: str(ref.get(col, "")) for col in REFERENCE_COLUMNS}
        rec["found_in_shadow"] = bool(match is not None)
        rec["shadow_candidate_id"] = str(match.get("candidate_id", "")) if match is not None else ""
        rec["shadow_source_streams"] = str(match.get("source_streams", "")) if match is not None else ""
        rows.append(rec)

    out = pd.DataFrame(rows).reindex(columns=REFERENCE_COLUMNS, fill_value="")
    if "curated_rank" in out.columns:
        out["_rank"] = pd.to_numeric(out["curated_rank"], errors="coerce").fillna(9999)
        out = out.sort_values(["found_in_shadow", "_rank"], ascending=[True, True]).drop(columns="_rank")
    return out.reset_index(drop=True)


def country_supply(shadow: pd.DataFrame, targets: dict[str, int]) -> pd.DataFrame:
    counts = (
        shadow.get("country_bucket", pd.Series(dtype=object))
        .astype(str)
        .replace("", "Other / Unresolved")
        .value_counts()
        .to_dict()
    ) if not shadow.empty else {}

    rows = []
    for country, target in targets.items():
        count = int(counts.get(country, 0))
        gap = max(0, int(target) - count)
        rows.append({
            "country": country,
            "configured_target": int(target),
            "raw_shadow_candidates": count,
            "raw_gap": gap,
            "raw_supply_status": "OK" if gap == 0 else "RAW DEFICIT",
        })
    return pd.DataFrame(rows).reindex(columns=COUNTRY_COLUMNS, fill_value="")


def _load_targets(path: Path) -> dict[str, int]:
    if not path.exists() or path.stat().st_size == 0:
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return {}
    return {
        str(country): int(target)
        for country, target in payload.get("top20_targets", {}).items()
        if int(target) > 0
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Compare shadow G with current live references without changing production")
    parser.add_argument("--shadow", required=True)
    parser.add_argument("--live-reference", required=True)
    parser.add_argument("--country-targets", required=True)
    parser.add_argument("--reference-out", required=True)
    parser.add_argument("--country-out", required=True)
    args = parser.parse_args()

    shadow = _read_csv(Path(args.shadow))
    reference = _read_csv(Path(args.live_reference))
    reference_report = compare_reference(shadow, reference)
    country_report = country_supply(shadow, _load_targets(Path(args.country_targets)))

    reference_path = Path(args.reference_out)
    country_path = Path(args.country_out)
    reference_path.parent.mkdir(parents=True, exist_ok=True)
    country_path.parent.mkdir(parents=True, exist_ok=True)
    reference_report.to_csv(reference_path, index=False)
    country_report.to_csv(country_path, index=False)

    found = int(reference_report["found_in_shadow"].astype(bool).sum()) if not reference_report.empty else 0
    print(f"live reference coverage: {found}/{len(reference_report)} roles found in shadow G")
    if not country_report.empty:
        deficits = country_report[country_report["raw_gap"].gt(0)]
        print(f"raw country deficits: {len(deficits)}/{len(country_report)} configured countries")


if __name__ == "__main__":
    main()
