from __future__ import annotations

from pathlib import Path

import pandas as pd
import streamlit as st

DATA_DIR = Path(__file__).parent / "data"
VERIFIED_JOB_TYPES = {
    "schema.org/JobPosting",
    "schema.org/JobPosting JSON-LD",
    "schema.org/JobPosting microdata",
    "official ATS vacancy detail",
}


def _country_from_market_and_location(market: str, location: str) -> str:
    if market != "Nordics":
        return market
    normalized = location.lower()
    country_terms = {
        "Sweden": ("sweden", "stockholm", "gothenburg", "malmö", "malmo"),
        "Denmark": ("denmark", "copenhagen", "aarhus"),
        "Norway": ("norway", "oslo", "bergen"),
        "Finland": ("finland", "helsinki", "espoo"),
    }
    matches = [
        country
        for country, terms in country_terms.items()
        if any(term in normalized for term in terms)
    ]
    return "; ".join(matches) if matches else "Nordics"


def render_jobs() -> None:
    st.markdown('<div class="eyebrow">Opportunity Radar</div>', unsafe_allow_html=True)
    st.title("Jobs")
    st.caption("Verified individual vacancies from the official Big Four career portals.")
    frames: list[pd.DataFrame] = []
    pilot_path = DATA_DIR / "jobs.csv"
    if pilot_path.exists():
        pilot = pd.read_csv(pilot_path).fillna("")
        if "verification" in pilot.columns:
            pilot = pilot[pilot["verification"].isin(VERIFIED_JOB_TYPES)].copy()
        if not pilot.empty:
            pilot = pilot.rename(
                columns={
                    "job_id": "opportunity_id",
                    "market": "countries",
                    "location": "cities",
                    "job_url": "source_url",
                }
            )
            pilot["countries"] = pilot.apply(
                lambda row: _country_from_market_and_location(row["countries"], row["cities"]),
                axis=1,
            )
            pilot["role_family"] = "Other relevant finance"
            pilot["seniority"] = ""
            if "matched_terms" in pilot.columns:
                pilot["fit_note"] = pilot["matched_terms"].apply(
                    lambda value: f"Matched role terms: {value}"
                    if value
                    else "Verified role from the Big Four pilot."
                )
            else:
                pilot["fit_note"] = "Verified role from the Big Four pilot."
            if "status" in pilot.columns:
                pilot["status"] = pilot["status"].replace("", "Open")
            else:
                pilot["status"] = "Open"
            pilot["review_status"] = "New"
            frames.append(pilot)

    if not frames:
        st.warning("The sourcing workflow has not produced its first verified vacancy snapshot yet.")
        return
    jobs = pd.concat(frames, ignore_index=True, sort=False).fillna("")
    jobs = jobs.drop_duplicates("source_url", keep="last")
    if jobs.empty:
        st.info(
            "The latest run did not verify any individual vacancies yet. "
            "Source diagnostics show which career portals need a dedicated adapter."
        )
        return

    ratings_path = DATA_DIR / "company_ratings.csv"
    if ratings_path.exists():
        ratings = pd.read_csv(ratings_path).fillna("")[["canonical_company_id", "rating"]]
        jobs = jobs.merge(ratings, on="canonical_company_id", how="left")
    else:
        jobs["rating"] = "Unrated"
    jobs["rating"] = jobs["rating"].replace("", "Unrated")
    for required, default in {
        "countries": "",
        "cities": "",
        "role_family": "Other relevant finance",
        "seniority": "",
        "fit_note": "",
        "discovered_at": "",
        "status": "Open",
        "review_status": "New",
    }.items():
        if required not in jobs.columns:
            jobs[required] = default

    countries = sorted(
        {
            country.strip()
            for value in jobs["countries"]
            for country in str(value).split(";")
            if country.strip()
        }
    )
    ratings = [rating for rating in ["A", "B", "C", "Unrated"] if rating in set(jobs["rating"])]
    roles = sorted(value for value in jobs["role_family"].unique() if value)
    f1, f2, f3 = st.columns(3)
    selected_countries = f1.multiselect("Countries", countries, default=countries)
    selected_ratings = f2.multiselect("Company rating", ratings, default=ratings)
    selected_roles = f3.multiselect("Role family", roles, default=roles)
    selected_country_set = set(selected_countries)
    country_match = jobs["countries"].apply(
        lambda value: bool(
            {country.strip() for country in str(value).split(";") if country.strip()}
            & selected_country_set
        )
    )
    view = jobs[
        country_match
        & jobs["rating"].isin(selected_ratings)
        & jobs["role_family"].isin(selected_roles)
        & jobs["status"].eq("Open")
    ].copy()
    view = view.sort_values(["rating", "discovered_at"], ascending=[True, False])

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Open opportunities", len(view))
    c2.metric("New", int(view["review_status"].eq("New").sum()))
    c3.metric("A-rated companies", int(view["rating"].eq("A").sum()))
    c4.metric("Selected countries", len(selected_countries))
    st.caption(
        "Pilot scope: Deloitte, PwC, EY and KPMG only. Multi-location opportunities appear under "
        "every listed country; Nordic vacancies are split by country when the official location allows it."
    )

    columns = [
        "title",
        "company",
        "rating",
        "countries",
        "cities",
        "role_family",
        "seniority",
        "fit_note",
        "discovered_at",
        "source_url",
    ]
    st.dataframe(
        view[columns],
        hide_index=True,
        width="stretch",
        height=620,
        row_height=82,
        column_config={
            "title": st.column_config.TextColumn("Opportunity", width="large"),
            "company": st.column_config.TextColumn("Company", width="medium"),
            "rating": st.column_config.TextColumn("Company rating", width="small"),
            "countries": st.column_config.TextColumn("Countries", width="medium"),
            "cities": st.column_config.TextColumn("Cities", width="medium"),
            "role_family": st.column_config.TextColumn("Role family", width="medium"),
            "seniority": st.column_config.TextColumn("Seniority", width="small"),
            "fit_note": st.column_config.TextColumn("Why it may fit", width=520),
            "discovered_at": st.column_config.TextColumn("Discovered", width="small"),
            "source_url": st.column_config.LinkColumn("Official job", display_text="Open", width="small"),
        },
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
        st.dataframe(
            sources[["company", "market", "priority_locations", "seed_url", "enabled"]],
            hide_index=True,
            width="stretch",
            column_config={
                "seed_url": st.column_config.LinkColumn("Career page", display_text="Open")
            },
        )

    if runs_path.exists():
        st.subheader("Recent source runs")
        runs = pd.read_csv(runs_path).fillna("").tail(100)
        runs = runs.sort_values("run_at", ascending=False)
        st.dataframe(
            runs,
            hide_index=True,
            width="stretch",
            column_config={
                "seed_url": st.column_config.LinkColumn("Source", display_text="Open")
            },
        )
    else:
        st.info("No source-run history yet. It will appear after the first workflow execution.")
