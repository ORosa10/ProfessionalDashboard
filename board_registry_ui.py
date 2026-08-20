from __future__ import annotations

from pathlib import Path

import pandas as pd
import streamlit as st

DATA_DIR = Path(__file__).parent / "data"

STATUS_LABELS = {
    "active": "Active",
    "candidate": "Candidate",
    "web_verified": "Web verified",
    "api_credentials": "API credentials needed",
    "blocked": "Blocked",
    "blocked_waf": "Blocked / WAF",
}

STATUS_ORDER = {
    "active": 0,
    "web_verified": 1,
    "api_credentials": 2,
    "candidate": 3,
    "blocked": 4,
    "blocked_waf": 5,
}


def render_board_registry() -> None:
    st.markdown('<div class="eyebrow">Opportunity Radar</div>', unsafe_allow_html=True)
    st.title("Country / Board Sweep")
    st.caption(
        "Workstream G source registry. This page tracks where jobs are sourced from; "
        "it is not a second job-review inbox. Jobs found here should flow through A "
        "(company context) and C (semantic role fit) into the normal Jobs review queue."
    )

    path = DATA_DIR / "job_boards.csv"
    if not path.exists():
        st.info("No job-board registry found yet.")
        return

    boards = pd.read_csv(path).fillna("")
    if boards.empty:
        st.info("The job-board registry is empty.")
        return

    boards["status_label"] = boards["status"].map(STATUS_LABELS).fillna(boards["status"])
    boards["_status_order"] = boards["status"].map(STATUS_ORDER).fillna(99)

    countries = sorted(c for c in boards["country"].unique() if c and c != "Multi-region")
    active = int(boards["status"].eq("active").sum())
    testable = int(boards["status"].isin(["web_verified", "api_credentials", "candidate"]).sum())
    blocked = int(boards["status"].isin(["blocked", "blocked_waf"]).sum())

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Countries", len(countries))
    m2.metric("Board sources", len(boards))
    m3.metric("Active adapters", active)
    m4.metric("Next to activate", testable)

    st.code("G BOARD → ROLE + COMPANY → A COMPANY CONTEXT → C SEMANTIC FIT → JOBS INBOX")

    f1, f2 = st.columns(2)
    selected_countries = f1.multiselect(
        "Countries",
        countries,
        default=countries,
    )
    status_options = [
        label
        for key, label in STATUS_LABELS.items()
        if key in set(boards["status"])
    ]
    selected_statuses = f2.multiselect(
        "Technical status",
        status_options,
        default=status_options,
    )

    selected_status_keys = {
        key for key, label in STATUS_LABELS.items() if label in selected_statuses
    }
    filtered = boards[
        boards["country"].isin(selected_countries)
        & boards["status"].isin(selected_status_keys)
    ].copy()

    st.caption(
        "Active = working adapter today. Web verified = public searchable pages are confirmed and "
        "an adapter can be tested next. API credentials needed = official API exists but requires onboarding/token. "
        "Candidate = source is registered but unattended access is not yet verified."
    )

    for country in selected_countries:
        country_rows = filtered[filtered["country"].eq(country)].copy()
        if country_rows.empty:
            continue
        country_rows = country_rows.sort_values(["_status_order", "finance_specific", "name"], ascending=[True, False, True])
        with st.expander(f"{country} — {len(country_rows)} sources", expanded=True):
            st.dataframe(
                country_rows[["name", "status_label", "adapter", "finance_specific", "base_url", "notes"]],
                hide_index=True,
                width="stretch",
                column_config={
                    "name": st.column_config.TextColumn("Board", width="medium"),
                    "status_label": st.column_config.TextColumn("Status", width="small"),
                    "adapter": st.column_config.TextColumn("Adapter", width="small"),
                    "finance_specific": st.column_config.CheckboxColumn("Finance-specific", width="small"),
                    "base_url": st.column_config.LinkColumn("Board", display_text="Open", width="small"),
                    "notes": st.column_config.TextColumn("Technical / sourcing note", width="large"),
                },
            )

    multi = boards[boards["country"].eq("Multi-region")].copy()
    if not multi.empty:
        multi = multi.sort_values(["_status_order", "name"])
        with st.expander(f"Multi-region — {len(multi)} sources", expanded=False):
            st.dataframe(
                multi[["name", "status_label", "adapter", "finance_specific", "base_url", "notes"]],
                hide_index=True,
                width="stretch",
                column_config={
                    "base_url": st.column_config.LinkColumn("Board", display_text="Open"),
                },
            )

    legacy_path = DATA_DIR / "jobs_board_staging.csv"
    if legacy_path.exists():
        legacy = pd.read_csv(legacy_path).fillna("")
        if not legacy.empty:
            st.divider()
            st.caption(
                f"Legacy G snapshot: {len(legacy)} previously collected board roles remain in "
                "data/jobs_board_staging.csv for migration/testing only. They are no longer a separate review queue."
            )

    if blocked:
        st.caption(f"{blocked} registered sources are currently blocked for unattended access and remain fallback/manual sources only.")
