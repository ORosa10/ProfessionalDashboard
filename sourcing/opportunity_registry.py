"""Persistent identity registry for sourced opportunities.

Semantic judgments intentionally remain a small event-like table.  This
registry is the durable join between those judgments and G vacancy metadata,
including after a vacancy leaves the current G staging snapshot.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

REGISTRY_COLUMNS = [
    "opportunity_id", "title", "company", "canonical_company_id", "market",
    "location", "job_url", "source_url", "source_id", "description",
    "description_en", "first_seen_at", "last_seen_at", "status",
]


def update_registry(existing_path: Path, jobs: pd.DataFrame) -> pd.DataFrame:
    """Merge current G metadata into a durable, append-preserving registry."""
    old = pd.DataFrame(columns=REGISTRY_COLUMNS)
    if existing_path.exists() and existing_path.stat().st_size > 0:
        old = pd.read_csv(existing_path).fillna("")
    current = jobs.copy().fillna("")
    if "job_id" in current.columns:
        current = current.rename(columns={"job_id": "opportunity_id"})
    for col in REGISTRY_COLUMNS:
        if col not in current.columns:
            current[col] = ""
    current = current[REGISTRY_COLUMNS]
    combined = pd.concat([old.reindex(columns=REGISTRY_COLUMNS, fill_value=""), current], ignore_index=True)
    combined = combined.drop_duplicates("opportunity_id", keep="last")
    combined = combined[combined["opportunity_id"].astype(str).str.strip().ne("")]
    return combined.sort_values("opportunity_id").reset_index(drop=True)


def validate_semantic_identity(semantic: pd.DataFrame, registry: pd.DataFrame) -> None:
    """Fail closed if a semantic judgment has no durable role identity."""
    if semantic.empty:
        return
    required = {"opportunity_id", "fit", "reasoning"}
    missing = required.difference(semantic.columns)
    if missing:
        raise ValueError(f"semantic_fit missing required columns: {sorted(missing)}")
    ids = set(semantic["opportunity_id"].astype(str).str.strip())
    known = set(registry["opportunity_id"].astype(str).str.strip())
    orphaned = sorted(x for x in ids - known if x)
    if orphaned:
        raise ValueError(
            f"semantic_fit contains {len(orphaned)} orphan opportunity_id(s); "
            "refusing to publish anonymous semantic judgments: "
            + ", ".join(orphaned[:10])
        )
    identity = registry.set_index("opportunity_id")
    blank = []
    for oid in ids:
        if not oid or oid not in identity.index:
            continue
        row = identity.loc[oid]
        if not str(row.get("title", "")).strip() or not str(row.get("job_url", "")).strip():
            blank.append(oid)
    if blank:
        raise ValueError(
            f"{len(blank)} semantic opportunity(s) have missing title/job_url metadata; "
            "refusing to publish incomplete identity records: " + ", ".join(blank[:10])
        )
