from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import streamlit as st

from github_storage import github_token, load_csv_file, save_csv_file

DATA_DIR = Path(__file__).parent / "data"
HISTORY_PATH = "data/opportunity_history.csv"
B_PATH = DATA_DIR / "user_submitted_opportunities.csv"

HISTORY_COLUMNS = [
    "opportunity_id", "source_stream", "source_id", "first_seen_at", "decision_at",
    "title", "company", "canonical_company_id", "company_category", "market", "location",
    "job_url", "action", "company_feedback", "role_feedback", "user_comment",
    "company_rating_at_decision", "semantic_fit_at_decision", "semantic_reasoning_at_decision",
    "calibration_score_at_decision", "application_stage", "stage_updated_at",
    "outcome_reason", "history_notes",
]

STAGES = [
    "Not applied",
    "Applied",
    "Rejected pre-screen",
    "1st interview",
    "Lost after 1st",
    "Case",
    "Lost after case",
    "Final",
    "Offer",
    "Withdrawn",
]


def _load_history() -> tuple[pd.DataFrame, str | None]:
    token = github_token()
    try:
        return load_csv_file(token, HISTORY_PATH, HISTORY_COLUMNS)
    except Exception:
        return pd.DataFrame(columns=HISTORY_COLUMNS), None


def _b_rows() -> pd.DataFrame:
    if not B_PATH.exists():
        return pd.DataFrame(columns=HISTORY_COLUMNS)
    submitted = pd.read_csv(B_PATH).fillna("")
    if submitted.empty or "feedback" not in submitted.columns:
        return pd.DataFrame(columns=HISTORY_COLUMNS)
    submitted = submitted[submitted["feedback"].isin(["Interested", "Maybe", "Pass"])].copy()
    if submitted.empty:
        return pd.DataFrame(columns=HISTORY_COLUMNS)

    rows = []
    for _, row in submitted.iterrows():
        feedback = str(row.get("feedback", ""))
        record = {col: "" for col in HISTORY_COLUMNS}
        record.update({
            "opportunity_id": f"B:{row.get('submission_id', '')}",
            "source_stream": "B",
            "source_id": str(row.get("source_domain", "")),
            "first_seen_at": str(row.get("submitted_at", "")),
            "decision_at": str(row.get("submitted_at", "")),
            "title": str(row.get("title", "")),
            "company": str(row.get("company", "")),
            "canonical_company_id": str(row.get("canonical_company_id", "")),
            "company_category": str(row.get("company_category", "")),
            "market": str(row.get("country", "")),
            "location": str(row.get("location", "")),
            "job_url": str(row.get("job_url", "") or row.get("company_url", "") or row.get("linkedin_url", "")),
            "action": feedback,
            "role_feedback": (
                "Positive" if feedback == "Interested"
                else "Neutral" if feedback == "Maybe"
                else "Negative"
            ),
            "user_comment": str(row.get("user_comment", "")),
            "semantic_reasoning_at_decision": str(row.get("role_profile", "")),
            "application_stage": "Not applied",
        })
        rows.append(record)
    return pd.DataFrame(rows).reindex(columns=HISTORY_COLUMNS, fill_value="")


def _unified(history: pd.DataFrame) -> pd.DataFrame:
    b = _b_rows()
    if history.empty:
        merged = b
    elif b.empty:
        merged = history.copy()
    else:
        stored_ids = set(history["opportunity_id"].astype(str))
        b = b[~b["opportunity_id"].astype(str).isin(stored_ids)]
        merged = pd.concat([history, b], ignore_index=True, sort=False)
    if merged.empty:
        return pd.DataFrame(columns=HISTORY_COLUMNS)
    merged = merged.reindex(columns=HISTORY_COLUMNS, fill_value="").fillna("")
    merged["application_stage"] = merged["application_stage"].replace("", "Not applied")
    return merged.drop_duplicates("opportunity_id", keep="last")


def _save_edits(unified: pd.DataFrame, edited: pd.DataFrame) -> pd.DataFrame:
    now = datetime.now(timezone.utc).isoformat()
    base = unified.copy().set_index("opportunity_id")
    for opportunity_id, row in edited.iterrows():
        old_stage = str(base.loc[opportunity_id].get("application_stage", "Not applied"))
        new_stage = str(row.get("application_stage", "Not applied"))
        base.loc[opportunity_id, "application_stage"] = new_stage
        base.loc[opportunity_id, "outcome_reason"] = str(row.get("outcome_reason", ""))
        base.loc[opportunity_id, "history_notes"] = str(row.get("history_notes", ""))
        if new_stage != old_stage:
            base.loc[opportunity_id, "stage_updated_at"] = now
    return base.reset_index().reindex(columns=HISTORY_COLUMNS, fill_value="")


def render_opportunity_history() -> None:
    st.markdown('<div class="eyebrow">Workstream I</div>', unsafe_allow_html=True)
    st.title("Opportunity & Application History")
    st.caption(
        "One factual memory of what you did with opportunities from B and J. "
        "This is the data layer that later feeds batch calibration in A/C and attainability in H."
    )

    history, history_sha = _load_history()
    unified = _unified(history)
    if unified.empty:
        st.info("No rated or actioned opportunities yet.")
        return

    applied_mask = unified["application_stage"].isin(
        ["Applied", "1st interview", "Lost after 1st", "Case", "Lost after case", "Final", "Offer", "Withdrawn", "Rejected pre-screen"]
    )
    active_mask = unified["application_stage"].isin(["Applied", "1st interview", "Case", "Final"])
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Decisions stored", len(unified))
    m2.metric("Applications", int(applied_mask.sum()))
    m3.metric("Active processes", int(active_mask.sum()))
    m4.metric("Offers", int(unified["application_stage"].eq("Offer").sum()))

    source_filter = st.multiselect(
        "Source",
        ["B", "G"],
        default=["B", "G"],
        help="B = manually added opportunities; G = automatically sourced jobs decided in J.",
    )
    filtered = unified[unified["source_stream"].isin(source_filter)].copy()
    filtered["_sort"] = pd.to_datetime(filtered["decision_at"], errors="coerce", utc=True)
    filtered = filtered.sort_values("_sort", ascending=False).drop(columns="_sort")

    display_cols = [
        "source_stream", "company", "title", "company_category", "market", "location",
        "action", "application_stage", "outcome_reason", "history_notes", "job_url",
    ]
    editor = filtered.set_index("opportunity_id")[display_cols]
    with st.form("history_form"):
        edited = st.data_editor(
            editor,
            hide_index=True,
            width="stretch",
            height=680,
            row_height=80,
            disabled=[c for c in display_cols if c not in {"application_stage", "outcome_reason", "history_notes"}],
            column_config={
                "source_stream": st.column_config.TextColumn("Source", width="small"),
                "company": st.column_config.TextColumn("Company", width="small"),
                "title": st.column_config.TextColumn("Role", width="medium"),
                "company_category": st.column_config.TextColumn("Category", width="small"),
                "market": st.column_config.TextColumn("Country", width="small"),
                "location": st.column_config.TextColumn("Location", width="small"),
                "action": st.column_config.TextColumn("Decision", width="small"),
                "application_stage": st.column_config.SelectboxColumn("Application stage", options=STAGES, required=True),
                "outcome_reason": st.column_config.TextColumn("Outcome / reason", width="medium"),
                "history_notes": st.column_config.TextColumn("Notes", width="medium"),
                "job_url": st.column_config.LinkColumn("Job", display_text="Open"),
            },
        )
        save = st.form_submit_button("Save application updates", type="primary")

    if save:
        token = github_token()
        if not token:
            st.error("GitHub saving is not configured for this app.")
            return
        updated = _save_edits(unified, edited)
        try:
            save_csv_file(token, HISTORY_PATH, updated, history_sha, "Update opportunity and application history")
        except Exception:
            st.error("Saving application history failed. Refresh and try again.")
        else:
            st.success("Saved. These outcomes are now available to H.")
            st.rerun()

    st.divider()
    st.subheader("H input — early attainability evidence")
    st.caption("No model inference yet; these are only factual counts from application outcomes.")
    app = unified[applied_mask].copy()
    if app.empty:
        st.info("Once applications accumulate, H can estimate attainability separately from C semantic fit.")
        return

    interview_reached = app["application_stage"].isin(["1st interview", "Lost after 1st", "Case", "Lost after case", "Final", "Offer"])
    case_reached = app["application_stage"].isin(["Case", "Lost after case", "Final", "Offer"])
    final_reached = app["application_stage"].isin(["Final", "Offer"])
    h1, h2, h3 = st.columns(3)
    h1.metric("Reached interview", int(interview_reached.sum()))
    h2.metric("Reached case", int(case_reached.sum()))
    h3.metric("Reached final / offer", int(final_reached.sum()))
