from __future__ import annotations

from pathlib import Path

import pandas as pd
import streamlit as st

from github_storage import github_token, load_ratings, save_ratings


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
            <div class="status-card"><strong>2. Persistence</strong><br><span class="muted">Direct GitHub saving is active for company feedback.</span></div>
            <div class="status-card"><strong>3. First real sourcing</strong><br><span class="muted">Next: turn the rated Company Universe into monitored job sources.</span></div>
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
        "Next build step: rate the Company Universe and connect the first real career-page source.",
        icon="🛠️",
    )


def companies_page() -> None:
    header(
        "Companies",
        "Review the first Company Universe across employer archetypes and target regions.",
    )
    data_dir = Path(__file__).parent / "data"
    data_path = data_dir / "company_universe.csv"
    category_path = data_dir / "company_categories.csv"
    universe = pd.read_csv(data_path).fillna("")
    categories = pd.read_csv(category_path)
    for wave_path in sorted(data_dir.glob("company_universe_wave*.csv")):
        wave = pd.read_csv(wave_path).fillna("")
        categories = pd.concat(
            [categories, wave[["canonical_company_id", "company_category"]]],
            ignore_index=True,
        )
        universe = pd.concat(
            [universe, wave.drop(columns=["company_category"])],
            ignore_index=True,
        )
    universe = universe.merge(categories, on="canonical_company_id", how="left", validate="one_to_one")
    universe["company_category"] = universe["company_category"].replace(
        {"Private Equity & Asset Management": "Private Equity & Private Markets"}
    )
    category_overrides_path = data_dir / "company_category_overrides.csv"
    if category_overrides_path.exists():
        category_overrides = pd.read_csv(category_overrides_path).set_index("canonical_company_id")
        overridden_categories = universe["canonical_company_id"].map(category_overrides["company_category"])
        universe["company_category"] = overridden_categories.fillna(universe["company_category"])
    url_overrides = pd.read_csv(data_dir / "company_url_overrides.csv").set_index("canonical_company_id")
    overridden_urls = universe["canonical_company_id"].map(url_overrides["career_url"])
    universe["career_url"] = overridden_urls.fillna(universe["career_url"])
    token = github_token()
    ratings_sha = None

    if token:
        try:
            saved_ratings, ratings_sha = load_ratings(token)
        except Exception:
            saved_ratings = pd.DataFrame(
                columns=["canonical_company_id", "rating", "contact_strength", "notes"]
            )
            st.warning("GitHub ratings could not be loaded. The company list is still available.")
    else:
        saved_ratings = pd.DataFrame(
            columns=["canonical_company_id", "rating", "contact_strength", "notes"]
        )

    base_ratings = universe[["canonical_company_id", "rating", "notes"]].copy()
    base_ratings["contact_strength"] = "None"
    if not saved_ratings.empty:
        if "contact_strength" not in saved_ratings.columns:
            saved_ratings["contact_strength"] = "None"
        base_ratings = base_ratings.drop(columns=["rating", "contact_strength", "notes"]).merge(
            saved_ratings[["canonical_company_id", "rating", "contact_strength", "notes"]],
            on="canonical_company_id",
            how="left",
        )
        base_ratings["rating"] = base_ratings["rating"].fillna("Unrated")
        base_ratings["contact_strength"] = base_ratings["contact_strength"].fillna("None")
        base_ratings["notes"] = base_ratings["notes"].fillna("")

    universe = universe.drop(columns=["rating", "notes"]).merge(
        base_ratings,
        on="canonical_company_id",
        how="left",
    )
    universe["company_description"] = (
        universe["archetype"].str.strip()
        + "\n"
        + universe["why_test"].str.strip()
    )

    filter_left, filter_right = st.columns(2)
    region_options = sorted(universe["region"].unique())
    category_options = sorted(universe["company_category"].unique())
    with filter_left:
        selected_regions = st.multiselect("Filter regions", region_options, default=region_options)
    with filter_right:
        selected_categories = st.multiselect(
            "Filter company categories",
            category_options,
            default=category_options,
        )
    filtered = universe[
        universe["region"].isin(selected_regions)
        & universe["company_category"].isin(selected_categories)
    ].copy()

    metric_total, metric_rated, metric_a, metric_contacts, metric_excluded = st.columns(5)
    rated_count = int((universe["rating"] != "Unrated").sum())
    metric_total.metric("Company Universe", len(universe))
    metric_rated.metric("Rated", rated_count)
    metric_a.metric("A priority", int((universe["rating"] == "A").sum()))
    metric_contacts.metric("Warm contacts", int(universe["contact_strength"].isin(["Warm contact", "Strong referral"]).sum()))
    metric_excluded.metric("Excluded", int((universe["rating"] == "Exclude").sum()))
    st.progress(rated_count / len(universe), text=f"Rating progress: {rated_count} / {len(universe)}")

    st.caption(
        f"Showing {len(filtered)} canonical companies across {len(selected_categories)} categories. "
        "Global and local career pages roll up to one company; "
        "duplicate vacancies will retain multiple source links."
    )
    st.caption(
        "Keyboard rating: select a Rating cell, type A, B, C or X, then press Enter or Tab. "
        "X means Exclude. Save all changes with the button below."
    )
    review_columns = [
        "company",
        "rating",
        "company_description",
        "contact_strength",
        "notes",
        "company_category",
        "region",
        "locations",
        "archetype",
        "why_test",
        "career_url",
        "source_strategy",
    ]
    edited = st.data_editor(
        filtered[review_columns],
        hide_index=True,
        width="stretch",
        height=620,
        row_height=96,
        disabled=[
            "company",
            "company_category",
            "company_description",
            "region",
            "locations",
            "archetype",
            "why_test",
            "career_url",
            "source_strategy",
        ],
        column_config={
            "company": st.column_config.TextColumn("Company", width="medium"),
            "company_description": st.column_config.TextColumn(
                "What they do / why relevant",
                width=560,
            ),
            "company_category": st.column_config.TextColumn("Category", width="medium"),
            "region": st.column_config.TextColumn("Region", width="small"),
            "locations": st.column_config.TextColumn("Locations", width="medium"),
            "archetype": st.column_config.TextColumn("Archetype", width="medium"),
            "why_test": st.column_config.TextColumn("Why test", width="large"),
            "career_url": st.column_config.LinkColumn("Careers", display_text="Open"),
            "source_strategy": st.column_config.TextColumn("Source structure", width="large"),
            "rating": st.column_config.TextColumn(
                "Rating",
                help="Type A, B, C or X and confirm with Enter or Tab.",
                validate=r"^(Unrated|unrated|U|u|A|a|B|b|C|c|Exclude|exclude|X|x)$",
                max_chars=7,
                width="small",
            ),
            "contact_strength": st.column_config.SelectboxColumn(
                "Contact",
                options=["None", "Known contact", "Warm contact", "Strong referral"],
                required=True,
                width="medium",
            ),
            "notes": st.column_config.TextColumn("Your notes", width="large"),
        },
        key="company_universe_editor",
    )

    if token:
        if st.button("Save feedback to GitHub", type="primary"):
            updated = base_ratings.set_index("canonical_company_id")
            edited_with_ids = edited.copy()
            edited_with_ids.insert(0, "canonical_company_id", filtered["canonical_company_id"].values)
            edited_with_ids = edited_with_ids.set_index("canonical_company_id")
            rating_aliases = {
                "UNRATED": "Unrated",
                "U": "Unrated",
                "A": "A",
                "B": "B",
                "C": "C",
                "EXCLUDE": "Exclude",
                "X": "Exclude",
            }
            raw_ratings = edited_with_ids["rating"].fillna("").astype(str).str.strip()
            normalized_ratings = raw_ratings.str.upper().map(rating_aliases)
            invalid_ratings = normalized_ratings.isna()
            if invalid_ratings.any():
                invalid_values = ", ".join(sorted(raw_ratings[invalid_ratings].unique()))
                st.error(
                    f"Invalid rating: {invalid_values or 'blank'}. "
                    "Use A, B, C, X/Exclude or U/Unrated."
                )
            else:
                edited_with_ids["rating"] = normalized_ratings
                updated.loc[edited_with_ids.index, ["rating", "contact_strength", "notes"]] = edited_with_ids[
                    ["rating", "contact_strength", "notes"]
                ]
                try:
                    save_ratings(token, updated.reset_index(), ratings_sha)
                except Exception:
                    st.error("Saving to GitHub failed. Refresh the page and try again.")
                else:
                    st.success("Saved directly to GitHub. Streamlit will load the new ratings automatically.")
    else:
        st.info(
            "Direct GitHub saving is ready. Add the repository token once in Streamlit Secrets to enable the Save button.",
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
