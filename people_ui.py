"""Workstream F - People / Network.

Ingests a LinkedIn "Connections" CSV export (no scraping), matches each person
to a company in the Company Universe, and stores them in data/connections.csv.
This is the access layer: knowing people at a company is a SEPARATE signal
(blueprint AccessStrength) that can boost opportunities there -- it never
overrides intrinsic fit.
"""
from __future__ import annotations

import io
import re
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import streamlit as st

from github_storage import github_token, load_csv_file, save_csv_file

DATA_DIR = Path(__file__).parent / "data"
CONNECTIONS_PATH = "data/connections.csv"
CONNECTIONS_COLUMNS = [
    "full_name", "first_name", "last_name", "company_raw",
    "canonical_company_id", "matched_company", "position",
    "connected_on", "linkedin_url", "added_at",
]


def _norm(value: object) -> str:
    return re.sub(r"[^a-z0-9]", "", str(value or "").lower())


def _company_lookup() -> dict[str, tuple[str, str]]:
    """normalized company/alias -> (canonical_company_id, display company)."""
    lookup: dict[str, tuple[str, str]] = {}
    files = [DATA_DIR / "company_universe.csv"] + sorted(DATA_DIR.glob("company_universe_wave*.csv"))
    for path in files:
        if not path.exists():
            continue
        frame = pd.read_csv(path).fillna("")
        for _, row in frame.iterrows():
            cid = str(row.get("canonical_company_id", "")).strip()
            comp = str(row.get("company", "")).strip()
            if not cid or not comp:
                continue
            keys = [comp, *str(row.get("aliases_entities", "")).split(";")]
            for key in keys:
                nk = _norm(key)
                if nk:
                    lookup.setdefault(nk, (cid, comp))
    return lookup


def parse_linkedin_csv(raw: bytes) -> pd.DataFrame:
    text = raw.decode("utf-8-sig", errors="replace")
    lines = text.splitlines()
    # LinkedIn prepends a "Notes:" preamble; the real table starts at the
    # header row that begins with "First Name".
    start = 0
    for i, line in enumerate(lines):
        if line.lower().startswith("first name,"):
            start = i
            break
    table = "\n".join(lines[start:])
    df = pd.read_csv(io.StringIO(table)).fillna("")
    df.columns = [c.strip() for c in df.columns]
    return df


def render_people() -> None:
    st.title("Lidé / Network")
    st.caption(
        "Your professional network (LinkedIn export), matched to companies in "
        "your universe. Knowing people at a company is a separate access signal "
        "that can boost opportunities there -- it never overrides role fit."
    )
    with st.expander("How to get your LinkedIn connections file"):
        st.write(
            "LinkedIn: Settings & Privacy -> Data privacy -> Get a copy of your "
            "data -> pick 'Connections' -> download the CSV, then upload it here. "
            "Re-upload anytime to refresh; existing people are kept and updated."
        )

    token = github_token()
    upload = st.file_uploader("Upload LinkedIn Connections CSV", type=["csv"])
    if upload is not None and st.button("Import connections", type="primary"):
        try:
            raw = parse_linkedin_csv(upload.getvalue())
        except Exception as exc:
            st.error(f"Could not read the file: {exc}")
            raw = None
        if raw is not None:
            lookup = _company_lookup()
            now = datetime.now(timezone.utc).isoformat()
            rows = []
            for _, r in raw.iterrows():
                first = str(r.get("First Name", "")).strip()
                last = str(r.get("Last Name", "")).strip()
                company_raw = str(r.get("Company", "")).strip()
                cid, matched = lookup.get(_norm(company_raw), ("", ""))
                rows.append({
                    "full_name": f"{first} {last}".strip(),
                    "first_name": first, "last_name": last,
                    "company_raw": company_raw,
                    "canonical_company_id": cid, "matched_company": matched,
                    "position": str(r.get("Position", "")).strip(),
                    "connected_on": str(r.get("Connected On", "")).strip(),
                    "linkedin_url": str(r.get("URL", "")).strip(),
                    "added_at": now,
                })
            incoming = pd.DataFrame(rows)
            if not token:
                st.error("GitHub saving is not configured for this app.")
            else:
                existing, sha = load_csv_file(token, CONNECTIONS_PATH, CONNECTIONS_COLUMNS)
                combined = pd.concat([existing, incoming], ignore_index=True)
                combined["_key"] = combined["linkedin_url"].where(
                    combined["linkedin_url"].ne(""),
                    combined["full_name"] + "|" + combined["company_raw"],
                )
                combined = combined.drop_duplicates("_key", keep="last").drop(columns=["_key"])
                try:
                    save_csv_file(token, CONNECTIONS_PATH, combined[CONNECTIONS_COLUMNS], sha, "Import LinkedIn connections")
                except Exception:
                    st.error("Saving failed. Refresh and try again.")
                else:
                    matched_n = int((incoming["canonical_company_id"] != "").sum())
                    st.success(f"Imported {len(incoming)} connections; {matched_n} matched to a universe company.")

    try:
        connections, _ = load_csv_file(token, CONNECTIONS_PATH, CONNECTIONS_COLUMNS)
    except Exception:
        connections = pd.DataFrame(columns=CONNECTIONS_COLUMNS)
    if connections.empty:
        st.info("No connections yet -- upload your LinkedIn export above.")
        return

    matched = connections[connections["canonical_company_id"].astype(str).str.strip() != ""]
    m1, m2, m3 = st.columns(3)
    m1.metric("Connections", len(connections))
    m2.metric("Matched to a company", len(matched))
    m3.metric("Companies you know someone at", matched["canonical_company_id"].nunique())

    if not matched.empty:
        st.subheader("Access by company")
        by_company = (
            matched.groupby(["canonical_company_id", "matched_company"])
            .size().reset_index(name="contacts")
            .sort_values("contacts", ascending=False)
        )
        st.dataframe(by_company[["matched_company", "contacts"]], hide_index=True, width="stretch")

    st.subheader("All connections")
    st.dataframe(
        connections.sort_values("full_name")[
            ["full_name", "position", "company_raw", "matched_company", "linkedin_url"]
        ],
        hide_index=True, width="stretch",
        column_config={"linkedin_url": st.column_config.LinkColumn("Profile", display_text="Open")},
    )
