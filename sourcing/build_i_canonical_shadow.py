"""Build a canonical I latest-state snapshot and seed append-only event log.

Production `data/opportunity_history.csv` and B submissions remain untouched.
The shadow builder is deliberately idempotent:
- live I latest state has authority for records already present;
- B fills missing metadata but never overwrites a non-blank live I value;
- B-only opportunities are added as action=Interested;
- event-log rows are deterministic seeds, so re-running the migration does not
  create duplicate events.
"""
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path

import pandas as pd


HISTORY_COLUMNS = [
    "opportunity_id", "source_stream", "source_id", "first_seen_at", "decision_at",
    "title", "company", "canonical_company_id", "company_category", "market",
    "location", "job_url", "action", "company_feedback", "role_feedback",
    "user_comment", "company_rating_at_decision", "semantic_fit_at_decision",
    "semantic_reasoning_at_decision", "calibration_score_at_decision",
    "application_stage", "stage_updated_at", "outcome_reason", "history_notes",
]
EVENT_COLUMNS = [
    "event_id", "opportunity_id", "event_at", "event_type", "source_stream",
    "action", "application_stage", "company_feedback", "role_feedback",
    "user_comment", "outcome_reason", "notes",
]


def _read(path: Path) -> pd.DataFrame:
    if not path.exists() or path.stat().st_size == 0:
        return pd.DataFrame()
    try:
        return pd.read_csv(path).fillna("")
    except (pd.errors.EmptyDataError, pd.errors.ParserError):
        return pd.DataFrame()


def _text(value: object) -> str:
    return str(value or "").strip()


def _normalise_history(history: pd.DataFrame) -> pd.DataFrame:
    if history.empty:
        return pd.DataFrame(columns=HISTORY_COLUMNS)
    out = history.fillna("").copy()
    for col in HISTORY_COLUMNS:
        if col not in out.columns:
            out[col] = ""
    out = out[out["opportunity_id"].astype(str).str.strip().ne("")].copy()
    return out.drop_duplicates("opportunity_id", keep="last").reindex(columns=HISTORY_COLUMNS, fill_value="")


def _b_record(row: pd.Series) -> dict[str, str]:
    return {
        "opportunity_id": _text(row.get("submission_id", "")),
        "source_stream": "B",
        "source_id": _text(row.get("source_domain", "")) or "manual-intake",
        "first_seen_at": _text(row.get("submitted_at", "")),
        "decision_at": _text(row.get("submitted_at", "")),
        "title": _text(row.get("title", "")),
        "company": _text(row.get("company", "")),
        "canonical_company_id": _text(row.get("canonical_company_id", "")),
        "company_category": _text(row.get("company_category", "")),
        "market": _text(row.get("country", "")),
        "location": _text(row.get("location", "")),
        "job_url": _text(row.get("job_url", "")) or _text(row.get("company_url", "")) or _text(row.get("linkedin_url", "")),
        "action": "Interested",
        "company_feedback": "Not rated",
        "role_feedback": "Not rated",
        "user_comment": _text(row.get("user_comment", "")),
        "company_rating_at_decision": "",
        "semantic_fit_at_decision": "",
        "semantic_reasoning_at_decision": "",
        "calibration_score_at_decision": "",
        "application_stage": "",
        "stage_updated_at": "",
        "outcome_reason": "",
        "history_notes": "Seeded from Workstream B during canonical-I shadow migration",
    }


def build_canonical_i(history: pd.DataFrame, submissions: pd.DataFrame) -> pd.DataFrame:
    latest = _normalise_history(history).set_index("opportunity_id", drop=False)

    if not submissions.empty and "submission_id" in submissions.columns:
        b = submissions.fillna("").drop_duplicates("submission_id", keep="last")
        for _, row in b.iterrows():
            rec = _b_record(row)
            oid = rec["opportunity_id"]
            if not oid:
                continue
            if oid not in latest.index:
                latest.loc[oid] = pd.Series(rec)
                continue
            # Live I wins. B is allowed only to fill metadata that is still blank.
            current = latest.loc[oid].copy()
            for col, value in rec.items():
                if col == "opportunity_id":
                    continue
                if not _text(current.get(col, "")) and _text(value):
                    current[col] = value
            latest.loc[oid] = current

    if latest.empty:
        return pd.DataFrame(columns=HISTORY_COLUMNS)
    out = latest.reset_index(drop=True).reindex(columns=HISTORY_COLUMNS, fill_value="").fillna("")
    out["_sort"] = pd.to_datetime(out["first_seen_at"], errors="coerce", utc=True)
    return out.sort_values(["_sort", "opportunity_id"], ascending=[False, True], na_position="last").drop(columns="_sort").reset_index(drop=True)


def _event_id(oid: str, event_type: str, event_at: str, action: str = "", stage: str = "") -> str:
    raw = "|".join([oid, event_type, event_at, action, stage])
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:20]


def build_event_seed(canonical_i: pd.DataFrame) -> pd.DataFrame:
    if canonical_i.empty:
        return pd.DataFrame(columns=EVENT_COLUMNS)
    events: list[dict[str, str]] = []

    def add(row: pd.Series, event_type: str, event_at: str, notes: str) -> None:
        oid = _text(row.get("opportunity_id", ""))
        if not oid or not event_at:
            return
        action = _text(row.get("action", ""))
        stage = _text(row.get("application_stage", ""))
        events.append({
            "event_id": _event_id(oid, event_type, event_at, action if event_type == "decision" else "", stage if event_type == "application_stage" else ""),
            "opportunity_id": oid,
            "event_at": event_at,
            "event_type": event_type,
            "source_stream": _text(row.get("source_stream", "")),
            "action": action if event_type == "decision" else "",
            "application_stage": stage if event_type == "application_stage" else "",
            "company_feedback": _text(row.get("company_feedback", "")) if event_type == "decision" else "",
            "role_feedback": _text(row.get("role_feedback", "")) if event_type == "decision" else "",
            "user_comment": _text(row.get("user_comment", "")) if event_type == "decision" else "",
            "outcome_reason": _text(row.get("outcome_reason", "")) if event_type == "application_stage" else "",
            "notes": notes,
        })

    for _, row in canonical_i.fillna("").iterrows():
        add(row, "opportunity_created", _text(row.get("first_seen_at", "")), "Seeded from latest-state I/B snapshot")
        action = _text(row.get("action", ""))
        if action and action.lower() not in {"new", "unrated"}:
            add(row, "decision", _text(row.get("decision_at", "")) or _text(row.get("first_seen_at", "")), "Seeded decision from latest-state snapshot")
        stage = _text(row.get("application_stage", ""))
        if stage:
            add(row, "application_stage", _text(row.get("stage_updated_at", "")) or _text(row.get("decision_at", "")), "Seeded current application stage; earlier intermediate stages may predate event logging")

    out = pd.DataFrame(events).reindex(columns=EVENT_COLUMNS, fill_value="").fillna("")
    if out.empty:
        return out
    out = out.drop_duplicates("event_id", keep="first")
    out["_sort"] = pd.to_datetime(out["event_at"], errors="coerce", utc=True)
    return out.sort_values(["_sort", "event_id"], ascending=[True, True], na_position="last").drop(columns="_sort").reset_index(drop=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--history", required=True)
    parser.add_argument("--submissions", required=True)
    parser.add_argument("--history-out", required=True)
    parser.add_argument("--events-out", required=True)
    args = parser.parse_args()

    canonical = build_canonical_i(_read(Path(args.history)), _read(Path(args.submissions)))
    events = build_event_seed(canonical)
    hist_out = Path(args.history_out)
    event_out = Path(args.events_out)
    hist_out.parent.mkdir(parents=True, exist_ok=True)
    event_out.parent.mkdir(parents=True, exist_ok=True)
    canonical.to_csv(hist_out, index=False)
    events.to_csv(event_out, index=False)
    b_count = int(canonical["source_stream"].eq("B").sum()) if len(canonical) else 0
    print(f"canonical I shadow: {len(canonical)} latest-state rows ({b_count} B-source rows)")
    print(f"event seed: {len(events)} deterministic events")


if __name__ == "__main__":
    main()
