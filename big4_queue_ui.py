from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import re

import pandas as pd
import streamlit as st

from github_storage import github_token, load_csv_file, save_csv_file


DATA = Path(__file__).parent / "data"
POOL = DATA / "j_big4_pool.csv"
PILOT_POOL = DATA / "j_big4_pilot20.csv"
CV_DIR = DATA / "big4_cv_pilot20"
CV_MAP = CV_DIR / "README.csv"
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
    st.caption("Pilot: 20 live-link roles from Deloitte · EY · KPMG · PwC — separate from the regular J shortlist. Language constraints are intentionally not applied here yet.")
    if not POOL.exists() or not POOL.stat().st_size:
        st.info("The Big Four career-site sweep has not produced a pool yet.")
        return
    all_jobs = pd.read_csv(POOL if POOL.exists() else PILOT_POOL).fillna("").drop_duplicates("job_id", keep="last")
    def manager_plus(title: str) -> bool:
        tokens = re.findall(r"\b(manager|director|partner|head)\b", title.lower())
        return bool(tokens) and not (title.lower().strip().startswith("assistant manager") and tokens == ["manager"])
    all_jobs = all_jobs[~all_jobs["title"].map(manager_plus)].copy()
    include_role = r"due diligence|transaction services|transaction diligence|m&a|corporate finance|valuation|modelling|modeling|capital markets|treasury|financial risk|finance consulting|cfo specialist|banking"
    exclude_role = r"intern|praktik|junior konzultant|tax|steuer|reward|account|audit|data management|data governance|\bit\b|non-financial risk|data acquisition|strategy & execution|finance optimization|people consulting|d365"
    role_title = all_jobs["title"].astype(str)
    all_jobs = all_jobs[role_title.str.contains(include_role, case=False, regex=True, na=False) & ~role_title.str.contains(exclude_role, case=False, regex=True, na=False)].copy()
    token = github_token()
    history, sha = load_csv_file(token, HISTORY_PATH, HISTORY_COLUMNS) if token else (pd.DataFrame(columns=HISTORY_COLUMNS), None)
    latest = history.drop_duplicates("opportunity_id", keep="last").set_index("opportunity_id") if not history.empty else pd.DataFrame()
    if not latest.empty:
        all_jobs["prior_action"] = all_jobs.job_id.map(latest.get("action", pd.Series(dtype=str))).fillna("")
    else:
        all_jobs["prior_action"] = ""
    companies = ["EY", "Deloitte", "KPMG", "PwC"]
    selected_company = st.selectbox("Big Four firma", companies, index=0, key="big4_company_filter")
    company_jobs = all_jobs[all_jobs["company"].eq(selected_company)].copy()
    jobs = company_jobs[~company_jobs.prior_action.isin(["Apply", "Skip", "Pass"])].copy()
    st.metric("Open relevant roles", len(jobs))
    resolved_count = len(company_jobs) - len(jobs)
    st.caption(f"{len(company_jobs)} relevantních rolí {selected_company} celkem · {resolved_count} již rozhodnuto a skryto · {len(jobs)} čeká na Apply / Skip.")
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

    st.subheader("K · CV pro Apply")
    st.caption("Každé CV vychází z Masteru a je upravené podle typu konkrétní Big Four role. Vyber roli a stáhni odpovídající PDF přímo z aplikace.")
    applied_jobs = company_jobs[company_jobs["prior_action"].eq("Apply")].copy()
    cv_options = applied_jobs[["job_id", "company", "title", "job_url"]].copy()
    cv_options["label"] = cv_options["company"] + " · " + cv_options["title"]
    if CV_MAP.exists():
        cv_map = pd.read_csv(CV_MAP).fillna("")
        cv_options = cv_options.merge(cv_map[["number", "job_url", "cv_file"]], on="job_url", how="left") if "job_url" in cv_map.columns else cv_options
    else:
        cv_options["cv_file"] = ""
    selected_cv = st.selectbox("Role pro CV", cv_options["label"].tolist(), key="big4_cv_role") if not cv_options.empty else ""
    if cv_options.empty:
        st.info("Nejdřív zvol u role v tabulce Apply. Potom se role objeví tady a bude mít své připravené CV.")
    if selected_cv:
        selected = cv_options.loc[cv_options["label"].eq(selected_cv)].iloc[0]
        cv_path = CV_DIR / str(selected.get("cv_file", ""))
        if cv_path.exists():
            st.download_button(
                "Stáhnout připravené CV",
                data=cv_path.read_bytes(),
                file_name=cv_path.name,
                mime="application/pdf",
                key=f"download_cv_{selected['job_id']}",
            )
        else:
            st.warning("Pro tuto roli zatím není soubor CV vložený do aplikace.")
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

