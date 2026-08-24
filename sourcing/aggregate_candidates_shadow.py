"""Shadow G candidate aggregator.

This module is intentionally NOT wired into the live application. It validates
our target G architecture in parallel with the current production pipeline.

Safety invariants:
- reads only explicitly supplied staging CSVs;
- writes only explicitly supplied shadow output / diagnostics paths;
- never writes jobs_board_staging.csv, semantic_fit.csv, j_curated_shortlist.csv,
  opportunity_history.csv, or any other live store;
- prefers false negatives in deduplication over false-positive merges.
"""
from __future__ import annotations

import argparse
import hashlib
import re
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import pandas as pd


TARGET_COUNTRIES = {
    "Czechia": ["czechia", "czech republic", "praha", "prague", " cz"],
    "Germany": ["germany", "deutschland", "berlin", "frankfurt", "munich", "münchen", "hamburg", "cologne", "köln", " düsseldorf", " stuttgart", " de"],
    "Austria": ["austria", "österreich", "vienna", "wien", "salzburg", "linz", "graz", " at"],
    "Switzerland": ["switzerland", "schweiz", "suisse", "zurich", "zürich", "geneva", "genève", "basel", " ch"],
    "United Kingdom": ["united kingdom", " uk", "london", "england", "scotland", "wales", "manchester", "birmingham"],
    "Sweden": ["sweden", "sverige", "stockholm", "gothenburg", "göteborg", " se"],
    "Norway": ["norway", "norge", "oslo", " no"],
    "Denmark": ["denmark", "danmark", "copenhagen", "københavn", " dk"],
    "Finland": ["finland", "helsinki", "suomi", " fi"],
}

TRACKING_QUERY_KEYS = {
    "source", "src", "ref", "referrer", "campaign", "tracking", "trk",
    "utm_source", "utm_medium", "utm_campaign", "utm_content", "utm_term",
}

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
    "country_bucket",
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

DIAGNOSTIC_COLUMNS = ["dimension", "value", "raw_rows", "candidate_count", "share_of_candidates"]


def _text(value: object) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    return str(value).strip()


def _norm_text(value: object) -> str:
    return re.sub(r"[^a-z0-9]+", "", _text(value).lower())


def _normalise_url(value: object) -> str:
    """Normalise tracking noise without dropping job-identifying query params."""
    raw = _text(value)
    if not raw:
        return ""
    try:
        parts = urlsplit(raw)
    except ValueError:
        return raw.rstrip("/")
    if not parts.scheme or not parts.netloc:
        return raw.rstrip("/")
    kept_query = []
    for key, val in parse_qsl(parts.query, keep_blank_values=True):
        lower = key.lower()
        if lower.startswith("utm_") or lower in TRACKING_QUERY_KEYS:
            continue
        kept_query.append((key, val))
    path = parts.path.rstrip("/") or "/"
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), path, urlencode(kept_query), ""))


def _country_bucket(row: pd.Series) -> str:
    market = _text(row.get("market", ""))
    if market in TARGET_COUNTRIES:
        return market
    haystack = f" {market} {_text(row.get('location', ''))} ".lower()
    for country, patterns in TARGET_COUNTRIES.items():
        if any(pattern in haystack for pattern in patterns):
            return country
    if market and market.lower() not in {"multi-region", "remote", "unknown", "n/a"}:
        return market
    return "Other / Unresolved"


def _candidate_key(row: pd.Series) -> str:
    """Stable cross-stream key with conservative fallback matching.

    1. Canonicalised job URL when available.
    2. Existing job_id when URL is unavailable.
    3. Company + title + location fingerprint as a last resort.

    Different non-tracking URLs are deliberately NOT merged just because their
    titles look similar. That is safer while the new pipeline is in shadow mode.
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
        safe = parsed.fillna(pd.Timestamp.min.tz_localize("UTC"))
        return items[int(safe.argmax())]
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
    out["country_bucket"] = out.apply(_country_bucket, axis=1)
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
            elif col in {"duplicate_count", "source_count", "country_bucket"}:
                continue
            else:
                row[col] = _first_nonblank(series)

        source_streams = [x.strip() for x in _text(row.get("source_streams", "")).split(";") if x.strip()]
        row["source_count"] = len(source_streams)
        row["duplicate_count"] = max(0, len(group) - 1)
        row["country_bucket"] = _country_bucket(pd.Series(row))
        row["candidate_id"] = hashlib.sha256(str(key).encode("utf-8")).hexdigest()[:16]
        rows.append(row)

    out = pd.DataFrame(rows).reindex(columns=OUTPUT_COLUMNS, fill_value="").fillna("")
    out["_sort_date"] = pd.to_datetime(out["last_seen_at"], errors="coerce", utc=True)
    out = out.sort_values(["_sort_date", "company", "title"], ascending=[False, True, True], na_position="last")
    return out.drop(columns="_sort_date").reset_index(drop=True)


def build_diagnostics(frames: list[tuple[str, pd.DataFrame]], candidates: pd.DataFrame) -> pd.DataFrame:
    """Long-form source/country diagnostics for shadow comparison and G coverage."""
    records: list[dict[str, object]] = []
    total = len(candidates)

    def add(dimension: str, value: str, *, raw_rows: int = 0, candidate_count: int = 0) -> None:
        records.append({
            "dimension": dimension,
            "value": value,
            "raw_rows": int(raw_rows),
            "candidate_count": int(candidate_count),
            "share_of_candidates": round(candidate_count / total, 4) if total else 0.0,
        })

    add("overall", "all_candidates", raw_rows=sum(len(frame) for _, frame in frames), candidate_count=total)
    add(
        "overall",
        "cross_source_candidates",
        candidate_count=int(pd.to_numeric(candidates.get("source_count", 0), errors="coerce").fillna(0).gt(1).sum()) if total else 0,
    )

    for stream, frame in frames:
        if frame.empty:
            add("source", stream, raw_rows=0, candidate_count=0)
            continue
        present = candidates["source_streams"].astype(str).apply(
            lambda value: stream in [x.strip() for x in value.split(";") if x.strip()]
        ) if total else pd.Series(dtype=bool)
        add("source", stream, raw_rows=len(frame), candidate_count=int(present.sum()) if total else 0)

    if total:
        for country, count in candidates["country_bucket"].replace("", "Other / Unresolved").value_counts().items():
            add("country", str(country), candidate_count=int(count))
        for status, count in candidates["status"].replace("", "Unknown").value_counts().items():
            add("status", str(status), candidate_count=int(count))
        for stream in sorted({x.strip() for v in candidates["source_streams"] for x in str(v).split(";") if x.strip()}):
            mask = candidates["source_streams"].astype(str).apply(
                lambda value: stream in [x.strip() for x in value.split(";") if x.strip()]
            )
            for country, count in candidates.loc[mask, "country_bucket"].replace("", "Other / Unresolved").value_counts().items():
                add("source_country", f"{stream} | {country}", candidate_count=int(count))

    return pd.DataFrame(records).reindex(columns=DIAGNOSTIC_COLUMNS, fill_value="")


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
    try:
        return stream, pd.read_csv(path).fillna("")
    except (pd.errors.EmptyDataError, pd.errors.ParserError):
        return stream, pd.DataFrame()


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
    parser.add_argument("--diagnostics-out", help="Optional shadow diagnostics CSV path.")
    args = parser.parse_args()

    frames = [_read_input(spec) for spec in args.input]
    result = aggregate_frames(frames)
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    result.to_csv(out_path, index=False)
    print(f"shadow aggregator wrote {len(result)} candidates to {out_path}")

    if args.diagnostics_out:
        diagnostics = build_diagnostics(frames, result)
        diag_path = Path(args.diagnostics_out)
        diag_path.parent.mkdir(parents=True, exist_ok=True)
        diagnostics.to_csv(diag_path, index=False)
        print(f"shadow aggregator wrote {len(diagnostics)} diagnostics rows to {diag_path}")


if __name__ == "__main__":
    main()
