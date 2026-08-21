"""Build the periodic A/C calibration input from real user decisions in I.

This module is deliberately deterministic. It does not rewrite targeting theses
or call an AI model. It prepares a compact batch that the scheduled calibration
process can review after enough new decisions have accumulated.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
HISTORY_PATH = ROOT / "data" / "opportunity_history.csv"
OUT_PATH = ROOT / "data" / "decision_feedback_batch.csv"

OUT_COLUMNS = [
    "opportunity_id", "decision_at", "source_stream", "company", "company_category",
    "title", "market", "action", "company_feedback", "role_feedback", "user_comment",
    "company_rating_at_decision", "semantic_fit_at_decision", "semantic_reasoning_at_decision",
    "calibration_score_at_decision", "application_stage", "outcome_reason",
    "a_signal", "c_signal", "h_evidence",
]


def _signal(value: object) -> str:
    text = str(value or "").strip().lower()
    return {
        "positive": "positive",
        "neutral": "neutral",
        "negative": "negative",
    }.get(text, "")


def _decision_role_signal(action: object, explicit: object) -> str:
    explicit_signal = _signal(explicit)
    if explicit_signal:
        return explicit_signal
    action_text = str(action or "").strip().lower()
    if action_text in {"apply", "interested"}:
        return "positive"
    if action_text in {"maybe"}:
        return "neutral"
    if action_text in {"skip", "pass"}:
        return "negative"
    return ""


def _h_evidence(stage: object) -> str:
    stage_text = str(stage or "").strip()
    if stage_text in {"Offer"}:
        return "offer"
    if stage_text in {"Final"}:
        return "reached_final"
    if stage_text in {"Case", "Lost after case"}:
        return "reached_case"
    if stage_text in {"1st interview", "Lost after 1st"}:
        return "reached_interview"
    if stage_text == "Rejected pre-screen":
        return "rejected_pre_screen"
    if stage_text == "Withdrawn":
        return "withdrawn"
    if stage_text == "Applied":
        return "applied_pending"
    return ""


def build_batch(history: pd.DataFrame) -> pd.DataFrame:
    if history.empty:
        return pd.DataFrame(columns=OUT_COLUMNS)

    frame = history.fillna("").copy()
    if "opportunity_id" not in frame.columns:
        return pd.DataFrame(columns=OUT_COLUMNS)
    frame = frame.drop_duplicates("opportunity_id", keep="last")

    for col in OUT_COLUMNS:
        if col not in frame.columns:
            frame[col] = ""

    frame["a_signal"] = frame["company_feedback"].map(_signal)
    frame["c_signal"] = frame.apply(
        lambda row: _decision_role_signal(row.get("action", ""), row.get("role_feedback", "")),
        axis=1,
    )
    frame["h_evidence"] = frame["application_stage"].map(_h_evidence)

    # Keep only rows that contain an actual decision or outcome. A blank/New row
    # is operational state, not calibration evidence.
    informative = (
        frame["action"].astype(str).isin(["Apply", "Maybe", "Skip", "Interested", "Pass"])
        | frame["a_signal"].ne("")
        | frame["c_signal"].ne("")
        | frame["h_evidence"].ne("")
    )
    frame = frame[informative].copy()
    if frame.empty:
        return pd.DataFrame(columns=OUT_COLUMNS)

    frame["_decision_sort"] = pd.to_datetime(frame["decision_at"], errors="coerce", utc=True)
    frame = frame.sort_values(["_decision_sort", "opportunity_id"], ascending=[False, True])
    return frame.reindex(columns=OUT_COLUMNS, fill_value="")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--history", default=str(HISTORY_PATH))
    parser.add_argument("--out", default=str(OUT_PATH))
    args = parser.parse_args()

    history_path = Path(args.history)
    out_path = Path(args.out)
    if history_path.exists() and history_path.stat().st_size > 0:
        try:
            history = pd.read_csv(history_path).fillna("")
        except (pd.errors.EmptyDataError, pd.errors.ParserError):
            history = pd.DataFrame()
    else:
        history = pd.DataFrame()

    batch = build_batch(history)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    batch.to_csv(out_path, index=False)
    print(f"wrote {len(batch)} decision feedback rows to {out_path}")


if __name__ == "__main__":
    main()
