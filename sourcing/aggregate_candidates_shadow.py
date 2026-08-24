"""Shadow G candidate aggregator.

This module is intentionally NOT wired into the live application or any workflow.
It exists to validate the target G architecture in parallel with the current
production pipeline.

Safety invariant:
- reads only explicitly supplied staging CSVs;
- writes only the explicitly supplied shadow output path;
- never writes jobs_board_staging.csv, semantic_fit.csv, j_curated_shortlist.csv,
  opportunity_history.csv, or any other current live store.

The source-specific scrapers remain unchanged. This layer only normalizes and
cross-source deduplicates their outputs into one candidate pool that can later be
compared with the existing G -> C flow before any consumer is switched.
"""
from __future__ import annotations

import argparse
import hashlib
import re
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

import pandas as pd


OUTPUT_COLUMNS = [
    "candidate_id",
    "job_id",
    "canonical_company_id",
    "company",
    "title",
    "description",
    "description_en",
    "translation_status",
    "market",
    "location",
    "priority_locations",
    "job_url",
    "source_url",
    "source_id",
    "date_posted",
    "discovered_at",
    "last_seen_at",
    "relevance_score",
    "matched_terms",
    "verification",
    "status",
    "alternate_job_urls",
    "duplicate_count",
    "calibration_score",
    "calibration_note",
    "source_streams",
    "source_count",
]


def _text(value: object) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    return str(value).strip()


def _norm_text(value: object) -> str:
    return re.sub(r"[^a-z0-9]+", "", _text(value).lower())


def _normalise_url(value: object) -> str:
    raw = _text(value)
    if not raw:
        return ""
    try:
        parts = urlsplit(raw)
    except ValueError:
        return raw.rstrip("/")
    if not parts.scheme or not parts.netloc:
        return raw.rstrip("/")
    path = parts.path.rstrip("/") or "/"
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), path, "", ""))


def _candidate_key(row: pd.Series) -> str:
    """Stable cross-stream key with conservative fallback matching.

    1. Canonicalised job URL when available.
    2. Existing job_id when URL is unavailable.
    3. Company + title + location fingerprint as a last resort.

    We deliberately do not merge two different URLs solely because their titles
    look similar; that would be too aggressive for a shadow migration layer.
    """
    url = _normalise_url(row.get("job_url", "") or row.get("source_url", ""))
    if url:
        return f"url:{url}"
    job_id = _text(row.get("job_id", ""))
    if job_id:
        return f"job:{job_id}"
    company = _norm_text(row.get("canonical_company_id", "") or row.get("company", ""))
    title = _norm_text(row.get("title", ""))
    location = _norm_text(row.get("location", ""))
    return f"fallback:{company}:{title}:{location}"


def _richest(values: pd.Series) -> str:
    items = [_text(v) for v in values if _text(v)]
    return max(items, key=len) if items else ""


def _latest(values: pd.Series) -> str:
    items = [_text(v) for v in values if _text(v)]
    if not items:
        return ""
    parsed = pd.to_datetime(pd.Series(items), errors="coerce", utc=True)
    if parsed.notna().any():
        return items[int(parsed.fillna(pd.Timestamp.min.tz_localize("UTC")).argmax())]
    return max(items)


def _first_nonblank(values: pd.Series) -> str:
    for value in values:
        text = _text(value)
        if text:
            return text
    return ""


def _unique_join(values: pd.Series, separator: str = "; ") -> str:
    out: list[str] = []
    for value in values:
        text = _text(value)
        if not text:
            continue
        for item in [x.strip() for x in text.split(";") if x.strip()]:
            if item not in out:
                out.append(item)
    return separator.join(out)


def _prepare(frame: pd.DataFrame, stream: str) -> pd.DataFrame:
    out = frame.copy().fillna("")
    for col in OUTPUT_COLUMNS:
        if col not in out.columns:
            out[col] = ""
    out["source_streams"] = stream
    out["_candidate_key"] = out.apply(_candidate_key, axis=1)
    return out


def aggregate_frames(frames: list[tuple[str, pd.DataFrame]]) -> pd.DataFrame:
    prepared = [_prepare(frame, stream) for stream, frame in frames if not frame.empty]
    if not prepared:
        return pd.DataFrame(columns=OUTPUT_COLUMNS)

    combined = pd.concat(prepared, ignore_index=True, sort=False).fillna("")
    combined = combined[
        combined["title"].astype(str).str.strip().ne("")
        & combined["company"].astype(str).str.strip().ne("")
    ].copy()
    if combined.empty:
        return pd.DataFrame(columns=OUTPUT_COLUMNS)

    rows: list[dict[str, object]] = []
    for key, group in combined.groupby("_candidate_key", sort=False, dropna=False):
        row: dict[str, object] = {}
        for col in OUTPUT_COLUMNS:
            series = group[col] if col in group.columns else pd.Series(dtype=object)
            if col in {"description", "description_en", "calibration_note"}:
                row[col] = _richest(series)
            elif col in {"last_seen_at", "date_posted"}:
                row[col] = _latest(series)
            elif col in {"matched_terms", "source_streams"}:
                row[col] = _unique_join(series)
            elif col == "alternate_job_urls":
                urls = list(series)
                urls += list(group.get("job_url", pd.Series(dtype=object)))
                row[col] = _unique_join(pd.Series(urls))
            elif col in {"duplicate_count", "source_count"}:
                continue
            else:
                row[col] = _first_nonblank(series)

        source_streams = [x.strip() for x in _text(row.get("source_streams", "")).split(";") if x.strip()]
        row["source_count"] = len(source_streams)
        row["duplicate_count"] = max(0, len(group) - 1)
        row["candidate_id"] = hashlib.sha256(str(key).encode("utf-8")).hexdigest()[:16]
        rows.append(row)

    out = pd.DataFrame(rows).reindex(columns=OUTPUT_COLUMNS, fill_value="").fillna("")
    out["_sort_date"] = pd.to_datetime(out["last_seen_at"], errors="coerce", utc=True)
    out = out.sort_values(["_sort_date", "company", "title"], ascending=[False, True, True], na_position="last")
    return out.drop(columns="_sort_date").reset_index(drop=True)


def _read_input(spec: str) -> tuple[str, pd.DataFrame]:
    if "=" not in spec:
        raise ValueError("--input must use STREAM=PATH, e.g. board=data/jobs_board_staging.csv")
    stream, raw_path = spec.split("=", 1)
    stream = stream.strip()
    path = Path(raw_path.strip())
    if not stream:
        raise ValueError("input stream name cannot be blank")
    if not path.exists() or path.stat().st_size == 0:
        return stream, pd.DataFrame()
    return stream, pd.read_csv(path).fillna("")


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a non-production shadow G candidate pool")
    parser.add_argument(
        "--input",
        action="append",
        default=[],
        metavar="STREAM=PATH",
        help="Repeat for every staging source to merge.",
    )
    parser.add_argument("--out", required=True, help="Shadow output path; no live default is provided intentionally.")
    args = parser.parse_args()

    frames = [_read_input(spec) for spec in args.input]
    result = aggregate_frames(frames)
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    result.to_csv(out_path, index=False)
    print(f"shadow aggregator wrote {len(result)} candidates to {out_path}")


if __name__ == "__main__":
    main()
