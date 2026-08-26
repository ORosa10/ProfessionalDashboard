"""Build the pending Workstream C semantic-fit queue from Workstream G roles.

This script is deterministic by design. GitHub Actions runs it after G sourcing.
The intelligence step that assigns Strong / Moderate / Weak is external and
writes data/semantic_fit.csv. Keeping these responsibilities separate preserves
our architecture: Actions prepare data; the semantic agent performs judgement.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import pandas as pd

from .opportunity_registry import REGISTRY_COLUMNS, update_registry, validate_semantic_identity
from .queue_selection import select_country_balanced_indices

ROOT = Path(__file__).resolve().parents[1]
JOBS_PATH = ROOT / "data" / "jobs_board_staging.csv"
SEMANTIC_PATH = ROOT / "data" / "semantic_fit.csv"
HISTORY_PATH = ROOT / "data" / "opportunity_history.csv"
OUT_PATH = ROOT / "data" / "semantic_fit_queue.csv"
COUNTRY_WEIGHTS_PATH = ROOT / "data" / "country_sourcing_weights.json"
REGISTRY_PATH = ROOT / "data" / "opportunity_registry.csv"

QUEUE_COLUMNS = [
    "opportunity_id", "title", "company", "canonical_company_id", "company_category",
    "company_rating", "market", "location", "job_url", "date_posted", "source_id",
    "calibration_score", "calibration_note", "matched_terms", "role_family",
    "company_context", "description_for_fit",
]


def _norm(value: object) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value or "").lower())


def _role_family(title: object, description: object = "") -> str:
    text = f"{title} {description}".lower()
    rules = [
        ("Treasury / Markets", ("treasury", "cash management", "liquidity", "hedging", "foreign exchange", "fx ", "interest rate", "alm", "commodity")),
        ("Investments / PE", ("private equity", "investment analyst", "investment associate", "investment manager", "portfolio management", "investments")),
        ("Corporate Finance / M&A", ("corporate finance", "corporate development", "m&a", "merger", "acquisition", "valuation", "transaction")),
        ("Risk", ("market risk", "financial risk", "risk analyst", "risk manager", "credit risk")),
        ("FP&A / Performance", ("fp&a", "financial planning", "controlling", "controller", "performance management")),
        ("Restructuring", ("restructur", "turnaround", "distressed", "insolvenc")),
        ("Asset Management", ("asset management", "portfolio manager", "equity analyst", "fixed income", "fund manager")),
    ]
    for family, terms in rules:
        if any(term in text for term in terms):
            return family
    return "Other finance"


def _country_weights() -> dict[str, float]:
    if not COUNTRY_WEIGHTS_PATH.exists():
        return {}
    try:
        payload = json.loads(COUNTRY_WEIGHTS_PATH.read_text(encoding="utf-8"))
        weights = {str(k): float(v) for k, v in payload.get("weights", {}).items() if float(v) > 0}
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return {}
    total = sum(weights.values())
    return {k: v / total for k, v in weights.items()} if total > 0 else {}


def _target_slots(limit: int) -> dict[str, int]:
    weights = _country_weights()
    if not weights or limit <= 0:
        return {}
    raw = {country: weight * limit for country, weight in weights.items()}
    slots = {country: int(value) for country, value in raw.items()}
    remaining = limit - sum(slots.values())
    order = sorted(raw, key=lambda country: (raw[country] - slots[country], raw[country]), reverse=True)
    for country in order[:remaining]:
        slots[country] += 1
    return slots


def _load_company_universe() -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    base = ROOT / "data" / "company_universe.csv"
    if base.exists():
        frames.append(pd.read_csv(base).fillna(""))
    for path in sorted((ROOT / "data").glob("company_universe_wave*.csv")):
        frames.append(pd.read_csv(path).fillna(""))
    if not frames:
        return pd.DataFrame()

    universe = pd.concat(frames, ignore_index=True, sort=False).fillna("")
    category_frames: list[pd.DataFrame] = []
    if "company_category" in universe.columns:
        category_frames.append(universe[["canonical_company_id", "company_category"]])
        universe = universe.drop(columns=["company_category"])
    categories_path = ROOT / "data" / "company_categories.csv"
    if categories_path.exists():
        categories = pd.read_csv(categories_path).fillna("")
        if {"canonical_company_id", "company_category"}.issubset(categories.columns):
            category_frames.append(categories[["canonical_company_id", "company_category"]])
    overrides_path = ROOT / "data" / "company_category_overrides.csv"
    if overrides_path.exists():
        overrides = pd.read_csv(overrides_path).fillna("")
        if {"canonical_company_id", "company_category"}.issubset(overrides.columns):
            category_frames.append(overrides[["canonical_company_id", "company_category"]])
    if category_frames:
        category = pd.concat(category_frames, ignore_index=True).drop_duplicates("canonical_company_id", keep="last")
        universe = universe.drop_duplicates("canonical_company_id", keep="last").merge(category, on="canonical_company_id", how="left")
    else:
        universe = universe.drop_duplicates("canonical_company_id", keep="last")
        universe["company_category"] = ""

    ratings_path = ROOT / "data" / "company_ratings.csv"
    if ratings_path.exists():
        ratings = pd.read_csv(ratings_path).fillna("")
        if {"canonical_company_id", "rating"}.issubset(ratings.columns):
            ratings = ratings[["canonical_company_id", "rating"]].drop_duplicates("canonical_company_id", keep="last")
            universe = universe.merge(ratings, on="canonical_company_id", how="left", suffixes=("", "_saved"))
            if "rating_saved" in universe.columns:
                universe["rating"] = universe["rating_saved"].where(universe["rating_saved"].ne(""), universe.get("rating", ""))
                universe = universe.drop(columns=["rating_saved"])
    for col in ["company", "aliases_entities", "canonical_company_id", "company_category", "rating", "why_test", "archetype"]:
        if col not in universe.columns:
            universe[col] = ""
    return universe.fillna("")


def _load_all_g_metadata() -> pd.DataFrame:
    """Load identity metadata from every G lane, not only country boards."""
    frames: list[pd.DataFrame] = []
    for path in sorted((ROOT / "data").glob("jobs*.csv")):
        try:
            frame = pd.read_csv(path).fillna("")
        except (OSError, pd.errors.EmptyDataError, pd.errors.ParserError):
            continue
        if "job_id" in frame.columns:
            frames.append(frame)
    return pd.concat(frames, ignore_index=True, sort=False) if frames else pd.DataFrame()


def _company_maps(universe: pd.DataFrame) -> tuple[dict[str, dict], dict[str, dict]]:
    exact: dict[str, dict] = {}
    aliases: dict[str, dict] = {}
    for _, row in universe.iterrows():
        rec = row.to_dict()
        key = _norm(rec.get("company", ""))
        if key:
            exact[key] = rec
        for alias in str(rec.get("aliases_entities", "")).split(";"):
            alias_key = _norm(alias)
            if alias_key:
                aliases[alias_key] = rec
    return exact, aliases


def build_queue(limit: int = 80) -> pd.DataFrame:
    if not JOBS_PATH.exists() or JOBS_PATH.stat().st_size == 0:
        return pd.DataFrame(columns=QUEUE_COLUMNS)
    jobs = pd.read_csv(JOBS_PATH).fillna("")
    if jobs.empty:
        return pd.DataFrame(columns=QUEUE_COLUMNS)
    jobs = jobs[jobs.get("status", "").eq("Open")].copy()
    jobs = jobs.drop_duplicates("job_id", keep="last")

    # Keep vacancy identity independently of the rolling Open staging pool.
    # Judgments must remain joinable after G stops returning a vacancy.
    registry = update_registry(REGISTRY_PATH, jobs)
    REGISTRY_PATH.parent.mkdir(parents=True, exist_ok=True)
    registry.to_csv(REGISTRY_PATH, index=False)

    already: set[str] = set()
    if SEMANTIC_PATH.exists() and SEMANTIC_PATH.stat().st_size > 0:
        sem = pd.read_csv(SEMANTIC_PATH).fillna("")
        if "opportunity_id" in sem.columns:
            already.update(str(x) for x in sem["opportunity_id"] if str(x))
    if HISTORY_PATH.exists() and HISTORY_PATH.stat().st_size > 0:
        hist = pd.read_csv(HISTORY_PATH).fillna("")
        if {"opportunity_id", "action"}.issubset(hist.columns):
            done = hist[hist["action"].isin(["Apply", "Skip"])]
            already.update(str(x) for x in done["opportunity_id"] if str(x))
    jobs = jobs[~jobs["job_id"].astype(str).isin(already)].copy()
    if jobs.empty:
        return pd.DataFrame(columns=QUEUE_COLUMNS)

    universe = _load_company_universe()
    exact, aliases = _company_maps(universe)

    def lookup(company: object) -> dict:
        key = _norm(company)
        return exact.get(key) or aliases.get(key) or {}

    found = jobs["company"].map(lookup)
    jobs["canonical_company_id"] = [str(x.get("canonical_company_id", "")) for x in found]
    jobs["company_category"] = [str(x.get("company_category", "")) for x in found]
    jobs["company_rating"] = [str(x.get("rating", "") or "Unrated") for x in found]
    jobs["company_context"] = [
        " · ".join(part for part in [str(x.get("archetype", "")), str(x.get("why_test", ""))] if part)
        for x in found
    ]
    jobs["description_for_fit"] = jobs.apply(
        lambda r: str(r.get("description_en", "") or r.get("description", ""))[:3500], axis=1
    )
    jobs["role_family"] = jobs.apply(
        lambda r: _role_family(r.get("title", ""), r.get("description_for_fit", "")), axis=1
    )
    jobs["calibration_score"] = pd.to_numeric(jobs.get("calibration_score", 0), errors="coerce").fillna(0)
    jobs["_posted"] = pd.to_datetime(jobs.get("date_posted", ""), errors="coerce", utc=True)
    jobs = jobs.sort_values(["calibration_score", "_posted", "last_seen_at"], ascending=[False, False, False])

    targets = _target_slots(limit)
    chosen = select_country_balanced_indices(jobs, limit, targets)

    queue = jobs.loc[chosen].copy()
    queue = queue.rename(columns={"job_id": "opportunity_id"})
    return queue.reindex(columns=QUEUE_COLUMNS, fill_value="")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=80)
    parser.add_argument("--out", default=str(OUT_PATH))
    args = parser.parse_args()
    queue = build_queue(args.limit)
    # The board queue is only one G lane.  Seed the durable registry from all
    # persisted G lanes before validating semantic history.
    all_g = _load_all_g_metadata()
    if not all_g.empty:
        registry = update_registry(REGISTRY_PATH, all_g)
        REGISTRY_PATH.parent.mkdir(parents=True, exist_ok=True)
        registry.to_csv(REGISTRY_PATH, index=False)
    if SEMANTIC_PATH.exists() and SEMANTIC_PATH.stat().st_size > 0 and REGISTRY_PATH.exists():
        validate_semantic_identity(
            pd.read_csv(SEMANTIC_PATH).fillna(""),
            pd.read_csv(REGISTRY_PATH).fillna(""),
        )
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    queue.to_csv(out, index=False)
    print(f"wrote {len(queue)} pending semantic-fit roles to {out}; registry={REGISTRY_PATH}")


if __name__ == "__main__":
    main()
