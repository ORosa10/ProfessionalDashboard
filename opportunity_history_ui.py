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

APPLICATION_STAGES = [
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
ACTIVE_STAGES = ["Applied", "1st interview", "Case", "Final"]
INTERVIEW_REACHED_STAGES = ["1st interview", "Lost after 1st", "Case", "Lost after case", "Final", "Offer"]
CASE_REACHED_STAGES = ["Case", "Lost after case", "Final", "Offer"]
FINAL_REACHED_STAGES = ["Final", "Offer"]


def _load_history() -> tuple[pd.DataFrame, str | None]:
    token = github_token()
    try:
        return load_csv_file(token, HISTORY_PATH, HISTORY_COLUMNS)
    except Exception:
        return pd.DataFrame(columns=HISTORY_COLUMNS), None


def _b_rows() -> pd.DataFrame:
    """Manual B intake is factual application intake: B means Applied."""
    if not B_PATH.exists():
        return pd.DataFrame(columns=HISTORY_COLUMNS)
    try:
        submitted = pd.read_csv(B_PATH).fillna("")
    except Exception:
        return pd.DataFrame(columns=HISTORY_COLUMNS)
    if submitted.empty or "submission_id" not in submitted.columns:
        return pd.DataFrame(columns=HISTORY_COLUMNS)

    rows = []
    for _, row in submitted.iterrows():
        submission_id = str(row.get("submission_id", "")).strip()
        if not submission_id:
            continue
        submitted_at = str(row.get("submitted_at", ""))
        record = {col: "" for col in HISTORY_COLUMNS}
        record.update({
            "opportunity_id": f"B:{submission_id}",
            "source_stream": "B",
            "source_id": str(row.get("source_domain", "")),
            "first_seen_at": submitted_at,
            "decision_at": submitted_at,
            "title": str(row.get("title", "")),
            "company": str(row.get("company", "")),
            "canonical_company_id": str(row.get("canonical_company_id", "")),
            "company_category": str(row.get("company_category", "")),
            "market": str(row.get("country", "")),
            "location": str(row.get("location", "")),
            "job_url": str(row.get("job_url", "") or row.get("company_url", "") or row.get("linkedin_url", "")),
            "action": "Apply",
            "role_feedback": "Positive",
            "user_comment": str(row.get("user_comment", "")),
            "semantic_reasoning_at_decision": str(row.get("role_profile", "")),
            "application_stage": "Applied",
            "stage_updated_at": submitted_at,
        })
        rows.append(record)
    return pd.DataFrame(rows).reindex(columns=HISTORY_COLUMNS, fill_value="")


def _unified(history: pd.DataFrame) -> pd.DataFrame:
    """Keep full factual history, while adding legacy B applications without destroying decisions."""
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
    merged = merged.drop_duplicates("opportunity_id", keep="last")

    # B is manual application intake. Preserve any more advanced historical stage,
    # but normalize old B rows that were previously stored as Interested/Not applied.
    b_mask = merged["source_stream"].eq("B")
    not_applied = merged["application_stage"].isin(["", "Not applied"])
    merged.loc[b_mask & not_applied, "application_stage"] = "Applied"
    merged.loc[b_mask & not_applied, "stage_updated_at"] = merged.loc[b_mask & not_applied, "decision_at"]
    merged.loc[b_mask, "action"] = "Apply"
    return merged


def _canonicalize_b(history: pd.DataFrame, history_sha: str | None) -> tuple[pd.DataFrame, str | None]:
    """Persist missing/legacy B applications into canonical history once, without touching J decisions."""
    token = github_token()
    if not token:
        return history, history_sha

    canonical = history.reindex(columns=HISTORY_COLUMNS, fill_value="").fillna("").copy()
    unified = _unified(canonical)
    if unified.empty:
        return canonical, history_sha

    left = canonical.drop_duplicates("opportunity_id", keep="last").sort_values("opportunity_id").reset_index(drop=True)
    right = unified.drop_duplicates("opportunity_id", keep="last").sort_values("opportunity_id").reset_index(drop=True)
    if left.equals(right):
        return canonical, history_sha

    try:
        save_csv_file(token, HISTORY_PATH, right, history_sha, "Reconcile manual B applications into canonical history")
        refreshed, refreshed_sha = load_csv_file(token, HISTORY_PATH, HISTORY_COLUMNS)
        return refreshed, refreshed_sha
    except Exception:
        # The view remains usable even if reconciliation races another live write.
        return canonical, history_sha


def _save_edits(unified: pd.DataFrame, edited: pd.DataFrame) -> pd.DataFrame:
    now = datetime.now(timezone.utc).isoformat()
    base = unified.copy().set_index("opportunity_id")
    for opportunity_id, row in edited.iterrows():
        if opportunity_id not in base.index:
            continue
        old_stage = str(base.loc[opportunity_id].get("application_stage", "Applied"))
        new_stage = str(row.get("application_stage", "Applied"))
        base.loc[opportunity_id, "application_stage"] = new_stage
        base.loc[opportunity_id, "outcome_reason"] = str(row.get("outcome_reason", ""))
        base.loc[opportunity_id, "history_notes"] = str(row.get("history_notes", ""))
        if new_stage != old_stage:
            base.loc[opportunity_id, "stage_updated_at"] = now
    return base.reset_index().reindex(columns=HISTORY_COLUMNS, fill_value="")


def render_opportunity_history() -> None:
    st.markdown('<div class="eyebrow">Workstream I</div>', unsafe_allow_html=True)
    st.title("Application Tracker")
    st.caption(
        "Only roles you actually applied to. B enters here directly as Applied; J enters after an Apply decision. "
        "Update process stages and outcomes here; those factual results feed H."
    )

    history, history_sha = _load_history()
    history, history_sha = _canonicalize_b(history, history_sha)
    unified = _unified(history)
    if unified.empty:
        st.info("No applications yet.")
        return

    applications = unified[unified["application_stage"].isin(APPLICATION_STAGES)].copy()
    if applications.empty:
        st.info("No applications yet. Add a role in B or choose Apply in J.")
        return

    applications["_sort"] = pd.to_datetime(applications["decision_at"], errors="coerce", utc=True)
    applications = applications.sort_values("_sort", ascending=False).drop(columns="_sort")

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Applications", len(applications))
    m2.metric("Active processes", int(applications["application_stage"].isin(ACTIVE_STAGES).sum()))
    m3.metric("Reached interview", int(applications["application_stage"].isin(INTERVIEW_REACHED_STAGES).sum()))
    m4.metric("Offers", int(applications["application_stage"].eq("Offer").sum()))

    source_options = [x for x in ["B", "G"] if x in set(applications["source_stream"].astype(str))]
    source_filter = st.multiselect(
        "Source",
        source_options,
        default=source_options,
        format_func=lambda x: "B · Manual Add" if x == "B" else "J · Apply Shortlist",
        help="B = manually added/application roles; J = automatically sourced roles you chose to apply to.",
    )
    filtered = applications[applications["source_stream"].isin(source_filter)].copy() if source_filter else applications.iloc[0:0].copy()
    if filtered.empty:
        st.info("No applications match this source filter.")
        return

    filtered["source"] = filtered["source_stream"].map({"B": "B · Manual", "G": "J · Shortlist"}).fillna(filtered["source_stream"])
    filtered["applied_at"] = filtered["decision_at"]

    display_cols = [
        "source", "company", "title", "market", "location", "applied_at",
        "application_stage", "outcome_reason", "history_notes", "job_url",
    ]
    editor = filtered.set_index("opportunity_id")[display_cols]
    with st.form("application_tracker_form"):
        edited = st.data_editor(
            editor,
            hide_index=True,
            width="stretch",
            height=680,
            row_height=80,
            disabled=[c for c in display_cols if c not in {"application_stage", "outcome_reason", "history_notes"}],
            column_config={
                "source": st.column_config.TextColumn("Source", width="small"),
                "company": st.column_config.TextColumn("Company", width="small"),
                "title": st.column_config.TextColumn("Role", width="medium"),
                "market": st.column_config.TextColumn("Country", width="small"),
                "location": st.column_config.TextColumn("Location", width="small"),
                "applied_at": st.column_config.TextColumn("Applied", width="medium"),
                "application_stage": st.column_config.SelectboxColumn(
                    "Application stage", options=APPLICATION_STAGES, required=True
                ),
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
            save_csv_file(token, HISTORY_PATH, updated, history_sha, "Update application tracker")
        except Exception:
            st.error("Saving application history failed. Refresh and try again.")
        else:
            st.success("Saved. These factual outcomes are now available to H.")
            st.rerun()

    st.divider()
    st.subheader("H input — attainability evidence")
    st.caption("Factual application outcomes only; H does not change semantic fit in C.")
    h1, h2, h3 = st.columns(3)
    h1.metric("Reached interview", int(applications["application_stage"].isin(INTERVIEW_REACHED_STAGES).sum()))
    h2.metric("Reached case", int(applications["application_stage"].isin(CASE_REACHED_STAGES).sum()))
    h3.metric("Reached final / offer", int(applications["application_stage"].isin(FINAL_REACHED_STAGES).sum()))
