from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import streamlit as st

from github_storage import (
    RATING_COLUMNS,
    github_token,
    load_csv_file,
    load_ratings,
    save_csv_file,
    save_ratings,
)
from sourcing.g_data_quality import invalid_company_name, invalid_job_title

COMPANY_TARGETING_FEEDBACK_PATH = "data/company_targeting_feedback.csv"
COMPANY_TARGETING_FEEDBACK_COLUMNS = ["submitted_at", "scope", "feedback"]
DISCOVERED_COMPANIES_PATH = Path(__file__).parent / "data" / "a_discovered_companies.csv"
DISCOVERED_COLUMNS = [
    "suggested_company_id", "company", "role_count", "countries", "source_streams",
    "sample_titles", "first_seen_at", "last_seen_at", "suggested_rating", "evidence_source",
]
COMPANY_THESIS_SCOPES = [
    "General (all company types)",
    "Big Four",
    "Consulting",
    "Corporate",
    "Banking & Financial Services",
    "Holding & Conglomerate",
    "Private Equity & Private Markets",
    "Investment Banking",
    "Public Markets & Asset Management",
    "Specialist & Boutique Funds",
]


def _norm(value: object) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value or "").lower())


def _known_company_names() -> set[str]:
    root = Path(__file__).parent / "data"
    names: set[str] = set()
    for path in [root / "company_universe.csv", *sorted(root.glob("company_universe_wave*.csv"))]:
        if not path.exists() or not path.stat().st_size:
            continue
        try:
            frame = pd.read_csv(path).fillna("")
        except Exception:
            continue
        for _, row in frame.iterrows():
            for value in [row.get("company", ""), *str(row.get("aliases_entities", "")).split(";")]:
                key = _norm(value)
                if key:
                    names.add(key)
    return names


def _usable_suggestion(row: pd.Series, known_names: set[str]) -> bool:
    company = str(row.get("company", "")).strip()
    if invalid_company_name(company) or _norm(company) in known_names:
        return False
    titles = [x.strip() for x in str(row.get("sample_titles", "")).split("|") if x.strip()]
    return any(not invalid_job_title(title) for title in titles)


def render_discovered_company_suggestions() -> None:
    """Show G-discovered employers as A suggestions without auto-rating them."""
    if not DISCOVERED_COMPANIES_PATH.exists() or not DISCOVERED_COMPANIES_PATH.stat().st_size:
        return
    try:
        discovered = pd.read_csv(DISCOVERED_COMPANIES_PATH).fillna("").reindex(columns=DISCOVERED_COLUMNS, fill_value="")
    except Exception:
        return
    if discovered.empty:
        return

    known_names = _known_company_names()
    discovered = discovered[discovered.apply(lambda r: _usable_suggestion(r, known_names), axis=1)].copy()
    if discovered.empty:
        return

    token = github_token()
    try:
        ratings, ratings_sha = load_ratings(token)
    except Exception:
        ratings = pd.DataFrame(columns=RATING_COLUMNS)
        ratings_sha = None
    ratings = ratings.reindex(columns=RATING_COLUMNS, fill_value="")
    rating_map = (
        ratings.drop_duplicates("canonical_company_id", keep="last")
        .set_index("canonical_company_id")["rating"].to_dict()
        if not ratings.empty else {}
    )
    discovered["rating"] = discovered["suggested_company_id"].map(rating_map).fillna("Unrated").replace("", "Unrated")

    st.divider()
    st.subheader("Discovered by G")
    st.caption(
        "New employers found while sourcing vacancies. They enter A only as Unrated suggestions. "
        "Nothing changes your company thesis unless you explicitly assign A/B/C/Exclude here."
    )
    st.metric("Unrated / discovered employers", int((discovered["rating"] == "Unrated").sum()))

    view = discovered[[
        "suggested_company_id", "company", "rating", "role_count", "countries",
        "sample_titles", "last_seen_at",
    ]].set_index("suggested_company_id")
    edited = st.data_editor(
        view,
        hide_index=True,
        width="stretch",
        height=min(620, 105 + 42 * min(len(view), 12)),
        disabled=["company", "role_count", "countries", "sample_titles", "last_seen_at"],
        column_config={
            "company": st.column_config.TextColumn("Company", width="medium"),
            "rating": st.column_config.SelectboxColumn(
                "A rating",
                options=["Unrated", "A", "B", "C", "Exclude"],
                required=True,
                help="Only an explicit change here becomes an A rating.",
            ),
            "role_count": st.column_config.NumberColumn("G roles", width="small"),
            "countries": st.column_config.TextColumn("Markets", width="small"),
            "sample_titles": st.column_config.TextColumn("Why G found it", width="large"),
            "last_seen_at": st.column_config.TextColumn("Last seen", width="medium"),
        },
        key="a_discovered_company_editor",
    )

    changed = []
    for suggested_id, row in edited.iterrows():
        old = str(view.loc[suggested_id, "rating"] or "Unrated")
        new = str(row.get("rating", "Unrated") or "Unrated")
        if new != old:
            changed.append((suggested_id, new))

    if changed:
        if not token:
            st.error("GitHub saving is not configured, so the A rating could not be saved.")
            return
        current = ratings.drop_duplicates("canonical_company_id", keep="last").set_index("canonical_company_id")
        for suggested_id, new_rating in changed:
            if suggested_id not in current.index:
                current.loc[suggested_id] = {
                    "rating": new_rating,
                    "familiarity": "Unknown",
                    "contact_strength": "None",
                    "relationship_type": "None",
                    "reference_notes": "",
                    "notes": "G-discovered employer; explicitly rated in A.",
                }
            else:
                current.at[suggested_id, "rating"] = new_rating
        try:
            save_ratings(token, current.reset_index().reindex(columns=RATING_COLUMNS, fill_value=""), ratings_sha)
        except Exception as exc:
            st.error(f"Saving A rating failed: {exc}")
        else:
            st.toast("A rating saved", icon="✅")
            st.rerun()


def render_company_targeting_feedback() -> None:
    render_discovered_company_suggestions()

    with st.expander("Give feedback on the company targeting thesis"):
        st.caption(
            "Tell company discovery what kinds of employers to prioritise or downrank. "
            "For example: 'large multi-country corporates are attractive', "
            "'avoid tiny advisory boutiques', or 'asset managers similar to X are interesting'. "
            "This is company-level feedback for A, separate from the role-level thesis in Jobs."
        )
        scope = st.selectbox(
            "Scope",
            COMPANY_THESIS_SCOPES,
            key="company_thesis_fb_scope",
        )
        feedback_text = st.text_area(
            "Your company thesis feedback",
            key="company_thesis_fb_text",
            placeholder="What should company discovery emphasise or avoid?",
        )
        if st.button(
            "Save company thesis feedback",
            key="company_thesis_fb_save",
            disabled=not feedback_text.strip(),
        ):
            token = github_token()
            if not token:
                st.error("GitHub saving is not configured for this app.")
            else:
                existing, sha = load_csv_file(
                    token,
                    COMPANY_TARGETING_FEEDBACK_PATH,
                    COMPANY_TARGETING_FEEDBACK_COLUMNS,
                )
                new_row = {
                    "submitted_at": datetime.now(timezone.utc).isoformat(),
                    "scope": scope,
                    "feedback": feedback_text.strip(),
                }
                existing = pd.concat(
                    [existing, pd.DataFrame([new_row])],
                    ignore_index=True,
                )
                try:
                    save_csv_file(
                        token,
                        COMPANY_TARGETING_FEEDBACK_PATH,
                        existing,
                        sha,
                        "Add company targeting thesis feedback",
                    )
                except Exception:
                    st.error("Saving failed. Refresh and try again.")
                else:
                    st.success("Saved. It is ready for the next company-thesis calibration.")

        try:
            prior, _ = load_csv_file(
                github_token(),
                COMPANY_TARGETING_FEEDBACK_PATH,
                COMPANY_TARGETING_FEEDBACK_COLUMNS,
            )
        except Exception:
            prior = pd.DataFrame(columns=COMPANY_TARGETING_FEEDBACK_COLUMNS)
        if not prior.empty:
            st.caption("Your company thesis feedback so far:")
            st.dataframe(
                prior.sort_values("submitted_at", ascending=False)[
                    ["scope", "feedback", "submitted_at"]
                ],
                hide_index=True,
                width="stretch",
            )