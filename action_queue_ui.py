from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import streamlit as st

from github_storage import github_token, load_csv_file, save_csv_file

DATA_DIR = Path(__file__).parent / "data"
CURATED_PATH = DATA_DIR / "j_curated_shortlist.csv"
BOARD_PATH = DATA_DIR / "jobs_board_staging.csv"
SEMANTIC_PATH = DATA_DIR / "semantic_fit.csv"
COUNTRY_PATH = DATA_DIR / "country_sourcing_weights.json"
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


def _norm(v: object) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(v or "").lower())


def _country_targets() -> dict[str, int]:
    try:
        payload = json.loads(COUNTRY_PATH.read_text(encoding="utf-8"))
        return {str(k): int(v) for k, v in payload.get("top20_targets", {}).items() if int(v) > 0}
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return {}


def _load_candidates() -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    if CURATED_PATH.exists() and CURATED_PATH.stat().st_size:
        c = pd.read_csv(CURATED_PATH).fillna("")
        c["is_curated"] = True
        c["curated_rank"] = pd.to_numeric(c.get("curated_rank", 999), errors="coerce").fillna(999)
        frames.append(c)
    if BOARD_PATH.exists() and BOARD_PATH.stat().st_size:
        b = pd.read_csv(BOARD_PATH).fillna("")
        if not b.empty and "status" in b.columns:
            b = b[b["status"].eq("Open")].copy()
            b["is_curated"] = False
            b["curated_rank"] = 999
            frames.append(b)
    if not frames:
        return pd.DataFrame()
    out = pd.concat(frames, ignore_index=True, sort=False).fillna("")
    out = out.drop_duplicates("job_id", keep="first")
    for col in ["source_id", "date_posted", "description", "description_en", "role_family"]:
        if col not in out.columns:
            out[col] = ""
    return out


def _merge_semantic(jobs: pd.DataFrame) -> pd.DataFrame:
    out = jobs.copy()
    for col in ["semantic_fit", "semantic_reasoning"]:
        if col not in out.columns:
            out[col] = ""
    if not SEMANTIC_PATH.exists() or not SEMANTIC_PATH.stat().st_size:
        return out.fillna("")
    sem = pd.read_csv(SEMANTIC_PATH).fillna("")
    if sem.empty or "opportunity_id" not in sem.columns:
        return out.fillna("")
    sem = sem.drop_duplicates("opportunity_id", keep="last").set_index("opportunity_id")
    fit_col = "fit" if "fit" in sem.columns else "semantic_fit" if "semantic_fit" in sem.columns else None
    reason_col = "reasoning" if "reasoning" in sem.columns else "fit_reasoning" if "fit_reasoning" in sem.columns else None
    if fit_col:
        mapped = out["job_id"].map(sem[fit_col]).fillna("")
        out["semantic_fit"] = out["semantic_fit"].fillna("").where(out["semantic_fit"].fillna("").ne(""), mapped)
    if reason_col:
        mapped = out["job_id"].map(sem[reason_col]).fillna("")
        out["semantic_reasoning"] = out["semantic_reasoning"].fillna("").where(out["semantic_reasoning"].fillna("").ne(""), mapped)
    return out.fillna("")


def _company_context(jobs: pd.DataFrame) -> pd.DataFrame:
    out = jobs.copy()
    out["canonical_company_id"] = ""
    out["company_category"] = ""
    out["company_rating"] = "Unrated"
    frames = []
    base = DATA_DIR / "company_universe.csv"
    if base.exists():
        frames.append(pd.read_csv(base).fillna(""))
    frames += [pd.read_csv(p).fillna("") for p in sorted(DATA_DIR.glob("company_universe_wave*.csv"))]
    if not frames:
        return out
    u = pd.concat(frames, ignore_index=True, sort=False).fillna("")
    if "canonical_company_id" in u.columns:
        u = u.drop_duplicates("canonical_company_id", keep="last")
    for col in ["company", "canonical_company_id", "company_category", "rating"]:
        if col not in u.columns:
            u[col] = ""
    for path, value_col in [
        (DATA_DIR / "company_categories.csv", "company_category"),
        (DATA_DIR / "company_category_overrides.csv", "company_category"),
        (DATA_DIR / "company_ratings.csv", "rating"),
    ]:
        if path.exists():
            x = pd.read_csv(path).fillna("")
            if {"canonical_company_id", value_col}.issubset(x.columns):
                m = x.drop_duplicates("canonical_company_id", keep="last").set_index("canonical_company_id")[value_col]
                vals = u["canonical_company_id"].map(m).fillna("")
                u[value_col] = vals.where(vals.ne(""), u[value_col])
    by_name = {_norm(r["company"]): r for _, r in u.iterrows() if _norm(r["company"])}
    for idx, company in out["company"].items():
        r = by_name.get(_norm(company))
        if r is not None:
            out.at[idx, "canonical_company_id"] = str(r.get("canonical_company_id", ""))
            out.at[idx, "company_category"] = str(r.get("company_category", ""))
            out.at[idx, "company_rating"] = str(r.get("rating", "") or "Unrated")
    return out


def _quality_and_rank(jobs: pd.DataFrame) -> pd.DataFrame:
    out = jobs.copy()
    strong = out["semantic_fit"].eq("Strong")
    moderate = out["semantic_fit"].eq("Moderate") & out["is_curated"].eq(True)
    out = out[strong | moderate].copy()
    out = out[~out["company_rating"].eq("Exclude")].copy()
    out["_fit"] = out["semantic_fit"].map({"Strong": 0, "Moderate": 1}).fillna(9)
    out["_curated"] = pd.to_numeric(out["curated_rank"], errors="coerce").fillna(999)
    out["_company"] = out["company_rating"].map({"A": 0, "B": 1, "C": 2, "Unrated": 3, "": 3}).fillna(3)
    out["_date"] = pd.to_datetime(out["date_posted"], errors="coerce", utc=True)
    return out.sort_values(["_fit", "_curated", "_company", "_date"], ascending=[True, True, True, False])


def _select_top(jobs: pd.DataFrame, limit: int = 20) -> pd.DataFrame:
    """Reviewed shortlist first. Country mix only guides replenishment. No role-family quota."""
    if jobs.empty:
        return jobs
    selected: list[int] = []
    companies: dict[str, int] = {}

    def add(idx: int, row: pd.Series) -> bool:
        key = _norm(row.get("company", "")) or str(idx)
        if idx in selected or companies.get(key, 0) >= 2:
            return False
        selected.append(idx)
        companies[key] = companies.get(key, 0) + 1
        return True

    curated = jobs[jobs["is_curated"].eq(True)]
    for idx, row in curated.iterrows():
        add(idx, row)
        if len(selected) >= limit:
            return jobs.loc[selected[:limit]].copy()

    pool = jobs[~jobs["is_curated"].eq(True)]
    targets = _country_targets()
    counts = jobs.loc[selected, "market"].astype(str).value_counts().to_dict() if selected else {}
    for country, target in targets.items():
        missing = max(0, target - int(counts.get(country, 0)))
        for idx, row in pool[pool["market"].astype(str).eq(country)].iterrows():
            if missing <= 0 or len(selected) >= limit:
                break
            if add(idx, row):
                missing -= 1
        if len(selected) >= limit:
            return jobs.loc[selected[:limit]].copy()
    for idx, row in pool.iterrows():
        add(idx, row)
        if len(selected) >= limit:
            break
    return jobs.loc[selected[:limit]].copy()


def _history() -> tuple[pd.DataFrame, str | None]:
    try:
        return load_csv_file(github_token(), HISTORY_PATH, HISTORY_COLUMNS)
    except Exception:
        return pd.DataFrame(columns=HISTORY_COLUMNS), None


def _current_shortlist() -> tuple[pd.DataFrame, pd.DataFrame, str | None]:
    jobs = _load_candidates()
    if jobs.empty:
        return jobs, pd.DataFrame(columns=HISTORY_COLUMNS), None
    jobs = _quality_and_rank(_company_context(_merge_semantic(jobs)))
    history, sha = _history()
    latest = history.drop_duplicates("opportunity_id", keep="last").set_index("opportunity_id") if not history.empty else None
    for col, hist_col in [
        ("prior_action", "action"), ("prior_company_feedback", "company_feedback"),
        ("prior_role_feedback", "role_feedback"), ("prior_comment", "user_comment"),
    ]:
        jobs[col] = jobs["job_id"].map(latest[hist_col]).fillna("") if latest is not None and hist_col in latest.columns else ""
    jobs = jobs[~jobs["prior_action"].isin(["Apply", "Skip"])].copy()
    return _select_top(jobs, 20), history, sha


def _upsert_history(history: pd.DataFrame, edited: pd.DataFrame, source: pd.DataFrame) -> pd.DataFrame:
    now = datetime.now(timezone.utc).isoformat()
    current = history.reindex(columns=HISTORY_COLUMNS, fill_value="").copy()
    by_id = current.drop_duplicates("opportunity_id", keep="last").set_index("opportunity_id") if not current.empty else pd.DataFrame(columns=HISTORY_COLUMNS[1:])
    by_id.index.name = "opportunity_id"
    source = source.set_index("job_id")
    for oid, row in edited.iterrows():
        action = str(row.get("action", "New"))
        cf = str(row.get("company_feedback", "Not rated"))
        rf = str(row.get("role_feedback", "Not rated"))
        comment = str(row.get("user_comment", ""))
        src = source.loc[oid]
        if (action, cf, rf, comment) == (
            str(src.get("prior_action", "") or "New"),
            str(src.get("prior_company_feedback", "") or "Not rated"),
            str(src.get("prior_role_feedback", "") or "Not rated"),
            str(src.get("prior_comment", "")),
        ):
            continue
        old = by_id.loc[oid].to_dict() if oid in by_id.index else {}
        rec = {c: str(old.get(c, "")) for c in HISTORY_COLUMNS[1:]}
        rec.update({
            "source_stream": "G", "source_id": str(src.get("source_id", "")),
            "first_seen_at": str(old.get("first_seen_at", "") or now), "decision_at": now,
            "title": str(src.get("title", "")), "company": str(src.get("company", "")),
            "canonical_company_id": str(src.get("canonical_company_id", "")),
            "company_category": str(src.get("company_category", "")), "market": str(src.get("market", "")),
            "location": str(src.get("location", "")), "job_url": str(src.get("job_url", "")),
            "action": action, "company_feedback": cf, "role_feedback": rf, "user_comment": comment,
            "company_rating_at_decision": str(src.get("company_rating", "")),
            "semantic_fit_at_decision": str(src.get("semantic_fit", "")),
            "semantic_reasoning_at_decision": str(src.get("semantic_reasoning", "")),
            "calibration_score_at_decision": "",
        })
        if action == "Apply" and not rec["application_stage"]:
            rec["application_stage"] = "Applied"
            rec["stage_updated_at"] = now
        by_id.loc[oid] = pd.Series(rec)
    return by_id.reset_index().reindex(columns=HISTORY_COLUMNS, fill_value="")


def render_action_queue() -> None:
    st.markdown('<div class="eyebrow">Workstream J</div>', unsafe_allow_html=True)
    st.title("Apply Shortlist")
    st.caption("Only reviewed, actionable roles. Quality first; country mix is soft; role families have no quotas.")
    shortlist, history, history_sha = _current_shortlist()
    if shortlist.empty:
        st.info("No actionable reviewed roles are ready. Source/review more in G/C rather than lowering the J bar.")
        return
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Actionable roles", len(shortlist))
    m2.metric("Companies", shortlist["company"].nunique())
    m3.metric("Countries", shortlist["market"].nunique())
    m4.metric("Strong", int(shortlist["semantic_fit"].eq("Strong").sum()))
    moderate = int(shortlist["semantic_fit"].eq("Moderate").sum())
    st.caption(f"Strong first; {moderate} explicitly curated Moderate role(s). Weak/unreviewed are excluded. Calibration score does not rank J.")
    targets = _country_targets()
    if targets:
        st.caption("Soft country targets: " + " · ".join(f"{k}: {v}" for k, v in targets.items()) + ". Reviewed quality always wins.")

    display = shortlist.set_index("job_id").copy()
    display["action"] = display["prior_action"].replace("", "New")
    display["company_feedback"] = display["prior_company_feedback"].replace("", "Not rated")
    display["role_feedback"] = display["prior_role_feedback"].replace("", "Not rated")
    display["user_comment"] = display["prior_comment"]
    display["fit"] = display.apply(lambda r: f"{r.get('semantic_fit')} · {r.get('semantic_reasoning')}" if r.get("semantic_reasoning") else str(r.get("semantic_fit", "")), axis=1)
    cols = ["company", "title", "role_family", "market", "location", "fit", "job_url", "action", "company_feedback", "role_feedback", "user_comment"]
    with st.form("action_queue_form"):
        edited = st.data_editor(
            display[cols], hide_index=True, width="stretch", height=720, row_height=95,
            disabled=[c for c in cols if c not in {"action", "company_feedback", "role_feedback", "user_comment"}],
            column_config={
                "company": st.column_config.TextColumn("Company", width="small"),
                "title": st.column_config.TextColumn("Role", width="medium"),
                "role_family": st.column_config.TextColumn("Bucket", width="small"),
                "market": st.column_config.TextColumn("Country", width="small"),
                "location": st.column_config.TextColumn("Location", width="small"),
                "fit": st.column_config.TextColumn("C — semantic fit", width="large"),
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
        try:
            save_csv_file(token, HISTORY_PATH, _upsert_history(history, edited, shortlist), history_sha, "Save J shortlist decisions")
        except Exception:
            st.error("Saving decisions failed. Refresh and try again.")
        else:
            st.success("Saved to I — Opportunity History. Apply/Skip will leave this shortlist on refresh.")
            st.rerun()
    with st.expander("How J is built"):
        st.write("G sources broadly. C reviews semantic fit. Reviewed J choices come first; country targets only guide replenishment. There is no role-family quota.")
