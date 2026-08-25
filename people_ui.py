"""Workstream F - People / Network.

Imports a user-provided LinkedIn Connections CSV (no scraping), records factual
company access evidence, and keeps access separate from company preference,
semantic role fit and attainability.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import streamlit as st

from github_storage import github_token, load_csv_file, save_csv_file
from sourcing.network_access import (
    CONNECTIONS_COLUMNS,
    build_access_summary,
    build_alias_index,
    deduplicate_connections,
    match_linkedin_connections,
    parse_linkedin_csv,
)

DATA_DIR = Path(__file__).parent / "data"
CONNECTIONS_PATH = "data/connections.csv"


def _company_universes() -> list[pd.DataFrame]:
    frames: list[pd.DataFrame] = []
    files = [DATA_DIR / "company_universe.csv"] + sorted(DATA_DIR.glob("company_universe_wave*.csv"))
    for path in files:
        if not path.exists():
            continue
        try:
            frames.append(pd.read_csv(path).fillna(""))
        except (pd.errors.EmptyDataError, pd.errors.ParserError, OSError):
            continue
    return frames


def render_people() -> None:
    st.title("Lidé / Network")
    st.caption(
        "Your professional network, matched conservatively to canonical employers. "
        "Access is factual context only: it never overrides company preference or role fit."
    )
    with st.expander("How to get your LinkedIn connections file"):
        st.write(
            "LinkedIn: Settings & Privacy -> Data privacy -> Get a copy of your "
            "data -> pick 'Connections' -> download the CSV, then upload it here. "
            "Re-upload anytime to refresh; a person with the same LinkedIn URL is updated."
        )
        st.caption(
            "Company matching uses only exact normalized names and explicit aliases from A. "
            "Ambiguous or unknown company labels stay unresolved instead of being guessed."
        )

    token = github_token()
    upload = st.file_uploader("Upload LinkedIn Connections CSV", type=["csv"])
    if upload is not None and st.button("Import connections", type="primary"):
        try:
            raw = parse_linkedin_csv(upload.getvalue())
            alias_index = build_alias_index(_company_universes())
            incoming = match_linkedin_connections(raw, alias_index)
        except Exception as exc:
            st.error(f"Could not read the file: {exc}")
            incoming = None

        if incoming is not None:
            if not token:
                st.error("GitHub saving is not configured for this app.")
            else:
                existing, sha = load_csv_file(token, CONNECTIONS_PATH, CONNECTIONS_COLUMNS)
                combined = deduplicate_connections(existing, incoming)
                try:
                    save_csv_file(
                        token,
                        CONNECTIONS_PATH,
                        combined[CONNECTIONS_COLUMNS],
                        sha,
                        "Import LinkedIn connections",
                    )
                except Exception:
                    st.error("Saving failed. Refresh and try again.")
                else:
                    statuses = incoming["company_match_status"].value_counts()
                    matched_n = int(statuses.get("matched_exact_alias", 0))
                    ambiguous_n = int(statuses.get("ambiguous_alias", 0))
                    unmatched_n = int(statuses.get("unmatched_company", 0))
                    st.success(
                        f"Imported {len(incoming)} connections; {matched_n} matched to a canonical company."
                    )
                    if ambiguous_n or unmatched_n:
                        st.info(
                            f"Company identity still needs resolution for {ambiguous_n} ambiguous "
                            f"and {unmatched_n} unmatched label(s). Nothing was guessed."
                        )

    try:
        connections, _ = load_csv_file(token, CONNECTIONS_PATH, CONNECTIONS_COLUMNS)
    except Exception:
        connections = pd.DataFrame(columns=CONNECTIONS_COLUMNS)
    if connections.empty:
        st.info("No connections yet -- upload your LinkedIn export above.")
        return

    connections = connections.reindex(columns=CONNECTIONS_COLUMNS, fill_value="").fillna("")
    matched = connections[connections["company_match_status"].eq("matched_exact_alias")]
    unresolved = connections[~connections["company_match_status"].eq("matched_exact_alias")]

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Connections", len(connections))
    m2.metric("Matched to a company", len(matched))
    m3.metric("Companies with access", matched["canonical_company_id"].nunique())
    m4.metric("Identity unresolved", len(unresolved))

    access = build_access_summary(connections)
    if not access.empty:
        st.subheader("Access by company")
        st.dataframe(
            access[["company", "contact_count", "positions"]],
            hide_index=True,
            width="stretch",
        )
        st.caption("This is factual F -> A access evidence only; no company rating is inferred.")

    if not unresolved.empty:
        with st.expander(f"Unresolved company identities ({len(unresolved)})"):
            st.dataframe(
                unresolved[["full_name", "company_raw", "position", "company_match_status"]]
                .sort_values(["company_match_status", "company_raw", "full_name"]),
                hide_index=True,
                width="stretch",
            )

    st.subheader("All connections")
    st.dataframe(
        connections.sort_values("full_name")[
            ["full_name", "position", "company_raw", "matched_company", "company_match_status", "linkedin_url"]
        ],
        hide_index=True,
        width="stretch",
        column_config={"linkedin_url": st.column_config.LinkColumn("Profile", display_text="Open")},
    )
