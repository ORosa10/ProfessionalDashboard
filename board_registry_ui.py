from __future__ import annotations

from pathlib import Path

import pandas as pd
import streamlit as st

DATA_DIR = Path(__file__).parent / "data"

STATUS_LABELS = {
    "active": "Active",
    "adapter_ready": "Adapter ready",
    "web_verified": "Web verified",
    "api_credentials": "API credentials needed",
    "manual_fallback": "Manual fallback",
    "candidate": "Candidate",
    "blocked": "Blocked",
    "blocked_waf": "Blocked / WAF",
    "closed": "Closed",
}

STATUS_ORDER = {
    "active": 0,
    "adapter_ready": 1,
    "api_credentials": 2,
    "web_verified": 3,
    "candidate": 4,
    "manual_fallback": 5,
    "blocked": 6,
    "blocked_waf": 7,
    "closed": 8,
}


def _load_registry() -> pd.DataFrame:
    path = DATA_DIR / "job_boards.csv"
    boards = pd.read_csv(path).fillna("")
    audit_path = DATA_DIR / "job_board_access_audit.csv"
    if not audit_path.exists() or boards.empty:
        return boards

    audit = pd.read_csv(audit_path).fillna("")
    if audit.empty or "board_id" not in audit.columns:
        return boards
    audit = audit.drop_duplicates("board_id", keep="last").set_index("board_id")

    status = boards["board_id"].map(audit.get("status_override", pd.Series(dtype=str))).fillna("")
    adapter = boards["board_id"].map(audit.get("adapter_override", pd.Series(dtype=str))).fillna("")
    enabled = boards["board_id"].map(audit.get("enabled_override", pd.Series(dtype=str))).fillna("")
    audit_note = boards["board_id"].map(audit.get("audit_note", pd.Series(dtype=str))).fillna("")
    audited_at = boards["board_id"].map(audit.get("audited_at", pd.Series(dtype=str))).fillna("")

    boards["status"] = status.where(status.ne(""), boards["status"])
    boards["adapter"] = adapter.where(adapter.ne(""), boards["adapter"])
    boards["enabled"] = enabled.where(enabled.ne(""), boards["enabled"])
    boards["notes"] = audit_note.where(audit_note.ne(""), boards["notes"])
    boards["audited_at"] = audited_at
    return boards


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

    boards = _load_registry()
    if boards.empty:
        st.info("The job-board registry is empty.")
        return

    boards["status_label"] = boards["status"].map(STATUS_LABELS).fillna(boards["status"])
    boards["_status_order"] = boards["status"].map(STATUS_ORDER).fillna(99)

    countries = sorted(c for c in boards["country"].unique() if c and c != "Multi-region")
    active = int(boards["status"].eq("active").sum())
    ready = int(boards["status"].eq("adapter_ready").sum())
    structured = int(boards["status"].isin(["active", "adapter_ready", "api_credentials"]).sum())
    fallback = int(boards["status"].isin(["manual_fallback", "blocked", "blocked_waf", "closed"]).sum())

    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric("Countries", len(countries))
    m2.metric("Board sources", len(boards))
    m3.metric("Active", active)
    m4.metric("Adapter ready", ready)
    m5.metric("Structured path", structured)

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
        "Active = working production adapter. Adapter ready = code exists and awaits/undergoes live runner validation. "
        "API credentials needed = official structured source exists but onboarding/token is required. "
        "Web verified = useful public source whose unattended transport still needs validation. "
        "Manual fallback = useful for ad-hoc research but intentionally not scheduled."
    )

    for country in selected_countries:
        country_rows = filtered[filtered["country"].eq(country)].copy()
        if country_rows.empty:
            continue
        country_rows = country_rows.sort_values(["_status_order", "finance_specific", "name"], ascending=[True, False, True])
        with st.expander(f"{country} — {len(country_rows)} sources", expanded=True):
            display_columns = ["name", "status_label", "adapter", "finance_specific", "base_url", "notes"]
            if "audited_at" in country_rows.columns:
                display_columns.append("audited_at")
            st.dataframe(
                country_rows[display_columns],
                hide_index=True,
                width="stretch",
                column_config={
                    "name": st.column_config.TextColumn("Board", width="medium"),
                    "status_label": st.column_config.TextColumn("Status", width="small"),
                    "adapter": st.column_config.TextColumn("Adapter", width="small"),
                    "finance_specific": st.column_config.CheckboxColumn("Finance-specific", width="small"),
                    "base_url": st.column_config.LinkColumn("Board", display_text="Open", width="small"),
                    "notes": st.column_config.TextColumn("Technical / sourcing note", width="large"),
                    "audited_at": st.column_config.TextColumn("Audited", width="small"),
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

    if fallback:
        st.caption(
            f"{fallback} registered sources are intentionally non-scheduled (manual fallback, blocked, or closed)."
        )
