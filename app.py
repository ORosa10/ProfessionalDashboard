from __future__ import annotations

import streamlit as st


st.set_page_config(
    page_title="Professional Dashboard",
    page_icon="ðŸ§­",
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

SECTIONS = [
    "Home",
    "Opportunities",
    "Jobs",
    "Companies",
    "Pipeline",
    "Ideas & Projects",
    "Sources / Radar",
]


def header(title: str, description: str) -> None:
    st.markdown('<div class="eyebrow">Opportunity Radar</div>', unsafe_allow_html=True)
    st.title(title)
    st.markdown(f'<p class="muted">{description}</p>', unsafe_allow_html=True)


def placeholder(title: str, body: str, next_step: str) -> None:
    header(title, body)
    st.info(f"Next build step: {next_step}", icon="ðŸ› ï¸")


with st.sidebar:
    st.title("ðŸ§­ Professional Dashboard")
    st.caption("Personal opportunity intelligence")
    section = st.radio("Navigation", SECTIONS, label_visibility="collapsed")
    st.divider()
    st.caption("v0 foundation Â· Build for iteration")

if section == "Home":
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
        st.code("SOURCES â†’ DISCOVERY â†’ INBOX â†’ REVIEW â†’ ACTIVE â†’ OUTCOME")
        st.caption("Jobs are the first product wedge. Scoring comes only after real feedback.")

elif section == "Opportunities":
    placeholder(
        "Opportunities",
        "The unified inbox and catalogue for all professional opportunity types.",
        "Add the Opportunity model, durable storage, and the review queue.",
    )

elif section == "Jobs":
    header("Jobs", "The first real sourcing engine, structured as WHAT Ã— WHERE Ã— WHO Ã— SOURCE.")
    what, where, who, source = st.columns(4)
    what.text_input("WHAT", placeholder="Roles, functions, seniority")
    where.text_input("WHERE", placeholder="Locations, remote preference")
    who.text_input("WHO", placeholder="Companies, sectors, stages")
    source.text_input("SOURCE", placeholder="Boards, ATS, career pages")
    st.warning("This is currently an interface preview. Search persistence and sourcing are the next implementation step.", icon="â„¹ï¸")

elif section == "Companies":
    placeholder(
        "Companies",
        "The Company Universe and career-page monitoring workspace.",
        "Create Company records and add the first manually curated target list.",
    )

elif section == "Pipeline":
    placeholder(
        "Pipeline",
        "Active pursuits, stages, deadlines, next actions, and outcomes.",
        "Define pipeline stages after the first review workflow is usable.",
    )

elif section == "Ideas & Projects":
    placeholder(
        "Ideas & Projects",
        "Self-created opportunities, experiments, collaborations, and possible projects.",
        "Add this engine after the job learning loop is working.",
    )

else:
    placeholder(
        "Sources / Radar",
        "Source configuration, freshness, run history, monitoring, and discovery diagnostics.",
        "Implement the shared Source and source-run framework with one genuine job source.",
    )
