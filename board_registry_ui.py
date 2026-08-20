from __future__ import annotations

from pathlib import Path

import pandas as pd
import streamlit as st

DATA_DIR = Path(__file__).parent / "data"

STATUS_LABELS = {
    "active": "Active", "adapter_ready": "Adapter ready", "web_verified": "Web verified",
    "api_credentials": "API credentials needed", "manual_fallback": "Manual fallback",
    "candidate": "Candidate", "blocked": "Blocked", "blocked_waf": "Blocked / WAF", "closed": "Closed",
}
STATUS_ORDER = {
    "active": 0, "adapter_ready": 1, "api_credentials": 2, "web_verified": 3,
    "candidate": 4, "manual_fallback": 5, "blocked": 6, "blocked_waf": 7, "closed": 8,
}


def _load_registry() -> pd.DataFrame:
    boards = pd.read_csv(DATA_DIR / "job_boards.csv").fillna("")
    audit_path = DATA_DIR / "job_board_access_audit.csv"
    if audit_path.exists() and not boards.empty:
        audit = pd.read_csv(audit_path).fillna("")
        if not audit.empty and "board_id" in audit.columns:
            audit = audit.drop_duplicates("board_id", keep="last").set_index("board_id")
            for target, source in (
                ("status", "status_override"), ("adapter", "adapter_override"), ("enabled", "enabled_override")
            ):
                mapped = boards["board_id"].map(audit.get(source, pd.Series(dtype=str))).fillna("")
                boards[target] = mapped.where(mapped.ne(""), boards[target])
            note = boards["board_id"].map(audit.get("audit_note", pd.Series(dtype=str))).fillna("")
            boards["notes"] = note.where(note.ne(""), boards["notes"])
            boards["audited_at"] = boards["board_id"].map(
                audit.get("audited_at", pd.Series(dtype=str))
            ).fillna("")

    runs_path = DATA_DIR / "board_source_runs.csv"
    boards["last_run"] = ""
    boards["last_verified_jobs"] = ""
    boards["last_error"] = ""
    if runs_path.exists():
        runs = pd.read_csv(runs_path).fillna("")
        if not runs.empty and "board_id" in runs.columns:
            runs = runs.sort_values("run_at").drop_duplicates("board_id", keep="last").set_index("board_id")
            boards["last_run"] = boards["board_id"].map(runs.get("run_at", pd.Series(dtype=str))).fillna("")
            boards["last_verified_jobs"] = boards["board_id"].map(
                runs.get("verified_jobs", pd.Series(dtype=str))
            ).fillna("")
            boards["last_error"] = boards["board_id"].map(runs.get("errors", pd.Series(dtype=str))).fillna("")
    return boards


def _table(frame: pd.DataFrame) -> None:
    columns = [
        "name", "status_label", "last_verified_jobs", "last_run", "adapter",
        "finance_specific", "base_url", "last_error", "notes",
    ]
    st.dataframe(
        frame[columns], hide_index=True, width="stretch",
        column_config={
            "name": st.column_config.TextColumn("Board", width="medium"),
            "status_label": st.column_config.TextColumn("Status", width="small"),
            "last_verified_jobs": st.column_config.TextColumn("Last roles", width="small"),
            "last_run": st.column_config.TextColumn("Last live run", width="medium"),
            "adapter": st.column_config.TextColumn("Adapter", width="small"),
            "finance_specific": st.column_config.CheckboxColumn("Finance-specific", width="small"),
            "base_url": st.column_config.LinkColumn("Board", display_text="Open", width="small"),
            "last_error": st.column_config.TextColumn("Last error", width="large"),
            "notes": st.column_config.TextColumn("Technical / sourcing note", width="large"),
        },
    )


def render_board_registry() -> None:
    st.markdown('<div class="eyebrow">Opportunity Radar</div>', unsafe_allow_html=True)
    st.title("Country / Board Sweep")
    st.caption(
        "Workstream G source registry and live diagnostics. G finds roles; A adds company context; "
        "C judges semantic role fit; retained opportunities belong in the normal Jobs inbox."
    )
    if not (DATA_DIR / "job_boards.csv").exists():
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
    ran = int(boards["last_run"].ne("").sum())

    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric("Countries", len(countries)); m2.metric("Board sources", len(boards)); m3.metric("Active", active)
    m4.metric("Adapter ready", ready); m5.metric("Ever live-tested", ran)
    st.code("G BOARD → ROLE + COMPANY → A COMPANY CONTEXT → C SEMANTIC FIT → JOBS INBOX")

    f1, f2 = st.columns(2)
    selected_countries = f1.multiselect("Countries", countries, default=countries)
    status_options = [label for key, label in STATUS_LABELS.items() if key in set(boards["status"])]
    selected_statuses = f2.multiselect("Technical status", status_options, default=status_options)
    selected_keys = {key for key, label in STATUS_LABELS.items() if label in selected_statuses}
    filtered = boards[boards["country"].isin(selected_countries) & boards["status"].isin(selected_keys)].copy()

    st.caption(
        "Active = proven in GitHub Actions. Adapter ready = implemented and awaiting/undergoing live validation. "
        "API credentials needed = official structured source needs onboarding/token. Web verified = useful public source "
        "whose unattended transport is not yet production-ready. Manual fallback = intentionally not scheduled."
    )
    for country in selected_countries:
        rows = filtered[filtered["country"].eq(country)].copy()
        if rows.empty:
            continue
        rows = rows.sort_values(["_status_order", "finance_specific", "name"], ascending=[True, False, True])
        with st.expander(f"{country} — {len(rows)} sources", expanded=True):
            _table(rows)

    multi = boards[boards["country"].eq("Multi-region")].sort_values(["_status_order", "name"])
    if not multi.empty:
        with st.expander(f"Multi-region — {len(multi)} sources", expanded=False):
            _table(multi)

    legacy_path = DATA_DIR / "jobs_board_staging.csv"
    if legacy_path.exists():
        legacy = pd.read_csv(legacy_path).fillna("")
        if not legacy.empty:
            st.divider()
            st.caption(
                f"Legacy/current G staging contains {len(legacy)} board-sourced rows for pipeline testing. "
                "This is not a separate user review queue."
            )
