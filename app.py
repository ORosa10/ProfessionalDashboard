from __future__ import annotations

from pathlib import Path

import pandas as pd
import streamlit as st


st.set_page_config(
    page_title="Professional Dashboard",
    page_icon="🧭",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
    <style>
        .block-container {padding-top: 2rem; padding-bottom: 3rem; max-width: 1280px;}
        [data-testid="stMetric"] {background: #f7f8fa; border: 1px solid #e6e8ec; padding: 1rem; border-radius: 0.8rem;}
        .eyebrow {color: #667085; font-size: 0.78rem; font-weight: 700; letter-spacing: 0.08em; text-transform: uppercase;}
        .muted {color: #667085;}
        .status-card {border: 1px solid #e6e8ec; border-radius: 0.8rem; padding: 1rem 1.1rem; margin-bottom: 0.75rem;}
    </style>
    """,
    unsafe_allow_html=True,
)

def header(title: str, description: str) -> None:
    st.markdown('<div class="eyebrow">Opportunity Radar</div>', unsafe_allow_html=True)
    st.title(title)
    st.markdown(f'<p class="muted">{description}</p>', unsafe_allow_html=True)


def placeholder(title: str, body: str, next_step: str) -> None:
    header(title, body)
    st.info(f"Next build step: {next_step}", icon="🛠️")


def home_page() -> None:
    header(
        "Good evening",
        "Your future daily view of new opportunities, decisions, and active next steps.",
    )
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("New opportunities", 0)
    col2.metric("Needs review", 0)
    col3.metric("Active", 0)
    col4.metric("Radar signals", 0)

    st.subheader("Foundation status")
    left, right = st.columns([1.4, 1])
    with left:
        st.markdown(
            """
            <div class="status-card"><strong>1. App shell</strong><br><span class="muted">Ready for deployment and iteration.</span></div>
            <div class="status-card"><strong>2. Persistence</strong><br><span class="muted">Next: choose durable external storage for Streamlit Cloud.</span></div>
            <div class="status-card"><strong>3. First real sourcing</strong><br><span class="muted">Next: define the first SearchProfile and source.</span></div>
            """,
            unsafe_allow_html=True,
        )
    with right:
        st.subheader("Operating model")
        st.code("SOURCES → DISCOVERY → INBOX → REVIEW → ACTIVE → OUTCOME")
        st.caption("Jobs are the first product wedge. Scoring comes only after real feedback.")


def opportunities_page() -> None:
    placeholder(
        "Opportunity overview",
        "The unified inbox and catalogue for all professional opportunity types.",
        "Add the Opportunity model, durable storage, and the review queue.",
    )


def jobs_page() -> None:
    header("Jobs", "The first real sourcing engine, structured as WHAT × WHERE × WHO × SOURCE.")
    st.success("Initial SearchProfile v0.1 is defined and intentionally stored outside the public repository.")
    st.markdown(
        "The profile evaluates seniority by role family, uses penalties instead of premature hard filters, "
        "and keeps a dedicated exploration bucket. Personal language, citizenship, and compensation inputs "
        "remain private."
    )
    st.info(
        "Next build step: persist this profile, create the first Company Universe, and connect a real source.",
        icon="🛠️",
    )


def companies_page() -> None:
    header(
        "Companies",
        "Review the first Company Universe across employer archetypes and target regions.",
    )
    data_path = Path(__file__).parent / "data" / "company_universe.csv"
    universe = pd.read_csv(data_path).fillna("")

    region_options = sorted(universe["region"].unique())
    selected_regions = st.multiselect("Filter regions", region_options, default=region_options)
    filtered = universe[universe["region"].isin(selected_regions)].copy()

    st.caption(
        f"Showing {len(filtered)} canonical companies. Global and local career pages roll up to one company; "
        "duplicate vacancies will retain multiple source links."
    )
    review_columns = [
        "company",
        "region",
        "locations",
        "archetype",
        "why_test",
        "career_url",
        "source_strategy",
        "rating",
        "notes",
    ]
    edited = st.data_editor(
        filtered[review_columns],
        hide_index=True,
        width="stretch",
        height=620,
        disabled=[
            "company",
            "region",
            "locations",
            "archetype",
            "why_test",
            "career_url",
            "source_strategy",
        ],
        column_config={
            "company": st.column_config.TextColumn("Company", width="medium"),
            "region": st.column_config.TextColumn("Region", width="small"),
            "locations": st.column_config.TextColumn("Locations", width="medium"),
            "archetype": st.column_config.TextColumn("Archetype", width="medium"),
            "why_test": st.column_config.TextColumn("Why test", width="large"),
            "career_url": st.column_config.LinkColumn("Careers", display_text="Open"),
            "source_strategy": st.column_config.TextColumn("Source structure", width="large"),
            "rating": st.column_config.SelectboxColumn(
                "Rating",
                options=["Unrated", "A", "B", "C", "Exclude"],
                required=True,
                width="small",
            ),
            "notes": st.column_config.TextColumn("Your notes", width="large"),
        },
        key="company_universe_editor",
    )

    st.download_button(
        "Download ratings as CSV",
        data=edited.to_csv(index=False).encode("utf-8-sig"),
        file_name="company_universe_ratings.csv",
        mime="text/csv",
        type="primary",
    )
    st.info(
        "Ratings are editable now but not yet durable. Download the CSV before the app resets; database persistence is the next infrastructure step.",
        icon="ℹ️",
    )


def pipeline_page() -> None:
    placeholder(
        "Pipeline",
        "Active pursuits, stages, deadlines, next actions, and outcomes.",
        "Define pipeline stages after the first review workflow is usable.",
    )


def ideas_page() -> None:
    placeholder(
        "Ideas & Projects",
        "Self-created opportunities, experiments, collaborations, and possible projects.",
        "Add this engine after the job learning loop is working.",
    )


def sources_page() -> None:
    placeholder(
        "Sources / Radar",
        "Source configuration, freshness, run history, monitoring, and discovery diagnostics.",
        "Implement the shared Source and source-run framework with one genuine job source.",
    )


with st.sidebar:
    st.title("🧭 Professional Dashboard")
    st.caption("Personal opportunity intelligence")

navigation = st.navigation(
    {
        "Dashboard": [st.Page(home_page, title="Home")],
        "Opportunities": [
            st.Page(opportunities_page, title="Overview"),
            st.Page(jobs_page, title="Jobs"),
            st.Page(companies_page, title="Companies"),
        ],
        "Workspace": [
            st.Page(pipeline_page, title="Pipeline"),
            st.Page(ideas_page, title="Ideas & Projects"),
        ],
        "System": [st.Page(sources_page, title="Sources / Radar")],
    }
)

with st.sidebar:
    st.divider()
    st.caption("v0 foundation · Build for iteration")

navigation.run()
