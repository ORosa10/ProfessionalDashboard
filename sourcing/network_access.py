"""Deterministic Workstream F network identity and access evidence.

F answers a narrow factual question: do we know one or more people associated
with a canonical employer? It must not infer company preference, semantic role
fit or hiring attainability from the existence of a connection.

Matching is intentionally conservative. Only exact normalised company names or
explicit aliases are accepted, and a label that maps to more than one canonical
company is marked ambiguous rather than silently choosing one.
"""
from __future__ import annotations

import io
import re
from dataclasses import dataclass
from datetime import datetime, timezone

import pandas as pd


CONNECTIONS_COLUMNS = [
    "full_name", "first_name", "last_name", "company_raw",
    "canonical_company_id", "matched_company", "company_match_status",
    "position", "connected_on", "linkedin_url", "added_at",
]

ACCESS_SUMMARY_COLUMNS = [
    "canonical_company_id", "company", "contact_count", "positions",
    "has_access", "evidence_source",
]


def norm_company(value: object) -> str:
    return re.sub(r"[^a-z0-9]", "", str(value or "").lower())


@dataclass(frozen=True)
class AliasIndex:
    unique: dict[str, tuple[str, str]]
    ambiguous: set[str]


def build_alias_index(universes: list[pd.DataFrame]) -> AliasIndex:
    """Build an exact alias index while retaining ambiguity explicitly."""
    candidates: dict[str, dict[str, str]] = {}
    for frame in universes:
        if frame is None or frame.empty:
            continue
        for _, row in frame.fillna("").iterrows():
            cid = str(row.get("canonical_company_id", "")).strip()
            company = str(row.get("company", "")).strip()
            if not cid or not company:
                continue
            labels = [company, *str(row.get("aliases_entities", "")).split(";")]
            for label in labels:
                key = norm_company(label)
                if not key:
                    continue
                candidates.setdefault(key, {})[cid] = company

    unique: dict[str, tuple[str, str]] = {}
    ambiguous: set[str] = set()
    for key, by_id in candidates.items():
        if len(by_id) == 1:
            cid, company = next(iter(by_id.items()))
            unique[key] = (cid, company)
        elif len(by_id) > 1:
            ambiguous.add(key)
    return AliasIndex(unique=unique, ambiguous=ambiguous)


def _match_company_label(company_raw: str, alias_index: AliasIndex) -> tuple[str, str, str]:
    key = norm_company(company_raw)
    if key and key in alias_index.unique:
        cid, company = alias_index.unique[key]
        return cid, company, "matched_exact_alias"
    if key and key in alias_index.ambiguous:
        return "", "", "ambiguous_alias"
    if company_raw:
        return "", "", "unmatched_company"
    return "", "", "company_missing"


def parse_linkedin_csv(raw: bytes) -> pd.DataFrame:
    """Parse LinkedIn Connections.csv including its optional Notes preamble."""
    text = raw.decode("utf-8-sig", errors="replace")
    lines = text.splitlines()
    start = None
    for index, line in enumerate(lines):
        if line.strip().lower().startswith("first name,"):
            start = index
            break
    if start is None:
        raise ValueError("LinkedIn connections header 'First Name' was not found")
    frame = pd.read_csv(io.StringIO("\n".join(lines[start:]))).fillna("")
    frame.columns = [str(column).strip() for column in frame.columns]
    required = {"First Name", "Last Name"}
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"LinkedIn connections file is missing columns: {', '.join(sorted(missing))}")
    return frame


def match_linkedin_connections(
    raw: pd.DataFrame,
    alias_index: AliasIndex,
    *,
    added_at: str | None = None,
) -> pd.DataFrame:
    """Convert LinkedIn rows to canonical F evidence without fuzzy guessing."""
    timestamp = added_at or datetime.now(timezone.utc).isoformat()
    rows: list[dict[str, str]] = []
    for _, row in raw.fillna("").iterrows():
        first = str(row.get("First Name", "")).strip()
        last = str(row.get("Last Name", "")).strip()
        company_raw = str(row.get("Company", "")).strip()
        cid, company, match_status = _match_company_label(company_raw, alias_index)
        rows.append({
            "full_name": f"{first} {last}".strip(),
            "first_name": first,
            "last_name": last,
            "company_raw": company_raw,
            "canonical_company_id": cid,
            "matched_company": company,
            "company_match_status": match_status,
            "position": str(row.get("Position", "")).strip(),
            "connected_on": str(row.get("Connected On", "")).strip(),
            "linkedin_url": str(row.get("URL", "")).strip(),
            "added_at": timestamp,
        })
    return pd.DataFrame(rows).reindex(columns=CONNECTIONS_COLUMNS, fill_value="").fillna("")


def rematch_existing_connections(existing: pd.DataFrame, alias_index: AliasIndex) -> pd.DataFrame:
    """Migrate old F rows to current identity rules without losing contact facts.

    Existing canonical IDs are intentionally recomputed from company_raw. This
    removes legacy silent/ambiguous matches and makes the migration idempotent.
    Names, positions, dates, URLs and original added_at timestamps are preserved.
    """
    if existing is None or existing.empty:
        return pd.DataFrame(columns=CONNECTIONS_COLUMNS)
    source = existing.fillna("")
    rows: list[dict[str, str]] = []
    for _, row in source.iterrows():
        company_raw = str(row.get("company_raw", "")).strip()
        cid, company, match_status = _match_company_label(company_raw, alias_index)
        first = str(row.get("first_name", "")).strip()
        last = str(row.get("last_name", "")).strip()
        full_name = str(row.get("full_name", "")).strip() or f"{first} {last}".strip()
        rows.append({
            "full_name": full_name,
            "first_name": first,
            "last_name": last,
            "company_raw": company_raw,
            "canonical_company_id": cid,
            "matched_company": company,
            "company_match_status": match_status,
            "position": str(row.get("position", "")).strip(),
            "connected_on": str(row.get("connected_on", "")).strip(),
            "linkedin_url": str(row.get("linkedin_url", "")).strip(),
            "added_at": str(row.get("added_at", "")).strip(),
        })
    return pd.DataFrame(rows).reindex(columns=CONNECTIONS_COLUMNS, fill_value="").fillna("")


def deduplicate_connections(existing: pd.DataFrame, incoming: pd.DataFrame) -> pd.DataFrame:
    """Update a known person by LinkedIn URL, falling back to name+raw company."""
    frames = [
        frame.reindex(columns=CONNECTIONS_COLUMNS, fill_value="").fillna("")
        for frame in [existing, incoming]
        if frame is not None and not frame.empty
    ]
    if not frames:
        return pd.DataFrame(columns=CONNECTIONS_COLUMNS)
    combined = pd.concat(frames, ignore_index=True, sort=False).fillna("")
    combined["_key"] = combined["linkedin_url"].where(
        combined["linkedin_url"].astype(str).str.strip().ne(""),
        combined["full_name"].astype(str) + "|" + combined["company_raw"].astype(str),
    )
    combined = combined.drop_duplicates("_key", keep="last").drop(columns=["_key"])
    return combined.reindex(columns=CONNECTIONS_COLUMNS, fill_value="").reset_index(drop=True)


def build_access_summary(connections: pd.DataFrame) -> pd.DataFrame:
    """Build factual F -> A access evidence; no preference/fit inference."""
    if connections is None or connections.empty:
        return pd.DataFrame(columns=ACCESS_SUMMARY_COLUMNS)
    frame = connections.reindex(columns=CONNECTIONS_COLUMNS, fill_value="").fillna("")
    matched = frame[
        frame["canonical_company_id"].astype(str).str.strip().ne("")
        & frame["company_match_status"].astype(str).eq("matched_exact_alias")
    ].copy()
    if matched.empty:
        return pd.DataFrame(columns=ACCESS_SUMMARY_COLUMNS)

    def unique_positions(series: pd.Series) -> str:
        values: list[str] = []
        for value in series:
            item = str(value).strip()
            if item and item not in values:
                values.append(item)
        return "; ".join(values)

    summary = (
        matched.groupby(["canonical_company_id", "matched_company"], dropna=False)
        .agg(contact_count=("full_name", "size"), positions=("position", unique_positions))
        .reset_index()
        .rename(columns={"matched_company": "company"})
    )
    summary["has_access"] = True
    summary["evidence_source"] = "linkedin_connections_export"
    return summary.reindex(columns=ACCESS_SUMMARY_COLUMNS, fill_value="").sort_values(
        ["contact_count", "company"], ascending=[False, True]
    ).reset_index(drop=True)
