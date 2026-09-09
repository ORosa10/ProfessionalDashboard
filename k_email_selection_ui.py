from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd
import streamlit as st

from github_storage import github_token, load_csv_file, save_csv_file


DIGEST_PATH = "data/j_daily_digest_log.csv"
SELECTION_PATH = "data/k_email_selection.csv"

DIGEST_COLUMNS = ["sent_at", "opportunity_id", "title", "company", "job_url"]
SELECTION_COLUMNS = [
    "selection_id",
    "opportunity_id",
    "digest_sent_at",
    "title",
    "company",
    "job_url",
    "email_action",
    "selection_action",
    "selected_at",
    "notes",
]
HISTORY_PATH = "data/opportunity_history.csv"
HISTORY_COLUMNS = [
    "opportunity_id", "source_stream", "source_id", "first_seen_at", "decision_at",
    "title", "company", "canonical_company_id", "company_category", "market", "location",
    "job_url", "action", "company_feedback", "role_feedback", "user_comment",
    "company_rating_at_decision", "semantic_fit_at_decision", "semantic_reasoning_at_decision",
    "calibration_score_at_decision", "application_stage", "stage_updated_at",
    "outcome_reason", "history_notes",
]
ACTION_OPTIONS = ["New", "To be applied", "Maybe", "Skip"]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _legacy_action(value: object) -> str:
    action = str(value or "").strip()
    return {"Apply": "To be applied", "Maybe": "Maybe", "Skip": "Skip"}.get(action, "New")


def _load_history_actions(token: str | None) -> dict[str, str]:
    history, _ = load_csv_file(token, HISTORY_PATH, HISTORY_COLUMNS)
    if history.empty or "opportunity_id" not in history.columns:
        return {}
    history = history.drop_duplicates("opportunity_id", keep="last")
    return {
        str(row["opportunity_id"]): str(row.get("action", ""))
        for _, row in history.iterrows()
        if str(row.get("opportunity_id", "")).strip()
    }


def _merge_digest_rows(
    digest: pd.DataFrame,
    selection: pd.DataFrame,
    history_actions: dict[str, str],
) -> tuple[pd.DataFrame, bool]:
    out = selection.reindex(columns=SELECTION_COLUMNS, fill_value="").copy()
    if out.empty:
        known: set[str] = set()
    else:
        known = set(out["opportunity_id"].astype(str))

    changed = False
    for _, row in digest.iterrows():
        opportunity_id = str(row.get("opportunity_id", "")).strip()
        if not opportunity_id or opportunity_id in known:
            continue
        email_action = str(history_actions.get(opportunity_id, "")).strip()
        out.loc[len(out)] = {
            "selection_id": f"KSEL:{opportunity_id}",
            "opportunity_id": opportunity_id,
            "digest_sent_at": str(row.get("sent_at", "")),
            "title": str(row.get("title", "")),
            "company": str(row.get("company", "")),
            "job_url": str(row.get("job_url", "")),
            "email_action": email_action,
            "selection_action": _legacy_action(email_action),
            "selected_at": "",
            "notes": "Imported from J email digest; CV prepared manually.",
        }
        known.add(opportunity_id)
        changed = True
    return out.reindex(columns=SELECTION_COLUMNS, fill_value="").fillna(""), changed


def _load_and_sync(token: str | None) -> tuple[pd.DataFrame, str | None]:
    digest, _ = load_csv_file(token, DIGEST_PATH, DIGEST_COLUMNS)
    selection, selection_sha = load_csv_file(token, SELECTION_PATH, SELECTION_COLUMNS)
    merged, changed = _merge_digest_rows(digest, selection, _load_history_actions(token))
    if changed and token:
        save_csv_file(token, SELECTION_PATH, merged, selection_sha, "Sync J digest roles into K email selection")
        selection, selection_sha = load_csv_file(token, SELECTION_PATH, SELECTION_COLUMNS)
        return selection, selection_sha
    return merged, selection_sha


def record_email_action(opportunity_id: str, action: str) -> tuple[str, str]:
    """Store an email click as a non-binding K selection, never as Applied."""
    token = github_token()
    selection, _ = _load_and_sync(token)
    if selection.empty or opportunity_id not in set(selection["opportunity_id"].astype(str)):
        return "", "The role was not found in the archived J digest log."
    selection_sha = load_csv_file(token, SELECTION_PATH, SELECTION_COLUMNS)[1] if token else None
    mapped = {"Apply": "To be applied", "Maybe": "Maybe", "Skip": "Skip"}.get(action, "New")
    mask = selection["opportunity_id"].astype(str).eq(opportunity_id)
    selection.loc[mask, "email_action"] = action
    selection.loc[mask, "selection_action"] = mapped
    selection.loc[mask, "selected_at"] = _now()
    selection.loc[mask, "notes"] = "Selected from J email; this is not a submitted application."
    if not token:
        return mapped, "GitHub saving is not configured; the selection could not be persisted."
    save_csv_file(token, SELECTION_PATH, selection, selection_sha, "Record non-binding J email selection in K")
    return mapped, ""


def render_email_selection(token: str | None = None) -> None:
    token = token or github_token()
    selection, selection_sha = _load_and_sync(token)
    st.subheader(f"K · mezivýběr z J e-mailů ({len(selection)})")
    st.caption(
        "Všechny role, které kdy přišly v J digestu, zůstávají zde s odkazem na původní nabídku. "
        "Apply z e-mailu znamená pouze To be applied: CV připravíš ručně a skutečné podání nastane až později."
    )
    if selection.empty:
        st.info("V archivovaných J digestech zatím nejsou žádné role.")
        return

    display = selection.sort_values("digest_sent_at", ascending=False).copy()
    edited = st.data_editor(
        display,
        hide_index=True,
        width="stretch",
        height=520,
        row_height=72,
        disabled=[
            "selection_id", "opportunity_id", "digest_sent_at", "title", "company",
            "job_url", "email_action", "selected_at", "notes",
        ],
        column_config={
            "selection_id": None,
            "opportunity_id": None,
            "digest_sent_at": st.column_config.TextColumn("Digest", width="small"),
            "title": st.column_config.TextColumn("Role", width="large"),
            "company": st.column_config.TextColumn("Company", width="medium"),
            "job_url": st.column_config.LinkColumn("Původní nabídka", display_text="Otevřít", width="small"),
            "email_action": st.column_config.TextColumn("E-mail", width="small"),
            "selection_action": st.column_config.SelectboxColumn(
                "K výběr", options=ACTION_OPTIONS, required=True, width="medium"
            ),
            "selected_at": None,
            "notes": st.column_config.TextColumn("Poznámka", width="medium"),
        },
        key="k_email_selection_editor",
    )
    if not token:
        st.info("Pro uložení výběru nastav GitHub token ve Streamlit Secrets.")
        return
    changed = not edited[SELECTION_COLUMNS].reset_index(drop=True).equals(
        display[SELECTION_COLUMNS].reset_index(drop=True)
    )
    if changed:
        edited = edited.reindex(columns=SELECTION_COLUMNS, fill_value="").copy()
        old = display.set_index("opportunity_id")
        edited = edited.set_index("opportunity_id")
        for opportunity_id in edited.index:
            if opportunity_id in old.index and str(edited.at[opportunity_id, "selection_action"]) != str(old.at[opportunity_id, "selection_action"]):
                edited.at[opportunity_id, "selected_at"] = _now()
                edited.at[opportunity_id, "notes"] = "Selected in K; CV prepared manually."
        edited = edited.reset_index().reindex(columns=SELECTION_COLUMNS, fill_value="")
        try:
            save_csv_file(token, SELECTION_PATH, edited, selection_sha, "Save K email selection")
        except Exception as exc:
            st.error(f"K výběr se nepodařilo uložit: {exc}")
        else:
            st.success("K výběr uložený. CV se automaticky nevytváří.")
            st.rerun()
