from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import streamlit as st

from github_storage import github_token, load_csv_file, save_csv_file

DATA_DIR = Path(__file__).parent / "data"
K_REQUEST_PATH = "data/k_requests.csv"
K_REGISTRY_PATH = "data/k_output_registry.csv"
K_FEEDBACK_PATH = "data/k_review_feedback.csv"

K_COLUMNS = [
    "request_id", "opportunity_id", "requested_at", "title", "company",
    "market", "location", "job_url", "description", "description_en",
    "semantic_fit", "semantic_reasoning", "status", "output_path", "error",
]
JOB_URL_OVERRIDES = {
    "stepstone-de_14317130": "https://www.stepstone.de/stellenangebote--Specialist-m-w-d-Financial-Risk-Management-Muenchen-KNDS--14317130-inline.html",
}
LIBRARY_URL = "https://chatgpt.com/library"

REGISTRY_COLUMNS = [
    "opportunity_id", "request_id", "title", "company", "market", "location", "job_url",
    "version", "status", "output_path", "created_at", "source",
]
FEEDBACK_COLUMNS = [
    "feedback_id", "opportunity_id", "request_id", "submitted_at",
    "target_version", "feedback", "status",
]


def _load(path: str, columns: list[str]) -> tuple[pd.DataFrame, str | None]:
    try:
        frame, sha = load_csv_file(github_token(), path, columns)
        return frame.reindex(columns=columns, fill_value="").fillna(""), sha
    except Exception:
        return pd.DataFrame(columns=columns), None


def _links(output_path: object) -> dict[str, str]:
    text = str(output_path or "")
    found: dict[str, str] = {}
    for label, url in re.findall(r"(PDF|DOCX|Cover letter):\s*(https?://[^;\s]+)", text, flags=re.I):
        key = label.lower().replace(" ", "_")
        found[key] = url
    return found


def _records(requests: pd.DataFrame, registry: pd.DataFrame) -> pd.DataFrame:
    rows: dict[str, dict[str, str]] = {}
    for _, row in registry.iterrows():
        oid = str(row.get("opportunity_id", "")).strip()
        if oid:
            rows[oid] = {col: str(row.get(col, "") or "") for col in REGISTRY_COLUMNS}
    for _, row in requests.iterrows():
        oid = str(row.get("opportunity_id", "")).strip()
        if not oid:
            continue
        current = rows.setdefault(oid, {col: "" for col in REGISTRY_COLUMNS})
        for col in ["request_id", "title", "company", "market", "location", "job_url", "status", "output_path"]:
            value = str(row.get(col, "") or "")
            if value or not current.get(col):
                current[col] = value
        current["opportunity_id"] = oid
        current["source"] = current.get("source") or "K queue"
        current["version"] = current.get("version") or ("1" if current.get("output_path") else "")
    return pd.DataFrame(list(rows.values())).reindex(columns=REGISTRY_COLUMNS, fill_value="").fillna("")


def _save_feedback(record: dict[str, str]) -> str | None:
    token = github_token()
    if not token:
        return "GitHub saving is not configured for this app."
    feedback, sha = _load(K_FEEDBACK_PATH, FEEDBACK_COLUMNS)
    new_row = pd.DataFrame([record]).reindex(columns=FEEDBACK_COLUMNS, fill_value="")
    combined = pd.concat([feedback, new_row], ignore_index=True)
    try:
        save_csv_file(token, K_FEEDBACK_PATH, combined, sha, "Store K CV review feedback")
    except Exception as exc:
        return str(exc)
    return None


def render_k_review() -> None:
    st.markdown('<div class="eyebrow">Workstream K</div>', unsafe_allow_html=True)
    st.title("K · CV Review")
    st.caption(
        "Otevři PDF preview, zkontroluj DOCX a cover letter, napiš připomínky a požádej o novou verzi. "
        "Původní verze zůstává zachovaná."
    )

    requests, _ = _load(K_REQUEST_PATH, K_COLUMNS)
    registry, _ = _load(K_REGISTRY_PATH, REGISTRY_COLUMNS)
    records = _records(requests, registry)
    feedback, _ = _load(K_FEEDBACK_PATH, FEEDBACK_COLUMNS)

    if records.empty:
        st.info("Zatím není k dispozici žádný K balíček. Apply role se zde objeví po dokončení K.")
        return

    global_feedback = ""
    if not feedback.empty:
        global_rows = feedback[
            feedback["opportunity_id"].astype(str).eq("__global__")
        ].sort_values("submitted_at")
        if not global_rows.empty:
            global_feedback = str(global_rows.iloc[-1].get("feedback", "") or "")
        feedback = feedback[
            ~feedback["opportunity_id"].astype(str).eq("__global__")
        ]
        if not feedback.empty:
            feedback = feedback.sort_values("submitted_at").drop_duplicates(
                "opportunity_id", keep="last"
            )
            feedback = feedback.set_index("opportunity_id")

    with st.container(border=True):
        st.subheader("Obecné nastavení pro všechny budoucí K výstupy")
        st.caption(
            "Tento feedback není jen pro jednu pozici. K ho použije jako trvalé obecné "
            "instrukce při tvorbě všech dalších CV a cover letterů; konkrétní připomínky "
            "k jedné roli zůstávají níže u jejího balíčku."
        )
        with st.form("k_global_feedback_form"):
            global_comment = st.text_area(
                "Globální instrukce pro AI",
                value=global_feedback,
                height=150,
                placeholder=(
                    "Např. zachovej starší černobílý serifový master layout, "
                    "nepřidávej modrý header ani Selected Relevance, "
                    "na první stránce ponech Profile a Work Experience…"
                ),
            )
            save_global = st.form_submit_button(
                "Uložit obecné nastavení pro všechny K výstupy", type="primary"
            )
        if save_global:
            text = global_comment.strip()
            if not text:
                st.warning("Globální instrukce jsou prázdné; nic se neuložilo.")
            else:
                now = datetime.now(timezone.utc).isoformat()
                record = {
                    "feedback_id": f"KREV:GLOBAL:{now}",
                    "opportunity_id": "__global__",
                    "request_id": "K:GLOBAL",
                    "submitted_at": now,
                    "target_version": "GLOBAL",
                    "feedback": text,
                    "status": "Global instruction",
                }
                error = _save_feedback(record)
                if error:
                    st.error(f"Obecné nastavení se nepodařilo uložit: {error}")
                else:
                    st.success("Obecné nastavení je uložené pro všechny další K výstupy.")
                    st.rerun()

    ready = int(records["output_path"].astype(str).str.len().gt(0).sum())
    pending = int(records["status"].astype(str).str.contains("Pending|requested|progress", case=False, na=False).sum())
    revisions = int(
        feedback["status"].astype(str).eq("Revision requested").sum()
    ) if not feedback.empty else 0
    m1, m2, m3 = st.columns(3)
    m1.metric("CV balíčky", len(records))
    m2.metric("Ready / preview", ready)
    m3.metric("Čeká nebo se přepracovává", pending + revisions)

    for _, row in records.sort_values(["status", "company", "title"]).iterrows():
        oid = str(row.get("opportunity_id", "")).strip()
        title = str(row.get("title", "")).strip() or oid
        company = str(row.get("company", "")).strip()
        status = str(row.get("status", "")).strip() or "Unknown"
        links = _links(row.get("output_path", ""))
        job_url = str(row.get("job_url", "") or "").strip() or JOB_URL_OVERRIDES.get(oid, "")
        old_feedback = ""
        old_status = ""
        old_version = "1"
        if not feedback.empty and oid in feedback.index:
            old = feedback.loc[oid]
            old_feedback = str(old.get("feedback", "") or "")
            old_status = str(old.get("status", "") or "")
            old_version = str(old.get("target_version", "") or "1")

        with st.container(border=True):
            st.subheader(f"{company} — {title}")
            st.caption(
                f"{row.get('market', '')} · {row.get('location', '')} · "
                f"stav K: {status} · verze {row.get('version', '') or old_version}"
            )
            if links or job_url:
                b1, b2, b3, b4 = st.columns(4)
                if job_url:
                    b1.link_button("Otevřít pracovní nabídku", job_url, use_container_width=True)
                else:
                    b1.caption("Pracovní nabídka: odkaz chybí")
                if links.get("pdf"):
                    b2.link_button("Otevřít CV (PDF) v Library", LIBRARY_URL, use_container_width=True)
                else:
                    b2.caption("CV (PDF): čeká")
                if links.get("docx"):
                    b3.link_button("Otevřít CV (DOCX) v Library", LIBRARY_URL, use_container_width=True)
                else:
                    b3.caption("CV (DOCX): čeká")
                if links.get("cover_letter"):
                    b4.link_button("Otevřít Cover letter v Library", LIBRARY_URL, use_container_width=True)
                else:
                    b4.caption("Cover letter: čeká")
                st.caption(
                    "Pracovní odkaz vede přímo na pozici. Tři dokumentová tlačítka otevírají Library; "
                    "tam vyhledej soubor podle firmy a role."
                )
            else:
                st.info("K request je ve frontě; preview se objeví po dokončení generování.")

            if old_status:
                st.caption(f"Poslední review: {old_status} · cílová verze {old_version}")
            with st.form(f"k_review_form_{oid}"):
                comment = st.text_area(
                    "Feedback k této konkrétní pozici / verzi",
                    value=old_feedback,
                    height=130,
                    placeholder=(
                        "Např. zachovej dvoustránkový layout, zvýrazni FX hedging, "
                        "zkrátit profil, nepřidávej nic co není v master CV…"
                    ),
                )
                submit = st.form_submit_button("Uložit feedback a požádat o přepracování", type="primary")
            if submit:
                now = datetime.now(timezone.utc).isoformat()
                record = {
                    "feedback_id": f"KREV:{oid}:{now}",
                    "opportunity_id": oid,
                    "request_id": str(row.get("request_id", "") or f"K:{oid}"),
                    "submitted_at": now,
                    "target_version": str(row.get("version", "") or "1"),
                    "feedback": comment.strip(),
                    "status": "Revision requested",
                }
                error = _save_feedback(record)
                if error:
                    st.error(f"Feedback se nepodařilo uložit: {error}")
                else:
                    st.success("Feedback je uložený. K vytvoří novou verzi a ponechá původní.")
                    st.rerun()

    st.divider()
    st.caption(
        "Globální instrukce platí pro všechny další K výstupy; tento formulář ovlivňuje jen konkrétní balíček. C/J rating se tím zpětně nemění. "
        "Žádost zaměstnavateli se z dashboardu automaticky neodesílá."
    )
