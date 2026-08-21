from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import streamlit as st

from github_storage import github_token, load_csv_file, save_csv_file

DATA_DIR = Path(__file__).parent / "data"
BOARD_JOBS_PATH = DATA_DIR / "jobs_board_staging.csv"
SEMANTIC_FIT_PATH = DATA_DIR / "semantic_fit.csv"
HISTORY_PATH = "data/opportunity_history.csv"

HISTORY_COLUMNS = [
    "opportunity_id", "source_stream", "source_id", "first_seen_at", "decision_at",
    "title", "company", "canonical_company_id", "company_category", "market", "location",
    "job_url", "action", "company_feedback", "role_feedback", "user_comment",
    "company_rating_at_decision", "semantic_fit_at_decision", "semantic_reasoning_at_decision",
    "calibration_score_at_decision", "application_stage", "stage_updated_at",
    "outcome_reason", "history_notes",
]
ACTION_OPTIONS = ["New", "Apply", "Maybe", "Skip"]
FEEDBACK_OPTIONS = ["Not rated", "Positive", "Neutral", "Negative"]


def _norm(value: object) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value or "").lower())


def _role_family(title: object, description: object = "") -> str:
    text = f"{title} {description}".lower()
    rules = [
        ("Treasury / Markets", ("treasury", "cash management", "liquidity", "hedging", "fx ", "interest rate", "alm")),
        ("Investments / PE", ("private equity", "investment analyst", "investment associate", "portfolio management", "investments")),
        ("Corporate Finance / M&A", ("corporate finance", "corporate development", "m&a", "merger", "acquisition", "valuation", "transaction")),
        ("Risk", ("market risk", "financial risk", "risk analyst", "risk manager", "credit risk")),
        ("FP&A / Performance", ("fp&a", "financial planning", "controlling", "controller", "performance management")),
        ("Restructuring", ("restructur", "turnaround", "distressed", "insolvenc")),
        ("Asset Management", ("asset management", "portfolio manager", "equity analyst", "fixed income", "fund manager")),
    ]
    for family, terms in rules:
        if any(term in text for term in terms):
            return family
    return "Other finance"


@st.cache_data(ttl=300)
def _load_company_context() -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    base_path = DATA_DIR / "company_universe.csv"
    if base_path.exists():
        frames.append(pd.read_csv(base_path).fillna(""))
    for path in sorted(DATA_DIR.glob("company_universe_wave*.csv")):
        frames.append(pd.read_csv(path).fillna(""))
    if not frames:
        return pd.DataFrame(columns=["canonical_company_id", "company", "company_category", "why_test", "archetype", "rating"])

    universe = pd.concat(frames, ignore_index=True, sort=False).fillna("")
    universe = universe.drop_duplicates("canonical_company_id", keep="last")

    # Keep the universe's default rating as a fallback, but let the user's live
    # company_ratings.csv value override it. Avoid pandas rating_x/rating_y,
    # which would otherwise silently remove A's rating from J's rank.
    if "rating" in universe.columns:
        universe["base_rating"] = universe["rating"].fillna("")
        universe = universe.drop(columns=["rating"])
    else:
        universe["base_rating"] = ""

    category_frames: list[pd.DataFrame] = []
    if "company_category" in universe.columns:
        category_frames.append(universe[["canonical_company_id", "company_category"]])
        universe = universe.drop(columns=["company_category"])
    categories_path = DATA_DIR / "company_categories.csv"
    if categories_path.exists():
        category_frames.append(pd.read_csv(categories_path).fillna("")[["canonical_company_id", "company_category"]])
    overrides_path = DATA_DIR / "company_category_overrides.csv"
    if overrides_path.exists():
        category_frames.append(pd.read_csv(overrides_path).fillna("")[["canonical_company_id", "company_category"]])
    if category_frames:
        categories = pd.concat(category_frames, ignore_index=True).drop_duplicates("canonical_company_id", keep="last")
        universe = universe.merge(categories, on="canonical_company_id", how="left")
    else:
        universe["company_category"] = ""

    ratings_path = DATA_DIR / "company_ratings.csv"
    if ratings_path.exists():
        ratings = pd.read_csv(ratings_path).fillna("")
        ratings = ratings.drop_duplicates("canonical_company_id", keep="last")
        ratings = ratings[["canonical_company_id", "rating"]].rename(columns={"rating": "saved_rating"})
        universe = universe.merge(ratings, on="canonical_company_id", how="left")
        universe["saved_rating"] = universe["saved_rating"].fillna("")
        universe["rating"] = universe["saved_rating"].where(
            universe["saved_rating"].ne(""), universe["base_rating"]
        )
        universe = universe.drop(columns=["saved_rating"])
    else:
        universe["rating"] = universe["base_rating"]
    universe["rating"] = universe["rating"].replace("", "Unrated")

    for col in ["why_test", "archetype", "aliases_entities", "company_category", "rating"]:
        if col not in universe.columns:
            universe[col] = ""
    return universe.fillna("")


def _company_lookup(universe: pd.DataFrame) -> tuple[dict[str, dict], dict[str, dict]]:
    exact: dict[str, dict] = {}
    alias: dict[str, dict] = {}
    for _, row in universe.iterrows():
        record = row.to_dict()
        key = _norm(record.get("company", ""))
        if key:
            exact[key] = record
        for item in str(record.get("aliases_entities", "")).split(";"):
            alias_key = _norm(item)
            if alias_key:
                alias[alias_key] = record
    return exact, alias


def _enrich_company(jobs: pd.DataFrame) -> pd.DataFrame:
    universe = _load_company_context()
    exact, alias = _company_lookup(universe)
    out = jobs.copy()

    def find(company: object) -> dict:
        key = _norm(company)
        return exact.get(key) or alias.get(key) or {}

    found = out["company"].map(find)
    out["canonical_company_id"] = [str(item.get("canonical_company_id", "")) for item in found]
    out["company_category"] = [str(item.get("company_category", "")) for item in found]
    out["company_rating"] = [str(item.get("rating", "") or "Unrated") for item in found]
    out["company_context"] = [
        " · ".join(
            part for part in [
                str(item.get("company_category", "")),
                (f"A rating: {item.get('rating')}" if item.get("rating") else ""),
                str(item.get("why_test", "")),
            ] if part
        )
        for item in found
    ]
    return out


def _merge_semantic_fit(jobs: pd.DataFrame) -> pd.DataFrame:
    out = jobs.copy()
    out["semantic_fit"] = ""
    out["semantic_reasoning"] = ""
    if not SEMANTIC_FIT_PATH.exists():
        return out
    sem = pd.read_csv(SEMANTIC_FIT_PATH).fillna("")
    if sem.empty or "opportunity_id" not in sem.columns:
        return out
    sem = sem.drop_duplicates("opportunity_id", keep="last").set_index("opportunity_id")
    fit_col = "fit" if "fit" in sem.columns else "semantic_fit" if "semantic_fit" in sem.columns else ""
    reasoning_col = "reasoning" if "reasoning" in sem.columns else "fit_reasoning" if "fit_reasoning" in sem.columns else ""
    if fit_col:
        out["semantic_fit"] = out["job_id"].map(sem[fit_col]).fillna("")
    if reasoning_col:
        out["semantic_reasoning"] = out["job_id"].map(sem[reasoning_col]).fillna("")
    return out


def _rank(jobs: pd.DataFrame) -> pd.DataFrame:
    out = jobs.copy()
    out["calibration_score"] = pd.to_numeric(out.get("calibration_score", 0), errors="coerce").fillna(0)
    fit_points = {"Strong": 30, "Moderate": 15, "Weak": -15}
    company_points = {"A": 12, "B": 6, "C": 0, "Exclude": -20, "Unrated": 0, "": 0}
    out["_score"] = (
        out["calibration_score"]
        + out["semantic_fit"].map(fit_points).fillna(0)
        + out["company_rating"].map(company_points).fillna(0)
    )
    out["role_family"] = out.apply(
        lambda r: _role_family(r.get("title", ""), r.get("description_en", "") or r.get("description", "")),
        axis=1,
    )
    out["_posted"] = pd.to_datetime(out.get("date_posted", ""), errors="coerce", utc=True)
    return out.sort_values(["_score", "_posted", "last_seen_at"], ascending=[False, False, False])


def _diversified_top(jobs: pd.DataFrame, limit: int = 20) -> pd.DataFrame:
    if jobs.empty:
        return jobs
    selected: list[int] = []
    family_count: dict[str, int] = {}
    company_count: dict[str, int] = {}
    country_count: dict[str, int] = {}

    for idx, row in jobs.iterrows():
        family = str(row.get("role_family", "Other finance"))
        company = _norm(row.get("company", "")) or str(idx)
        country = str(row.get("market", ""))
        if family_count.get(family, 0) >= 4:
            continue
        if company_count.get(company, 0) >= 2:
            continue
        if country_count.get(country, 0) >= 6:
            continue
        selected.append(idx)
        family_count[family] = family_count.get(family, 0) + 1
        company_count[company] = company_count.get(company, 0) + 1
        country_count[country] = country_count.get(country, 0) + 1
        if len(selected) >= limit:
            break

    if len(selected) < limit:
        for idx, row in jobs.iterrows():
            if idx in selected:
                continue
            company = _norm(row.get("company", "")) or str(idx)
            if company_count.get(company, 0) >= 2:
                continue
            selected.append(idx)
            company_count[company] = company_count.get(company, 0) + 1
            if len(selected) >= limit:
                break
    return jobs.loc[selected].copy()


def _history() -> tuple[pd.DataFrame, str | None]:
    token = github_token()
    try:
        return load_csv_file(token, HISTORY_PATH, HISTORY_COLUMNS)
    except Exception:
        return pd.DataFrame(columns=HISTORY_COLUMNS), None


def _current_shortlist() -> tuple[pd.DataFrame, pd.DataFrame, str | None]:
    if not BOARD_JOBS_PATH.exists():
        return pd.DataFrame(), pd.DataFrame(columns=HISTORY_COLUMNS), None
    jobs = pd.read_csv(BOARD_JOBS_PATH).fillna("")
    if jobs.empty:
        return jobs, pd.DataFrame(columns=HISTORY_COLUMNS), None
    jobs = jobs[jobs["status"].eq("Open")].copy()
    jobs = jobs.drop_duplicates("job_id", keep="last")
    jobs = _merge_semantic_fit(_enrich_company(jobs))
    jobs = _rank(jobs)

    history, history_sha = _history()
    if not history.empty:
        latest = history.drop_duplicates("opportunity_id", keep="last").set_index("opportunity_id")
        jobs["prior_action"] = jobs["job_id"].map(latest["action"]).fillna("")
        jobs["prior_company_feedback"] = jobs["job_id"].map(latest["company_feedback"]).fillna("")
        jobs["prior_role_feedback"] = jobs["job_id"].map(latest["role_feedback"]).fillna("")
        jobs["prior_comment"] = jobs["job_id"].map(latest["user_comment"]).fillna("")
        jobs = jobs[~jobs["prior_action"].isin(["Apply", "Skip"])].copy()
    else:
        jobs["prior_action"] = ""
        jobs["prior_company_feedback"] = ""
        jobs["prior_role_feedback"] = ""
        jobs["prior_comment"] = ""

    return _diversified_top(jobs, 20), history, history_sha


def _upsert_history(history: pd.DataFrame, edited: pd.DataFrame, source: pd.DataFrame) -> pd.DataFrame:
    now = datetime.now(timezone.utc).isoformat()
    current = history.copy().reindex(columns=HISTORY_COLUMNS, fill_value="")
    if current.empty:
        by_id = pd.DataFrame(columns=[c for c in HISTORY_COLUMNS if c != "opportunity_id"])
        by_id.index.name = "opportunity_id"
    else:
        by_id = current.drop_duplicates("opportunity_id", keep="last").set_index("opportunity_id")

    source = source.set_index("job_id")
    for opportunity_id, row in edited.iterrows():
        action = str(row.get("action", "New"))
        company_feedback = str(row.get("company_feedback", "Not rated"))
        role_feedback = str(row.get("role_feedback", "Not rated"))
        comment = str(row.get("user_comment", ""))
        changed = (
            action != str(source.loc[opportunity_id].get("prior_action", "") or "New")
            or company_feedback != str(source.loc[opportunity_id].get("prior_company_feedback", "") or "Not rated")
            or role_feedback != str(source.loc[opportunity_id].get("prior_role_feedback", "") or "Not rated")
            or comment != str(source.loc[opportunity_id].get("prior_comment", ""))
        )
        if not changed:
            continue

        src = source.loc[opportunity_id]
        existing = by_id.loc[opportunity_id].to_dict() if opportunity_id in by_id.index else {}
        record = {col: str(existing.get(col, "")) for col in HISTORY_COLUMNS if col != "opportunity_id"}
        record.update({
            "source_stream": "G",
            "source_id": str(src.get("source_id", "")),
            "first_seen_at": str(existing.get("first_seen_at", "") or src.get("discovered_at", "") or now),
            "decision_at": now,
            "title": str(src.get("title", "")),
            "company": str(src.get("company", "")),
            "canonical_company_id": str(src.get("canonical_company_id", "")),
            "company_category": str(src.get("company_category", "")),
            "market": str(src.get("market", "")),
            "location": str(src.get("location", "")),
            "job_url": str(src.get("job_url", "")),
            "action": action,
            "company_feedback": company_feedback,
            "role_feedback": role_feedback,
            "user_comment": comment,
            "company_rating_at_decision": str(src.get("company_rating", "")),
            "semantic_fit_at_decision": str(src.get("semantic_fit", "")),
            "semantic_reasoning_at_decision": str(src.get("semantic_reasoning", "")),
            "calibration_score_at_decision": str(src.get("calibration_score", "")),
        })
        if action == "Apply" and not record["application_stage"]:
            record["application_stage"] = "Applied"
            record["stage_updated_at"] = now
        by_id.loc[opportunity_id] = pd.Series(record)

    return by_id.reset_index().reindex(columns=HISTORY_COLUMNS, fill_value="")


def render_action_queue() -> None:
    st.markdown('<div class="eyebrow">Workstream J</div>', unsafe_allow_html=True)
    st.title("Apply Shortlist")
    st.caption(
        "Your actionable TOP 20 from automated sourcing. G finds roles; A adds company context; "
        "C ranks role fit; this page is where you decide what to do."
    )

    shortlist, history, history_sha = _current_shortlist()
    if shortlist.empty:
        st.info("No open G roles are currently available for the shortlist.")
        return

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Action shortlist", len(shortlist))
    m2.metric("Companies", shortlist["company"].nunique())
    m3.metric("Countries", shortlist["market"].nunique())
    m4.metric("Strong semantic fit", int(shortlist["semantic_fit"].eq("Strong").sum()))

    st.caption(
        "The list is deliberately diversified: one role family, company or country cannot fill the whole TOP 20. "
        "Apply and Skip leave this queue after saving; Maybe stays available."
    )

    display = shortlist.set_index("job_id").copy()
    display["action"] = display["prior_action"].replace("", "New")
    display["company_feedback"] = display["prior_company_feedback"].replace("", "Not rated")
    display["role_feedback"] = display["prior_role_feedback"].replace("", "Not rated")
    display["user_comment"] = display["prior_comment"]
    display["fit"] = display.apply(
        lambda r: (
            f"{r.get('semantic_fit') or 'C pre-score'}"
            + (f" · {r.get('semantic_reasoning')}" if r.get("semantic_reasoning") else "")
            + (f" · score {r.get('calibration_score')}" if r.get("calibration_score") != "" else "")
        ),
        axis=1,
    )
    display["company_view"] = display.apply(
        lambda r: (
            f"{r.get('company_category') or 'Unclassified'}"
            + (f" · A={r.get('company_rating')}" if r.get("company_rating") else "")
            + (f" · {r.get('company_context')}" if r.get("company_context") else "")
        ),
        axis=1,
    )

    cols = [
        "company", "title", "role_family", "market", "location", "fit", "company_view",
        "job_url", "action", "company_feedback", "role_feedback", "user_comment",
    ]
    with st.form("action_queue_form"):
        edited = st.data_editor(
            display[cols],
            hide_index=True,
            width="stretch",
            height=720,
            row_height=95,
            disabled=[c for c in cols if c not in {"action", "company_feedback", "role_feedback", "user_comment"}],
            column_config={
                "company": st.column_config.TextColumn("Company", width="small"),
                "title": st.column_config.TextColumn("Role", width="medium"),
                "role_family": st.column_config.TextColumn("Bucket", width="small"),
                "market": st.column_config.TextColumn("Country", width="small"),
                "location": st.column_config.TextColumn("Location", width="small"),
                "fit": st.column_config.TextColumn("C — role fit", width="large"),
                "company_view": st.column_config.TextColumn("A — company context", width="large"),
                "job_url": st.column_config.LinkColumn("Job page", display_text="Open"),
                "action": st.column_config.SelectboxColumn("Your action", options=ACTION_OPTIONS, required=True),
                "company_feedback": st.column_config.SelectboxColumn("Company", options=FEEDBACK_OPTIONS, required=True),
                "role_feedback": st.column_config.SelectboxColumn("Role", options=FEEDBACK_OPTIONS, required=True),
                "user_comment": st.column_config.TextColumn("Comment", width="medium"),
            },
        )
        save = st.form_submit_button("Save decisions", type="primary")

    if save:
        token = github_token()
        if not token:
            st.error("GitHub saving is not configured for this app.")
            return
        updated = _upsert_history(history, edited, shortlist)
        try:
            save_csv_file(token, HISTORY_PATH, updated, history_sha, "Save J shortlist decisions")
        except Exception:
            st.error("Saving decisions failed. Refresh and try again.")
        else:
            st.success("Saved to I — Opportunity History. Apply/Skip will leave this shortlist on refresh.")
            st.rerun()

    with st.expander("How feedback is used"):
        st.write(
            "Your action is the primary operational signal. Company and role feedback are stored separately so "
            "future batch calibration can feed company patterns back to A and role patterns back to C. "
            "Nothing rewrites A/C after every single click; calibration can use accumulated batches."
        )
