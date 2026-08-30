from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import streamlit as st

from github_storage import github_token, load_csv_file, save_csv_file


DATA = Path(__file__).parent / "data"
POOL = DATA / "j_big4_pool.csv"
HISTORY_PATH = "data/opportunity_history.csv"
HISTORY_COLUMNS = [
    "opportunity_id", "source_stream", "source_id", "first_seen_at", "decision_at",
    "title", "company", "canonical_company_id", "company_category", "market", "location",
    "job_url", "action", "company_feedback", "role_feedback", "user_comment",
    "company_rating_at_decision", "semantic_fit_at_decision", "semantic_reasoning_at_decision",
    "calibration_score_at_decision", "application_stage", "stage_updated_at",
    "outcome_reason", "history_notes",
]


def render_big4_queue() -> None:
    st.markdown('<div class="eyebrow">Separate application lane</div>', unsafe_allow_html=True)
    st.title("J · Big Four")
    st.caption("Deloitte · EY · KPMG · PwC — separate from the regular J shortlist. Language constraints are intentionally not applied here yet.")
    if not POOL.exists() or not POOL.stat().st_size:
        st.info("The Big Four career-site sweep has not produced a pool yet.")
        return
    jobs = pd.read_csv(POOL).fillna("").drop_duplicates("job_id", keep="last")
    token = github_token()
    history, sha = load_csv_file(token, HISTORY_PATH, HISTORY_COLUMNS) if token else (pd.DataFrame(columns=HISTORY_COLUMNS), None)
    latest = history.drop_duplicates("opportunity_id", keep="last").set_index("opportunity_id") if not history.empty else pd.DataFrame()
    if not latest.empty:
        jobs["prior_action"] = jobs.job_id.map(latest.get("action", pd.Series(dtype=str))).fillna("")
    else:
        jobs["prior_action"] = ""
    jobs = jobs[~jobs.prior_action.isin(["Apply", "Skip", "Pass"])].copy()
    st.metric("Relevant Big Four roles", len(jobs))
    bands = ["All seniority bands", "Realistic target / adjacent", "Junior / early-career", "Too senior / upper-level", "Seniority unclear"]
    selected_band = st.selectbox("Seniority filter", bands, index=0)
    if selected_band != bands[0]:
        jobs = jobs[jobs["seniority_band"].eq(selected_band)].copy()
    st.caption("Seniority is separated for review; language constraints remain intentionally off.")
    jobs["action"] = jobs.prior_action.replace("", "New")
    jobs["company_feedback"] = "Not rated"
    jobs["role_feedback"] = "Not rated"
    jobs["user_comment"] = ""
    display = jobs.set_index("job_id")
    cols = ["company", "title", "seniority_band", "market", "location", "big4_relevance_reason", "job_url", "action", "company_feedback", "role_feedback", "user_comment"]
    edited = st.data_editor(display[cols], hide_index=True, width="stretch", height=760, row_height=85,
        disabled=[c for c in cols if c not in {"action", "company_feedback", "role_feedback", "user_comment"}],
        column_config={"seniority_band": st.column_config.TextColumn("Seniority", width="small"),
                       "job_url": st.column_config.LinkColumn("Job page", display_text="Open"),
                       "action": st.column_config.SelectboxColumn("Your action", options=["New", "Apply", "Maybe", "Skip"]),
                       "company_feedback": st.column_config.SelectboxColumn("Company", options=["Not rated", "Positive", "Neutral", "Negative"]),
                       "role_feedback": st.column_config.SelectboxColumn("Role", options=["Not rated", "Positive", "Neutral", "Negative"])},
        key="big4_queue_editor")
    changed = edited[["action", "company_feedback", "role_feedback", "user_comment"]].astype(str).ne(
        display[["action", "company_feedback", "role_feedback", "user_comment"]].astype(str)
    ).any(axis=1)
    if changed.any() and token:
        now = datetime.now(timezone.utc).isoformat()
        records = []
        for job_id, row in edited[changed].iterrows():
            src = jobs.set_index("job_id").loc[job_id]
            records.append({c: "" for c in HISTORY_COLUMNS} | {
                "opportunity_id": job_id, "source_stream": "Big Four", "source_id": src.get("source_id", ""),
                "first_seen_at": src.get("discovered_at", now), "decision_at": now,
                "title": src.get("title", ""), "company": src.get("company", ""),
                "canonical_company_id": src.get("canonical_company_id", ""), "market": src.get("market", ""),
                "location": src.get("location", ""), "job_url": src.get("job_url", ""),
                "action": row.get("action", "New"), "company_feedback": row.get("company_feedback", "Not rated"),
                "role_feedback": row.get("role_feedback", "Not rated"), "user_comment": row.get("user_comment", ""),
                "application_stage": "Applied" if row.get("action") == "Apply" else "",
                "stage_updated_at": now if row.get("action") == "Apply" else "",
            })
        updated = pd.concat([history, pd.DataFrame(records)], ignore_index=True).reindex(columns=HISTORY_COLUMNS, fill_value="")
        save_csv_file(token, HISTORY_PATH, updated, sha, "Auto-save Big Four shortlist decision")
        st.rerun()

