from __future__ import annotations

from pathlib import Path

import pandas as pd
import streamlit as st

DATA_DIR = Path(__file__).parent / "data"


def render_jobs() -> None:
    st.markdown('<div class="eyebrow">Opportunity Radar</div>', unsafe_allow_html=True)
    st.title("Jobs")
    st.caption("Live pilot: PwC · EY · Deloitte · KPMG across your priority markets.")
    jobs_path = DATA_DIR / "jobs.csv"
    if not jobs_path.exists():
        st.warning("The sourcing workflow has not produced its first snapshot yet.")
        st.caption("Once the scheduled GitHub Action runs, sourced vacancies will appear here automatically.")
        return
    jobs = pd.read_csv(jobs_path).fillna("")
    if jobs.empty:
        st.info("The latest sourcing run completed but did not retain any vacancy links.")
        return
    c1, c2, c3 = st.columns(3)
    c1.metric("Open links tracked", len(jobs))
    c2.metric("Companies", jobs["company"].nunique())
    c3.metric("Markets", jobs["market"].nunique())
    companies = sorted(jobs["company"].unique())
    markets = sorted(jobs["market"].unique())
    left, right = st.columns(2)
    selected_companies = left.multiselect("Companies", companies, default=companies)
    selected_markets = right.multiselect("Markets", markets, default=markets)
    view = jobs[jobs["company"].isin(selected_companies) & jobs["market"].isin(selected_markets)].copy()
    view = view.sort_values(["relevance_score", "last_seen_at"], ascending=[False, False])
    st.dataframe(
        view[["company", "title", "market", "priority_locations", "relevance_score", "matched_terms", "job_url", "last_seen_at"]],
        hide_index=True,
        width="stretch",
        column_config={"job_url": st.column_config.LinkColumn("Vacancy", display_text="Open")},
    )


def render_sources() -> None:
    st.markdown('<div class="eyebrow">Opportunity Radar</div>', unsafe_allow_html=True)
    st.title("Sources / Radar")
    st.caption("Diagnostics for the autonomous career-page monitor.")
    source_path = DATA_DIR / "job_sources_pilot.csv"
    runs_path = DATA_DIR / "source_runs.csv"
    if source_path.exists():
        sources = pd.read_csv(source_path).fillna("")
        st.metric("Configured pilot sources", len(sources))
        st.dataframe(sources[["company", "market", "priority_locations", "seed_url", "enabled"]], hide_index=True, width="stretch", column_config={"seed_url": st.column_config.LinkColumn("Career page", display_text="Open")})
    if runs_path.exists():
        st.subheader("Recent source runs")
        runs = pd.read_csv(runs_path).fillna("").tail(100).sort_values("run_at", ascending=False)
        st.dataframe(runs, hide_index=True, width="stretch", column_config={"seed_url": st.column_config.LinkColumn("Source", display_text="Open")})
    else:
        st.info("No source-run history yet. It will appear after the first workflow execution.")
