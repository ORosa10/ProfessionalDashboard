from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import pandas as pd
import streamlit as st

from github_storage import (
    github_token,
    load_csv_file,
    load_file_bytes,
    save_csv_file,
    save_file_bytes,
)

from k_email_selection_ui import render_email_selection


LIBRARY_URL = "https://chatgpt.com/library"
K_REQUEST_PATH = "data/k_requests.csv"
K_PACKAGE_PATH = "data/k_review_packages.csv"
K_LEGACY_REGISTRY_PATH = "data/k_output_registry.csv"
HISTORY_PATH = "data/opportunity_history.csv"
K_REVIEW_SETTINGS_PATH = "data/k_review_settings.csv"
K_REVIEW_MESSAGES_PATH = "data/k_review_messages.csv"
K_REVIEW_ATTACHMENTS_PATH = "data/k_review_attachments.csv"

K_REQUEST_COLUMNS = [
    "request_id", "opportunity_id", "requested_at", "title", "company", "market",
    "location", "job_url", "description", "description_en", "semantic_fit",
    "semantic_reasoning", "status", "output_path", "error",
]
PACKAGE_COLUMNS = [
    "package_id", "opportunity_id", "title", "company", "market", "location",
    "job_url", "version", "status", "cv_pdf_url", "cv_docx_url",
    "cover_letter_url", "updated_at", "notes",
]
LEGACY_REGISTRY_COLUMNS = [
    "opportunity_id", "request_id", "title", "company", "market", "location",
    "job_url", "version", "status", "output_path", "created_at", "source",
]
SETTINGS_COLUMNS = ["updated_at", "global_instructions"]
MESSAGE_COLUMNS = [
    "message_id", "package_id", "version", "submitted_at", "author",
    "message_type", "status", "body",
]
ATTACHMENT_COLUMNS = [
    "attachment_id", "message_id", "package_id", "uploaded_at", "filename",
    "repository_path", "mime_type", "size_bytes",
]
HISTORY_COLUMNS = [
    "opportunity_id", "source_stream", "source_id", "first_seen_at", "decision_at",
    "title", "company", "canonical_company_id", "company_category", "market", "location",
    "job_url", "action", "company_feedback", "role_feedback", "user_comment",
    "company_rating_at_decision", "semantic_fit_at_decision", "semantic_reasoning_at_decision",
    "calibration_score_at_decision", "application_stage", "stage_updated_at",
    "outcome_reason", "history_notes",
]
MAX_IMAGE_BYTES = 8 * 1024 * 1024
MAX_IMAGES_PER_MESSAGE = 6
IMAGE_TYPES = ["png", "jpg", "jpeg", "webp"]

DEFAULT_GLOBAL_INSTRUCTIONS = """K CV generation rules:

- Use MASTER(3) as the sole starting document. Other CV variants are reference material only for verified formulations, projects, metrics and emphasis.
- Preserve the Master CV visual system 1:1: black-and-white Times New Roman, top header treatment, right-aligned location/dates, original hierarchy, spacing, bullet style, density and two-page structure. Do not invent a new modern template or redesign.
- Tailor content to the role, but do not invent experience, metrics or responsibilities.
- The approximately six-month PwC secondment at an energy-sector company is a verified experience. It covered treasury and accounting-related projects, including FX management, liquidity planning and commodity-risk hedging. Use it selectively where relevant and present it as a distinct Selected Project Experience item when the format calls for project experience.
- Preserve the substance of the PwC work: FX, interest-rate and commodity exposures, derivatives valuation, IFRS 9 hedge accounting, cash/liquidity forecasting, working capital and quantitative modelling.
- Treat every user review message and attached screenshot as authoritative feedback for the named version. Keep the whole review history, explain what was changed, and return the next draft to this same K Review thread.
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _text(value: object) -> str:
    return str(value or "").strip()


def _safe_filename(name: str) -> str:
    original = Path(name).name
    suffix = Path(original).suffix.lower()
    stem = re.sub(r"[^A-Za-z0-9_-]+", "_", Path(original).stem).strip("._")
    return f"{stem[:120]}{suffix}" if stem else "screenshot.png"


def _package_id(row: pd.Series, index: int) -> str:
    return (
        _text(row.get("package_id"))
        or _text(row.get("request_id"))
        or _text(row.get("opportunity_id"))
        or f"package-{index}"
    )


def _load_table(token: str | None, path: str, columns: list[str]) -> tuple[pd.DataFrame, str | None]:
    try:
        frame, sha = load_csv_file(token, path, columns)
        return frame.reindex(columns=columns, fill_value="").fillna(""), sha
    except Exception:
        return pd.DataFrame(columns=columns), None




def _mark_package_in_i(
    token: str,
    row: pd.Series,
    history: pd.DataFrame,
    history_sha: str | None,
) -> None:
    """Record a role as actually applied from K without touching K ordering."""
    opportunity_id = _display_value(row, "opportunity_id", "package_id")
    if not opportunity_id:
        raise ValueError("Role nemá opportunity ID, takže ji nelze zapsat do I.")

    now = _now()
    updated = history.reindex(columns=HISTORY_COLUMNS, fill_value="").fillna("").copy()
    existing = updated["opportunity_id"].astype(str).eq(opportunity_id)

    if existing.any():
        index = updated.index[existing][-1]
        updated.loc[index, "action"] = "Apply"
        updated.loc[index, "application_stage"] = "Applied"
        updated.loc[index, "stage_updated_at"] = now
        if not _text(updated.loc[index, "decision_at"]):
            updated.loc[index, "decision_at"] = now
        if not _text(updated.loc[index, "source_stream"]):
            updated.loc[index, "source_stream"] = "G"
        if not _text(updated.loc[index, "source_id"]):
            updated.loc[index, "source_id"] = "k-review"
        for column, names in {
            "title": ("title",),
            "company": ("company",),
            "market": ("market",),
            "location": ("location",),
            "job_url": ("job_url",),
        }.items():
            value = _display_value(row, *names)
            if value and not _text(updated.loc[index, column]):
                updated.loc[index, column] = value
    else:
        updated = pd.concat([
            updated,
            pd.DataFrame([{
                "opportunity_id": opportunity_id,
                "source_stream": "G",
                "source_id": "k-review",
                "first_seen_at": _display_value(row, "updated_at") or now,
                "decision_at": now,
                "title": _text(row.get("title")),
                "company": _text(row.get("company")),
                "canonical_company_id": "",
                "company_category": "",
                "market": _text(row.get("market")),
                "location": _text(row.get("location")),
                "job_url": _text(row.get("job_url")),
                "action": "Apply",
                "company_feedback": "Not rated",
                "role_feedback": "Not rated",
                "user_comment": "",
                "company_rating_at_decision": "",
                "semantic_fit_at_decision": "",
                "semantic_reasoning_at_decision": "",
                "calibration_score_at_decision": "",
                "application_stage": "Applied",
                "stage_updated_at": now,
                "outcome_reason": "",
                "history_notes": "Marked from K after manual CV preparation and application.",
            }], columns=HISTORY_COLUMNS),
        ], ignore_index=True)

    save_csv_file(token, HISTORY_PATH, updated, history_sha, "Mark K role as applied in I")


def _render_i_action(
    token: str | None,
    row: pd.Series,
    history: pd.DataFrame,
    history_sha: str | None,
) -> None:
    """Render the K -> I hand-off while leaving the K list untouched."""
    package_id = _display_value(row, "package_id", "opportunity_id")
    applied = pd.Series(False, index=history.index)
    if not history.empty and "opportunity_id" in history.columns:
        applied = history["opportunity_id"].astype(str).eq(package_id)
        if "application_stage" in history.columns:
            applied &= history["application_stage"].astype(str).eq("Applied")
        else:
            applied &= False
    if bool(applied.any()):
        st.button(
            "✓ Už je v I",
            disabled=True,
            use_container_width=True,
            key=f"k_to_i_done_{_safe_filename(package_id)}",
        )
        return

    if st.button(
        "Přidat do I · Applied",
        type="secondary",
        use_container_width=True,
        disabled=not token,
        key=f"k_to_i_{_safe_filename(package_id)}",
        help="Použij po skutečném podání přihlášky. Role se zapíše do I jako Applied.",
    ):
        try:
            _mark_package_in_i(token, row, history, history_sha)
        except Exception as exc:
            st.error(f"Role se nepodařilo přidat do I: {exc}")
        else:
            st.success("Role byla přidána do I jako Applied.")
            st.rerun()

def _display_value(row: pd.Series, *names: str) -> str:
    for name in names:
        value = _text(row.get(name))
        if value:
            return value
    return ""


def _legacy_registry_view(legacy: pd.DataFrame) -> pd.DataFrame:
    """Adapt the pre-review output registry so existing KNDS packages remain visible."""
    if legacy.empty:
        return pd.DataFrame(columns=PACKAGE_COLUMNS)
    rows: list[dict[str, str]] = []
    for _, source in legacy.iterrows():
        links = _output_links(source.get("output_path"))
        package_id = _text(source.get("opportunity_id")) or _text(source.get("request_id"))
        rows.append({
            "package_id": package_id,
            "opportunity_id": _text(source.get("opportunity_id")),
            "title": _text(source.get("title")),
            "company": _text(source.get("company")),
            "market": _text(source.get("market")),
            "location": _text(source.get("location")),
            "job_url": _text(source.get("job_url")),
            "version": _text(source.get("version")),
            "status": _text(source.get("status")),
            "cv_pdf_url": links.get("pdf", ""),
            "cv_docx_url": links.get("docx", ""),
            "cover_letter_url": links.get("cover letter", ""),
            "updated_at": _text(source.get("created_at")),
            "notes": "legacy output registry",
        })
    view = pd.DataFrame(rows).reindex(columns=PACKAGE_COLUMNS, fill_value="").fillna("")
    view["_version_num"] = pd.to_numeric(view["version"], errors="coerce").fillna(0)
    view = view.sort_values(["package_id", "_version_num"], ascending=[True, False])
    return view.drop_duplicates("package_id", keep="first").drop(columns=["_version_num"])


def _output_links(output_path: object) -> dict[str, str]:
    output = _text(output_path)
    links: dict[str, str] = {}
    for label, key in (("PDF", "pdf"), ("DOCX", "docx"), ("Cover letter", "cover letter")):
        match = re.search(rf"{re.escape(label)}:\s*(https?://[^;]+)", output, flags=re.IGNORECASE)
        if match:
            links[key] = match.group(1).strip()
    return links


def _document_url(url: str) -> str:
    """Avoid blocked cross-site Library download endpoints from Streamlit."""
    lowered = url.lower()
    if "chatgpt.com/api/library" in lowered or "/download" in lowered:
        return LIBRARY_URL
    return url


def _render_document_links(row: pd.Series) -> None:
    links = [
        ("Pracovní nabídka", _display_value(row, "job_url")),
        ("CV · PDF", _document_url(_display_value(row, "cv_pdf_url", "pdf_url", "cv_url"))),
        ("CV · DOCX", _document_url(_display_value(row, "cv_docx_url", "docx_url"))),
        ("Cover letter", _document_url(_display_value(row, "cover_letter_url", "cover_url"))),
    ]
    cols = st.columns(4, gap="small")
    for col, (label, url) in zip(cols, links):
        with col:
            if url.startswith(("https://", "http://")):
                col.link_button(label, url, use_container_width=True)
            else:
                st.button(label, disabled=True, use_container_width=True, key=f"missing_{_safe_filename(label)}_{_safe_filename(_text(row.get('package_id')))}")
    if not any(url.startswith(("https://", "http://")) for _, url in links):
        output = _text(row.get("output_path"))
        if output:
            st.caption(f"K output: {output}")
        st.caption("Dokumentové odkazy se zobrazí, jakmile je K zapíše do registru.")


def _render_attachment(token: str | None, attachment: pd.Series) -> None:
    path = _text(attachment.get("repository_path"))
    if not path:
        return
    try:
        content, _ = load_file_bytes(token, path)
        if content:
            st.image(content, caption=_text(attachment.get("filename")), width="stretch")
        else:
            st.caption(f"Příloha není dostupná: {_text(attachment.get('filename'))}")
    except Exception as exc:
        st.caption(f"Přílohu se nepodařilo načíst: {exc}")


def _save_user_review(
    token: str,
    package_id: str,
    version: str,
    body: str,
    uploads: list,
    messages: pd.DataFrame,
    messages_sha: str | None,
    attachments: pd.DataFrame,
    attachments_sha: str | None,
    requests: pd.DataFrame,
    requests_sha: str | None,
    packages: pd.DataFrame,
    packages_sha: str | None,
    legacy: pd.DataFrame,
    legacy_sha: str | None,
) -> tuple[pd.DataFrame, str | None, pd.DataFrame, str | None, str | None]:
    message_id = f"KR-{uuid4().hex[:12]}"
    submitted_at = _now()
    new_attachments: list[dict[str, str]] = []
    for upload in uploads:
        raw = upload.getvalue()
        if len(raw) > MAX_IMAGE_BYTES:
            raise ValueError(f"{upload.name} je větší než 8 MB.")
        attachment_id = f"ATT-{uuid4().hex[:12]}"
        safe_name = _safe_filename(upload.name)
        repo_path = f"data/k_review_attachments/{_safe_filename(package_id)}/{message_id}_{safe_name}"
        save_file_bytes(token, repo_path, raw, None, f"Add K review screenshot for {package_id}")
        new_attachments.append({
            "attachment_id": attachment_id,
            "message_id": message_id,
            "package_id": package_id,
            "uploaded_at": submitted_at,
            "filename": safe_name,
            "repository_path": repo_path,
            "mime_type": _text(upload.type) or "image/png",
            "size_bytes": str(len(raw)),
        })

    new_message = pd.DataFrame([{
        "message_id": message_id,
        "package_id": package_id,
        "version": version,
        "submitted_at": submitted_at,
        "author": "user",
        "message_type": "review_feedback",
        "status": "Revision requested",
        "body": body,
    }], columns=MESSAGE_COLUMNS)
    updated_messages = pd.concat([messages, new_message], ignore_index=True)
    save_csv_file(token, K_REVIEW_MESSAGES_PATH, updated_messages, messages_sha, "Add K CV review feedback")

    updated_attachments = attachments.copy()
    if new_attachments:
        updated_attachments = pd.concat([updated_attachments, pd.DataFrame(new_attachments)], ignore_index=True)
        save_csv_file(token, K_REVIEW_ATTACHMENTS_PATH, updated_attachments, attachments_sha, "Add K CV review screenshots")

    updated_requests = requests.copy()
    match = (
        updated_requests.get("request_id", pd.Series(dtype=str)).astype(str).eq(package_id)
        | updated_requests.get("opportunity_id", pd.Series(dtype=str)).astype(str).eq(package_id)
    )
    if match.any() and "status" in updated_requests.columns:
        updated_requests.loc[match, "status"] = "Revision requested"
        updated_requests.loc[match, "error"] = ""
        save_csv_file(token, K_REQUEST_PATH, updated_requests, requests_sha, "Mark K CV revision requested")

    updated_packages = packages.copy()
    package_match = (
        updated_packages.get("package_id", pd.Series(dtype=str)).astype(str).eq(package_id)
        | updated_packages.get("opportunity_id", pd.Series(dtype=str)).astype(str).eq(package_id)
    )
    if package_match.any() and "status" in updated_packages.columns:
        updated_packages.loc[package_match, "status"] = "Revision requested"
        updated_packages.loc[package_match, "updated_at"] = submitted_at
        save_csv_file(token, K_PACKAGE_PATH, updated_packages, packages_sha, "Mark K package revision requested")

    if not legacy.empty and legacy_sha:
        updated_legacy = legacy.copy()
        legacy_match = (
            updated_legacy["opportunity_id"].astype(str).eq(package_id)
            | updated_legacy["request_id"].astype(str).eq(package_id)
        )
        if legacy_match.any():
            updated_legacy.loc[legacy_match, "status"] = "Revision requested"
            save_csv_file(token, K_LEGACY_REGISTRY_PATH, updated_legacy, legacy_sha, "Mark legacy K CV revision requested")

    return updated_messages, None, updated_attachments, None, message_id


def _render_thread(
    token: str | None,
    package_id: str,
    version: str,
    messages: pd.DataFrame,
    attachments: pd.DataFrame,
    requests: pd.DataFrame,
    requests_sha: str | None,
    packages: pd.DataFrame,
    packages_sha: str | None,
    messages_sha: str | None,
    attachments_sha: str | None,
    legacy: pd.DataFrame,
    legacy_sha: str | None,
) -> None:
    package_messages = messages[messages["package_id"].astype(str).eq(package_id)].sort_values("submitted_at")
    package_attachments = attachments[attachments["package_id"].astype(str).eq(package_id)]
    if package_messages.empty:
        st.caption("Zatím žádný feedback ani AI odpověď.")
    for _, message in package_messages.iterrows():
        author = _text(message.get("author"))
        with st.chat_message("assistant" if author == "ai" else "user"):
            label = "AI / K" if author == "ai" else "Ty"
            st.caption(f"{label} · {_text(message.get('submitted_at'))} · {_text(message.get('status'))}")
            st.markdown(_text(message.get("body")))
            for _, attachment in package_attachments[
                package_attachments["message_id"].astype(str).eq(_text(message.get("message_id")))
            ].iterrows():
                _render_attachment(token, attachment)

    st.markdown("**Nový feedback k této verzi**")
    st.caption("Toto pole je záměrně prázdné. Obecné instrukce jsou nahoře; sem patří jen připomínky k této konkrétní verzi.")
    feedback = st.text_area(
        "Feedback",
        key=f"k_review_feedback_{_safe_filename(package_id)}_{_safe_filename(version)}",
        placeholder="Např. tento bullet přesuň, zkrať druhou stranu, zachovej přesný wording...",
        label_visibility="collapsed",
    )
    disabled = not token or not feedback.strip()
    if st.button(
        "Uložit feedback a požádat o revizi",
        type="primary",
        key=f"k_review_submit_{_safe_filename(package_id)}_{_safe_filename(version)}",
        disabled=disabled,
    ):
        if not token:
            st.error("Pro uložení feedbacku musí být nastavený GitHub token ve Streamlit Secrets.")
            return
        try:
            _save_user_review(
                token,
                package_id,
                version,
                feedback.strip(),
                [],
                messages,
                messages_sha,
                attachments,
                attachments_sha,
                requests,
                requests_sha,
                packages,
                packages_sha,
                legacy,
                legacy_sha,
            )
        except Exception as exc:
            st.error(f"Feedback se nepodařilo uložit: {exc}")
        else:
            st.success("Feedback je uložený. K je nyní označené jako Revision requested.")
            st.rerun()


def render_k_review() -> None:
    st.title("K · CV Review")
    st.caption("Jedno místo pro prohlížení CV a samostatnou konverzaci s K u každé pozice.")
    token = github_token()
    if not token:
        st.warning("GitHub saving není nastavené. Dokumenty můžeš číst, ale feedback a screenshoty se bez tokenu neuloží.")

    settings, settings_sha = _load_table(token, K_REVIEW_SETTINGS_PATH, SETTINGS_COLUMNS)
    current_context = _text(settings.iloc[-1]["global_instructions"]) if not settings.empty else DEFAULT_GLOBAL_INSTRUCTIONS
    st.subheader("Globální kontext pro všechny K výstupy")
    st.caption("Toto je trvalé nastavení. Není to feedback k jedné pozici a nezobrazuje se v prázdném feedback poli níže.")
    global_context = st.text_area("Globální instrukce", value=current_context, height=260, key="k_global_context")
    if st.button("Uložit globální kontext", type="secondary", disabled=not token, key="k_global_context_save"):
        updated = pd.DataFrame([{"updated_at": _now(), "global_instructions": global_context.strip()}], columns=SETTINGS_COLUMNS)
        try:
            save_csv_file(token, K_REVIEW_SETTINGS_PATH, updated, settings_sha, "Update global K CV context")
        except Exception as exc:
            st.error(f"Globální kontext se nepodařilo uložit: {exc}")
        else:
            st.success("Globální K kontext uložen.")
            st.rerun()

    st.divider()
    render_email_selection(token)
    st.divider()
    requests, requests_sha = _load_table(token, K_REQUEST_PATH, K_REQUEST_COLUMNS)
    packages, packages_sha = _load_table(token, K_PACKAGE_PATH, PACKAGE_COLUMNS)
    legacy, legacy_sha = _load_table(token, K_LEGACY_REGISTRY_PATH, LEGACY_REGISTRY_COLUMNS)
    history, history_sha = _load_table(token, HISTORY_PATH, HISTORY_COLUMNS)
    messages, messages_sha = _load_table(token, K_REVIEW_MESSAGES_PATH, MESSAGE_COLUMNS)
    attachments, attachments_sha = _load_table(token, K_REVIEW_ATTACHMENTS_PATH, ATTACHMENT_COLUMNS)
    if requests.empty and packages.empty and legacy.empty:
        st.info("V K zatím není žádný balíček připravený k review.")
        return

    request_view = requests.copy()
    request_view = request_view[~request_view["status"].astype(str).str.startswith("Cancelled", na=False)].copy()
    request_view["package_id"] = request_view["opportunity_id"].where(
        request_view["opportunity_id"].astype(str).str.strip().ne(""),
        request_view["request_id"],
    )
    for column in PACKAGE_COLUMNS:
        if column not in request_view.columns:
            request_view[column] = ""
    for index, request in request_view.iterrows():
        links = _output_links(request.get("output_path"))
        request_view.at[index, "cv_pdf_url"] = request_view.at[index, "cv_pdf_url"] or links.get("pdf", "")
        request_view.at[index, "cv_docx_url"] = request_view.at[index, "cv_docx_url"] or links.get("docx", "")
        request_view.at[index, "cover_letter_url"] = request_view.at[index, "cover_letter_url"] or links.get("cover letter", "")
    request_view = request_view[PACKAGE_COLUMNS]
    package_view = packages.reindex(columns=PACKAGE_COLUMNS, fill_value="").copy()
    legacy_view = _legacy_registry_view(legacy)
    visible = pd.concat([package_view, legacy_view, request_view], ignore_index=True).fillna("")
    visible = visible.drop_duplicates("package_id", keep="first")
    visible = visible[visible.apply(lambda row: _package_id(row, row.name) != "", axis=1)]
    st.subheader(f"Balíčky k review ({len(visible)})")
    for index, row in visible.iterrows():
        package_id = _text(row.get("package_id")) or _package_id(row, int(index))
        version = _display_value(row, "version", "cv_version") or "current"
        title = _text(row.get("title")) or "Untitled role"
        company = _text(row.get("company")) or "Unknown company"
        status = _text(row.get("status")) or "Unknown status"
        with st.container(border=True):
            st.markdown(f"### {company} — {title}")
            st.caption(f"{_display_value(row, 'location', 'market')} · {status} · version {version}")
            _render_document_links(row)
            _render_i_action(token, row, history, history_sha)
            _render_thread(
                token, package_id, version, messages, attachments, requests,
                requests_sha, packages, packages_sha, messages_sha, attachments_sha,
                legacy, legacy_sha,
            )
