from __future__ import annotations

from pathlib import Path

import pandas as pd
import streamlit as st

from add_opportunity_ui import render_add_opportunity
from cost_of_living_ui import render_cost_of_living
from github_storage import RATING_COLUMNS, github_token, load_ratings, save_ratings
from jobs_ui import render_jobs, render_sources

COMPANY_TARGETING_PATH = Path(__file__).parent / "COMPANY_TARGETING.md"
GENERAL_COMPANY_TARGETING_PATH = Path(__file__).parent / "GENERAL_COMPANY_TARGETING.md"
COMPANY_SECTORS = [
    "Consulting",
    "Corporate",
    "Banking & Financial Services",
    "Holding & Conglomerate",
    "Private Equity & Asset Management",
    "Investment Banking",
    "Public Markets & Asset Management",
    "Specialist & Boutique Funds",
]


def _load_company_targeting_sections() -> dict[str, str]:
    """Split COMPANY_TARGETING.md into {sector: markdown body} by '## ' headings."""
    if not COMPANY_TARGETING_PATH.exists():
        return {}
    sections: dict[str, str] = {}
    current: str | None = None
    body: list[str] = []
    for line in COMPANY_TARGETING_PATH.read_text(encoding="utf-8").splitlines():
        if line.startswith("## "):
            if current is not None:
                sections[current] = "\n".join(body).strip()
            current = line[3:].strip()
            body = []
        elif current is not None:
            body.append(line)
    if current is not None:
        sections[current] = "\n".join(body).strip()
    return sections

VERIFIED_JOB_TYPES = {
    "schema.org/JobPosting",
    "schema.org/JobPosting JSON-LD",
    "schema.org/JobPosting microdata",
    "official ATS vacancy detail",
}

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

DATA_DIR = Path(__file__).parent / "data"


def header(title: str, description: str) -> None:
    st.markdown('<div class="eyebrow">Opportunity Radar</div>', unsafe_allow_html=True)
    st.title(title)
    st.markdown(f'<p class="muted">{description}</p>', unsafe_allow_html=True)


def placeholder(title: str, body: str, next_step: str) -> None:
    header(title, body)
    st.info(f"Next build step: {next_step}", icon="🛠️")


def home_page() -> None:
    header("Good morning", "Your daily view of sourced opportunities, decisions, and active next steps.")
    runs_path = DATA_DIR / "source_runs.csv"
    job_frames = []
    for jobs_path in [DATA_DIR / "jobs.csv"]:
        if jobs_path.exists():
            frame = pd.read_csv(jobs_path).fillna("")
            if "verification" in frame.columns:
                frame = frame[frame["verification"].isin(VERIFIED_JOB_TYPES)]
            job_frames.append(frame)
    jobs = pd.concat(job_frames, ignore_index=True, sort=False).fillna("") if job_frames else pd.DataFrame()
    if not jobs.empty:
        if "job_url" in jobs.columns:
            jobs["_source_url"] = jobs["job_url"]
        else:
            jobs["_source_url"] = jobs.get("source_url", "")
        jobs = jobs.drop_duplicates("_source_url", keep="last")
        jobs["_market"] = jobs.get("countries", "")
        if "market" in jobs.columns:
            jobs["_market"] = jobs["_market"].where(jobs["_market"].ne(""), jobs["market"])
    runs = pd.read_csv(runs_path).fillna("") if runs_path.exists() else pd.DataFrame()
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Tracked job links", len(jobs))
    col2.metric("Companies with jobs", jobs["company"].nunique() if not jobs.empty else 0)
    col3.metric("Markets", jobs["_market"].nunique() if not jobs.empty else 0)
    col4.metric("Source runs", len(runs))
    st.subheader("Operating model")
    st.code("COMPANY RADAR → CAREER PAGES → DISCOVERY → JOBS INBOX → FEEDBACK → CALIBRATION")
    if jobs.empty:
        st.info("The sourcing framework is ready. Scheduled runs will populate the Jobs page automatically.")
    else:
        st.success("Live sourcing is active. Open Jobs to review the latest discovered vacancies.")


def opportunities_page() -> None:
    placeholder(
        "Opportunity overview",
        "The unified inbox and catalogue for jobs and broader professional opportunities.",
        "Add non-job opportunity types after the job learning loop is working.",
    )


def jobs_page() -> None:
    render_jobs()


def add_opportunity_page() -> None:
    render_add_opportunity()


def cost_of_living_page() -> None:
    render_cost_of_living()


def _load_company_universe() -> pd.DataFrame:
    universe = pd.read_csv(DATA_DIR / "company_universe.csv").fillna("")
    categories = pd.read_csv(DATA_DIR / "company_categories.csv").fillna("")
    for wave_path in sorted(DATA_DIR.glob("company_universe_wave*.csv")):
        wave = pd.read_csv(wave_path).fillna("")
        if "company_category" in wave.columns:
            categories = pd.concat(
                [categories, wave[["canonical_company_id", "company_category"]]],
                ignore_index=True,
            )
            wave = wave.drop(columns=["company_category"])
        universe = pd.concat([universe, wave], ignore_index=True)
    universe = universe.drop_duplicates("canonical_company_id", keep="last")
    categories = categories.drop_duplicates("canonical_company_id", keep="last")
    universe = universe.merge(categories, on="canonical_company_id", how="left")
    universe["company_category"] = universe["company_category"].replace(
        {"Private Equity & Asset Management": "Private Equity & Private Markets"}
    )
    overrides_path = DATA_DIR / "company_category_overrides.csv"
    if overrides_path.exists():
        overrides = pd.read_csv(overrides_path).set_index("canonical_company_id")
        mapped = universe["canonical_company_id"].map(overrides["company_category"])
        universe["company_category"] = mapped.fillna(universe["company_category"])
    url_path = DATA_DIR / "company_url_overrides.csv"
    if url_path.exists():
        url_overrides = pd.read_csv(url_path).set_index("canonical_company_id")
        mapped = universe["canonical_company_id"].map(url_overrides["career_url"])
        universe["career_url"] = mapped.fillna(universe["career_url"])
    return universe.fillna("")


def companies_page() -> None:
    header("Companies", "Your rated Company Universe and the input layer for company-driven job sourcing.")
    universe = _load_company_universe()
    token = github_token()
    ratings_sha = None
    if token:
        try:
            saved_ratings, ratings_sha = load_ratings(token)
        except Exception:
            saved_ratings = pd.DataFrame(columns=RATING_COLUMNS)
            st.warning("GitHub ratings could not be loaded. Showing the base universe.")
    else:
        saved_ratings = pd.DataFrame(columns=RATING_COLUMNS)

    base = universe[["canonical_company_id"]].copy()
    if saved_ratings.empty:
        base["rating"] = universe.get("rating", "Unrated")
        base["familiarity"] = "Unknown"
        base["contact_strength"] = "None"
        base["relationship_type"] = "None"
        base["reference_notes"] = ""
        base["notes"] = universe.get("notes", "")
    else:
        base = base.merge(saved_ratings, on="canonical_company_id", how="left")
        base["rating"] = base["rating"].replace("", pd.NA).fillna("Unrated")
        base["familiarity"] = base["familiarity"].replace("", pd.NA).fillna("Unknown")
        base["contact_strength"] = base["contact_strength"].replace("", pd.NA).fillna("None")
        base["relationship_type"] = base["relationship_type"].replace("", pd.NA).fillna("None")
        base["reference_notes"] = base["reference_notes"].fillna("")
        base["notes"] = base["notes"].fillna("")
    universe = universe.drop(columns=[c for c in ["rating", "notes"] if c in universe.columns]).merge(base, on="canonical_company_id", how="left")
    universe["company_description"] = universe["archetype"].astype(str).str.strip() + "\n" + universe["why_test"].astype(str).str.strip()

    left, right = st.columns(2)
    regions = sorted(x for x in universe["region"].unique() if x)
    categories = sorted(x for x in universe["company_category"].unique() if x)
    selected_regions = left.multiselect("Filter regions", regions, default=regions)
    selected_categories = right.multiselect("Filter company categories", categories, default=categories)
    filtered = universe[universe["region"].isin(selected_regions) & universe["company_category"].isin(selected_categories)].copy()

    m1, m2, m3, m4, m5, m6 = st.columns(6)
    m1.metric("Company Universe", len(universe))
    m2.metric("A priority", int((universe["rating"] == "A").sum()))
    m3.metric("B priority", int((universe["rating"] == "B").sum()))
    m4.metric("Known well", int(universe["familiarity"].isin(["Know well", "Worked with"]).sum()))
    m5.metric("Warm contacts", int(universe["contact_strength"].isin(["Warm contact", "Strong referral"]).sum()))
    m6.metric("Excluded", int((universe["rating"] == "Exclude").sum()))

    columns = [
        "company", "rating", "company_description", "familiarity", "contact_strength",
        "relationship_type", "reference_notes", "notes", "company_category", "region",
        "locations", "career_url",
    ]
    edited = st.data_editor(
        filtered[columns],
        hide_index=True,
        width="stretch",
        height=620,
        row_height=90,
        disabled=["company", "company_description", "company_category", "region", "locations", "career_url"],
        column_config={
            "company": st.column_config.TextColumn("Company", width="medium"),
            "company_description": st.column_config.TextColumn("What they do / why relevant", width=520),
            "career_url": st.column_config.LinkColumn("Careers", display_text="Open"),
            "rating": st.column_config.TextColumn("Rating", help="A, B, C, X/Exclude or U/Unrated"),
            "familiarity": st.column_config.SelectboxColumn(
                "How well you know them",
                options=["Unknown", "Know of", "Know reasonably", "Know well", "Worked with"],
                required=True,
            ),
            "contact_strength": st.column_config.SelectboxColumn("Contact", options=["None", "Known contact", "Warm contact", "Strong referral"], required=True),
            "relationship_type": st.column_config.SelectboxColumn(
                "Relationship",
                options=["None", "Former employer", "Former client", "Alumni network", "Personal / professional network"],
                required=True,
            ),
            "reference_notes": st.column_config.TextColumn("References / who you know", width="large"),
            "notes": st.column_config.TextColumn("Preference notes", width="large"),
        },
        key="company_universe_editor",
    )

    if token and st.button("Save feedback to GitHub", type="primary"):
        updated = base.set_index("canonical_company_id")
        rows = edited.copy()
        rows.insert(0, "canonical_company_id", filtered["canonical_company_id"].values)
        rows = rows.set_index("canonical_company_id")
        aliases = {"A": "A", "B": "B", "C": "C", "X": "Exclude", "EXCLUDE": "Exclude", "U": "Unrated", "UNRATED": "Unrated"}
        normalized = rows["rating"].fillna("").astype(str).str.strip().str.upper().map(aliases)
        if normalized.isna().any():
            st.error("Invalid rating. Use A, B, C, X/Exclude or U/Unrated.")
        else:
            rows["rating"] = normalized
            editable = [
                "rating", "familiarity", "contact_strength", "relationship_type",
                "reference_notes", "notes",
            ]
            updated.loc[rows.index, editable] = rows[editable]
            try:
                save_ratings(token, updated.reset_index(), ratings_sha)
            except Exception:
                st.error("Saving to GitHub failed. Refresh and try again.")
            else:
                st.success("Saved to GitHub.")
    elif not token:
        st.info("Add the repository token in Streamlit Secrets to enable direct saving.")

    st.divider()
    st.subheader("Company sourcing hypothesis")
    st.caption(
        "Per-sector rationale for which new companies the scheduled discovery task "
        "(Mon/Thu) proposes, inferred from your ratings and notes above."
    )
    if GENERAL_COMPANY_TARGETING_PATH.exists():
        with st.expander("General company targeting principles (cross-sector)"):
            st.markdown(GENERAL_COMPANY_TARGETING_PATH.read_text(encoding="utf-8"))

    sections = _load_company_targeting_sections()
    for sector in COMPANY_SECTORS:
        with st.expander(f"{sector} — sourcing hypothesis"):
            st.markdown(sections.get(sector, "_Not yet generated._"))


def pipeline_page() -> None:
    placeholder("Pipeline", "Active pursuits, stages, deadlines, next actions, and outcomes.", "Add the application workflow after live job review is stable.")


def ideas_page() -> None:
    placeholder("Ideas & Projects", "Self-created opportunities, experiments, collaborations, and possible projects.", "Add after the job learning loop is working.")


def sources_page() -> None:
    render_sources()


with st.sidebar:
    st.title("🧭 Professional Dashboard")
    st.caption("Personal opportunity intelligence")

navigation = st.navigation(
    {
        "Dashboard": [st.Page(home_page, title="Home")],
        "Opportunities": [
            st.Page(opportunities_page, title="Overview"),
            st.Page(jobs_page, title="Jobs"),
            st.Page(add_opportunity_page, title="Add Opportunity"),
            st.Page(companies_page, title="Companies"),
            st.Page(cost_of_living_page, title="Cost of Living"),
        ],
        "Workspace": [st.Page(pipeline_page, title="Pipeline"), st.Page(ideas_page, title="Ideas & Projects")],
        "System": [st.Page(sources_page, title="Sources / Radar")],
    }
)

with st.sidebar:
    st.divider()
    st.caption("v0 live sourcing pilot · Build for iteration")

navigation.run()
