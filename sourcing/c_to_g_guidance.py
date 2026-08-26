"""Safe C -> G sourcing guidance loader.

C may add search coverage, but this module never hard-filters G candidates.
"""
from __future__ import annotations

import re
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
GUIDANCE_PATH = ROOT / "data" / "c_to_g_sourcing_guidance.csv"


def _clean(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def priority_queries_from_frame(frame: pd.DataFrame) -> list[str]:
    if frame.empty:
        return []
    data = frame.fillna("").copy()
    for col in ["status", "direction", "query_term"]:
        if col not in data.columns:
            return []
    active = data[
        data["status"].astype(str).str.strip().str.lower().eq("active")
        & data["direction"].astype(str).str.strip().str.lower().eq("prioritize")
    ]
    queries: list[str] = []
    seen: set[str] = set()
    for value in active["query_term"]:
        query = _clean(value)
        key = query.casefold()
        if query and key not in seen:
            queries.append(query)
            seen.add(key)
    return queries


def active_priority_queries(path: Path = GUIDANCE_PATH) -> list[str]:
    if not path.exists() or not path.stat().st_size:
        return []
    try:
        frame = pd.read_csv(path).fillna("")
    except (pd.errors.EmptyDataError, pd.errors.ParserError, OSError):
        return []
    return priority_queries_from_frame(frame)
