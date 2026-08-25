"""Build factual learning evidence tables from canonical I shadow state.

No inference happens here. In particular this module does NOT:
- assign or change A/B/C/Exclude company ratings;
- assign or change C Strong/Moderate/Weak semantic fit;
- calculate an H attainability score;
- change G sourcing weights.

It only separates the factual evidence already stored in I into clean downstream
inputs for A, C and H so later policy/model choices can be audited independently.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd


A_EVENT_COLUMNS = [
    "opportunity_id", "decision_at", "canonical_company_id", "company",
    "company_category", "market", "company_feedback", "action", "user_comment",
]
A_SUMMARY_COLUMNS = [
    "canonical_company_id", "company", "company_category", "evidence_rows",
    "positive", "neutral", "negative", "latest_feedback_at",
]
C_EVENT_COLUMNS = [
    "opportunity_id", "decision_at", "source_stream", "title", "company",
    "company_category", "market", "action", "role_feedback", "c_signal",
    "user_comment", "semantic_fit_at_decision", "semantic_reasoning_at_decision",
]
H_EVENT_COLUMNS = [
    "opportunity_id", "company", "canonical_company_id", "company_category",
    "title", "market", "application_stage", "stage_updated_at", "outcome_reason",
    "h_evidence",
]
H_SUMMARY_COLUMNS = [
    "dimension", "value", "applications", "rejected_pre_screen", "reached_interview",
    "reached_case", "reached_final", "offers", "withdrawn",
]


def _read(path: Path) -> pd.DataFrame:
    if not path.exists() or path.stat().st_size == 0:
        return pd.DataFrame()
    try:
        return pd.read_csv(path).fillna("")
    except (pd.errors.EmptyDataError, pd.errors.ParserError):
        return pd.DataFrame()


def _signal(value: object) -> str:
    return {
        "positive": "positive", "neutral": "neutral", "negative": "negative",
    }.get(str(value or "").strip().lower(), "")


def _c_signal(action: object, role_feedback: object) -> str:
    explicit = _signal(role_feedback)
    if explicit:
        return explicit
    action_text = str(action or "").strip().lower()
    if action_text in {"apply", "interested"}:
        return "positive"
    if action_text == "maybe":
        return "neutral"
    if action_text in {"skip", "pass"}:
        return "negative"
    return ""


def _h_evidence(stage: object) -> str:
    value = str(stage or "").strip()
    return {
        "Offer": "offer",
        "Final": "reached_final",
        "Case": "reached_case",
        "Lost after case": "reached_case",
        "1st interview": "reached_interview",
        "Lost after 1st": "reached_interview",
        "Rejected pre-screen": "rejected_pre_screen",
        "Withdrawn": "withdrawn",
        "Applied": "applied_pending",
    }.get(value, "")


def build_a_evidence(history: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    if history.empty:
        return pd.DataFrame(columns=A_EVENT_COLUMNS), pd.DataFrame(columns=A_SUMMARY_COLUMNS)
    frame = history.fillna("").copy()
    for col in A_EVENT_COLUMNS:
        if col not in frame.columns:
            frame[col] = ""
    frame["_signal"] = frame["company_feedback"].map(_signal)
    events = frame[frame["_signal"].ne("")].copy()
    if events.empty:
        return pd.DataFrame(columns=A_EVENT_COLUMNS), pd.DataFrame(columns=A_SUMMARY_COLUMNS)
    events = events.reindex(columns=A_EVENT_COLUMNS + ["_signal"], fill_value="")

    rows: list[dict[str, object]] = []
    # Prefer canonical ID; fall back to literal company only for auditability.
    events["_company_key"] = events.apply(
        lambda r: str(r.get("canonical_company_id", "")).strip() or f"name:{str(r.get('company', '')).strip().lower()}", axis=1
    )
    for _, group in events.groupby("_company_key", sort=False):
        latest = group.copy()
        latest["_dt"] = pd.to_datetime(latest["decision_at"], errors="coerce", utc=True)
        latest = latest.sort_values("_dt", ascending=False, na_position="last")
        first = latest.iloc[0]
        counts = group["_signal"].value_counts().to_dict()
        rows.append({
            "canonical_company_id": str(first.get("canonical_company_id", "")),
            "company": str(first.get("company", "")),
            "company_category": str(first.get("company_category", "")),
            "evidence_rows": len(group),
            "positive": int(counts.get("positive", 0)),
            "neutral": int(counts.get("neutral", 0)),
            "negative": int(counts.get("negative", 0)),
            "latest_feedback_at": str(first.get("decision_at", "")),
        })
    summary = pd.DataFrame(rows).reindex(columns=A_SUMMARY_COLUMNS, fill_value="")
    return events.reindex(columns=A_EVENT_COLUMNS, fill_value="").reset_index(drop=True), summary


def build_c_evidence(history: pd.DataFrame) -> pd.DataFrame:
    if history.empty:
        return pd.DataFrame(columns=C_EVENT_COLUMNS)
    frame = history.fillna("").copy()
    for col in C_EVENT_COLUMNS:
        if col not in frame.columns and col != "c_signal":
            frame[col] = ""
    frame["c_signal"] = frame.apply(lambda r: _c_signal(r.get("action", ""), r.get("role_feedback", "")), axis=1)
    frame = frame[frame["c_signal"].ne("")].copy()
    return frame.reindex(columns=C_EVENT_COLUMNS, fill_value="").reset_index(drop=True)


def build_h_evidence(history: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    if history.empty:
        return pd.DataFrame(columns=H_EVENT_COLUMNS), pd.DataFrame(columns=H_SUMMARY_COLUMNS)
    frame = history.fillna("").copy()
    for col in H_EVENT_COLUMNS:
        if col not in frame.columns and col != "h_evidence":
            frame[col] = ""
    frame["h_evidence"] = frame["application_stage"].map(_h_evidence)
    events = frame[frame["h_evidence"].ne("")].reindex(columns=H_EVENT_COLUMNS, fill_value="").copy()
    if events.empty:
        return events, pd.DataFrame(columns=H_SUMMARY_COLUMNS)

    rows: list[dict[str, object]] = []
    dimensions = {
        "company": events["canonical_company_id"].where(events["canonical_company_id"].ne(""), events["company"]),
        "company_category": events["company_category"],
        "market": events["market"],
    }
    for dimension, values in dimensions.items():
        temp = events.copy()
        temp["_value"] = values.astype(str).str.strip()
        temp = temp[temp["_value"].ne("")]
        for value, group in temp.groupby("_value", sort=False):
            evidence = set(group["h_evidence"].astype(str))
            # These are factual counts by current outcome stage, not funnel-derived
            # estimates. We intentionally do not infer missing intermediate stages.
            counts = group["h_evidence"].value_counts().to_dict()
            rows.append({
                "dimension": dimension,
                "value": value,
                "applications": len(group),
                "rejected_pre_screen": int(counts.get("rejected_pre_screen", 0)),
                "reached_interview": int(counts.get("reached_interview", 0)),
                "reached_case": int(counts.get("reached_case", 0)),
                "reached_final": int(counts.get("reached_final", 0)),
                "offers": int(counts.get("offer", 0)),
                "withdrawn": int(counts.get("withdrawn", 0)),
            })
    summary = pd.DataFrame(rows).reindex(columns=H_SUMMARY_COLUMNS, fill_value="")
    return events.reset_index(drop=True), summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--history", required=True)
    parser.add_argument("--a-events-out", required=True)
    parser.add_argument("--a-summary-out", required=True)
    parser.add_argument("--c-events-out", required=True)
    parser.add_argument("--h-events-out", required=True)
    parser.add_argument("--h-summary-out", required=True)
    args = parser.parse_args()

    history = _read(Path(args.history))
    a_events, a_summary = build_a_evidence(history)
    c_events = build_c_evidence(history)
    h_events, h_summary = build_h_evidence(history)

    outputs = [
        (a_events, args.a_events_out), (a_summary, args.a_summary_out),
        (c_events, args.c_events_out), (h_events, args.h_events_out),
        (h_summary, args.h_summary_out),
    ]
    for frame, raw_path in outputs:
        path = Path(raw_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        frame.to_csv(path, index=False)

    print(f"A factual feedback events: {len(a_events)} across {len(a_summary)} companies")
    print(f"C factual preference events: {len(c_events)}")
    print(f"H factual application outcomes: {len(h_events)} across {len(h_summary)} grouped rows")


if __name__ == "__main__":
    main()
