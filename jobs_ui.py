from __future__ import annotations

import base64
from datetime import datetime, timezone
from io import StringIO
from pathlib import Path

import pandas as pd
import requests
import streamlit as st

from personal_fit import build_personal_fit_summary

DATA_DIR = Path(__file__).parent / "data"
GENERAL_TARGETING_PATH = Path(__file__).parent / "GENERAL_TARGETING.md"
CONSULTING_TARGETING_PATH = Path(__file__).parent / "CONSULTING_TARGETING.md"
VERIFIED_JOB_TYPES = {
    "schema.org/JobPosting",
    "schema.org/JobPosting JSON-LD",
    "schema.org/JobPosting microdata",
    "official ATS vacancy detail",
    "official Deloitte ATS vacancy detail",
    "official SmartRecruiters vacancy API",
    "official Workday vacancy API",
    "official KPMG UK vacancy detail",
    "official KPMG Switzerland vacancy API",
}
FEEDBACK_PATH = "data/job_feedback.csv"
FEEDBACK_API_URL = (
    "https://api.github.com/repos/ORosa10/ProfessionalDashboard/contents/"
    + FEEDBACK_PATH
)
FEEDBACK_OPTIONS = ["Unrated", "Interested", "Maybe", "Pass"]


def _github_token() -> str | None:
    try:
        value = st.secrets["github"]["token"]
    except (FileNotFoundError, KeyError, TypeError):
        return None
    return str(value) if value else None


def _github_headers(token: str) -> dict[str, str]:
    return {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {token}",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def _load_job_feedback(token: str | None) -> tuple[pd.DataFrame, str | None]:
    columns = ["opportunity_id", "feedback", "comment", "updated_at"]
    if token:
        response = requests.get(
            FEEDBACK_API_URL,
            headers=_github_headers(token),
            params={"ref": "main"},
            timeout=20,
        )
        if response.status_code == 404:
            return pd.DataFrame(columns=columns), None
        response.raise_for_status()
        payload = response.json()
        content = base64.b64decode(payload["content"]).decode("utf-8-sig")
        return pd.read_csv(StringIO(content)).fillna("").reindex(columns=columns), payload["sha"]
    local = DATA_DIR / "job_feedback.csv"
    if local.exists():
        return pd.read_csv(local).fillna("").reindex(columns=columns), None
    return pd.DataFrame(columns=columns), None


def _save_job_feedback(
    token: str,
    feedback: pd.DataFrame,
    sha: str | None,
) -> None:
    csv_bytes = feedback.to_csv(index=False).encode("utf-8-sig")
    payload: dict[str, str] = {
        "message": "Update job feedback from Streamlit",
        "content": base64.b64encode(csv_bytes).decode("ascii"),
        "branch": "main",
    }
    if sha:
        payload["sha"] = sha
    response = requests.put(
        FEEDBACK_API_URL,
        headers=_github_headers(token),
        json=payload,
        timeout=20,
    )
    response.raise_for_status()


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


def _salary_context(location: str, benchmarks: pd.DataFrame) -> str:
    normalized = str(location).lower()
    for _, row in benchmarks.iterrows():
        city = str(row.get("city", ""))
        if city and city.lower() in normalized:
            target = pd.to_numeric(row.get("benchmark_gross_annual_local", ""), errors="coerce")
            currency = str(row.get("currency", ""))
            if pd.notna(target):
                return f"{city}: target about {float(target):,.0f} {currency} gross/year"
    return "No city-specific salary benchmark yet"


def render_jobs() -> None:
    st.markdown('<div class="eyebrow">Opportunity Radar</div>', unsafe_allow_html=True)
    st.title("Jobs")
    st.caption("Verified individual vacancies from official employer career portals.")
    if GENERAL_TARGETING_PATH.exists():
        with st.expander(
            "General targeting principles (cross-sector)",
            expanded=False,
        ):
            st.markdown(GENERAL_TARGETING_PATH.read_text(encoding="utf-8"))
            st.caption(
                "General principles are updated only when a signal belongs to the personal baseline "
                "or repeats across multiple employer sectors."
            )
    if CONSULTING_TARGETING_PATH.exists():
        with st.expander(
            "Consulting sector hypothesis — first 50 Big Four ratings",
            expanded=False,
        ):
            st.markdown(CONSULTING_TARGETING_PATH.read_text(encoding="utf-8"))
            st.caption(
                "This is the first sector-specific learning hypothesis. Review it in the project chat; "
                "Private Markets and later sectors will retain their own hypotheses."
            )
    frames: list[pd.DataFrame] = []
    staging_path = DATA_DIR / "jobs_staging.csv"
    pilot_path = staging_path if staging_path.exists() else DATA_DIR / "jobs.csv"
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
                }
            )
            if "job_url" in pilot.columns:
                pilot["source_url"] = pilot["job_url"]
            pilot["countries"] = pilot.apply(
                lambda row: _country_from_market_and_location(row["countries"], row["cities"]),
                axis=1,
            )
            pilot["role_family"] = "Other relevant finance"
            pilot["seniority"] = ""
            if "description_en" in pilot.columns:
                pilot["description_display"] = pilot["description_en"].where(
                    pilot["description_en"].ne(""), pilot.get("description", "")
                )
            elif "description" in pilot.columns:
                pilot["description_display"] = pilot["description"]
            else:
                pilot["description_display"] = ""
            if "matched_terms" in pilot.columns:
                pilot["fit_note"] = pilot["matched_terms"].apply(
                    lambda value: f"Matched role terms: {value}"
                    if value
                    else "Verified role from the Big Four pilot."
                )
            else:
                pilot["fit_note"] = "Verified role from the Big Four pilot."
            if "calibration_note" in pilot.columns:
                pilot["fit_note"] = pilot["calibration_note"].where(
                    pilot["calibration_note"].ne(""), pilot["fit_note"]
                )
            if "status" in pilot.columns:
                pilot["status"] = pilot["status"].replace({"": "Open", "New": "Open"})
            else:
                pilot["status"] = "Open"
            pilot["review_status"] = "New"
            frames.append(pilot)

    pe_path = DATA_DIR / "pe_research_candidates.csv"
    if pe_path.exists():
        pe = pd.read_csv(pe_path).fillna("")
        pe = pe[pe["status"].eq("Open")].copy()
        pe = pe.rename(
            columns={
                "candidate_id": "opportunity_id",
                "city": "cities",
                "country": "countries",
                "official_url": "source_url",
                "role_summary_en": "description_display",
                "experience_signal": "seniority",
                "checked_at": "discovered_at",
            }
        )
        pe["job_url"] = pe["source_url"]
        pe["role_family"] = "Private markets"
        pe["fit_note"] = pe.apply(
            lambda row: " | ".join(
                value
                for value in [
                    f"Initial bucket: {row.get('initial_bucket', '')}",
                    f"Experience: {row.get('seniority', '')}",
                    f"Language: {row.get('language_signal', '')}",
                ]
                if value.split(": ", 1)[-1]
            ),
            axis=1,
        )
        pe["review_status"] = "New"
        frames.append(pe)

    consulting_path = DATA_DIR / "consulting_research_candidates.csv"
    if consulting_path.exists():
        consulting = pd.read_csv(consulting_path).fillna("")
        consulting = consulting[consulting["status"].eq("Open")].copy()
        consulting = consulting.rename(
            columns={
                "candidate_id": "opportunity_id",
                "city": "cities",
                "country": "countries",
                "official_url": "source_url",
                "role_summary_en": "description_display",
                "experience_signal": "seniority",
                "checked_at": "discovered_at",
            }
        )
        consulting["job_url"] = consulting["source_url"]
        consulting["role_family"] = "Consulting"
        consulting["fit_note"] = consulting.apply(
            lambda row: " | ".join(
                value
                for value in [
                    f"Initial bucket: {row.get('initial_bucket', '')}",
                    f"Experience: {row.get('seniority', '')}",
                    f"Language: {row.get('language_signal', '')}",
                ]
                if value.split(": ", 1)[-1]
            ),
            axis=1,
        )
        consulting["review_status"] = "New"
        frames.append(consulting)

    if not frames:
        st.warning("The sourcing workflow has not produced its first verified vacancy snapshot yet.")
        return
    jobs = pd.concat(frames, ignore_index=True, sort=False).fillna("")
    jobs = jobs.drop_duplicates("opportunity_id", keep="last")
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
    token = _github_token()
    try:
        feedback_data, feedback_sha = _load_job_feedback(token)
    except Exception:
        feedback_data = pd.DataFrame(
            columns=["opportunity_id", "feedback", "comment", "updated_at"]
        )
        feedback_sha = None
        st.warning("Job feedback could not be loaded from GitHub. Refresh and try again.")
    feedback_data = feedback_data.drop_duplicates("opportunity_id", keep="last")
    jobs = jobs.merge(
        feedback_data[["opportunity_id", "feedback", "comment"]],
        on="opportunity_id",
        how="left",
    )
    jobs["feedback"] = jobs["feedback"].fillna("").replace("", "Unrated")
    jobs["comment"] = jobs["comment"].fillna("")
    jobs["review_status"] = jobs["feedback"].apply(
        lambda value: "New" if value == "Unrated" else "Reviewed"
    )
    review_maps: list[pd.DataFrame] = []
    batch_path = DATA_DIR / "job_calibration_batch.csv"
    if batch_path.exists():
        batch = pd.read_csv(batch_path).fillna("").drop_duplicates("opportunity_id")
        batch["review_set"] = "Big Four calibration"
        review_maps.append(batch)
    pe_batch_path = DATA_DIR / "pe_calibration_shortlist.csv"
    if pe_batch_path.exists():
        pe_batch = pd.read_csv(pe_batch_path).fillna("").rename(
            columns={"candidate_id": "opportunity_id"}
        )
        pe_batch["seniority_band"] = ""
        pe_batch["review_set"] = "PE calibration"
        review_maps.append(pe_batch)
    consulting_batch_path = DATA_DIR / "consulting_calibration_shortlist.csv"
    if consulting_batch_path.exists():
        consulting_batch = pd.read_csv(consulting_batch_path).fillna("").rename(
            columns={"candidate_id": "opportunity_id"}
        )
        consulting_batch["seniority_band"] = ""
        consulting_batch["review_set"] = "Consulting calibration"
        review_maps.append(consulting_batch)
    if review_maps:
        review_map = pd.concat(review_maps, ignore_index=True, sort=False)
        review_map = review_map.drop_duplicates("opportunity_id", keep="last")
        jobs = jobs.merge(
            review_map[[
                "opportunity_id", "display_order", "cohort", "theme",
                "seniority_band", "selection_reason", "review_set",
            ]],
            on="opportunity_id",
            how="left",
        )
        for column in ["cohort", "theme", "seniority_band", "selection_reason"]:
            jobs[column] = jobs[column].fillna("")
        jobs["review_set"] = jobs["review_set"].fillna("").replace("", "Backlog")
        themed_rows = jobs["review_set"].isin(
            ["PE calibration", "Consulting calibration"]
        ) & jobs["theme"].ne("")
        jobs.loc[themed_rows, "role_family"] = jobs.loc[themed_rows, "theme"]
    else:
        jobs["display_order"] = ""
        jobs["cohort"] = ""
        jobs["theme"] = ""
        jobs["seniority_band"] = ""
        jobs["selection_reason"] = ""
        jobs["review_set"] = "Backlog"
    for required, default in {
        "countries": "",
        "cities": "",
        "role_family": "Other relevant finance",
        "seniority": "",
        "fit_note": "",
        "description_display": "",
        "discovered_at": "",
        "status": "Open",
        "review_status": "New",
    }.items():
        if required not in jobs.columns:
            jobs[required] = default

    jobs["personal_fit_summary"] = jobs.apply(build_personal_fit_summary, axis=1)
    cost_path = DATA_DIR / "cost_of_living.csv"
    if cost_path.exists():
        benchmarks = pd.read_csv(cost_path).fillna("")
        jobs["salary_location_context"] = jobs["cities"].apply(
            lambda value: _salary_context(value, benchmarks)
        )
    else:
        jobs["salary_location_context"] = "No city-specific salary benchmark yet"

    review_scope = st.radio(
        "Review set",
        [
            "Big Four calibration (50)",
            "PE calibration (20)",
            "Consulting calibration (20)",
            "All opportunities",
            "Backlog only",
        ],
        horizontal=True,
        help="Each shortlist is a diverse learning sample. All sourced roles remain available.",
    )
    if review_scope == "Big Four calibration (50)":
        jobs = jobs[jobs["review_set"].eq("Big Four calibration")].copy()
    elif review_scope == "PE calibration (20)":
        jobs = jobs[jobs["review_set"].eq("PE calibration")].copy()
    elif review_scope == "Consulting calibration (20)":
        jobs = jobs[jobs["review_set"].eq("Consulting calibration")].copy()
    elif review_scope == "Backlog only":
        jobs = jobs[jobs["review_set"].eq("Backlog")].copy()

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
    available_feedback = [
        value for value in FEEDBACK_OPTIONS if value in set(jobs["feedback"])
    ]
    f1, f2, f3, f4 = st.columns(4)
    selected_countries = f1.multiselect("Countries", countries, default=countries)
    selected_ratings = f2.multiselect("Company rating", ratings, default=ratings)
    selected_feedback = f3.multiselect(
        "Your job rating", available_feedback, default=available_feedback
    )
    selected_roles = f4.multiselect("Role family", roles, default=roles)
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
        & jobs["feedback"].isin(selected_feedback)
        & jobs["role_family"].isin(selected_roles)
        & jobs["status"].eq("Open")
    ].copy()
    view["_feedback_order"] = view["feedback"].map(
        {"Unrated": 0, "Interested": 1, "Maybe": 2, "Pass": 3}
    ).fillna(4)
    if "calibration_score" not in view.columns:
        view["calibration_score"] = 0
    view = view.sort_values(
        ["_feedback_order", "display_order", "rating", "calibration_score", "discovered_at"],
        ascending=[True, True, True, False, False],
    )

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Open opportunities", len(view))
    c2.metric("Unrated", int(view["feedback"].eq("Unrated").sum()))
    c3.metric(
        "A-rated companies",
        view.loc[view["rating"].eq("A"), "company"].nunique(),
    )
    c4.metric("Selected countries", len(selected_countries))
    st.caption(
        "The Big Four shortlist contains 30 likely-fit roles, 12 boundary cases and 8 exploration cases. "
        "The PE shortlist contains 20 roles selected from 25 verified candidates across 21 checked A-rated firms. "
        "The consulting shortlist contains 20 roles selected from 35 verified candidates across nine firms. "
        "All three are learning samples, not hard recommendations. Switch to All opportunities to see every retained role."
    )

    st.caption(
        "Choose Interested, Maybe or Pass directly in the table. Add a comment when the reason "
        "will help calibrate future sourcing, then save the changes to GitHub. Personal fit is a reasoning summary, "
        "not a numeric score: it keeps CV fit, preferences, constraints and salary viability conceptually separate."
    )
    columns = [
        "title",
        "feedback",
        "comment",
        "review_set",
        "cohort",
        "theme",
        "personal_fit_summary",
        "salary_location_context",
        "description_display",
        "fit_note",
        "rating",
        "company",
        "countries",
        "cities",
        "role_family",
        "source_url",
    ]
    editor_view = view.set_index("opportunity_id")[columns]
    with st.form("job_feedback_form", clear_on_submit=False):
        edited = st.data_editor(
            editor_view,
            hide_index=True,
            width="stretch",
            height=620,
            row_height=180,
            disabled=[column for column in columns if column not in {"feedback", "comment"}],
            key="job_feedback_editor",
            column_config={
            "title": st.column_config.TextColumn("Opportunity", width="large"),
            "feedback": st.column_config.SelectboxColumn(
                "Your rating", options=FEEDBACK_OPTIONS, required=True, width="small"
            ),
            "rating": st.column_config.TextColumn("Company rating", width="small"),
            "review_set": st.column_config.TextColumn("Review set", width="small"),
            "cohort": st.column_config.TextColumn("Calibration cohort", width="small"),
            "theme": st.column_config.TextColumn("Role theme", width="medium"),
            "personal_fit_summary": st.column_config.TextColumn("Personal fit reasoning", width=620),
            "salary_location_context": st.column_config.TextColumn(
                "Salary target for location", width=320
            ),
            "description_display": st.column_config.TextColumn(
                "What the role does (English)", width=620
            ),
            "fit_note": st.column_config.TextColumn("Why sourced", width=320),
            "comment": st.column_config.TextColumn("Your comment", width=420),
            "company": st.column_config.TextColumn("Company", width="medium"),
            "countries": st.column_config.TextColumn("Countries", width="medium"),
            "cities": st.column_config.TextColumn("Cities", width="medium"),
            "role_family": st.column_config.TextColumn("Role family", width="medium"),
            "source_url": st.column_config.LinkColumn("Official job", display_text="Open", width="small"),
            },
        )
        save_feedback = st.form_submit_button(
            "Save job feedback to GitHub",
            type="primary",
            disabled=not bool(token),
        )
    if token and save_feedback:
        updates = edited[["feedback", "comment"]].reset_index()
        updates["updated_at"] = datetime.now(timezone.utc).isoformat()
        existing = feedback_data.set_index("opportunity_id")
        incoming = updates.set_index("opportunity_id")
        existing = existing.loc[~existing.index.isin(incoming.index)]
        combined = pd.concat([existing, incoming]).reset_index()
        try:
            _save_job_feedback(token, combined, feedback_sha)
        except Exception:
            st.error("Saving job feedback to GitHub failed. Refresh and try again.")
        else:
            st.success("Job feedback saved to GitHub.")
    elif not token:
        st.info("Add the repository token in Streamlit Secrets to enable job-feedback saving.")


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
