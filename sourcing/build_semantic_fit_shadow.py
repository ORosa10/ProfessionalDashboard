"""Build a non-production canonical semantic-fit shadow store.

The live `data/semantic_fit.csv` remains untouched. Existing canonical C rows have
highest authority. Curated J semantic judgments are used only to backfill roles
that are absent from C so we can measure what a single semantic truth would look
like before any live consumer is switched.
"""
from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path

import pandas as pd


OUTPUT_COLUMNS = ["opportunity_id", "fit", "reasoning", "generated_at", "semantic_source"]
VALID_FITS = {"Strong", "Moderate", "Weak"}


def _read(path: Path) -> pd.DataFrame:
    if not path.exists() or path.stat().st_size == 0:
        return pd.DataFrame()
    try:
        return pd.read_csv(path).fillna("")
    except (pd.errors.EmptyDataError, pd.errors.ParserError):
        return pd.DataFrame()


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
        for _, row in curated_j.iterrows():
            oid = str(row.get("job_id", "")).strip()
            fit = str(row.get("semantic_fit", "")).strip()
            if not oid or oid in seen or fit not in VALID_FITS:
                continue
            rows.append({
                "opportunity_id": oid,
                "fit": fit,
                "reasoning": str(row.get("semantic_reasoning", "")).strip(),
                "generated_at": str(row.get("date_posted", "")).strip() or date.today().isoformat(),
                "semantic_source": "curated_j_backfill",
            })
            seen.add(oid)

    return pd.DataFrame(rows).reindex(columns=OUTPUT_COLUMNS, fill_value="")


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a canonical semantic-fit shadow store without changing production")
    parser.add_argument("--canonical", required=True)
    parser.add_argument("--curated-j", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    result = build_semantic_shadow(_read(Path(args.canonical)), _read(Path(args.curated_j)))
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    result.to_csv(out, index=False)

    existing = int(result["semantic_source"].eq("canonical_existing").sum()) if not result.empty else 0
    backfill = int(result["semantic_source"].eq("curated_j_backfill").sum()) if not result.empty else 0
    print(f"semantic shadow: {len(result)} rows = {existing} existing C + {backfill} curated backfill")


if __name__ == "__main__":
    main()
