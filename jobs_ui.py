from __future__ import annotations

import base64
from datetime import datetime, timezone
from io import StringIO
from pathlib import Path

import pandas as pd
import requests
import streamlit as st

from personal_fit import build_personal_fit_summary
from github_storage import load_csv_file, save_csv_file

DATA_DIR = Path(__file__).parent / "data"
GENERAL_TARGETING_PATH = Path(__file__).parent / "GENERAL_TARGETING.md"
CONSULTING_TARGETING_PATH = Path(__file__).parent / "CONSULTING_TARGETING.md"
PE_TARGETING_PATH = Path(__file__).parent / "PE_TARGETING.md"
TARGETING_FEEDBACK_PATH = "data/targeting_feedback.csv"
TARGETING_FEEDBACK_COLUMNS = ["submitted_at", "scope", "feedback"]
THESIS_SCOPES = [
    "General (all sectors)", "Big Four", "Consulting", "Corporate",
    "Banking & Financial Services", "Holding & Conglomerate",
    "Private Equity & Private Markets", "Investment Banking",
    "Public Markets & Asset Management", "Specialist & Boutique Funds",
]
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
STAGING_BRANCH = "sourcing-staging"
STAGING_JOBS_API_URL = (
    "https://api.github.com/repos/ORosa10/ProfessionalDashboard/contents/data/jobs_staging.csv"
)
PROMOTE_WORKFLOW_API_URL = (
    "https://api.github.com/repos/ORosa10/ProfessionalDashboard/actions/"
    "workflows/promote-staging.yml/dispatches"
)


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


def _load_staging_summary(token: str | None) -> tuple[int, int] | None:
    """Roles and companies waiting on the sourcing-staging branch, or None if unavailable.

    These roles are not yet in data/jobs.csv, so they never appear in the
    Jobs review queue until someone explicitly promotes them.
    """
    if not token:
        return None
    response = requests.get(
        STAGING_JOBS_API_URL,
        headers=_github_headers(token),
        params={"ref": STAGING_BRANCH},
        timeout=20,
    )
    if response.status_code != 200:
        return None
    content = base64.b64decode(response.json()["content"]).decode("utf-8-sig")
    staged = pd.read_csv(StringIO(content)).fillna("")
    if staged.empty:
        return (0, 0)
    companies = staged["company"].nunique() if "company" in staged.columns else 0
    return (len(staged), companies)


def _dispatch_promote_workflow(token: str) -> bool:
    response = requests.post(
        PROMOTE_WORKFLOW_API_URL,
        headers=_github_headers(token),
        json={"ref": "main"},
        timeout=20,
    )
    return response.status_code == 204


def _local_job_feedback(columns: list[str]) -> pd.DataFrame:
    local = DATA_DIR / "job_feedback.csv"
    if local.exists():
        return pd.read_csv(local).fillna("").reindex(columns=columns)
    return pd.DataFrame(columns=columns)


def _load_job_feedback(token: str | None) -> tuple[pd.DataFrame, str | None]:
    columns = ["opportunity_id", "feedback", "comment", "updated_at"]
    if token:
        try:
            response = requests.get(
                FEEDBACK_API_URL,
                headers=_github_headers(token),
                params={"ref": "main"},
                timeout=20,
            )
            if response.status_code == 404:
                return _local_job_feedback(columns), None
            response.raise_for_status()
            payload = response.json()
            content = base64.b64decode(payload["content"]).decode("utf-8-sig")
            return pd.read_csv(StringIO(content)).fillna("").reindex(columns=columns), payload["sha"]
        except requests.RequestException:
            # Token present but GitHub read failed: fall back to the bundled CSV
            # so historical job feedback/comments still show instead of nothing.
            return _local_job_feedback(columns), None
    return _local_job_feedback(columns), None


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

def _company_category_map(company_ids: "pd.Series") -> "pd.Series":
    """Map each job's canonical_company_id to its Company Universe category
    (the same 8 labels as the Companies page). This is the only categorisation
    dimension for jobs -- there is no separate role-family sub-division."""
    frames: list[pd.DataFrame] = []
    base = pd.read_csv(DATA_DIR / "company_universe.csv").fillna("")
    if "company_category" in base.columns:
        frames.append(base[["canonical_company_id", "company_category"]])
    categories_path = DATA_DIR / "company_categories.csv"
    if categories_path.exists():
        frames.append(pd.read_csv(categories_path).fillna("")[["canonical_company_id", "company_category"]])
    for wave_path in sorted(DATA_DIR.glob("company_universe_wave*.csv")):
        wave = pd.read_csv(wave_path).fillna("")
        if "company_category" in wave.columns:
            frames.append(wave[["canonical_company_id", "company_category"]])
    combined = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(
        columns=["canonical_company_id", "company_category"]
    )
    base_map = combined.drop_duplicates("canonical_company_id", keep="last").set_index(
        "canonical_company_id"
    )["company_category"]
    overrides_path = DATA_DIR / "company_category_overrides.csv"
    if overrides_path.exists():
        overrides = (
            pd.read_csv(overrides_path)
            .fillna("")
            .drop_duplicates("canonical_company_id", keep="last")
            .set_index("canonical_company_id")["company_category"]
        )
        mapped = company_ids.map(overrides)
        mapped = mapped.where(mapped.notna() & mapped.ne(""), company_ids.map(base_map))
    else:
        mapped = company_ids.map(base_map)
    return mapped.fillna("").replace(
        {"Private Equity & Asset Management": "Private Equity & Private Markets"}
    )



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
    st.caption(
        "Targeting hypotheses below are the current per-sector thesis. Read them, and if a "
        "sector is mis-targeted, correct it in \"Give feedback on the targeting thesis\" below "
        "— that feedback is the top input to the next calibration."
    )
    _thesis_docs = [
        (GENERAL_TARGETING_PATH, "General targeting principles (cross-sector)"),
        (CONSULTING_TARGETING_PATH, "Consulting hypothesis (incl. Big Four)"),
        (PE_TARGETING_PATH, "Private Equity hypothesis"),
        (Path(__file__).parent / "CORPORATE_TARGETING.md", "Corporate hypothesis"),
        (Path(__file__).parent / "FINANCIAL_SERVICES_TARGETING.md", "Banking & Financial Services hypothesis"),
        (Path(__file__).parent / "PUBLIC_MARKETS_TARGETING.md", "Public Markets & Asset Management hypothesis"),
        (Path(__file__).parent / "SPECIALIST_FUNDS_TARGETING.md", "Specialist & Boutique Funds hypothesis"),
    ]
    for _doc_path, _doc_title in _thesis_docs:
        if _doc_path.exists():
            with st.expander(_doc_title, expanded=False):
                st.markdown(_doc_path.read_text(encoding="utf-8"))

    with st.expander("Give feedback on the targeting thesis"):
        st.caption(
            "Tell the calibration what to change in the thesis directly -- e.g. "
            "'downrank pure compliance', 'treasury / FX is top priority', "
            "'Manager level is fine if hands-on'. This is read by the calibration "
            "refresh alongside your individual job ratings."
        )
        thesis_scope = st.selectbox("Scope", THESIS_SCOPES, key="thesis_fb_scope")
        thesis_text = st.text_area(
            "Your thesis feedback",
            key="thesis_fb_text",
            placeholder="What should the targeting emphasise or avoid?",
        )
        if st.button("Save thesis feedback", key="thesis_fb_save", disabled=not thesis_text.strip()):
            fb_token = _github_token()
            if not fb_token:
                st.error("GitHub saving is not configured for this app.")
            else:
                existing, fb_sha = load_csv_file(fb_token, TARGETING_FEEDBACK_PATH, TARGETING_FEEDBACK_COLUMNS)
                new_row = {
                    "submitted_at": datetime.now(timezone.utc).isoformat(),
                    "scope": thesis_scope,
                    "feedback": thesis_text.strip(),
                }
                existing = pd.concat([existing, pd.DataFrame([new_row])], ignore_index=True)
                try:
                    save_csv_file(fb_token, TARGETING_FEEDBACK_PATH, existing, fb_sha, "Add targeting thesis feedback")
                except Exception:
                    st.error("Saving failed. Refresh and try again.")
                else:
                    st.success("Saved. It will be picked up on the next calibration refresh.")
        try:
            prior, _ = load_csv_file(_github_token(), TARGETING_FEEDBACK_PATH, TARGETING_FEEDBACK_COLUMNS)
        except Exception:
            prior = pd.DataFrame(columns=TARGETING_FEEDBACK_COLUMNS)
        if not prior.empty:
            st.caption("Your thesis feedback so far:")
            st.dataframe(
                prior.sort_values("submitted_at", ascending=False)[["scope", "feedback", "submitted_at"]],
                hide_index=True, width="stretch",
            )

    frames: list[pd.DataFrame] = []
    # Always read the live, promoted snapshot. Newly sourced roles land in
    # jobs_staging.csv on the sourcing-staging branch first and only appear
    # here once explicitly promoted (see render_sources), so a background
    # sourcing run never changes what's in front of you mid-review.
    # Sector job snapshots, matching the Company Universe's own category
    # labels (Filter company categories on the Companies page) so a sector
    # here means the same thing it does there. "Big Four" (jobs.csv) is the
    # There used to be a "Core" bucket here for company_universe.csv's
    # companies, back when that file had no company_category column -- it
    # was never a real Company Universe category, just a catch-all for
    # companies that hadn't been classified yet. Backfilled 2026-08-16 and
    # folded into the real sectors below instead.
    SECTOR_JOB_FILES = [
        ("jobs.csv", "Verified role from the Big Four pilot."),
        ("jobs_corporate_staging.csv", "Verified role from the Corporate sector pilot."),
        ("jobs_financial-services_staging.csv", "Verified role from the Banking & Financial Services sector pilot."),
        ("jobs_public-markets_staging.csv", "Verified role from the Public Markets & Asset Management sector pilot."),
        ("jobs_specialist-funds_staging.csv", "Verified role from the Specialist & Boutique Funds sector pilot."),
    ]
    for filename, default_fit_note in SECTOR_JOB_FILES:
        pilot_path = DATA_DIR / filename
        if not pilot_path.exists():
            continue
        pilot = pd.read_csv(pilot_path).fillna("")
        if "verification" in pilot.columns:
            pilot = pilot[pilot["verification"].isin(VERIFIED_JOB_TYPES)].copy()
        if pilot.empty:
            continue
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
                lambda value: f"Matched role terms: {value}" if value else default_fit_note
            )
        else:
            pilot["fit_note"] = default_fit_note
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
    # Company category (same 8 labels as the Companies page) is the only
    # categorisation dimension for jobs. Every job must belong to a company
    # that has a category; drop any that don't so the inbox never shows a
    # company-less / category-less role.
    jobs["company_category"] = _company_category_map(jobs["canonical_company_id"])
    jobs = jobs[
        jobs["canonical_company_id"].astype(str).str.strip().ne("")
        & jobs["company_category"].astype(str).str.strip().ne("")
    ].copy()
    if jobs.empty:
        st.info("No jobs are attached to a categorised company yet.")
        return
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
    # New sector calibration shortlists (built from the automated sector
    # pilots' own sourced jobs, not a separate manual-research pass like PE/
    # Consulting originally were). Deliberately NOT added to `themed_rows`
    # below -- jobs are categorised solely by their company's category.
    SECTOR_CALIBRATION_FILES = [
        ("corporate_calibration_shortlist.csv", "Corporate calibration"),
        ("financial_services_calibration_shortlist.csv", "Banking & Financial Services calibration"),
        ("public_markets_calibration_shortlist.csv", "Public Markets & Asset Management calibration"),
        ("specialist_funds_calibration_shortlist.csv", "Specialist & Boutique Funds calibration"),
    ]
    for filename, review_set_label in SECTOR_CALIBRATION_FILES:
        batch_file = DATA_DIR / filename
        if not batch_file.exists():
            continue
        sector_batch = pd.read_csv(batch_file).fillna("")
        sector_batch["review_set"] = review_set_label
        review_maps.append(sector_batch)
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
    # Semantic fit is the PRIMARY signal (per product vision): Claude-generated
    # reasoning per role in data/semantic_fit.csv overrides the coarse keyword
    # summary wherever present. The keyword calibration_score is only a coarse
    # pre-filter / tie-breaker, not the headline fit.
    jobs["fit_verdict"] = ""
    _sem_path = DATA_DIR / "semantic_fit.csv"
    if _sem_path.exists():
        _sem = pd.read_csv(_sem_path).fillna("")
        if not _sem.empty and "opportunity_id" in _sem.columns:
            _sem = _sem.drop_duplicates("opportunity_id", keep="last").set_index("opportunity_id")
            if "fit" in _sem.columns:
                jobs["fit_verdict"] = jobs["opportunity_id"].map(_sem["fit"]).fillna("")
            if "reasoning" in _sem.columns:
                _reason = jobs["opportunity_id"].map(_sem["reasoning"]).fillna("")
                jobs["personal_fit_summary"] = _reason.where(
                    _reason.str.strip().ne(""), jobs["personal_fit_summary"]
                )
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
            "Corporate calibration (20)",
            "Banking & Financial Services calibration (20)",
            "Public Markets & Asset Management calibration (12)",
            "Specialist & Boutique Funds calibration (6)",
            "All opportunities",
            "Backlog only",
        ],
        horizontal=True,
        help="Each shortlist is a diverse learning sample. All sourced roles remain available.",
    )
    REVIEW_SCOPE_TO_SET = {
        "Big Four calibration (50)": "Big Four calibration",
        "PE calibration (20)": "PE calibration",
        "Consulting calibration (20)": "Consulting calibration",
        "Corporate calibration (20)": "Corporate calibration",
        "Banking & Financial Services calibration (20)": "Banking & Financial Services calibration",
        "Public Markets & Asset Management calibration (12)": "Public Markets & Asset Management calibration",
        "Specialist & Boutique Funds calibration (6)": "Specialist & Boutique Funds calibration",
    }
    if review_scope in REVIEW_SCOPE_TO_SET:
        jobs = jobs[jobs["review_set"].eq(REVIEW_SCOPE_TO_SET[review_scope])].copy()
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
    company_categories = sorted(value for value in jobs["company_category"].unique() if value)
    available_feedback = [
        value for value in FEEDBACK_OPTIONS if value in set(jobs["feedback"])
    ]
    f1, f2, f3, f4 = st.columns(4)
    selected_countries = f1.multiselect("Countries", countries, default=countries)
    selected_ratings = f2.multiselect("Company rating", ratings, default=ratings)
    selected_feedback = f3.multiselect(
        "Your job rating", available_feedback, default=available_feedback
    )
    selected_categories = f4.multiselect("Company category", company_categories, default=company_categories)
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
        & jobs["company_category"].isin(selected_categories)
        & jobs["status"].eq("Open")
    ].copy()
    view["_feedback_order"] = view["feedback"].map(
        {"Unrated": 0, "Interested": 1, "Maybe": 2, "Pass": 3}
    ).fillna(4)
    if "calibration_score" not in view.columns:
        view["calibration_score"] = 0
    _fit_rank = {"strong": 0, "moderate": 1, "partial": 1, "weak": 2}
    view["_fit_order"] = view["fit_verdict"].astype(str).str.lower().map(
        lambda v: next((r for k, r in _fit_rank.items() if k in v), 3)
    )
    view = view.sort_values(
        ["_feedback_order", "_fit_order", "display_order", "rating", "calibration_score", "discovered_at"],
        ascending=[True, True, True, True, False, False],
    )

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Open opportunities", len(view))
    c2.metric("Unrated", int(view["feedback"].eq("Unrated").sum()))
    c3.metric(
        "A-rated companies",
        view.loc[view["rating"].eq("A"), "company"].nunique(),
    )
    c4.metric("Selected countries", len(selected_countries))
    _scope_blurb = {
        "Big Four calibration (50)": "Big Four shortlist: 30 likely-fit, 12 boundary and 8 exploration roles.",
        "PE calibration (20)": "PE shortlist: 20 roles from 25 verified candidates across 21 A-rated firms.",
        "Consulting calibration (20)": "Consulting shortlist: 20 roles from 35 verified candidates across nine firms.",
        "Corporate calibration (20)": "Corporate shortlist: a diverse 20-role learning sample from the Corporate sourcing.",
        "Banking & Financial Services calibration (20)": "Banking & Financial Services shortlist: a diverse 20-role learning sample.",
        "Public Markets & Asset Management calibration (12)": "Public Markets & Asset Management shortlist: a diverse learning sample.",
        "Specialist & Boutique Funds calibration (6)": "Specialist & Boutique Funds shortlist: a small diverse learning sample.",
        "All opportunities": "Every retained sourced role across all sectors.",
        "Backlog only": "Roles not currently in any calibration shortlist.",
    }
    st.caption(
        f"Showing: {review_scope}. {_scope_blurb.get(review_scope, '')} "
        "Shortlists are diverse learning samples, not hard recommendations. "
        "Switch to All opportunities to see every retained role."
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
        "fit_verdict",
        "personal_fit_summary",
        "salary_location_context",
        "description_display",
        "fit_note",
        "rating",
        "company",
        "countries",
        "cities",
        "company_category",
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
            "fit_verdict": st.column_config.TextColumn("Fit", width="small"),
            "personal_fit_summary": st.column_config.TextColumn("Personal fit (semantic)", width=620),
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
            "company_category": st.column_config.TextColumn("Company category", width="medium"),
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

    st.subheader("Pending sourcing results")
    token = _github_token()
    staging_summary = _load_staging_summary(token)
    if staging_summary is None:
        st.caption(
            "No sourcing-staging snapshot found yet, or the configured GitHub token "
            "cannot read the sourcing-staging branch."
        )
    else:
        pending_count, pending_companies = staging_summary
        st.metric("New roles waiting to promote", pending_count)
        if pending_count:
            st.caption(
                f"Across {pending_companies} companies. Not yet visible in the Jobs "
                "review queue — promote them to add them to data/jobs.csv."
            )
            if token and st.button("Promote new jobs to live review queue"):
                if _dispatch_promote_workflow(token):
                    st.success(
                        "Promotion triggered. It runs in the background; refresh this "
                        "page in a minute or two once the workflow finishes and "
                        "Streamlit redeploys."
                    )
                else:
                    st.error(
                        "Could not trigger the promote workflow. Check that the GitHub "
                        "token has 'Actions: read and write' permission."
                    )
        else:
            st.caption("Nothing new since the last promotion.")

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


def _render_board_stream(staging_filename: str, title: str, caption: str, key_prefix: str) -> None:
    """Shared review view for board-sourced streams (D Remote, E Projects/Interim):
    no company layer, same feedback + semantic-fit machinery as Jobs."""
    st.title(title)
    st.caption(caption)
    path = DATA_DIR / staging_filename
    if not path.exists():
        st.info("Sourcing has not produced its first snapshot yet.")
        return
    jobs = pd.read_csv(path).fillna("")
    if jobs.empty:
        st.info("Nothing here yet -- the daily sourcing will populate this.")
        return
    jobs = jobs.rename(columns={"job_id": "opportunity_id"})
    if "source_url" not in jobs.columns or jobs["source_url"].eq("").all():
        jobs["source_url"] = jobs.get("job_url", "")

    token = _github_token()
    try:
        feedback, feedback_sha = _load_job_feedback(token)
    except Exception:
        feedback = pd.DataFrame(columns=["opportunity_id", "feedback", "comment", "updated_at"])
        feedback_sha = None
        st.warning("Job feedback could not be loaded.")
    feedback = feedback.drop_duplicates("opportunity_id", keep="last")
    jobs = jobs.merge(feedback[["opportunity_id", "feedback", "comment"]], on="opportunity_id", how="left")
    jobs["feedback"] = jobs["feedback"].fillna("").replace("", "Unrated")
    jobs["comment"] = jobs["comment"].fillna("")

    jobs["fit_verdict"] = ""
    jobs["fit_reasoning"] = ""
    sem_path = DATA_DIR / "semantic_fit.csv"
    if sem_path.exists():
        sem = pd.read_csv(sem_path).fillna("")
        if not sem.empty and "opportunity_id" in sem.columns:
            sem = sem.drop_duplicates("opportunity_id", keep="last").set_index("opportunity_id")
            if "fit" in sem.columns:
                jobs["fit_verdict"] = jobs["opportunity_id"].map(sem["fit"]).fillna("")
            if "reasoning" in sem.columns:
                jobs["fit_reasoning"] = jobs["opportunity_id"].map(sem["reasoning"]).fillna("")
    if "calibration_score" not in jobs.columns:
        jobs["calibration_score"] = 0

    f1, f2 = st.columns(2)
    available = [v for v in FEEDBACK_OPTIONS if v in set(jobs["feedback"])]
    selected = f1.multiselect("Your rating", available, default=available, key=f"{key_prefix}_fb")
    query = f2.text_input("Search role / company", key=f"{key_prefix}_q")
    view = jobs[jobs["feedback"].isin(selected)].copy()
    if query.strip():
        q = query.lower()
        view = view[view["title"].str.lower().str.contains(q) | view["company"].str.lower().str.contains(q)]

    fit_rank = {"strong": 0, "moderate": 1, "partial": 1, "weak": 2}
    view["_fit_order"] = view["fit_verdict"].astype(str).str.lower().map(
        lambda v: next((r for k, r in fit_rank.items() if k in v), 3))
    view["_fb_order"] = view["feedback"].map({"Unrated": 0, "Interested": 1, "Maybe": 2, "Pass": 3}).fillna(4)
    view = view.sort_values(["_fb_order", "_fit_order", "calibration_score"], ascending=[True, True, False])

    c1, c2 = st.columns(2)
    c1.metric("Roles", len(view))
    c2.metric("Unrated", int(view["feedback"].eq("Unrated").sum()))

    columns = ["title", "company", "feedback", "comment", "fit_verdict",
               "fit_reasoning", "location", "source_url"]
    for column in columns:
        if column not in view.columns:
            view[column] = ""
    editor_view = view.set_index("opportunity_id")[columns]
    with st.form(f"{key_prefix}_form"):
        edited = st.data_editor(
            editor_view, hide_index=True, width="stretch", height=560,
            disabled=[c for c in columns if c not in {"feedback", "comment"}],
            column_config={
                "title": st.column_config.TextColumn("Role", width="large"),
                "company": st.column_config.TextColumn("Company", width="medium"),
                "feedback": st.column_config.SelectboxColumn("Your rating", options=FEEDBACK_OPTIONS, required=True, width="small"),
                "comment": st.column_config.TextColumn("Your comment", width="medium"),
                "fit_verdict": st.column_config.TextColumn("Fit", width="small"),
                "fit_reasoning": st.column_config.TextColumn("Personal fit (semantic)", width=560),
                "location": st.column_config.TextColumn("Location", width="small"),
                "source_url": st.column_config.LinkColumn("Open", display_text="Open", width="small"),
            },
            key=f"{key_prefix}_editor",
        )
        saved = st.form_submit_button("Save my ratings", type="primary")
    if saved:
        if not token:
            st.error("GitHub saving is not configured for this app.")
        else:
            base = feedback.set_index("opportunity_id")
            now = datetime.now(timezone.utc).isoformat()
            for oid, row in edited.iterrows():
                base.loc[oid, "feedback"] = row["feedback"]
                base.loc[oid, "comment"] = row["comment"]
                base.loc[oid, "updated_at"] = now
            try:
                _save_job_feedback(token, base.reset_index(), feedback_sha)
            except Exception:
                st.error("Saving failed. Refresh and try again.")
            else:
                st.success("Ratings saved.")


def render_remote() -> None:
    _render_board_stream(
        "jobs_remote_staging.csv", "Remote",
        "Remote-work roles from public remote boards, judged against the same "
        "profile and semantic fit as Jobs. Permanent/ongoing roles only "
        "(contract/interim live under Projects). No company layer.",
        "remote",
    )


def render_projects() -> None:
    _render_board_stream(
        "jobs_projects_staging.csv", "Projekty / Interim",
        "Paid project / interim / contract / freelance finance work for you "
        "personally -- any location. Fit is judged on relevance, whether you "
        "can personally deliver it, and reachability given your ICO and "
        "experience (no company references). No company layer.",
        "projects",
    )
