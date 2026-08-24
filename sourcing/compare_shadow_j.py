"""Explain every difference between today's live curated J reference and shadow J.

This is a migration audit, not production logic. It tells us why a currently
visible J role is absent from the future Strong/actionable/quota shortlist and
which new shadow roles would appear. The report is deliberately explicit so a
cutover cannot silently lose a good role.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd


LIVE_COLUMNS = [
    "job_id", "company", "title", "market", "live_semantic_fit",
    "in_shadow_g", "shadow_semantic_fit", "shadow_actionable",
    "shadow_blockers", "history_action", "in_shadow_j", "explanation",
]

NEW_COLUMNS = [
    "opportunity_id", "company", "title", "country_bucket", "company_rating",
    "selection_origin", "priority_order", "explanation",
]


def _read(path: Path) -> pd.DataFrame:
    if not path.exists() or path.stat().st_size == 0:
        return pd.DataFrame()
    try:
        return pd.read_csv(path).fillna("")
    except (pd.errors.EmptyDataError, pd.errors.ParserError):
        return pd.DataFrame()


def _bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"true", "1", "yes", "y"}


def compare_live_to_shadow(
    live_j: pd.DataFrame,
    candidates: pd.DataFrame,
    semantic: pd.DataFrame,
    actionability: pd.DataFrame,
    history: pd.DataFrame,
    shadow_j: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    if live_j.empty:
        live_report = pd.DataFrame(columns=LIVE_COLUMNS)
    else:
        candidates = candidates.fillna("").copy()
        semantic = semantic.fillna("").copy()
        actionability = actionability.fillna("").copy()
        history = history.fillna("").copy()
        shadow_j = shadow_j.fillna("").copy()
        live_j = live_j.fillna("").copy()

        candidate_ids = set(candidates.get("job_id", pd.Series(dtype=object)).astype(str))
        semantic_map = {}
        if {"opportunity_id", "fit"}.issubset(semantic.columns):
            semantic_map = dict(zip(semantic["opportunity_id"].astype(str), semantic["fit"].astype(str)))
        act_map = {}
        if "opportunity_id" in actionability.columns:
            act_map = {
                str(row["opportunity_id"]): row.to_dict()
                for _, row in actionability.drop_duplicates("opportunity_id", keep="last").iterrows()
            }
        history_map = {}
        if "opportunity_id" in history.columns:
            latest = history.drop_duplicates("opportunity_id", keep="last")
            history_map = dict(zip(latest["opportunity_id"].astype(str), latest.get("action", "")))
        shadow_ids = set(shadow_j.get("opportunity_id", pd.Series(dtype=object)).astype(str))

        rows = []
        for _, row in live_j.iterrows():
            oid = str(row.get("job_id", "")).strip()
            in_g = oid in candidate_ids
            sem_fit = str(semantic_map.get(oid, ""))
            act_rec = act_map.get(oid, {})
            actionable = _bool(act_rec.get("actionable", False)) if act_rec else False
            blockers = str(act_rec.get("blockers", ""))
            hist_action = str(history_map.get(oid, ""))
            in_shadow_j = oid in shadow_ids
            live_fit = str(row.get("semantic_fit", ""))

            if in_shadow_j:
                explanation = "kept_in_shadow_j"
            elif not in_g:
                explanation = "missing_from_shadow_g_sources"
            elif sem_fit and sem_fit != "Strong":
                explanation = f"semantic_{sem_fit.lower()}_excluded"
            elif not sem_fit:
                explanation = "no_canonical_semantic_fit_yet"
            elif not actionable:
                explanation = "actionability_blocked" if blockers else "actionability_not_confirmed"
            elif hist_action in {"Apply", "Skip", "Pass"}:
                explanation = f"history_{hist_action.lower()}_removed_from_working_queue"
            else:
                explanation = "eligible_but_not_selected_limit_quota_or_company_cap"

            rows.append({
                "job_id": oid,
                "company": str(row.get("company", "")),
                "title": str(row.get("title", "")),
                "market": str(row.get("market", "")),
                "live_semantic_fit": live_fit,
                "in_shadow_g": in_g,
                "shadow_semantic_fit": sem_fit,
                "shadow_actionable": actionable,
                "shadow_blockers": blockers,
                "history_action": hist_action,
                "in_shadow_j": in_shadow_j,
                "explanation": explanation,
            })

        live_report = pd.DataFrame(rows).reindex(columns=LIVE_COLUMNS, fill_value="")

    live_ids = set(live_j.get("job_id", pd.Series(dtype=object)).astype(str)) if not live_j.empty else set()
    new_rows = []
    if not shadow_j.empty:
        for _, row in shadow_j.fillna("").iterrows():
            oid = str(row.get("opportunity_id", ""))
            if oid in live_ids:
                continue
            new_rows.append({
                "opportunity_id": oid,
                "company": str(row.get("company", "")),
                "title": str(row.get("title", "")),
                "country_bucket": str(row.get("country_bucket", "")),
                "company_rating": str(row.get("company_rating", "")),
                "selection_origin": str(row.get("selection_origin", "")),
                "priority_order": row.get("priority_order", ""),
                "explanation": "new_shadow_j_role",
            })
    new_report = pd.DataFrame(new_rows).reindex(columns=NEW_COLUMNS, fill_value="")
    return live_report, new_report


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit differences between live J reference and shadow J")
    parser.add_argument("--live-j", required=True)
    parser.add_argument("--candidates", required=True)
    parser.add_argument("--semantic", required=True)
    parser.add_argument("--actionability", required=True)
    parser.add_argument("--history", required=True)
    parser.add_argument("--shadow-j", required=True)
    parser.add_argument("--live-report-out", required=True)
    parser.add_argument("--new-report-out", required=True)
    args = parser.parse_args()

    live_report, new_report = compare_live_to_shadow(
        _read(Path(args.live_j)),
        _read(Path(args.candidates)),
        _read(Path(args.semantic)),
        _read(Path(args.actionability)),
        _read(Path(args.history)),
        _read(Path(args.shadow_j)),
    )
    live_out = Path(args.live_report_out)
    new_out = Path(args.new_report_out)
    live_out.parent.mkdir(parents=True, exist_ok=True)
    new_out.parent.mkdir(parents=True, exist_ok=True)
    live_report.to_csv(live_out, index=False)
    new_report.to_csv(new_out, index=False)

    kept = int(live_report["in_shadow_j"].map(_bool).sum()) if not live_report.empty else 0
    print(f"live J roles kept by shadow J: {kept}/{len(live_report)}")
    if not live_report.empty:
        print("live exclusions by reason:")
        print(live_report.loc[~live_report["in_shadow_j"].map(_bool), "explanation"].value_counts().to_string())
    print(f"new shadow-J roles not in current live reference: {len(new_report)}")


if __name__ == "__main__":
    main()
