"""Reconcile production I latest-state history, append-only events and A/C/H evidence.

I is factual memory. This module never changes A ratings, C semantic fit, H scores
or G/J selection. It only:
- ensures manual B submissions exist in canonical I as Apply/Applied;
- preserves one latest-state row per opportunity;
- appends lifecycle events when a decision or application stage changes;
- derives factual downstream evidence tables for A, C and H.
"""
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path

import pandas as pd

HISTORY_COLUMNS = [
    "opportunity_id", "source_stream", "source_id", "first_seen_at", "decision_at",
    "title", "company", "canonical_company_id", "company_category", "market", "location",
    "job_url", "action", "company_feedback", "role_feedback", "user_comment",
    "company_rating_at_decision", "semantic_fit_at_decision", "semantic_reasoning_at_decision",
    "calibration_score_at_decision", "application_stage", "stage_updated_at",
    "outcome_reason", "history_notes",
]
EVENT_COLUMNS = [
    "event_id", "opportunity_id", "event_at", "event_type", "source_stream",
    "action", "application_stage", "company_feedback", "role_feedback",
    "user_comment", "outcome_reason", "notes",
]
A_EVENT_COLUMNS = [
    "event_id", "opportunity_id", "event_at", "canonical_company_id", "company",
    "company_category", "market", "company_feedback", "action", "user_comment",
]
A_SUMMARY_COLUMNS = [
    "canonical_company_id", "company", "company_category", "evidence_rows",
    "positive", "neutral", "negative", "latest_feedback_at", "evidence_direction",
]
C_EVENT_COLUMNS = [
    "event_id", "opportunity_id", "event_at", "source_stream", "title", "company",
    "company_category", "market", "action", "role_feedback", "c_signal",
    "evidence_type", "user_comment", "semantic_fit_at_decision",
    "semantic_reasoning_at_decision",
]
H_EVENT_COLUMNS = [
    "event_id", "opportunity_id", "event_at", "company", "canonical_company_id",
    "company_category", "title", "market", "application_stage", "outcome_reason",
    "h_evidence",
]
H_SUMMARY_COLUMNS = [
    "dimension", "value", "applications", "rejected_pre_screen", "reached_interview",
    "reached_case", "reached_final", "offers", "withdrawn",
]


def _read(path: Path, columns: list[str] | None = None) -> pd.DataFrame:
    if not path.exists() or path.stat().st_size == 0:
        return pd.DataFrame(columns=columns or [])
    try:
        frame = pd.read_csv(path).fillna("")
    except (pd.errors.EmptyDataError, pd.errors.ParserError):
        return pd.DataFrame(columns=columns or [])
    if columns is not None:
        frame = frame.reindex(columns=columns, fill_value="")
    return frame


def _text(value: object) -> str:
    return str(value or "").strip()


def _normalise_history(history: pd.DataFrame) -> pd.DataFrame:
    out = history.reindex(columns=HISTORY_COLUMNS, fill_value="").fillna("").copy()
    if out.empty:
        return out
    out = out[out["opportunity_id"].astype(str).str.strip().ne("")]
    return out.drop_duplicates("opportunity_id", keep="last").reset_index(drop=True)


def _b_record(row: pd.Series) -> dict[str, str]:
    submitted_at = _text(row.get("submitted_at", ""))
    sid = _text(row.get("submission_id", ""))
    return {
        "opportunity_id": f"B:{sid}" if sid else "",
        "source_stream": "B",
        "source_id": _text(row.get("source_domain", "")) or "manual-intake",
        "first_seen_at": submitted_at,
        "decision_at": submitted_at,
        "title": _text(row.get("title", "")),
        "company": _text(row.get("company", "")),
        "canonical_company_id": _text(row.get("canonical_company_id", "")),
        "company_category": _text(row.get("company_category", "")),
        "market": _text(row.get("country", "")),
        "location": _text(row.get("location", "")),
        "job_url": _text(row.get("job_url", "")) or _text(row.get("company_url", "")) or _text(row.get("linkedin_url", "")),
        "action": "Apply",
        "company_feedback": "Not rated",
        "role_feedback": "Positive",
        "user_comment": _text(row.get("user_comment", "")),
        "company_rating_at_decision": "",
        "semantic_fit_at_decision": "",
        "semantic_reasoning_at_decision": _text(row.get("role_profile", "")),
        "calibration_score_at_decision": "",
        "application_stage": "Applied",
        "stage_updated_at": submitted_at,
        "outcome_reason": "",
        "history_notes": "Canonical B manual application intake",
    }


def reconcile_history(history: pd.DataFrame, submissions: pd.DataFrame) -> pd.DataFrame:
    latest = _normalise_history(history).set_index("opportunity_id", drop=False)
    if not submissions.empty and "submission_id" in submissions.columns:
        for _, row in submissions.fillna("").drop_duplicates("submission_id", keep="last").iterrows():
            rec = _b_record(row)
            oid = rec["opportunity_id"]
            if not oid:
                continue
            if oid not in latest.index:
                latest.loc[oid] = pd.Series(rec)
                continue
            current = latest.loc[oid].copy()
            # B owns identity/metadata for its own row, but must never roll an
            # application backwards after the user advances it in I.
            for col in [
                "source_stream", "source_id", "title", "company", "canonical_company_id",
                "company_category", "market", "location", "job_url",
            ]:
                if not _text(current.get(col, "")) and _text(rec.get(col, "")):
                    current[col] = rec[col]
            if _text(rec.get("user_comment", "")):
                current["user_comment"] = rec["user_comment"]
            current["source_stream"] = "B"
            current["action"] = "Apply"
            if _text(current.get("role_feedback", "")).lower() in {"", "not rated"}:
                current["role_feedback"] = "Positive"
            if _text(current.get("application_stage", "")) in {"", "Not applied"}:
                current["application_stage"] = "Applied"
                current["stage_updated_at"] = _text(current.get("stage_updated_at", "")) or rec["stage_updated_at"]
            current["first_seen_at"] = _text(current.get("first_seen_at", "")) or rec["first_seen_at"]
            current["decision_at"] = _text(current.get("decision_at", "")) or rec["decision_at"]
            latest.loc[oid] = current
    if latest.empty:
        return pd.DataFrame(columns=HISTORY_COLUMNS)
    out = latest.reset_index(drop=True).reindex(columns=HISTORY_COLUMNS, fill_value="").fillna("")
    out["_sort"] = pd.to_datetime(out["first_seen_at"], errors="coerce", utc=True)
    return out.sort_values(["_sort", "opportunity_id"], ascending=[False, True], na_position="last").drop(columns="_sort").reset_index(drop=True)


def _event_id(*parts: object) -> str:
    raw = "|".join(_text(x) for x in parts)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:20]


def _payload(row: pd.Series, event_type: str) -> tuple[str, ...]:
    if event_type == "decision":
        return tuple(_text(row.get(c, "")) for c in ["action", "company_feedback", "role_feedback", "user_comment"])
    if event_type == "application_stage":
        return tuple(_text(row.get(c, "")) for c in ["application_stage", "outcome_reason", "history_notes"])
    return ()


def _latest_event(events: pd.DataFrame, oid: str, event_type: str) -> pd.Series | None:
    if events.empty:
        return None
    subset = events[(events["opportunity_id"].astype(str) == oid) & (events["event_type"].astype(str) == event_type)].copy()
    if subset.empty:
        return None
    subset["_dt"] = pd.to_datetime(subset["event_at"], errors="coerce", utc=True)
    subset = subset.sort_values(["_dt", "event_id"], ascending=[True, True], na_position="first")
    return subset.iloc[-1]


def _make_event(row: pd.Series, event_type: str, event_at: str, note: str) -> dict[str, str]:
    action = _text(row.get("action", "")) if event_type == "decision" else ""
    stage = _text(row.get("application_stage", "")) if event_type == "application_stage" else ""
    cf = _text(row.get("company_feedback", "")) if event_type == "decision" else ""
    rf = _text(row.get("role_feedback", "")) if event_type == "decision" else ""
    comment = _text(row.get("user_comment", "")) if event_type == "decision" else ""
    outcome = _text(row.get("outcome_reason", "")) if event_type == "application_stage" else ""
    notes = _text(row.get("history_notes", "")) if event_type == "application_stage" else note
    oid = _text(row.get("opportunity_id", ""))
    return {
        "event_id": _event_id(oid, event_type, event_at, action, stage, cf, rf, comment, outcome, notes),
        "opportunity_id": oid,
        "event_at": event_at,
        "event_type": event_type,
        "source_stream": _text(row.get("source_stream", "")),
        "action": action,
        "application_stage": stage,
        "company_feedback": cf,
        "role_feedback": rf,
        "user_comment": comment,
        "outcome_reason": outcome,
        "notes": notes,
    }


def reconcile_events(history: pd.DataFrame, events: pd.DataFrame) -> pd.DataFrame:
    out = events.reindex(columns=EVENT_COLUMNS, fill_value="").fillna("").copy()
    additions: list[dict[str, str]] = []
    for _, row in history.fillna("").iterrows():
        oid = _text(row.get("opportunity_id", ""))
        if not oid:
            continue
        if _latest_event(out, oid, "opportunity_created") is None:
            at = _text(row.get("first_seen_at", "")) or _text(row.get("decision_at", ""))
            if at:
                additions.append(_make_event(row, "opportunity_created", at, "Opportunity entered canonical I"))
        action = _text(row.get("action", ""))
        if action and action.lower() not in {"new", "unrated"}:
            latest = _latest_event(pd.concat([out, pd.DataFrame(additions)], ignore_index=True), oid, "decision")
            if latest is None or _payload(latest, "decision") != _payload(row, "decision"):
                at = _text(row.get("decision_at", "")) or _text(row.get("first_seen_at", ""))
                if at:
                    additions.append(_make_event(row, "decision", at, "Decision/feedback snapshot"))
        stage = _text(row.get("application_stage", ""))
        if stage:
            current_events = pd.concat([out, pd.DataFrame(additions)], ignore_index=True)
            latest = _latest_event(current_events, oid, "application_stage")
            if latest is None or _payload(latest, "application_stage") != _payload(row, "application_stage"):
                at = _text(row.get("stage_updated_at", "")) or _text(row.get("decision_at", "")) or _text(row.get("first_seen_at", ""))
                if at:
                    additions.append(_make_event(row, "application_stage", at, "Application lifecycle snapshot"))
    if additions:
        out = pd.concat([out, pd.DataFrame(additions)], ignore_index=True, sort=False)
    out = out.reindex(columns=EVENT_COLUMNS, fill_value="").fillna("").drop_duplicates("event_id", keep="first")
    if out.empty:
        return out
    out["_sort"] = pd.to_datetime(out["event_at"], errors="coerce", utc=True)
    return out.sort_values(["_sort", "event_id"], ascending=[True, True], na_position="last").drop(columns="_sort").reset_index(drop=True)


def _history_map(history: pd.DataFrame) -> pd.DataFrame:
    if history.empty:
        return pd.DataFrame(columns=HISTORY_COLUMNS).set_index(pd.Index([], name="opportunity_id"))
    return history.drop_duplicates("opportunity_id", keep="last").set_index("opportunity_id")


def _signal(value: object) -> str:
    return {"positive": "positive", "neutral": "neutral", "negative": "negative"}.get(_text(value).lower(), "")


def _c_signal(action: object, role_feedback: object) -> tuple[str, str]:
    explicit = _signal(role_feedback)
    if explicit:
        return explicit, "explicit_role_feedback"
    a = _text(action).lower()
    if a == "apply":
        return "positive", "decision_action"
    if a == "maybe":
        return "neutral", "decision_action"
    if a in {"skip", "pass"}:
        return "negative", "decision_action"
    return "", ""


def _h_evidence(stage: object) -> str:
    return {
        "Offer": "offer", "Final": "reached_final", "Case": "reached_case",
        "Lost after case": "reached_case", "1st interview": "reached_interview",
        "Lost after 1st": "reached_interview", "Rejected pre-screen": "rejected_pre_screen",
        "Withdrawn": "withdrawn", "Applied": "applied_pending",
    }.get(_text(stage), "")


def build_learning(history: pd.DataFrame, events: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    meta = _history_map(history)
    decisions = events[events["event_type"].eq("decision")].copy() if not events.empty else pd.DataFrame(columns=EVENT_COLUMNS)
    stages = events[events["event_type"].eq("application_stage")].copy() if not events.empty else pd.DataFrame(columns=EVENT_COLUMNS)

    a_rows: list[dict[str, str]] = []
    c_rows: list[dict[str, str]] = []
    for _, event in decisions.iterrows():
        oid = _text(event.get("opportunity_id", ""))
        m = meta.loc[oid] if oid in meta.index else pd.Series(dtype=object)
        company_signal = _signal(event.get("company_feedback", ""))
        if company_signal:
            a_rows.append({
                "event_id": _text(event.get("event_id", "")), "opportunity_id": oid,
                "event_at": _text(event.get("event_at", "")),
                "canonical_company_id": _text(m.get("canonical_company_id", "")),
                "company": _text(m.get("company", "")), "company_category": _text(m.get("company_category", "")),
                "market": _text(m.get("market", "")), "company_feedback": _text(event.get("company_feedback", "")),
                "action": _text(event.get("action", "")), "user_comment": _text(event.get("user_comment", "")),
            })
        c_signal, evidence_type = _c_signal(event.get("action", ""), event.get("role_feedback", ""))
        if evidence_type or _text(event.get("user_comment", "")):
            if not evidence_type:
                evidence_type = "comment_only"
            c_rows.append({
                "event_id": _text(event.get("event_id", "")), "opportunity_id": oid,
                "event_at": _text(event.get("event_at", "")), "source_stream": _text(event.get("source_stream", "")),
                "title": _text(m.get("title", "")), "company": _text(m.get("company", "")),
                "company_category": _text(m.get("company_category", "")), "market": _text(m.get("market", "")),
                "action": _text(event.get("action", "")), "role_feedback": _text(event.get("role_feedback", "")),
                "c_signal": c_signal, "evidence_type": evidence_type,
                "user_comment": _text(event.get("user_comment", "")),
                "semantic_fit_at_decision": _text(m.get("semantic_fit_at_decision", "")),
                "semantic_reasoning_at_decision": _text(m.get("semantic_reasoning_at_decision", "")),
            })

    a_events = pd.DataFrame(a_rows).reindex(columns=A_EVENT_COLUMNS, fill_value="")
    a_summary_rows: list[dict[str, object]] = []
    if not a_events.empty:
        a_events["_signal"] = a_events["company_feedback"].map(_signal)
        a_events["_key"] = a_events.apply(lambda r: _text(r.get("canonical_company_id", "")) or f"name:{_text(r.get('company', '')).lower()}", axis=1)
        for _, group in a_events.groupby("_key", sort=False):
            g = group.copy(); g["_dt"] = pd.to_datetime(g["event_at"], errors="coerce", utc=True); g = g.sort_values("_dt", ascending=False, na_position="last")
            first = g.iloc[0]; counts = group["_signal"].value_counts().to_dict(); pos = int(counts.get("positive", 0)); neg = int(counts.get("negative", 0))
            direction = "positive pattern" if pos >= 2 and pos > neg else "negative pattern" if neg >= 2 and neg > pos else "mixed / insufficient"
            a_summary_rows.append({
                "canonical_company_id": _text(first.get("canonical_company_id", "")), "company": _text(first.get("company", "")),
                "company_category": _text(first.get("company_category", "")), "evidence_rows": len(group),
                "positive": pos, "neutral": int(counts.get("neutral", 0)), "negative": neg,
                "latest_feedback_at": _text(first.get("event_at", "")), "evidence_direction": direction,
            })
    a_summary = pd.DataFrame(a_summary_rows).reindex(columns=A_SUMMARY_COLUMNS, fill_value="")
    c_events = pd.DataFrame(c_rows).reindex(columns=C_EVENT_COLUMNS, fill_value="")

    h_rows: list[dict[str, str]] = []
    for _, event in stages.iterrows():
        oid = _text(event.get("opportunity_id", "")); m = meta.loc[oid] if oid in meta.index else pd.Series(dtype=object); evidence = _h_evidence(event.get("application_stage", ""))
        if not evidence:
            continue
        h_rows.append({
            "event_id": _text(event.get("event_id", "")), "opportunity_id": oid, "event_at": _text(event.get("event_at", "")),
            "company": _text(m.get("company", "")), "canonical_company_id": _text(m.get("canonical_company_id", "")),
            "company_category": _text(m.get("company_category", "")), "title": _text(m.get("title", "")), "market": _text(m.get("market", "")),
            "application_stage": _text(event.get("application_stage", "")), "outcome_reason": _text(event.get("outcome_reason", "")), "h_evidence": evidence,
        })
    h_events = pd.DataFrame(h_rows).reindex(columns=H_EVENT_COLUMNS, fill_value="")

    h_summary_rows: list[dict[str, object]] = []
    if not h_events.empty:
        progress = h_events.groupby("opportunity_id")["h_evidence"].agg(list).to_dict()
        dims = {
            "company": h_events["canonical_company_id"].where(h_events["canonical_company_id"].ne(""), h_events["company"]),
            "company_category": h_events["company_category"], "market": h_events["market"],
        }
        for dim, values in dims.items():
            temp = h_events[["opportunity_id"]].copy(); temp["value"] = values.astype(str).str.strip(); temp = temp[temp["value"].ne("")].drop_duplicates(["opportunity_id", "value"])
            for value, group in temp.groupby("value", sort=False):
                oids = set(group["opportunity_id"].astype(str)); flags = {oid: set(progress.get(oid, [])) for oid in oids}
                def anyflag(oid: str, names: set[str]) -> bool: return bool(flags[oid] & names)
                h_summary_rows.append({
                    "dimension": dim, "value": value, "applications": len(oids),
                    "rejected_pre_screen": sum(anyflag(o, {"rejected_pre_screen"}) for o in oids),
                    "reached_interview": sum(anyflag(o, {"reached_interview", "reached_case", "reached_final", "offer"}) for o in oids),
                    "reached_case": sum(anyflag(o, {"reached_case", "reached_final", "offer"}) for o in oids),
                    "reached_final": sum(anyflag(o, {"reached_final", "offer"}) for o in oids),
                    "offers": sum(anyflag(o, {"offer"}) for o in oids), "withdrawn": sum(anyflag(o, {"withdrawn"}) for o in oids),
                })
    h_summary = pd.DataFrame(h_summary_rows).reindex(columns=H_SUMMARY_COLUMNS, fill_value="")
    return a_events.drop(columns=[c for c in ["_signal", "_key"] if c in a_events.columns], errors="ignore"), a_summary, c_events, h_events, h_summary


def _write(frame: pd.DataFrame, raw_path: str) -> None:
    path = Path(raw_path); path.parent.mkdir(parents=True, exist_ok=True); frame.to_csv(path, index=False)


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--history", required=True); p.add_argument("--submissions", required=True); p.add_argument("--events", required=True)
    p.add_argument("--history-out", required=True); p.add_argument("--events-out", required=True)
    p.add_argument("--a-events-out", required=True); p.add_argument("--a-summary-out", required=True); p.add_argument("--c-events-out", required=True)
    p.add_argument("--h-events-out", required=True); p.add_argument("--h-summary-out", required=True)
    a = p.parse_args()
    history = reconcile_history(_read(Path(a.history), HISTORY_COLUMNS), _read(Path(a.submissions)))
    events = reconcile_events(history, _read(Path(a.events), EVENT_COLUMNS))
    a_events, a_summary, c_events, h_events, h_summary = build_learning(history, events)
    for frame, path in [
        (history, a.history_out), (events, a.events_out), (a_events, a.a_events_out), (a_summary, a.a_summary_out),
        (c_events, a.c_events_out), (h_events, a.h_events_out), (h_summary, a.h_summary_out),
    ]: _write(frame, path)
    print(f"I latest-state: {len(history)} opportunities; append-only events: {len(events)}")
    print(f"A evidence: {len(a_events)} events / {len(a_summary)} companies")
    print(f"C evidence: {len(c_events)} events; H evidence: {len(h_events)} events / {len(h_summary)} groups")


if __name__ == "__main__":
    main()
