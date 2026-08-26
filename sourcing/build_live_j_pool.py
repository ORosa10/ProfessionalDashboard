from __future__ import annotations

import argparse
import re
from pathlib import Path

import pandas as pd

OUTPUT_COLUMNS = [
    "job_id", "candidate_id", "source_id", "canonical_company_id", "company",
    "title", "role_family", "market", "country_bucket", "location", "date_posted",
    "last_seen_at", "job_url", "semantic_fit", "semantic_reasoning",
    "actionability_warnings",
]
EXCLUDED_COLUMNS = ["opportunity_id", "company", "title", "excluded_reason"]

BAD_COMPANY_PATTERNS = [
    r"^\s*linkedin\s*$",
    r"^\s*nabídka\s+pracovní\s+nabídka",
    r"^\s*poslat\s+nabídku\s+na\s+e-mail",
    r"^\s*navštivte\s+naše\s+sociální\s+sítě",
    r"^\s*práce\s+v\s+oboru",
]
LOW_EXTREME_PATTERN = re.compile(
    r"\b(intern(?:ship)?|off[- ]?cycle|trainee|graduate|working student|"
    r"werkstudent|praktikant(?:in)?|apprentice)\b",
    re.IGNORECASE,
)
HIGH_EXTREME_PATTERN = re.compile(
    r"\b(senior manager|vice president|senior vice president|director|head of|"
    r"partner|principal consultant|investment leader)\b",
    re.IGNORECASE,
)

TARGET_COUNTRIES = {
    "Czechia", "Germany", "Austria", "Switzerland", "United Kingdom",
    "Sweden", "Norway", "Denmark", "Finland",
}
AMBIGUOUS_COUNTRIES = {"", "Other / Unresolved", "Multi-region", "Remote", "Unknown", "Europe", "EMEA", "Nordics"}
TARGET_LOCATION_MARKERS = (
    "czechia", "czech republic", "prague", "praha",
    "germany", "berlin", "frankfurt", "munich", "münchen", "hamburg",
    "austria", "vienna", "wien", "salzburg", "linz",
    "switzerland", "zurich", "zürich", "geneva", "genève", "basel",
    "united kingdom", "london", "manchester", "edinburgh",
    "sweden", "stockholm", "göteborg", "gothenburg",
    "norway", "oslo", "denmark", "copenhagen", "københavn",
    "finland", "helsinki",
)
OUTSIDE_LOCATION_MARKERS = {
    "Singapore": ("singapore",),
    "United States": ("united states", "usa", "u.s."),
    "Canada": ("canada",),
    "India": ("india", "bengaluru", "bangalore", "mumbai", "hyderabad"),
    "Hong Kong": ("hong kong",),
    "United Arab Emirates": ("united arab emirates", "dubai", "abu dhabi"),
    "Australia": ("australia", "sydney", "melbourne"),
    "New Zealand": ("new zealand",),
    "Poland": ("poland", "warsaw", "warszawa", "krakow", "kraków"),
    "France": ("france", "paris"),
    "Netherlands": ("netherlands", "amsterdam"),
    "Belgium": ("belgium", "brussels", "bruxelles"),
    "Ireland": ("ireland", "dublin"),
    "Italy": ("italy", "milan", "milano", "rome", "roma"),
    "Spain": ("spain", "madrid", "barcelona"),
    "Luxembourg": ("luxembourg",),
    "Portugal": ("portugal", "lisbon", "lisboa"),
}


def _read(path: Path) -> pd.DataFrame:
    if not path.exists() or path.stat().st_size == 0:
        return pd.DataFrame()
    try:
        return pd.read_csv(path).fillna("")
    except (pd.errors.EmptyDataError, pd.errors.ParserError):
        return pd.DataFrame()


def _as_bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"true", "1", "yes", "y"}


def _bad_company(company: object) -> bool:
    value = str(company or "").strip()
    if not value:
        return True
    return any(re.search(pattern, value, flags=re.IGNORECASE) for pattern in BAD_COMPANY_PATTERNS)


def _seniority_blocker(title: object) -> str:
    value = str(title or "")
    if LOW_EXTREME_PATTERN.search(value):
        return "seniority:below_target_extreme"
    if HIGH_EXTREME_PATTERN.search(value):
        return "seniority:above_target_extreme"
    return ""


def _geography_blocker(row: pd.Series) -> str:
    """Block only explicit non-target geography; uncertainty remains eligible."""
    country = str(row.get("country_bucket", "") or "").strip()
    if country in TARGET_COUNTRIES:
        return ""
    if country not in AMBIGUOUS_COUNTRIES:
        return f"geography:outside_target:{country}"

    raw = " ".join(str(row.get(col, "") or "") for col in ("location", "market")).lower()
    if any(marker in raw for marker in TARGET_LOCATION_MARKERS):
        return ""
    for label, markers in OUTSIDE_LOCATION_MARKERS.items():
        if any(marker in raw for marker in markers):
            return f"geography:outside_target:{label}"
    return ""


def build_live_pool(
    candidates: pd.DataFrame,
    semantic: pd.DataFrame,
    actionability: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    if candidates.empty:
        return pd.DataFrame(columns=OUTPUT_COLUMNS), pd.DataFrame(columns=EXCLUDED_COLUMNS)

    jobs = candidates.fillna("").copy()
    for col in [
        "candidate_id", "job_id", "source_id", "canonical_company_id", "company",
        "title", "role_family", "market", "country_bucket", "location",
        "date_posted", "last_seen_at", "job_url",
    ]:
        if col not in jobs.columns:
            jobs[col] = ""

    jobs["opportunity_id"] = jobs.apply(
        lambda r: str(r.get("job_id", "")).strip() or str(r.get("candidate_id", "")).strip(),
        axis=1,
    )
    jobs = jobs[jobs["opportunity_id"].ne("")].drop_duplicates("opportunity_id", keep="first")

    sem_map: dict[str, dict] = {}
    if not semantic.empty and "opportunity_id" in semantic.columns:
        sem = semantic.fillna("").drop_duplicates("opportunity_id", keep="last")
        sem_map = {str(r["opportunity_id"]): r.to_dict() for _, r in sem.iterrows()}

    act_map: dict[str, dict] = {}
    if not actionability.empty and "opportunity_id" in actionability.columns:
        act = actionability.fillna("").drop_duplicates("opportunity_id", keep="last")
        act_map = {str(r["opportunity_id"]): r.to_dict() for _, r in act.iterrows()}

    jobs["semantic_fit"] = jobs["opportunity_id"].map(
        lambda oid: str(sem_map.get(str(oid), {}).get("fit", ""))
    )
    jobs["semantic_reasoning"] = jobs["opportunity_id"].map(
        lambda oid: str(sem_map.get(str(oid), {}).get("reasoning", ""))
    )
    jobs["actionable"] = jobs["opportunity_id"].map(
        lambda oid: _as_bool(act_map.get(str(oid), {}).get("actionable", False))
    )
    jobs["actionability_warnings"] = jobs["opportunity_id"].map(
        lambda oid: str(act_map.get(str(oid), {}).get("warnings", ""))
    )

    excluded: list[dict[str, str]] = []

    def reject(row: pd.Series, reason: str) -> None:
        excluded.append({
            "opportunity_id": str(row.get("opportunity_id", "")),
            "company": str(row.get("company", "")),
            "title": str(row.get("title", "")),
            "excluded_reason": reason,
        })

    keep_indices: list[int] = []
    for idx, row in jobs.iterrows():
        if str(row.get("semantic_fit", "")) != "Strong":
            reject(row, "not_strong")
            continue
        if not bool(row.get("actionable", False)):
            reason = str(act_map.get(str(row.get("opportunity_id", "")), {}).get("blockers", "")) or "not_actionable"
            reject(row, f"actionability:{reason}")
            continue
        if _bad_company(row.get("company", "")):
            reject(row, "data_quality:invalid_company")
            continue
        geography = _geography_blocker(row)
        if geography:
            reject(row, geography)
            continue
        seniority = _seniority_blocker(row.get("title", ""))
        if seniority:
            reject(row, seniority)
            continue
        keep_indices.append(idx)

    pool = jobs.loc[keep_indices].copy() if keep_indices else jobs.iloc[0:0].copy()
    pool["job_id"] = pool["opportunity_id"]
    pool = pool.reindex(columns=OUTPUT_COLUMNS, fill_value="").reset_index(drop=True)
    excluded_df = pd.DataFrame(excluded).reindex(columns=EXCLUDED_COLUMNS, fill_value="")
    return pool, excluded_df


def main() -> None:
    parser = argparse.ArgumentParser(description="Promote shadow C/J outputs into a clean live J eligible pool")
    parser.add_argument("--candidates", required=True)
    parser.add_argument("--semantic", required=True)
    parser.add_argument("--actionability", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--excluded-out", required=True)
    args = parser.parse_args()

    pool, excluded = build_live_pool(
        _read(Path(args.candidates)),
        _read(Path(args.semantic)),
        _read(Path(args.actionability)),
    )
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    pool.to_csv(out, index=False)
    excluded_path = Path(args.excluded_out)
    excluded_path.parent.mkdir(parents=True, exist_ok=True)
    excluded.to_csv(excluded_path, index=False)
    print(f"live J eligible pool: {len(pool)}")
    if not excluded.empty:
        print(excluded["excluded_reason"].value_counts().to_string())


if __name__ == "__main__":
    main()
