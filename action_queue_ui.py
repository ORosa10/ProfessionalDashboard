from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import streamlit as st

from github_storage import github_token, load_csv_file, save_csv_file

DATA_DIR = Path(__file__).parent / "data"
BOARD_JOBS_PATH = DATA_DIR / "jobs_board_staging.csv"
CURATED_PATH = DATA_DIR / "j_curated_shortlist.csv"
SEMANTIC_FIT_PATH = DATA_DIR / "semantic_fit.csv"
COUNTRY_WEIGHTS_PATH = DATA_DIR / "country_sourcing_weights.json"
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
        ("Treasury / Markets", ("treasury", "cash management", "liquidity", "hedging", "fx ", "interest rate", "alm", "market risk", "commodity")),
        ("Investments / PE", ("private equity", "investment analyst", "investment associate", "portfolio management", "investments", "beteiligung")),
        ("Corporate Finance / M&A", ("corporate finance", "corporate development", "m&a", "merger", "acquisition", "valuation", "transaction")),
        ("Risk", ("market risk", "financial risk", "risk analyst", "risk manager", "credit risk")),
        ("FP&A / Performance", ("fp&a", "financial planning", "controlling", "controller", "performance management", "strategic finance")),
        ("Restructuring", ("restructur", "turnaround", "distressed", "insolvenc")),
        ("Asset Management", ("asset management", "portfolio manager", "equity analyst", "fixed income", "fund manager")),
    ]
    for family, terms in rules:
        if any(term in text for term in terms):
            return family
    return "Other finance"


def _country_targets() -> dict[str, int]:
    if not COUNTRY_WEIGHTS_PATH.exists():
        return {}
    try:
        payload = json.loads(COUNTRY_WEIGHTS_PATH.read_text(encoding="utf-8"))
        return {str(k): int(v) for k, v in payload.get("top20_targets", {}).items() if int(v) > 0}
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return {}


def _load_company_context() -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    base = DATA_DIR / "company_universe.csv"
    if base.exists():
        frames.append(pd.read_csv(base).fillna(""))
    for path in sorted(DATA_DIR.glob("company_universe_wave*.csv")):
        frames.append(pd.read_csv(path).fillna(""))
    if not frames:
        return pd.DataFrame()

    universe = pd.concat(frames, ignore_index=True, sort=False).fillna("")
    universe = universe.drop_duplicates("canonical_company_id", keep="last")

    if "company_category" not in universe.columns:
        universe["company_category"] = ""
    categories_path = DATA_DIR / "company_categories.csv"
    if categories_path.exists():
        categories = pd.read_csv(categories_path).fillna("")
        if {"canonical_company_id", "company_category"}.issubset(categories.columns):
            categories = categories[["canonical_company_id", "company_category"]].drop_duplicates("canonical_company_id", keep="last")
            category_map = categories.set_index("canonical_company_id")["company_category"]
            mapped = universe["canonical_company_id"].map(category_map).fillna("")
            universe["company_category"] = mapped.where(mapped.ne(""), universe["company_category"])

    overrides_path = DATA_DIR / "company_category_overrides.csv"
    if overrides_path.exists():
        overrides = pd.read_csv(overrides_path).fillna("")
        if {"canonical_company_id", "company_category"}.issubset(overrides.columns):
            override_map = overrides.drop_duplicates("canonical_company_id", keep="last").set_index("canonical_company_id")["company_category"]
            mapped = universe["canonical_company_id"].map(override_map).fillna("")
            universe["company_category"] = mapped.where(mapped.ne(""), universe["company_category"])

    if "rating" not in universe.columns:
        universe["rating"] = ""
    ratings_path = DATA_DIR / "company_ratings.csv"
    if ratings_path.exists():
        ratings = pd.read_csv(ratings_path).fillna("")
        if {"canonical_company_id", "rating"}.issubset(ratings.columns):
            rating_map = ratings.drop_duplicates("canonical_company_id", keep="last").set_index("canonical_company_id")["rating"]
            mapped = universe["canonical_company_id"].map(rating_map).fillna("")
            universe["rating"] = mapped.where(mapped.ne(""), universe["rating"])
    universe["rating"] = universe["rating"].replace("", "Unrated")

    for col in ["company", "aliases_entities", "why_test", "archetype", "company_category", "rating"]:
        if col not in universe.columns:
            universe[col] = ""
    return universe.fillna("")


def _enrich_company(jobs: pd.DataFrame) -> pd.DataFrame:
    universe = _load_company_context()
    out = jobs.copy()
    if universe.empty:
        out["canonical_company_id"] = ""
        out["company_category"] = ""
        out["company_rating"] = "Unrated"
        out["company_context"] = ""
        return out

    exact: dict[str, dict] = {}
    aliases: dict[str, dict] = {}
    for _, row in universe.iterrows():
        rec = row.to_dict()
        key = _norm(rec.get("company", ""))
        if key:
            exact[key] = rec
        for alias in str(rec.get("aliases_entities", "")).split(";"):
            alias_key = _norm(alias)
            if alias_key:
                aliases[alias_key] = rec

    def lookup(company: object) -> dict:
        key = _norm(company)
        return exact.get(key) or aliases.get(key) or {}

    found = out["company"].map(lookup)
    out["canonical_company_id"] = [str(x.get("canonical_company_id", "")) for x in found]
    out["company_category"] = [str(x.get("company_category", "")) for x in found]
    out["company_rating"] = [str(x.get("rating", "") or "Unrated") for x in found]
    out["company_context"] = [
        " · ".join(part for part in [str(x.get("why_test", "")), str(x.get("archetype", ""))] if part)
        for x in found
    ]
    return out


def _merge_semantic_fit(jobs: pd.DataFrame) -> pd.DataFrame:
    out = jobs.copy()
    for col in ["semantic_fit", "semantic_reasoning"]:
        if col not in out.columns:
            out[col] = ""
        out[col] = out[col].fillna("")
    if not SEMANTIC_FIT_PATH.exists() or SEMANTIC_FIT_PATH.stat().st_size == 0:
        return out

    sem = pd.read_csv(SEMANTIC_FIT_PATH).fillna("")
    if sem.empty or "opportunity_id" not in sem.columns:
        return out
    sem = sem.drop_duplicates("opportunity_id", keep="last").set_index("opportunity_id")
    fit_col = "fit" if "fit" in sem.columns else "semantic_fit" if "semantic_fit" in sem.columns else ""
    reasoning_col = "reasoning" if "reasoning" in sem.columns else "fit_reasoning" if "fit_reasoning" in sem.columns else ""
    if fit_col:
        mapped = out["job_id"].map(sem[fit_col]).fillna("")
        out["semantic_fit"] = out["semantic_fit"].where(out["semantic_fit"].ne(""), mapped)
    if reasoning_col:
        mapped = out["job_id"].map(sem[reasoning_col]).fillna("")
        out["semantic_reasoning"] = out["semantic_reasoning"].where(out["semantic_reasoning"].ne(""), mapped)
    return out


def _load_candidates() -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    if CURATED_PATH.exists() and CURATED_PATH.stat().st_size > 0:
        curated = pd.read_csv(CURATED_PATH).fillna("")
        curated["is_curated"] = True
        curated["curated_rank"] = pd.to_numeric(curated.get("curated_rank", 999), errors="coerce").fillna(999)
        curated["status"] = "Open"
        frames.append(curated)
    if BOARD_JOBS_PATH.exists() and BOARD_JOBS_PATH.stat().st_size > 0:
        board = pd.read_csv(BOARD_JOBS_PATH).fillna("")
        if not board.empty:
            board = board[board.get("status", "").eq("Open")].copy()
            board["is_curated"] = False
            board["curated_rank"] = 999
            frames.append(board)
    if not frames:
        return pd.DataFrame()
    jobs = pd.concat(frames, ignore_index=True, sort=False).fillna("")
    jobs = jobs.drop_duplicates("job_id", keep="first")
    for col in ["description", "description_en", "source_id", "date_posted", "discovered_at", "last_seen_at"]:
        if col not in jobs.columns:
            jobs[col] = ""
    return jobs


def _semantic_rank(jobs: pd.DataFrame) -> pd.DataFrame:
    """J is semantic-first. Technical calibration scores never rank the apply queue."""
    out = jobs.copy()
    out["role_family"] = out.apply(
        lambda r: str(r.get("role_family", "")) or _role_family(r.get("title", ""), r.get("description_en", "") or r.get("description", "")),
        axis=1,
    )
    out["_fit_rank"] = out["semantic_fit"].map({"Strong": 0, "Moderate": 1}).fillna(9)
    out["_curated_rank"] = pd.to_numeric(out.get("curated_rank", 999), errors="coerce").fillna(999)
    out["_company_rank"] = out["company_rating"].map({"A": 0, "B": 1, "C": 2, "Unrated": 3, "": 3}).fillna(3)
    out["_posted"] = pd.to_datetime(out.get("date_posted", ""), errors="coerce", utc=True)
    return out.sort_values(
        ["_fit_rank", "_curated_rank", "_company_rank", "_posted"],
        ascending=[True, True, True, False],
    )


def _quality_gate(jobs: pd.DataFrame) -> pd.DataFrame:
    """Only roles that are genuinely actionable after semantic review may enter J.

    Strong roles are eligible. Moderate roles require explicit curation into the
    prime shortlist. Weak, unreviewed and company-Exclude roles never appear.
    """
    strong = jobs["semantic_fit"].eq("Strong")
    curated_moderate = jobs["semantic_fit"].eq("Moderate") & jobs["is_curated"].eq(True)
    eligible = jobs[strong | curated_moderate].copy()
    if "company_rating" in eligible.columns:
        eligible = eligible[~eligible["company_rating"].eq("Exclude")].copy()
    return eligible


def _country_targeted_top(jobs: pd.DataFrame, limit: int = 20) -> pd.DataFrame:
    if jobs.empty or limit <= 0:
        return jobs.iloc[0:0].copy()
    targets = _country_targets()
    selected: list[int] = []
    family_count: dict[str, int] = {}
    company_count: dict[str, int] = {}

    if targets:
        for country, target in targets.items():
            taken = 0
            for idx, row in jobs[jobs["market"].astype(str).eq(country)].iterrows():
                family = str(row.get("role_family", "Other finance"))
                company = _norm(row.get("company", "")) or str(idx)
                if family_count.get(family, 0) >= 6 or company_count.get(company, 0) >= 2:
                    continue
                selected.append(idx)
                family_count[family] = family_count.get(family, 0) + 1
                company_count[company] = company_count.get(company, 0) + 1
                taken += 1
                if taken >= target or len(selected) >= limit:
                    break
            if len(selected) >= limit:
                break

    for idx, row in jobs.iterrows():
        if idx in selected:
            continue
        family = str(row.get("role_family", "Other finance"))
        company = _norm(row.get("company", "")) or str(idx)
        if family_count.get(family, 0) >= 6 or company_count.get(company, 0) >= 2:
            continue
        selected.append(idx)
        family_count[family] = family_count.get(family, 0) + 1
        company_count[company] = company_count.get(company, 0) + 1
        if len(selected) >= limit:
            break

    return jobs.loc[selected[:limit]].copy()


def _history() -> tuple[pd.DataFrame, str | None]:
    token = github_token()
    try:
        return load_csv_file(token, HISTORY_PATH, HISTORY_COLUMNS)
    except Exception:
        return pd.DataFrame(columns=HISTORY_COLUMNS), None


def _current_shortlist() -> tuple[pd.DataFrame, pd.DataFrame, str | None]:
    jobs = _load_candidates()
    if jobs.empty:
        return jobs, pd.DataFrame(columns=HISTORY_COLUMNS), None

    jobs = _merge_semantic_fit(_enrich_company(jobs))
    jobs = _quality_gate(jobs)
    jobs = _semantic_rank(jobs)

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

    return _country_targeted_top(jobs, 20), history, history_sha


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
        src = source.loc[opportunity_id]
        changed = (
            action != str(src.get("prior_action", "") or "New")
            or company_feedback != str(src.get("prior_company_feedback", "") or "Not rated")
            or role_feedback != str(src.get("prior_role_feedback", "") or "Not rated")
            or comment != str(src.get("prior_comment", ""))
        )
        if not changed:
            continue

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
            "calibration_score_at_decision": "",
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
        "Only semantically reviewed, actionable roles appear here. J does not fill 20 slots with weak matches: "
        "quality comes first, country mix is only a soft target."
    )

    shortlist, history, history_sha = _current_shortlist()
    if shortlist.empty:
        st.info("No semantically strong actionable G roles are ready for J yet. G/C should source and review more roles rather than fill this page with weak matches.")
        return

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Actionable roles", len(shortlist))
    m2.metric("Companies", shortlist["company"].nunique())
    m3.metric("Countries", shortlist["market"].nunique())
    m4.metric("Strong", int(shortlist["semantic_fit"].eq("Strong").sum()))

    moderate_count = int(shortlist["semantic_fit"].eq("Moderate").sum())
    st.caption(
        f"Semantic quality gate: Strong first; {moderate_count} curated Moderate role(s) currently included. "
        "Weak and unreviewed roles are excluded completely. No technical calibration score is used to rank J."
    )

    targets = _country_targets()
    if targets:
        target_text = " · ".join(f"{country}: {count}" for country, count in targets.items())
        st.caption(f"Soft country target for a full 20-role set: {target_text}. We do not lower fit quality to hit these numbers.")

    display = shortlist.set_index("job_id").copy()
    display["action"] = display["prior_action"].replace("", "New")
    display["company_feedback"] = display["prior_company_feedback"].replace("", "Not rated")
    display["role_feedback"] = display["prior_role_feedback"].replace("", "Not rated")
    display["user_comment"] = display["prior_comment"]
    display["fit"] = display.apply(
        lambda r: f"{r.get('semantic_fit')} · {r.get('semantic_reasoning')}" if r.get("semantic_reasoning") else str(r.get("semantic_fit", "")),
        axis=1,
    )
    display["company_view"] = display.apply(
        lambda r: " · ".join(
            part for part in [
                str(r.get("company_category", "")),
                (f"A={r.get('company_rating')}" if r.get("company_rating") else ""),
                str(r.get("company_context", "")),
            ] if part
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
                "fit": st.column_config.TextColumn("C — semantic fit", width="large"),
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

    with st.expander("How J is built"):
        st.write(
            "G sources broadly. C semantically reviews role content. J only admits Strong roles plus explicitly curated Moderate exceptions. "
            "Country targets diversify the final set but never force a weak role into the apply queue."
        )
