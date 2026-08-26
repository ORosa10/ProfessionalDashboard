"""Build the canonical semantic-fit shadow store used by the C pipeline."""
from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path

import pandas as pd


OUTPUT_COLUMNS = ["opportunity_id", "fit", "reasoning", "generated_at", "semantic_source"]
CANONICAL_COLUMNS = ["opportunity_id", "fit", "reasoning", "generated_at"]
VALID_FITS = {"Strong", "Moderate", "Weak"}


def _read(path: Path) -> pd.DataFrame:
    if not path.exists() or path.stat().st_size == 0:
        return pd.DataFrame()
    try:
        return pd.read_csv(path).fillna("")
    except (pd.errors.EmptyDataError, pd.errors.ParserError):
        return pd.DataFrame()


def compile_latest_judgments(frames: list[pd.DataFrame]) -> pd.DataFrame:
    """Return one C judgment per opportunity; newest generated_at wins.

    Input order is used only as a deterministic tiebreaker when timestamps are
    equal or missing. Filename ordering must never override a newer judgment.
    """
    prepared: list[pd.DataFrame] = []
    row_order = 0
    for source_order, frame in enumerate(frames):
        if frame is None or frame.empty:
            continue
        x = frame.fillna("").reindex(columns=CANONICAL_COLUMNS, fill_value="").copy()
        x = x[x["opportunity_id"].astype(str).str.strip().ne("")]
        if x.empty:
            continue
        x["_source_order"] = source_order
        x["_row_order"] = range(row_order, row_order + len(x))
        row_order += len(x)
        x["_generated_dt"] = pd.to_datetime(x["generated_at"], errors="coerce", utc=True)
        prepared.append(x)
    if not prepared:
        return pd.DataFrame(columns=CANONICAL_COLUMNS)

    combined = pd.concat(prepared, ignore_index=True, sort=False)
    combined = combined.sort_values(
        ["_generated_dt", "_source_order", "_row_order"],
        ascending=[True, True, True],
        na_position="first",
        kind="stable",
    )
    latest = combined.drop_duplicates("opportunity_id", keep="last")
    return latest.reindex(columns=CANONICAL_COLUMNS, fill_value="").reset_index(drop=True)


def compile_repository_judgments(
    base_path: Path = Path("data/semantic_fit.csv"),
    reviews_dir: Path = Path("data/semantic_fit_reviews"),
) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    base = _read(base_path)
    if not base.empty:
        frames.append(base)
    if reviews_dir.exists():
        for path in sorted(reviews_dir.glob("*.csv")):
            frame = _read(path)
            if not frame.empty:
                frames.append(frame)
    return compile_latest_judgments(frames)


def build_semantic_shadow(canonical: pd.DataFrame, curated_j: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, str]] = []
    seen: set[str] = set()

    if not canonical.empty:
        canonical = canonical.fillna("").copy()
        fit_col = "fit" if "fit" in canonical.columns else "semantic_fit" if "semantic_fit" in canonical.columns else None
        reason_col = "reasoning" if "reasoning" in canonical.columns else "semantic_reasoning" if "semantic_reasoning" in canonical.columns else None
        if "opportunity_id" in canonical.columns and fit_col:
            canonical = canonical.drop_duplicates("opportunity_id", keep="last")
            for _, row in canonical.iterrows():
                oid = str(row.get("opportunity_id", "")).strip()
                fit = str(row.get(fit_col, "")).strip()
                if not oid or fit not in VALID_FITS:
                    continue
                rows.append({
                    "opportunity_id": oid,
                    "fit": fit,
                    "reasoning": str(row.get(reason_col, "")).strip() if reason_col else "",
                    "generated_at": str(row.get("generated_at", "")).strip(),
                    "semantic_source": "canonical_existing",
                })
                seen.add(oid)

    if not curated_j.empty and "job_id" in curated_j.columns:
        curated_j = curated_j.fillna("").drop_duplicates("job_id", keep="first")
        migration_date = date.today().isoformat()
        for _, row in curated_j.iterrows():
            oid = str(row.get("job_id", "")).strip()
            fit = str(row.get("semantic_fit", "")).strip()
            if not oid or oid in seen or fit not in VALID_FITS:
                continue
            rows.append({
                "opportunity_id": oid,
                "fit": fit,
                "reasoning": str(row.get("semantic_reasoning", "")).strip(),
                "generated_at": migration_date,
                "semantic_source": "curated_j_backfill",
            })
            seen.add(oid)

    return pd.DataFrame(rows).reindex(columns=OUTPUT_COLUMNS, fill_value="")


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the canonical semantic-fit shadow store")
    parser.add_argument("--canonical", required=True)
    parser.add_argument("--curated-j", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    # Repository source files retain every review row, so compile them directly by
    # generated_at. The precompiled --canonical file is only a fallback for tests
    # or environments where repository review files are unavailable.
    canonical = compile_repository_judgments()
    if canonical.empty:
        canonical = _read(Path(args.canonical))
    result = build_semantic_shadow(canonical, _read(Path(args.curated_j)))
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    result.to_csv(out, index=False)

    existing = int(result["semantic_source"].eq("canonical_existing").sum()) if not result.empty else 0
    backfill = int(result["semantic_source"].eq("curated_j_backfill").sum()) if not result.empty else 0
    print(f"semantic shadow: {len(result)} rows = {existing} existing C + {backfill} curated backfill")


if __name__ == "__main__":
    main()
