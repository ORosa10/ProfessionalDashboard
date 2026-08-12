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
COMPANIES_PATH = "data/user_submitted_companies.csv"
SUBMISSION_COLUMNS = [
    "submission_id", "submitted_at", "job_url", "title", "company",
    "canonical_company_id", "company_category", "location", "country",
    "topic", "role_summary_en", "user_comment", "feedback",
    "calibration_signal", "targeting_scope", "review_status", "source_domain",
]
COMPANY_COLUMNS = [
    "canonical_company_id", "company", "company_category", "source_domain",
    "first_submitted_at", "latest_job_url", "review_status",
]
TOPICS = [
    "Transactions / M&A / Deals",
    "Corporate finance / valuation",
    "Restructuring / turnaround",
    "Treasury / financial risk / markets",
    "FP&A / controlling / performance management",
    "Finance-linked strategy and transformation",
    "Finance-linked data and analytics",
    "Private equity / investments",
    "Other / needs review",
]


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
        ip = ipaddress.ip_address(address)
        if not ip.is_global:
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
    if isinstance(value, dict):
        return _normalize(value.get("name"))
    return _normalize(value)


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
    return text[:2400]


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


def render_add_opportunity() -> None:
    st.markdown('<div class="eyebrow">Opportunity Radar</div>', unsafe_allow_html=True)
    st.title("Add Opportunity")
    st.caption(
        "Paste a job you already like. It will be saved with its company and used as a positive example for the relevant targeting hypothesis."
    )
    with st.expander("How this improves sourcing"):
        st.write(
            "The link is assigned to a company, sector and job theme. It becomes evidence for future searches, but it does not automatically become a hard rule or exclude exploratory roles."
        )

    url = st.text_input("Job link", placeholder="https://company.com/careers/job/...")
    if st.button("Load job from link", disabled=not url):
        try:
            st.session_state["submitted_job_draft"] = extract_job_page(url)
        except Exception as exc:
            st.session_state["submitted_job_draft"] = {
                "job_url": url.strip(), "title": "", "company": "", "location": "",
                "description": "", "source_domain": urlparse(url.strip()).hostname or "",
            }
            st.warning(f"The page could not be read automatically. Fill in the fields below. ({exc})")

    draft = st.session_state.get("submitted_job_draft")
    if draft:
        inferred_topic = infer_topic(draft.get("title", ""), draft.get("description", ""))
        with st.form("add_opportunity_form"):
            left, right = st.columns(2)
            title = left.text_input("Role title", value=draft.get("title", ""))
            company = right.text_input("Company", value=draft.get("company", ""))
            location = left.text_input("Location", value=draft.get("location", ""))
            country = right.text_input("Country")
            topic = st.selectbox("Theme", TOPICS, index=TOPICS.index(inferred_topic))
            role_summary = st.text_area(
                "What the role does (English)", value=draft.get("description", ""), height=180
            )
            comment = st.text_area(
                "Why this role is interesting to you",
                placeholder="Optional, but especially useful when the reason is not obvious from the job description.",
            )
            submitted = st.form_submit_button("Save opportunity and company", type="primary")

        if submitted:
            if not title.strip() or not company.strip():
                st.error("Role title and company are required.")
            else:
                token = github_token()
                if not token:
                    st.error("GitHub saving is not configured for this app.")
                else:
                    canonical_id, canonical_company, category = _company_context(
                        company.strip(), draft.get("source_domain", "")
                    )
                    now = datetime.now(timezone.utc).isoformat()
                    identifier = hashlib.sha256(draft["job_url"].encode("utf-8")).hexdigest()[:16]
                    opportunities, opp_sha = load_csv_file(token, SUBMISSIONS_PATH, SUBMISSION_COLUMNS)
                    row = {
                        "submission_id": identifier,
                        "submitted_at": now,
                        "job_url": draft["job_url"],
                        "title": title.strip(),
                        "company": canonical_company,
                        "canonical_company_id": canonical_id,
                        "company_category": category,
                        "location": location.strip(),
                        "country": country.strip(),
                        "topic": topic,
                        "role_summary_en": role_summary.strip(),
                        "user_comment": comment.strip(),
                        "feedback": "Interested",
                        "calibration_signal": "User-supplied positive example",
                        "targeting_scope": category if category != "Unclassified" else "General",
                        "review_status": "Needs targeting review",
                        "source_domain": draft.get("source_domain", ""),
                    }
                    opportunities = pd.concat([opportunities, pd.DataFrame([row])], ignore_index=True)
                    opportunities = opportunities.drop_duplicates("submission_id", keep="last")
                    companies, company_sha = load_csv_file(token, COMPANIES_PATH, COMPANY_COLUMNS)
                    company_row = {
                        "canonical_company_id": canonical_id,
                        "company": canonical_company,
                        "company_category": category,
                        "source_domain": draft.get("source_domain", ""),
                        "first_submitted_at": now,
                        "latest_job_url": draft["job_url"],
                        "review_status": "Known universe company" if category != "Unclassified" else "Needs company review",
                    }
                    existing = companies[companies["canonical_company_id"] == canonical_id]
                    if not existing.empty:
                        company_row["first_submitted_at"] = existing.iloc[0]["first_submitted_at"] or now
                    companies = pd.concat([companies, pd.DataFrame([company_row])], ignore_index=True)
                    companies = companies.drop_duplicates("canonical_company_id", keep="last")
                    try:
                        save_csv_file(token, COMPANIES_PATH, companies, company_sha, "Save submitted opportunity company")
                        save_csv_file(token, SUBMISSIONS_PATH, opportunities, opp_sha, "Save user-submitted opportunity")
                    except Exception:
                        st.error("Saving failed. Refresh the page and try again.")
                    else:
                        st.success("Saved. This role is now a positive targeting example and awaits semantic review.")
                        st.session_state.pop("submitted_job_draft", None)

    token = github_token()
    try:
        saved, _ = load_csv_file(token, SUBMISSIONS_PATH, SUBMISSION_COLUMNS)
    except Exception:
        saved = pd.DataFrame(columns=SUBMISSION_COLUMNS)
    if not saved.empty:
        st.subheader("Submitted opportunities")
        view = saved.sort_values("submitted_at", ascending=False)[
            ["title", "company", "topic", "location", "user_comment", "review_status", "job_url"]
        ]
        st.dataframe(
            view,
            hide_index=True,
            width="stretch",
            column_config={
                "title": "Role",
                "company": "Company",
                "topic": "Theme",
                "user_comment": "Why you like it",
                "review_status": "Targeting status",
                "job_url": st.column_config.LinkColumn("Link", display_text="Open"),
            },
        )
