"""Synchronise explicit A company ratings into G company-career source registries.

A owns company preference. G owns sourcing. This module only turns explicit
A/B/C/Exclude decisions into operational source settings; it never infers a
company rating or changes company-category semantics.

Rules:
- A/B/C => source enabled with cadence 7/14/30 days.
- Exclude or Unrated => existing managed source disabled; never create a source.
- Existing source rows keep their calibrated adapter and seed URL.
- Missing source rows are created from the Company's career_url with adapter=generic.
- Big Four stays in its dedicated multi-market registry and is never duplicated
  into the generic company-source registries.
- If an explicitly active company has no usable career URL and no existing source,
  record missing_career_url rather than silently failing.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
RATINGS_PATH = DATA / "company_ratings.csv"
STATUS_PATH = DATA / "a_to_g_company_source_status.csv"

SOURCE_COLUMNS = [
    "source_id", "canonical_company_id", "company", "market",
    "priority_locations", "seed_url", "adapter", "cadence_days", "enabled",
]
STATUS_COLUMNS = [
    "synced_at", "canonical_company_id", "company", "rating", "source_files",
    "source_ids", "status", "cadence_days", "career_url", "note",
]

CADENCE_DAYS = {"A": 7, "B": 14, "C": 30}

CATEGORY_TO_SOURCE = {
    "Consulting": "job_sources_consulting.csv",
    "Corporate": "job_sources_corporate.csv",
    "Banking & Financial Services": "job_sources_financial_services.csv",
    "Holding & Conglomerate": "job_sources_holdings.csv",
    "Private Equity & Private Markets": "job_sources_pe.csv",
    "Private Equity & Asset Management": "job_sources_pe.csv",
    "Investment Banking": "job_sources_investment_banking.csv",
    "Public Markets & Asset Management": "job_sources_public_markets.csv",
    "Specialist & Boutique Funds": "job_sources_specialist_funds.csv",
}

MANAGED_SOURCE_FILES = [
    "job_sources_consulting.csv",
    "job_sources_pe.csv",
    "job_sources_corporate.csv",
    "job_sources_financial_services.csv",
    "job_sources_holdings.csv",
    "job_sources_investment_banking.csv",
    "job_sources_public_markets.csv",
    "job_sources_specialist_funds.csv",
]
DEDICATED_BIG4_SOURCE = "job_sources_pilot.csv"


def _clean(value: object) -> str:
    return str(value or "").strip()


def _load_universe(data_dir: Path) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    base = data_dir / "company_universe.csv"
    if base.exists() and base.stat().st_size:
        frames.append(pd.read_csv(base).fillna(""))
    for path in sorted(data_dir.glob("company_universe_wave*.csv")):
        if path.exists() and path.stat().st_size:
            frames.append(pd.read_csv(path).fillna(""))
    if not frames:
        return pd.DataFrame()
    universe = pd.concat(frames, ignore_index=True, sort=False).fillna("")
    for col in [
        "canonical_company_id", "company", "region", "locations", "career_url",
        "company_category",
    ]:
        if col not in universe.columns:
            universe[col] = ""
    return universe.drop_duplicates("canonical_company_id", keep="last").fillna("")


def _load_source(path: Path) -> pd.DataFrame:
    if not path.exists() or not path.stat().st_size:
        return pd.DataFrame(columns=SOURCE_COLUMNS)
    frame = pd.read_csv(path).fillna("")
    missing = [col for col in SOURCE_COLUMNS if col not in frame.columns]
    if missing:
        raise ValueError(f"{path.name} missing source columns: {', '.join(missing)}")
    return frame.reindex(columns=SOURCE_COLUMNS, fill_value="")


def _dedicated_big4_ids(data_dir: Path) -> set[str]:
    path = data_dir / DEDICATED_BIG4_SOURCE
    if not path.exists() or not path.stat().st_size:
        return set()
    frame = pd.read_csv(path).fillna("")
    if "canonical_company_id" not in frame.columns:
        return set()
    return {str(x).strip() for x in frame["canonical_company_id"] if str(x).strip()}


def _target_source(category: str) -> str:
    # Newly discovered companies may not yet have a semantic company category.
    # Use the corporate file only as an operational generic-company bucket; this
    # does NOT change the A company_category and C still judges the role itself.
    return CATEGORY_TO_SOURCE.get(category, "job_sources_corporate.csv")


def _existing_locations(sources: dict[str, pd.DataFrame], company_id: str) -> list[tuple[str, int]]:
    hits: list[tuple[str, int]] = []
    for filename, frame in sources.items():
        if frame.empty:
            continue
        for idx in frame.index[frame["canonical_company_id"].astype(str).eq(company_id)]:
            hits.append((filename, int(idx)))
    return hits


def _remove_generic_duplicates(sources: dict[str, pd.DataFrame], company_id: str) -> None:
    for filename, frame in list(sources.items()):
        if frame.empty:
            continue
        sources[filename] = frame[
            ~frame["canonical_company_id"].astype(str).eq(company_id)
        ].reset_index(drop=True)


def sync_company_sources(
    data_dir: Path = DATA,
    ratings_path: Path | None = None,
    status_path: Path | None = None,
) -> pd.DataFrame:
    ratings_path = ratings_path or (data_dir / "company_ratings.csv")
    status_path = status_path or (data_dir / "a_to_g_company_source_status.csv")
    if not ratings_path.exists() or not ratings_path.stat().st_size:
        raise FileNotFoundError(f"Missing A ratings: {ratings_path}")

    ratings = pd.read_csv(ratings_path).fillna("")
    if not {"canonical_company_id", "rating"}.issubset(ratings.columns):
        raise ValueError("company_ratings.csv must contain canonical_company_id and rating")
    ratings = ratings.drop_duplicates("canonical_company_id", keep="last")

    universe = _load_universe(data_dir)
    universe_by_id = (
        universe.set_index("canonical_company_id").to_dict("index") if not universe.empty else {}
    )

    sources: dict[str, pd.DataFrame] = {}
    for filename in MANAGED_SOURCE_FILES:
        sources[filename] = _load_source(data_dir / filename)
    dedicated_big4 = _dedicated_big4_ids(data_dir)

    now = datetime.now(timezone.utc).isoformat()
    status_rows: list[dict[str, object]] = []

    for _, rating_row in ratings.iterrows():
        company_id = _clean(rating_row.get("canonical_company_id"))
        rating = _clean(rating_row.get("rating")) or "Unrated"
        if not company_id:
            continue
        rec = universe_by_id.get(company_id, {})
        company = _clean(rec.get("company")) or company_id
        category = _clean(rec.get("company_category"))
        career_url = _clean(rec.get("career_url"))
        locations = _clean(rec.get("locations"))
        region = _clean(rec.get("region")) or "Multi-region"

        if company_id in dedicated_big4:
            # The dedicated registry has one row per market and a different schema.
            # It is intentionally managed by the Big Four sourcing lane. Remove any
            # generic duplicate that an earlier sync may have created.
            _remove_generic_duplicates(sources, company_id)
            status_rows.append({
                "synced_at": now,
                "canonical_company_id": company_id,
                "company": company,
                "rating": rating,
                "source_files": DEDICATED_BIG4_SOURCE,
                "source_ids": "",
                "status": "separate_registry",
                "cadence_days": CADENCE_DAYS.get(rating, ""),
                "career_url": career_url,
                "note": "Big Four uses its dedicated multi-market G registry; generic duplicates removed.",
            })
            continue

        hits = _existing_locations(sources, company_id)

        if rating not in CADENCE_DAYS:
            for filename, idx in hits:
                sources[filename].at[idx, "enabled"] = False
            if hits:
                note = "Existing managed G source disabled; no new source created."
            else:
                note = "No managed G source exists; no new source created."
            status_rows.append({
                "synced_at": now,
                "canonical_company_id": company_id,
                "company": company,
                "rating": rating,
                "source_files": "; ".join(dict.fromkeys(f for f, _ in hits)),
                "source_ids": "; ".join(
                    dict.fromkeys(_clean(sources[f].at[i, "source_id"]) for f, i in hits)
                ),
                "status": "disabled_exclude" if rating == "Exclude" else "disabled_unrated",
                "cadence_days": "",
                "career_url": career_url,
                "note": note,
            })
            continue

        cadence = CADENCE_DAYS[rating]
        if hits:
            files: list[str] = []
            source_ids: list[str] = []
            effective_url = career_url
            for filename, idx in hits:
                frame = sources[filename]
                frame.at[idx, "cadence_days"] = cadence
                frame.at[idx, "enabled"] = True
                if not _clean(frame.at[idx, "company"]):
                    frame.at[idx, "company"] = company
                if not _clean(frame.at[idx, "priority_locations"]) and locations:
                    frame.at[idx, "priority_locations"] = locations
                if not _clean(frame.at[idx, "market"]):
                    frame.at[idx, "market"] = region
                if not _clean(frame.at[idx, "seed_url"]) and career_url:
                    frame.at[idx, "seed_url"] = career_url
                effective_url = _clean(frame.at[idx, "seed_url"]) or effective_url
                files.append(filename)
                source_ids.append(_clean(frame.at[idx, "source_id"]))
            status_rows.append({
                "synced_at": now,
                "canonical_company_id": company_id,
                "company": company,
                "rating": rating,
                "source_files": "; ".join(dict.fromkeys(files)),
                "source_ids": "; ".join(dict.fromkeys(source_ids)),
                "status": "active_existing_source",
                "cadence_days": cadence,
                "career_url": effective_url,
                "note": "Cadence/enabled synced from A; calibrated adapter and seed URL preserved.",
            })
            continue

        if not rec:
            status = "missing_universe_record"
            note = "Rated in A but no Company Universe record exists yet."
        elif not career_url:
            status = "missing_career_url"
            note = "Rated A/B/C but Company Universe has no career_url; source not created."
        else:
            filename = _target_source(category)
            frame = sources[filename]
            source_id = f"{company_id}-global"
            new_row = {
                "source_id": source_id,
                "canonical_company_id": company_id,
                "company": company,
                "market": region,
                "priority_locations": locations,
                "seed_url": career_url,
                "adapter": "generic",
                "cadence_days": cadence,
                "enabled": True,
            }
            sources[filename] = pd.concat(
                [frame, pd.DataFrame([new_row], columns=SOURCE_COLUMNS)],
                ignore_index=True,
            ).drop_duplicates("canonical_company_id", keep="last")
            status_rows.append({
                "synced_at": now,
                "canonical_company_id": company_id,
                "company": company,
                "rating": rating,
                "source_files": filename,
                "source_ids": source_id,
                "status": "active_new_source",
                "cadence_days": cadence,
                "career_url": career_url,
                "note": "Created automatically from explicit A rating and Company Universe career_url.",
            })
            continue

        status_rows.append({
            "synced_at": now,
            "canonical_company_id": company_id,
            "company": company,
            "rating": rating,
            "source_files": "",
            "source_ids": "",
            "status": status,
            "cadence_days": cadence,
            "career_url": career_url,
            "note": note,
        })

    for filename, frame in sources.items():
        path = data_dir / filename
        path.parent.mkdir(parents=True, exist_ok=True)
        frame = frame.reindex(columns=SOURCE_COLUMNS, fill_value="")
        frame.to_csv(path, index=False)

    status_df = pd.DataFrame(status_rows).reindex(columns=STATUS_COLUMNS, fill_value="")
    if not status_df.empty:
        status_df = status_df.sort_values(["status", "rating", "company"], ascending=[True, True, True])
    status_path.parent.mkdir(parents=True, exist_ok=True)
    status_df.to_csv(status_path, index=False)
    return status_df


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", type=Path, default=DATA)
    parser.add_argument("--status-out", type=Path, default=None)
    args = parser.parse_args()
    status = sync_company_sources(
        data_dir=args.data_dir,
        status_path=args.status_out,
    )
    counts = status["status"].value_counts().to_dict() if not status.empty else {}
    print(f"A → G company source sync: {len(status)} rated companies; {counts}")


if __name__ == "__main__":
    main()
