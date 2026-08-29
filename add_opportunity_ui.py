from __future__ import annotations

import hashlib
import ipaddress
import json
import re
import socket
from datetime import datetime, timezone
from html import unescape
from pathlib import Path
from urllib.parse import urljoin, urlparse

import pandas as pd
import requests
import streamlit as st
from bs4 import BeautifulSoup

from github_storage import github_token, load_csv_file, save_csv_file


DATA_DIR = Path(__file__).parent / "data"
SUBMISSIONS_PATH = "data/user_submitted_opportunities.csv"
SALARY_REQUESTS_PATH = "data/salary_research_requests.csv"
RESEARCH_OVERRIDES_PATH = DATA_DIR / "user_submitted_opportunity_research.csv"
SUBMISSION_COLUMNS = [
    "submission_id", "submitted_at", "linkedin_url", "company_url", "job_url",
    "title", "company", "canonical_company_id", "company_category", "location",
    "country", "topic", "role_summary_en", "company_profile", "role_profile",
    "salary_research", "salary_range", "user_comment", "feedback", "calibration_signal",
    "targeting_scope", "review_status", "source_domain",
]
SALARY_REQUEST_COLUMNS = ["submission_id", "requested_at", "status", "completed_at", "message"]


def _normalize(value: object) -> str:
    return re.sub(r"\s+", " ", unescape(str(value or ""))).strip()


def _slug(value: str) -> str:
    result = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return result or "submitted-company"


def _public_http_url(value: str) -> str:
    parsed = urlparse(value.strip())
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("Use a complete public http(s) job link.")
    host = parsed.hostname.lower()
    if host in {"localhost", "localhost.localdomain"} or host.endswith(".local"):
        raise ValueError("Local addresses cannot be loaded.")
    try:
        addresses = {item[4][0] for item in socket.getaddrinfo(host, None)}
    except socket.gaierror as exc:
        raise ValueError("The job website could not be found.") from exc
    for address in addresses:
        if not ipaddress.ip_address(address).is_global:
            raise ValueError("Only public job websites can be loaded.")
    return parsed.geturl()


def _json_job_postings(value: object) -> list[dict]:
    if isinstance(value, list):
        return [posting for item in value for posting in _json_job_postings(item)]
    if not isinstance(value, dict):
        return []
    postings: list[dict] = []
    kind = value.get("@type")
    kinds = kind if isinstance(kind, list) else [kind]
    if any(str(item).lower() == "jobposting" for item in kinds):
        postings.append(value)
    for key in ("@graph", "mainEntity", "itemListElement"):
        postings.extend(_json_job_postings(value.get(key)))
    return postings


def _organization_name(value: object) -> str:
    return _normalize(value.get("name")) if isinstance(value, dict) else _normalize(value)


def _location_text(value: object) -> str:
    if isinstance(value, list):
        return "; ".join(dict.fromkeys(filter(None, (_location_text(x) for x in value))))
    if not isinstance(value, dict):
        return _normalize(value)
    address = value.get("address", value)
    if isinstance(address, dict):
        parts = [
            _normalize(address.get("addressLocality")),
            _normalize(address.get("addressRegion")),
            _normalize(address.get("addressCountry")),
        ]
        return ", ".join(dict.fromkeys(part for part in parts if part))
    return _normalize(address)


def _focused_description(raw: object) -> str:
    text = BeautifulSoup(str(raw or ""), "html.parser").get_text(" ", strip=True)
    text = _normalize(text)
    markers = (
        "your role", "what you will do", "what you'll do", "your impact",
        "responsibilities", "job description", "the opportunity",
    )
    lower = text.lower()
    starts = [lower.find(marker) for marker in markers if lower.find(marker) >= 0]
    if starts:
        text = text[min(starts):]
    return text[:5000]


def extract_job_page(url: str) -> dict[str, str]:
    safe_url = _public_http_url(url)
    response = None
    for _ in range(6):
        response = requests.get(
            safe_url,
            headers={"User-Agent": "Mozilla/5.0 ProfessionalDashboard/1.0"},
            timeout=20,
            allow_redirects=False,
        )
        if not response.is_redirect:
            break
        redirect = response.headers.get("location", "")
        if not redirect:
            break
        safe_url = _public_http_url(urljoin(safe_url, redirect))
    if response is None or response.is_redirect:
        raise ValueError("The job website redirected too many times.")
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")
    postings: list[dict] = []
    for script in soup.select('script[type="application/ld+json"]'):
        try:
            postings.extend(_json_job_postings(json.loads(script.get_text())))
        except (json.JSONDecodeError, TypeError):
            continue
    posting = postings[0] if postings else {}
    title = _normalize(posting.get("title"))
    if not title:
        meta = soup.select_one('meta[property="og:title"], meta[name="twitter:title"]')
        title = _normalize(meta.get("content") if meta else "")
    if not title and soup.title:
        title = _normalize(soup.title.get_text())
    company = _organization_name(posting.get("hiringOrganization"))
    location = _location_text(posting.get("jobLocation"))
    description = _focused_description(posting.get("description"))
    if not description:
        meta = soup.select_one('meta[name="description"], meta[property="og:description"]')
        description = _focused_description(meta.get("content") if meta else "")
    return {
        "job_url": response.url,
        "title": title,
        "company": company,
        "location": location,
        "description": description,
        "source_domain": urlparse(response.url).hostname or "",
    }


def infer_topic(title: str, description: str) -> str:
    text = f"{title} {description}".lower()
    rules = [
        ("Restructuring / turnaround", ("restructur", "turnaround", "distressed", "insolvenc")),
        ("Transactions / M&A / Deals", ("due diligence", "transaction", "merger", "acquisition", "deal", "m&a", "carve-out")),
        ("Corporate finance / valuation", ("corporate finance", "valuation", "financial model", "capital structure")),
        ("Treasury / financial risk / markets", ("treasury", "liquidity", "hedging", "market risk", "alm", "funding")),
        ("FP&A / controlling / performance management", ("fp&a", "controlling", "performance management", "planning and analysis")),
        ("Private equity / investments", ("private equity", "investment", "portfolio company", "asset management")),
        ("Finance-linked data and analytics", ("analytics", "data analyst", "finance data", "financial analytics")),
        ("Finance-linked strategy and transformation", ("strategy", "transformation", "cfo advisory")),
    ]
    for topic, terms in rules:
        if any(term in text for term in terms):
            return topic
    return "Other / needs review"


def _company_context(company: str, domain: str) -> tuple[str, str, str]:
    universe_path = DATA_DIR / "company_universe.csv"
    if not universe_path.exists():
        return _slug(company), company, "Unclassified"
    frames = [pd.read_csv(universe_path).fillna("").drop(columns=["company_category"], errors="ignore")]
    frames.extend(
        pd.read_csv(path).fillna("").drop(columns=["company_category"], errors="ignore")
        for path in sorted(DATA_DIR.glob("company_universe_wave*.csv"))
    )
    universe = pd.concat(frames, ignore_index=True).drop_duplicates("canonical_company_id", keep="last")
    categories_path = DATA_DIR / "company_categories.csv"
    categories = pd.read_csv(categories_path).fillna("") if categories_path.exists() else pd.DataFrame()
    overrides_path = DATA_DIR / "company_category_overrides.csv"
    if overrides_path.exists():
        overrides = pd.read_csv(overrides_path).fillna("")
        categories = pd.concat([categories, overrides], ignore_index=True).drop_duplicates("canonical_company_id", keep="last")
    if not categories.empty:
        universe = universe.merge(categories, on="canonical_company_id", how="left")
    wanted = re.sub(r"[^a-z0-9]", "", company.lower())
    for _, row in universe.iterrows():
        candidates = [row.get("company", ""), *str(row.get("aliases_entities", "")).split(";")]
        if wanted and any(re.sub(r"[^a-z0-9]", "", str(x).lower()) == wanted for x in candidates):
            return (
                str(row["canonical_company_id"]),
                str(row.get("company") or company),
                str(row.get("company_category") or "Unclassified"),
            )
    inferred = company or domain.split(".")[0].replace("jobs", "").replace("careers", "").title()
    return _slug(inferred), inferred, "Unclassified"


def _fallback_metadata(url: str) -> dict[str, str]:
    """Recover basic metadata when an ATS blocks HTML parsing."""
    host = (urlparse(url).hostname or "").lower()
    path_text = urlparse(url).path.replace("-", " ").replace("_", " ")
    haystack = f"{host} {path_text}".lower()
    company = ""
    for domain, name in {
        "partnersgroup.com": "Partners Group",
        "terrepower.com": "TERREPOWER Europe",
        "nobia.com": "Nobia Group",
    }.items():
        if domain in host:
            company = name
            break
    location = ""
    country = ""
    for city, country_name in {
        "baar": "Switzerland", "zug": "Switzerland", "zurich": "Switzerland",
        "zürich": "Switzerland", "basel": "Switzerland", "geneva": "Switzerland",
        "luxembourg": "Luxembourg", "london": "United Kingdom",
        "frankfurt": "Germany", "munich": "Germany", "münchen": "Germany",
        "aarhus": "Denmark", "copenhagen": "Denmark", "paris": "France",
    }.items():
        if city in haystack:
            location = city.title()
            country = country_name
            break
    return {"company": company, "location": location, "country": country}


def _apply_research_overrides(saved: pd.DataFrame) -> pd.DataFrame:
    if saved.empty or not RESEARCH_OVERRIDES_PATH.exists():
        return saved
    try:
        research = pd.read_csv(RESEARCH_OVERRIDES_PATH).fillna("")
    except Exception:
        return saved
    if research.empty or "submission_id" not in research.columns:
        return saved
    research = research.drop_duplicates("submission_id", keep="last").set_index("submission_id")
    out = saved.copy()
    enrichment_cols = [
        "title", "company", "canonical_company_id", "company_category", "location",
        "country", "topic", "role_summary_en", "company_profile", "role_profile",
        "salary_research", "salary_range", "targeting_scope", "review_status",
    ]
    for col in enrichment_cols:
        if col not in out.columns or col not in research.columns:
            continue
        mapped = out["submission_id"].map(research[col]).fillna("")
        out[col] = mapped.where(mapped.ne(""), out[col].fillna(""))
    return out


def _queue_salary_research(token: str, submission_id: str) -> None:
    queue, queue_sha = load_csv_file(token, SALARY_REQUESTS_PATH, SALARY_REQUEST_COLUMNS)
    now = datetime.now(timezone.utc).isoformat()
    row = {
        "submission_id": submission_id,
        "requested_at": now,
        "status": "queued",
        "completed_at": "",
        "message": "",
    }
    queue = pd.concat([queue, pd.DataFrame([row])], ignore_index=True)
    queue = queue.drop_duplicates("submission_id", keep="last")
    save_csv_file(token, SALARY_REQUESTS_PATH, queue, queue_sha, "Queue zero-cost salary research")


def render_add_opportunity() -> None:
    st.markdown('<div class="eyebrow">Workstream B</div>', unsafe_allow_html=True)
    st.title("Add Opportunity")
    st.caption(
        "Paste a role you already applied to yourself. Saving it means Applied: it enters I immediately. "
        "A zero-cost public-web salary search is queued automatically; no paid model API is used."
    )
    with st.expander("How this works"):
        st.write(
            "B is an intentional manual-application lane. A role you add here is automatically treated as Applied, "
            "so there is no second preference-rating step and it never needs to pass through J. The app stores the raw link first "
            "and parses the company job page when possible. Salary research runs separately using public web-search results only; "
            "weak evidence is explicitly flagged for ChatGPT review instead of inventing a number."
        )

    linkedin_url = st.text_input(
        "LinkedIn link (optional)",
        placeholder="https://www.linkedin.com/jobs/view/...",
    )
    company_url = st.text_input(
        "Company job page link (optional)",
        placeholder="https://company.com/careers/job/...",
    )
    comment = st.text_area(
        "Why this role is interesting to you (optional)",
        placeholder="Useful when the reason is not obvious from the job description.",
    )
    has_link = bool(linkedin_url.strip() or company_url.strip())
    if st.button("Add as Applied", type="primary", disabled=not has_link):
        token = github_token()
        if not token:
            st.error("GitHub saving is not configured for this app.")
        else:
            primary_url = company_url.strip() or linkedin_url.strip()
            draft: dict[str, str] = {
                "title": "", "company": "", "location": "", "description": "",
                "source_domain": urlparse(primary_url).hostname or "",
            }
            if company_url.strip():
                try:
                    draft.update(extract_job_page(company_url.strip()))
                except Exception:
                    pass
            # ATS pages can block requests or omit JSON-LD. Keep enough
            # location/company metadata to drive the correct salary market.
            fallback = _fallback_metadata(company_url.strip() or linkedin_url.strip())
            for key, value in fallback.items():
                if not _normalize(draft.get(key)) and value:
                    draft[key] = value
            if draft.get("company", "").strip():
                canonical_id, canonical_company, category = _company_context(
                    draft["company"].strip(), draft.get("source_domain", "")
                )
            else:
                canonical_id, canonical_company, category = "", "", ""
            now = datetime.now(timezone.utc).isoformat()
            identifier = hashlib.sha256(primary_url.encode("utf-8")).hexdigest()[:16]
            opportunities, opp_sha = load_csv_file(token, SUBMISSIONS_PATH, SUBMISSION_COLUMNS)
            row = {col: "" for col in SUBMISSION_COLUMNS}
            row.update({
                "submission_id": identifier,
                "submitted_at": now,
                "linkedin_url": linkedin_url.strip(),
                "company_url": company_url.strip(),
                "job_url": primary_url,
                "title": draft.get("title", ""),
                "company": canonical_company if canonical_company else draft.get("company", ""),
                "canonical_company_id": canonical_id,
                "company_category": category if category != "Unclassified" else "",
                "location": draft.get("location", ""),
                "country": fallback.get("country", ""),
                "role_summary_en": draft.get("description", ""),
                "user_comment": comment.strip(),
                "feedback": "Applied",
                "calibration_signal": "User-supplied positive example",
                "targeting_scope": category if category != "Unclassified" else "General",
                "review_status": "Needs enrichment",
                "source_domain": draft.get("source_domain", ""),
            })
            opportunities = pd.concat([opportunities, pd.DataFrame([row])], ignore_index=True)
            opportunities = opportunities.drop_duplicates("submission_id", keep="last")
            try:
                save_csv_file(token, SUBMISSIONS_PATH, opportunities, opp_sha, "Add Applied opportunity")
            except Exception:
                st.error("Saving failed. Refresh the page and try again.")
            else:
                try:
                    _queue_salary_research(token, identifier)
                except Exception:
                    st.warning(
                        "Opportunity was saved and sent to I, but salary research could not be queued. "
                        "Use the Research / refresh salary button below."
                    )
                else:
                    st.success("Saved as Applied and sent to I. Zero-cost salary research is queued.")

    st.divider()
    token = github_token()
    try:
        raw_saved, saved_sha = load_csv_file(token, SUBMISSIONS_PATH, SUBMISSION_COLUMNS)
    except Exception:
        raw_saved, saved_sha = pd.DataFrame(columns=SUBMISSION_COLUMNS), None
    saved = _apply_research_overrides(raw_saved)
    if saved.empty:
        st.info("No opportunities yet. Paste a link above to add your first one.")
        return

    saved = saved.sort_values("submitted_at", ascending=False).reset_index(drop=True)

    st.subheader("Salary research")
    st.caption(
        "Every new B opportunity is queued automatically. Use this button to retry or refresh the current market read. "
        "The workflow uses public web search only and has no metered/paid API fallback."
    )
    labels: dict[str, str] = {}
    for _, item in saved.iterrows():
        sid = str(item.get("submission_id", ""))
        company = _normalize(item.get("company")) or "Unknown company"
        title = _normalize(item.get("title")) or "Unknown role"
        labels[sid] = f"{company} — {title}"
    selected_salary_id = st.selectbox(
        "Opportunity",
        list(labels),
        format_func=lambda sid: labels.get(sid, sid),
        key="salary_research_submission",
    )

    try:
        salary_queue, _ = load_csv_file(token, SALARY_REQUESTS_PATH, SALARY_REQUEST_COLUMNS)
    except Exception:
        salary_queue = pd.DataFrame(columns=SALARY_REQUEST_COLUMNS)
    latest_queue = salary_queue.drop_duplicates("submission_id", keep="last").set_index("submission_id") if not salary_queue.empty else pd.DataFrame()
    if selected_salary_id and not latest_queue.empty and selected_salary_id in latest_queue.index:
        q = latest_queue.loc[selected_salary_id]
        status = _normalize(q.get("status")) or "unknown"
        message = _normalize(q.get("message"))
        st.caption(f"Last request: **{status}**" + (f" — {message}" if message else ""))

    if st.button("Research / refresh salary (free web)", disabled=not bool(token)):
        try:
            _queue_salary_research(token, selected_salary_id)
        except Exception as exc:
            st.error(f"Could not queue salary research: {type(exc).__name__}")
        else:
            st.success("Queued. The result will appear after the GitHub workflow commits it; refresh the page shortly.")

    st.divider()
    st.subheader("Your manually added opportunities")
    st.caption("Application status is Applied in B. Salary research is read-only here; only your comment remains editable.")
    # Keep the decision-critical salary fields near the left edge so they
    # remain visible before the longer ChatGPT/company/role review fields.
    display_cols = [
        "title", "company", "company_category", "review_status", "feedback",
        "salary_range", "salary_research", "company_profile", "role_profile", "user_comment", "job_url",
    ]
    # Use presentation-only column names here.  In some Streamlit versions the
    # first column named "title" can render without its header in data_editor,
    # which makes the B table look shifted even though the data is correct.
    display_labels = {
        "title": "Role",
        "company": "Company",
        "company_category": "Category",
        "review_status": "Status",
        "feedback": "Intent",
        "salary_range": "Salary range",
        "salary_research": "Salary research / expectation",
        "company_profile": "ChatGPT company review",
        "role_profile": "ChatGPT role review",
        "user_comment": "Your comment",
        "job_url": "Link",
    }
    editor = (
        saved.set_index("submission_id")[display_cols]
        .rename(columns=display_labels)
    )
    with st.form("manual_opportunity_comments_form"):
        edited = st.data_editor(
            editor,
            hide_index=True,
            width="stretch",
            height=560,
            disabled=[c for c in editor.columns if c != "Your comment"],
            column_config={
                "Role": st.column_config.TextColumn("Role", width="medium"),
                "Company": st.column_config.TextColumn("Company", width="small"),
                "Category": st.column_config.TextColumn("Category", width="small"),
                "Status": st.column_config.TextColumn("Status", width="small"),
                "Intent": st.column_config.TextColumn("Intent", width="small"),
                "Salary range": st.column_config.TextColumn("Salary range", width="medium"),
                "Salary research / expectation": st.column_config.TextColumn("Salary research / expectation", width="medium"),
                "ChatGPT company review": st.column_config.TextColumn("ChatGPT company review", width="large"),
                "ChatGPT role review": st.column_config.TextColumn("ChatGPT role review", width="large"),
                "Your comment": st.column_config.TextColumn("Your comment", width="medium"),
                "Link": st.column_config.LinkColumn("Link", display_text="Open", width="small"),
            },
            key="submitted_opportunity_editor",
        )
        save_comments = st.form_submit_button("Save comments")
    if save_comments:
        if not token:
            st.error("GitHub saving is not configured for this app.")
        else:
            updated = raw_saved.set_index("submission_id")
            shared = updated.index.intersection(edited.index)
            updated.loc[shared, "user_comment"] = edited.loc[shared, "Your comment"]
            updated.loc[shared, "feedback"] = "Applied"
            updated.loc[shared, "calibration_signal"] = "User-supplied positive example"
            try:
                save_csv_file(
                    token, SUBMISSIONS_PATH, updated.reset_index(), saved_sha,
                    "Update manual opportunity comments",
                )
            except Exception:
                st.error("Saving failed. Refresh the page and try again.")
            else:
                st.success("Comments saved.")
