"""Prepare the candidate pool that is allowed to enter regular J.

Regular J is a fresh Apply shortlist, not a catalogue. Guardrails here are
identity/distribution rules, not semantic-fit inference:
- anything manually added in B is already Applied and cannot re-enter J;
- anything already reviewed in J stays in history and cannot re-enter J;
- Big Four is routed to a separate batch by default;
- A=Exclude remains handled by the J selector itself.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from sourcing.aggregate_candidates_shadow import _normalise_url, _norm_text
from sourcing.build_semantic_fit_queue import _company_maps, _load_company_universe, _norm

BIG4_TOKENS = (
    "deloitte",
    "kpmg",
    "pwc",
    "pricewaterhousecoopers",
    "eyparthenon",
    "ernstyoung",
)


def _read(path: Path) -> pd.DataFrame:
    if not path.exists() or path.stat().st_size == 0:
        return pd.DataFrame()
    try:
        return pd.read_csv(path).fillna("")
    except (pd.errors.EmptyDataError, pd.errors.ParserError):
        return pd.DataFrame()


def _identity_keys(frame: pd.DataFrame) -> tuple[set[str], set[str]]:
    urls: set[str] = set()
    roles: set[str] = set()
    if frame.empty:
        return urls, roles
    for _, row in frame.iterrows():
        url = _normalise_url(row.get("job_url", "") or row.get("company_url", "") or row.get("linkedin_url", ""))
        if url:
            urls.add(url)
        company = _norm_text(row.get("canonical_company_id", "") or row.get("company", ""))
        title = _norm_text(row.get("title", ""))
        if company and title:
            roles.add(f"{company}:{title}")
    return urls, roles


def _reviewed_history(history: pd.DataFrame) -> pd.DataFrame:
    if history.empty:
        return history
    h = history.fillna("").copy()
    for col in ["action", "company_feedback", "role_feedback", "user_comment", "application_stage"]:
        if col not in h.columns:
            h[col] = ""
    actioned = ~h["action"].astype(str).str.strip().isin({"", "New"})
    feedback = (
        ~h["company_feedback"].astype(str).str.strip().isin({"", "Not rated"})
        | ~h["role_feedback"].astype(str).str.strip().isin({"", "Not rated"})
    )
    commented = h["user_comment"].astype(str).str.strip().ne("")
    staged = ~h["application_stage"].astype(str).str.strip().isin({"", "Not applied"})
    return h[actioned | feedback | commented | staged].copy()


def _looks_big4(row: pd.Series, category: str) -> bool:
    if category == "Big Four":
        return True
    company_key = _norm_text(row.get("canonical_company_id", "") or row.get("company", ""))
    if any(token in company_key for token in BIG4_TOKENS):
        return True
    # EY is too short for a generic substring check. Restrict it to canonical
    # company/name forms that clearly identify the firm rather than arbitrary words.
    raw_company = str(row.get("company", "")).strip().lower()
    canonical = _norm_text(row.get("canonical_company_id", ""))
    return canonical in {"ey", "eyparthenon"} or raw_company in {"ey", "ey parthenon"}


def prepare_j_candidates(
    candidates: pd.DataFrame,
    history: pd.DataFrame,
    manual_b: pd.DataFrame,
    company_universe: pd.DataFrame | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    if candidates.empty:
        return candidates.copy(), pd.DataFrame(columns=["candidate_id", "company", "title", "excluded_reason"])

    jobs = candidates.fillna("").copy()
    for col in ["candidate_id", "company", "canonical_company_id", "title", "job_url"]:
        if col not in jobs.columns:
            jobs[col] = ""

    b_urls, b_roles = _identity_keys(manual_b)
    reviewed = _reviewed_history(history)
    h_urls, h_roles = _identity_keys(reviewed)

    universe = _load_company_universe() if company_universe is None else company_universe.fillna("")
    exact, aliases = _company_maps(universe) if not universe.empty else ({}, {})

    def company_category(row: pd.Series) -> str:
        key = _norm(row.get("company", ""))
        found = exact.get(key) or aliases.get(key) or {}
        return str(found.get("company_category", ""))

    reasons: list[str] = []
    keep: list[bool] = []
    for _, row in jobs.iterrows():
        url = _normalise_url(row.get("job_url", ""))
        company = _norm_text(row.get("canonical_company_id", "") or row.get("company", ""))
        title = _norm_text(row.get("title", ""))
        role_key = f"{company}:{title}" if company and title else ""
        category = company_category(row)
        reason = ""
        if (url and url in b_urls) or (role_key and role_key in b_roles):
            reason = "manual_B_already_applied"
        elif (url and url in h_urls) or (role_key and role_key in h_roles):
            reason = "already_reviewed_history"
        elif _looks_big4(row, category):
            reason = "big4_separate_batch"
        reasons.append(reason)
        keep.append(not bool(reason))

    excluded = jobs.loc[[not x for x in keep], ["candidate_id", "company", "title"]].copy()
    excluded["excluded_reason"] = [r for r in reasons if r]
    allowed = jobs.loc[keep].copy().reset_index(drop=True)
    return allowed, excluded.reset_index(drop=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Apply regular-J identity/distribution guardrails")
    parser.add_argument("--candidates", required=True)
    parser.add_argument("--history", required=True)
    parser.add_argument("--manual-b", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--excluded-out", required=True)
    args = parser.parse_args()
    allowed, excluded = prepare_j_candidates(
        _read(Path(args.candidates)), _read(Path(args.history)), _read(Path(args.manual_b))
    )
    out = Path(args.out)
    excluded_out = Path(args.excluded_out)
    out.parent.mkdir(parents=True, exist_ok=True)
    excluded_out.parent.mkdir(parents=True, exist_ok=True)
    allowed.to_csv(out, index=False)
    excluded.to_csv(excluded_out, index=False)
    print(f"regular J guardrails: {len(allowed)} allowed; {len(excluded)} excluded")
    if not excluded.empty:
        print(excluded["excluded_reason"].value_counts().to_string())


if __name__ == "__main__":
    main()
