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
SCRAPE_LABELS = {
    "YES": "YES",
    "YES_CREDENTIALS": "YES — credentials",
    "NO": "NO — manual",
}


def _load_registry() -> pd.DataFrame:
    boards = pd.read_csv(DATA_DIR / "job_boards.csv").fillna("")
    boards["scrapeability"] = ""
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
            boards["scrapeability"] = boards["board_id"].map(
                audit.get("scrapeability", pd.Series(dtype=str))
            ).fillna("")
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
        "name", "scrapeability_label", "status_label", "last_verified_jobs", "last_run", "adapter",
        "finance_specific", "base_url", "last_error", "notes",
    ]
    st.dataframe(
        frame[columns], hide_index=True, width="stretch",
        column_config={
            "name": st.column_config.TextColumn("Board", width="medium"),
            "scrapeability_label": st.column_config.TextColumn("Scrapeability", width="small"),
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


def _country_summary(boards: pd.DataFrame, countries: list[str]) -> pd.DataFrame:
    rows = []
    for country in countries:
        frame = boards[boards["country"].eq(country)]
        rows.append({
            "Country": country,
            "Active": int(frame["status"].eq("active").sum()),
            "Scrapeable": int(frame["scrapeability"].eq("YES").sum()),
            "Needs credentials": int(frame["scrapeability"].eq("YES_CREDENTIALS").sum()),
            "Manual / no": int(frame["scrapeability"].eq("NO").sum()),
            "Registered sources": len(frame),
        })
    return pd.DataFrame(rows)


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
    boards["scrapeability_label"] = boards["scrapeability"].map(SCRAPE_LABELS).fillna(boards["scrapeability"])
    boards["_status_order"] = boards["status"].map(STATUS_ORDER).fillna(99)
    countries = sorted(c for c in boards["country"].unique() if c and c != "Multi-region")
    scrape_yes = int(boards["scrapeability"].eq("YES").sum())
    scrape_creds = int(boards["scrapeability"].eq("YES_CREDENTIALS").sum())
    active = int(boards["status"].eq("active").sum())

    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric("Countries", len(countries))
    m2.metric("Registered sources", len(boards))
    m3.metric("Active now", active)
    m4.metric("Scrapeable", scrape_yes)
    m5.metric("Needs credentials", scrape_creds)
    st.code("G BOARD → ROLE + COMPANY → A COMPANY CONTEXT → C SEMANTIC FIT → JOBS INBOX")

    st.subheader("Coverage by country")
    st.dataframe(
        _country_summary(boards, countries),
        hide_index=True,
        width="stretch",
        column_config={
            "Active": st.column_config.NumberColumn("Active now", format="%d"),
            "Scrapeable": st.column_config.NumberColumn("Scrapeable", format="%d"),
            "Needs credentials": st.column_config.NumberColumn("Credentials", format="%d"),
            "Manual / no": st.column_config.NumberColumn("Manual / no", format="%d"),
            "Registered sources": st.column_config.NumberColumn("Registered sources", format="%d"),
        },
    )
    st.caption(
        "Registered sources is the total inventory for that country, so it includes scrapeable, credential-gated and manual/blocked sources. "
        "It is not an additional status bucket. Active now is the subset already proven in GitHub Actions."
    )

    f1, f2, f3 = st.columns(3)
    selected_countries = f1.multiselect("Countries", countries, default=countries)
    scrape_options = [label for key, label in SCRAPE_LABELS.items() if key in set(boards["scrapeability"])]
    selected_scrape = f2.multiselect("Scrapeability", scrape_options, default=scrape_options)
    status_options = [label for key, label in STATUS_LABELS.items() if key in set(boards["status"])]
    selected_statuses = f3.multiselect("Technical status", status_options, default=status_options)
    selected_keys = {key for key, label in STATUS_LABELS.items() if label in selected_statuses}
    selected_scrape_keys = {key for key, label in SCRAPE_LABELS.items() if label in selected_scrape}
    filtered = boards[
        boards["country"].isin(selected_countries)
        & boards["status"].isin(selected_keys)
        & boards["scrapeability"].isin(selected_scrape_keys)
    ].copy()

    st.caption(
        "Scrapeability: YES = technically usable for automated retrieval; YES — credentials = token/onboarding required; "
        "NO — manual = keep as a manual fallback. Status separately shows whether the scraper is already active or still being activated."
    )
    for country in selected_countries:
        rows = filtered[filtered["country"].eq(country)].copy()
        if rows.empty:
            continue
        all_country = boards[boards["country"].eq(country)]
        active_country = int(all_country["status"].eq("active").sum())
        scrape_country = int(all_country["scrapeability"].eq("YES").sum())
        creds_country = int(all_country["scrapeability"].eq("YES_CREDENTIALS").sum())
        rows = rows.sort_values(["_status_order", "finance_specific", "name"], ascending=[True, False, True])
        label = (
            f"{country} — {active_country} active / {scrape_country} scrapeable"
            + (f" / {creds_country} credentials" if creds_country else "")
            + f" / {len(all_country)} registered"
        )
        with st.expander(label, expanded=True):
            _table(rows)

    multi = boards[boards["country"].eq("Multi-region")].sort_values(["_status_order", "name"])
    if not multi.empty:
        with st.expander(f"Multi-region — {len(multi)} registered", expanded=False):
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
