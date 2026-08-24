"""Build the future J shortlist in shadow mode only.

Rules implemented here are intentionally transparent:
- hard quality floor: C == Strong;
- hard feasibility floor: actionability == true;
- explicit A == Exclude is not shown;
- country targets are real quotas above that floor;
- quota deficits never admit Moderate/Weak/non-actionable roles;
- unused slots are redistributed to the best remaining Strong/actionable roles;
- current Apply/Skip/Pass decisions are removed from the working queue;
- at most two roles per company, preserving current J diversity behaviour.

No production file is read as a writable target and no live UI consumes this.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import pandas as pd

from sourcing.build_semantic_fit_queue import _company_maps, _load_company_universe, _norm


OUTPUT_COLUMNS = [
    "opportunity_id", "candidate_id", "company", "title", "company_rating",
    "country_bucket", "market", "location", "semantic_fit", "actionable",
    "actionability_warnings", "date_posted", "last_seen_at", "source_streams",
    "job_url", "selection_origin", "priority_order",
]

QUOTA_COLUMNS = [
    "country", "target", "eligible_strong_actionable", "selected_in_quota",
    "quota_deficit", "final_selected_after_redistribution",
]


def _read_csv(path: Path) -> pd.DataFrame:
    if not path.exists() or path.stat().st_size == 0:
        return pd.DataFrame()
    try:
        return pd.read_csv(path).fillna("")
    except (pd.errors.EmptyDataError, pd.errors.ParserError):
        return pd.DataFrame()


def _read_targets(path: Path) -> dict[str, int]:
    if not path.exists() or path.stat().st_size == 0:
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return {}
    return {
        str(country): int(value)
        for country, value in payload.get("top20_targets", {}).items()
        if int(value) > 0
    }


def _as_bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"true", "1", "yes", "y"}


def _company_rating_map(universe: pd.DataFrame) -> tuple[dict[str, dict], dict[str, dict]]:
    if universe.empty:
        return {}, {}
    return _company_maps(universe)


def _enrich_company_rating(frame: pd.DataFrame, universe: pd.DataFrame) -> pd.DataFrame:
    out = frame.copy()
    exact, aliases = _company_rating_map(universe)

    def lookup(company: object) -> dict:
        key = _norm(company)
        return exact.get(key) or aliases.get(key) or {}

    found = out["company"].map(lookup)
    out["company_rating"] = [str(x.get("rating", "") or "Unrated") for x in found]
    return out


def _prepare_eligible(
    candidates: pd.DataFrame,
    semantic: pd.DataFrame,
    actionability: pd.DataFrame,
    history: pd.DataFrame,
    universe: pd.DataFrame,
) -> pd.DataFrame:
    if candidates.empty:
        return pd.DataFrame()

    jobs = candidates.fillna("").copy()
    for col in [
        "candidate_id", "job_id", "company", "title", "country_bucket", "market",
        "location", "date_posted", "last_seen_at", "source_streams", "job_url",
    ]:
        if col not in jobs.columns:
            jobs[col] = ""
    jobs["opportunity_id"] = jobs.apply(
        lambda row: str(row.get("job_id", "")).strip() or str(row.get("candidate_id", "")).strip(),
        axis=1,
    )
    jobs = jobs[jobs["opportunity_id"].ne("")].drop_duplicates("opportunity_id", keep="first")

    sem_map: dict[str, str] = {}
    if not semantic.empty and {"opportunity_id", "fit"}.issubset(semantic.columns):
        sem = semantic.fillna("").drop_duplicates("opportunity_id", keep="last")
        sem_map = dict(zip(sem["opportunity_id"].astype(str), sem["fit"].astype(str)))
    jobs["semantic_fit"] = jobs["opportunity_id"].map(sem_map).fillna("")
    jobs = jobs[jobs["semantic_fit"].eq("Strong")].copy()
    if jobs.empty:
        return jobs

    act_map: dict[str, dict] = {}
    if not actionability.empty and "opportunity_id" in actionability.columns:
        act = actionability.fillna("").drop_duplicates("opportunity_id", keep="last")
        act_map = {str(row["opportunity_id"]): row.to_dict() for _, row in act.iterrows()}
    jobs["actionable"] = jobs["opportunity_id"].map(
        lambda oid: _as_bool(act_map.get(str(oid), {}).get("actionable", False))
    )
    jobs["actionability_warnings"] = jobs["opportunity_id"].map(
        lambda oid: str(act_map.get(str(oid), {}).get("warnings", ""))
    )
    jobs = jobs[jobs["actionable"]].copy()
    if jobs.empty:
        return jobs

    if not history.empty and {"opportunity_id", "action"}.issubset(history.columns):
        latest = history.fillna("").drop_duplicates("opportunity_id", keep="last")
        done = set(
            latest.loc[latest["action"].astype(str).isin(["Apply", "Skip", "Pass"]), "opportunity_id"].astype(str)
        )
        jobs = jobs[~jobs["opportunity_id"].isin(done)].copy()
    if jobs.empty:
        return jobs

    jobs = _enrich_company_rating(jobs, universe)
    jobs = jobs[~jobs["company_rating"].eq("Exclude")].copy()
    jobs["_company_priority"] = jobs["company_rating"].map(
        {"A": 0, "B": 1, "C": 2, "Unrated": 3, "": 3}
    ).fillna(3)
    jobs["_posted"] = pd.to_datetime(jobs["date_posted"], errors="coerce", utc=True)
    jobs["_seen"] = pd.to_datetime(jobs["last_seen_at"], errors="coerce", utc=True)
    jobs = jobs.sort_values(
        ["_company_priority", "_posted", "_seen", "company", "title"],
        ascending=[True, False, False, True, True],
        na_position="last",
    )
    return jobs


def build_j_shadow(
    candidates: pd.DataFrame,
    semantic: pd.DataFrame,
    actionability: pd.DataFrame,
    history: pd.DataFrame,
    targets: dict[str, int],
    *,
    limit: int = 20,
    company_universe: pd.DataFrame | None = None,
    max_per_company: int = 2,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    universe = _load_company_universe() if company_universe is None else company_universe.fillna("")
    eligible = _prepare_eligible(candidates, semantic, actionability, history, universe)
    if eligible.empty:
        quotas = pd.DataFrame([
            {
                "country": country,
                "target": target,
                "eligible_strong_actionable": 0,
                "selected_in_quota": 0,
                "quota_deficit": target,
                "final_selected_after_redistribution": 0,
            }
            for country, target in targets.items()
        ]).reindex(columns=QUOTA_COLUMNS, fill_value="")
        return pd.DataFrame(columns=OUTPUT_COLUMNS), quotas

    selected: list[int] = []
    origin: dict[int, str] = {}
    company_counts: dict[str, int] = {}

    def company_key(row: pd.Series) -> str:
        return _norm(row.get("company", "")) or str(row.name)

    def add(idx: int, why: str) -> bool:
        if idx in selected:
            return False
        row = eligible.loc[idx]
        key = company_key(row)
        if company_counts.get(key, 0) >= max_per_company:
            return False
        selected.append(idx)
        origin[idx] = why
        company_counts[key] = company_counts.get(key, 0) + 1
        return True

    quota_rows: list[dict[str, object]] = []
    selected_in_quota: dict[str, int] = {}
    for country, target in targets.items():
        country_pool = eligible[eligible["country_bucket"].astype(str).eq(country)]
        taken = 0
        for idx in country_pool.index:
            if len(selected) >= limit or taken >= target:
                break
            if add(idx, f"quota:{country}"):
                taken += 1
        selected_in_quota[country] = taken
        quota_rows.append({
            "country": country,
            "target": target,
            "eligible_strong_actionable": len(country_pool),
            "selected_in_quota": taken,
            "quota_deficit": max(0, target - taken),
            "final_selected_after_redistribution": 0,
        })

    # Real quotas above a hard quality floor: if a country cannot fill its target,
    # remaining slots go only to other eligible Strong/actionable roles.
    if len(selected) < min(limit, len(eligible)):
        for idx in eligible.index:
            if len(selected) >= limit:
                break
            add(idx, "redistributed")

    final = eligible.loc[selected].copy() if selected else eligible.iloc[0:0].copy()
    final["selection_origin"] = [origin[idx] for idx in selected]
    final["priority_order"] = range(1, len(final) + 1)

    final_country_counts = final["country_bucket"].astype(str).value_counts().to_dict() if not final.empty else {}
    for row in quota_rows:
        row["final_selected_after_redistribution"] = int(final_country_counts.get(str(row["country"]), 0))

    quota_report = pd.DataFrame(quota_rows).reindex(columns=QUOTA_COLUMNS, fill_value="")
    return (
        final.reindex(columns=OUTPUT_COLUMNS, fill_value="").reset_index(drop=True),
        quota_report.reset_index(drop=True),
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Build future J selection in shadow mode")
    parser.add_argument("--candidates", required=True)
    parser.add_argument("--semantic", required=True)
    parser.add_argument("--actionability", required=True)
    parser.add_argument("--history", required=True)
    parser.add_argument("--country-targets", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--quota-out", required=True)
    parser.add_argument("--limit", type=int, default=20)
    args = parser.parse_args()

    shortlist, quotas = build_j_shadow(
        _read_csv(Path(args.candidates)),
        _read_csv(Path(args.semantic)),
        _read_csv(Path(args.actionability)),
        _read_csv(Path(args.history)),
        _read_targets(Path(args.country_targets)),
        limit=args.limit,
    )
    out = Path(args.out)
    quota_out = Path(args.quota_out)
    out.parent.mkdir(parents=True, exist_ok=True)
    quota_out.parent.mkdir(parents=True, exist_ok=True)
    shortlist.to_csv(out, index=False)
    quotas.to_csv(quota_out, index=False)
    print(f"shadow J: {len(shortlist)} Strong/actionable roles selected")
    if not quotas.empty:
        print(f"shadow J quota deficit total: {int(quotas['quota_deficit'].sum())}")


if __name__ == "__main__":
    main()
