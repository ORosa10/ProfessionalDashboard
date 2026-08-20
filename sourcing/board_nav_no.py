"""Official NAV Arbeidsplassen vacancy-feed adapter for Workstream G.

Uses NAV's experimental rotating public token at runtime. For long-term stable
production NAV recommends registering for a private consumer token.
"""
from __future__ import annotations

import hashlib
import re
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

BASE = "https://pam-stilling-feed.nav.no"
TOKEN_URL = BASE + "/api/publicToken"
FEED_URL = BASE + "/api/v1/feed"
PUBLIC_JOB_BASE = "https://arbeidsplassen.nav.no/stillinger/stilling/"
HEADERS = {
    "User-Agent": "ProfessionalDashboard/0.5 (+https://github.com/ORosa10/ProfessionalDashboard)",
    "Accept": "application/json",
}
TITLE_MARKERS = (
    "treasury", "finance", "financial", "finans", "controller", "controlling",
    "corporate finance", "corporate development", "investment", "investering",
    "portfolio", "risk", "risiko", "likvid", "liquidity", "cash management",
    "valuation", "verdsett", "transaction", "private equity", "asset management",
    "capital markets", "marked", "derivatives", "hedging",
)


def _clean(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _relevant_title(value: object) -> bool:
    title = _clean(value).lower()
    return any(marker in title for marker in TITLE_MARKERS)


def _get_public_token() -> str:
    response = requests.get(TOKEN_URL, headers=HEADERS, timeout=30)
    response.raise_for_status()
    try:
        payload = response.json()
    except ValueError:
        return response.text.strip().strip('"')
    if isinstance(payload, str):
        return payload.strip()
    if isinstance(payload, dict):
        for key in ("token", "publicToken", "access_token"):
            if payload.get(key):
                return str(payload[key]).strip()
    raise ValueError("NAV public token response did not contain a token")


def _auth_headers(token: str, since: datetime | None = None) -> dict[str, str]:
    headers = dict(HEADERS)
    headers["Authorization"] = f"Bearer {token}"
    if since is not None:
        headers["If-Modified-Since"] = format_datetime(since.astimezone(timezone.utc), usegmt=True)
    return headers


def _absolute_api_url(value: str) -> str:
    if value.startswith("http://") or value.startswith("https://"):
        return value
    return urljoin(BASE + "/", value.lstrip("/"))


def _location(ad: dict) -> str:
    locations = ad.get("workLocations") or []
    bits: list[str] = []
    for loc in locations:
        if not isinstance(loc, dict):
            continue
        value = ", ".join(
            str(loc.get(key) or "")
            for key in ("city", "municipal", "county", "country")
            if loc.get(key)
        )
        if value:
            bits.append(_clean(value))
    return "; ".join(dict.fromkeys(bits)) or "Norway"


def discover_nav(max_details: int, max_pages: int = 40) -> tuple[list[dict], list[str]]:
    """Fetch recent active NAV feed events and resolve relevant finance vacancies.

    NAV states an ad cannot remain active for more than six months, so the first
    request starts six months back. Duplicate feed events are collapsed by ad UUID.
    """
    now = datetime.now(timezone.utc)
    errors: list[str] = []
    try:
        token = _get_public_token()
    except Exception as exc:
        return [], [f"token: {type(exc).__name__}: {exc}"]

    next_url: str | None = FEED_URL
    since = now - timedelta(days=185)
    candidates: dict[str, dict] = {}
    pages = 0

    while next_url and pages < max_pages and len(candidates) < max_details * 5:
        try:
            response = requests.get(
                _absolute_api_url(next_url),
                headers=_auth_headers(token, since if pages == 0 else None),
                timeout=40,
            )
            if response.status_code == 304:
                break
            response.raise_for_status()
            page = response.json()
        except Exception as exc:
            errors.append(f"feed page {pages + 1}: {type(exc).__name__}")
            break

        for item in page.get("items") or []:
            if not isinstance(item, dict):
                continue
            meta = item.get("_feed_entry") or {}
            uuid = _clean(meta.get("uuid") or item.get("id"))
            if not uuid:
                continue
            # Feed can contain repeated changes; the later event wins.
            candidates[uuid] = item
        next_url = page.get("next_url")
        pages += 1

    jobs: list[dict] = []
    # newest candidate events arrive as feed pages progress; use the latest value
    for uuid, item in reversed(list(candidates.items())):
        meta = item.get("_feed_entry") or {}
        if str(meta.get("status") or "").upper() != "ACTIVE":
            continue
        header_title = _clean(meta.get("title") or item.get("title"))
        if not _relevant_title(header_title):
            continue
        detail_url = _absolute_api_url(str(item.get("url") or f"/api/v1/feedentry/{item.get('id')}"))
        try:
            response = requests.get(detail_url, headers=_auth_headers(token), timeout=35)
            response.raise_for_status()
            detail = response.json()
            ad = detail.get("json") or detail.get("ad_content") or {}
            if not isinstance(ad, dict):
                raise ValueError("NAV detail JSON missing")
        except Exception as exc:
            errors.append(f"detail {uuid}: {type(exc).__name__}")
            continue

        title = _clean(ad.get("title") or ad.get("jobtitle") or header_title)
        if not _relevant_title(title):
            continue
        employer = ad.get("employer") or {}
        company = _clean(employer.get("name") if isinstance(employer, dict) else "")
        if not company and isinstance(employer, dict):
            company = _clean(employer.get("businessName"))
        description = _clean(
            BeautifulSoup(str(ad.get("description") or ""), "html.parser").get_text(" ")
        )
        location = _location(ad)
        public_url = _clean(ad.get("link") or ad.get("sourceurl") or ad.get("applicationUrl"))
        if not public_url:
            public_url = PUBLIC_JOB_BASE + uuid
        job_id = hashlib.sha256(f"arbeidsplassen-no|{uuid}".encode("utf-8")).hexdigest()[:16]
        jobs.append({
            "job_id": job_id,
            "canonical_company_id": "",
            "company": company or _clean(meta.get("businessName")) or "Employer not stated",
            "title": title,
            "description": description,
            "description_en": "",
            "translation_status": "pending",
            "market": "Norway",
            "location": location,
            "priority_locations": location,
            "job_url": public_url,
            "source_url": public_url,
            "source_id": "arbeidsplassen-no",
            "date_posted": _clean(ad.get("published")),
            "discovered_at": now.isoformat(),
            "last_seen_at": now.isoformat(),
            "relevance_score": 1,
            "matched_terms": "official NAV vacancy feed",
            "verification": "official NAV Job Vacancy Feed",
            "status": "Open",
            "alternate_job_urls": "",
            "duplicate_count": 0,
            "calibration_score": "",
            "calibration_note": "",
        })
        if len(jobs) >= max_details:
            break

    return jobs, errors
