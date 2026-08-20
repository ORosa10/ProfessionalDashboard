"""Official NAV Arbeidsplassen vacancy-feed adapter for Workstream G."""
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
HEADERS = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/131.0 Safari/537.36", "Accept": "application/json"}
TITLE_MARKERS = ("treasury", "finance", "financial", "finans", "controller", "controlling", "corporate finance", "corporate development", "investment", "investering", "portfolio", "risk", "risiko", "likvid", "liquidity", "cash management", "valuation", "verdsett", "transaction", "private equity", "asset management", "capital markets", "marked", "derivatives", "hedging")


def _clean(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _relevant_title(value: object) -> bool:
    title = _clean(value).lower(); return any(marker in title for marker in TITLE_MARKERS)


def _sanitize_token(value: object) -> str:
    """Extract the signed JWT from NAV's human-readable public-token response."""
    raw = str(value or "").strip().strip('"').strip("'")
    # /api/publicToken currently returns text like:
    #   Current public token for Nav Job Vacancy Feed:\n<JWT>
    # rather than a bare token. Prefer extracting a JWT-shaped value so the
    # descriptive prefix never leaks into the Authorization header.
    jwt = re.search(r"([A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+)", raw)
    if jwt:
        return jwt.group(1)
    token = raw
    token = re.sub(r"(?i)^authorization\s*:\s*bearer\s+", "", token).strip()
    token = re.sub(r"(?i)^bearer\s+", "", token).strip()
    token = re.sub(r"\s+", "", token)
    if not token:
        raise ValueError("NAV token empty")
    return token


def _get_public_token() -> str:
    response = requests.get(TOKEN_URL, headers=HEADERS, timeout=30); response.raise_for_status()
    try: payload = response.json()
    except ValueError: return _sanitize_token(response.text)
    if isinstance(payload, str): return _sanitize_token(payload)
    if isinstance(payload, dict):
        for key in ("token", "publicToken", "access_token"):
            if payload.get(key): return _sanitize_token(payload[key])
    raise ValueError("NAV public token response did not contain a token")


def _auth_headers(token: str, since: datetime | None = None) -> dict[str, str]:
    headers = dict(HEADERS); headers["Authorization"] = f"Bearer {_sanitize_token(token)}"
    if since is not None: headers["If-Modified-Since"] = format_datetime(since.astimezone(timezone.utc), usegmt=True)
    return headers


def _absolute_api_url(value: str) -> str:
    return value if value.startswith(("http://", "https://")) else urljoin(BASE + "/", value.lstrip("/"))


def _location(ad: dict) -> str:
    bits = []
    for loc in ad.get("workLocations") or []:
        if isinstance(loc, dict):
            value = ", ".join(str(loc.get(k) or "") for k in ("city", "municipal", "county", "country") if loc.get(k))
            if value: bits.append(_clean(value))
    return "; ".join(dict.fromkeys(bits)) or "Norway"


def discover_nav(max_details: int, max_pages: int = 40) -> tuple[list[dict], list[str]]:
    now = datetime.now(timezone.utc); errors: list[str] = []
    try: token = _get_public_token()
    except Exception as exc: return [], [f"token: {type(exc).__name__}: {exc}"]
    next_url: str | None = FEED_URL; since = now - timedelta(days=185); candidates: dict[str, dict] = {}; pages = 0
    while next_url and pages < max_pages and len(candidates) < max_details * 5:
        try:
            response = requests.get(_absolute_api_url(next_url), headers=_auth_headers(token, since if pages == 0 else None), timeout=40)
            if response.status_code == 304: break
            response.raise_for_status(); page = response.json()
        except Exception as exc:
            status = getattr(getattr(exc, "response", None), "status_code", "")
            errors.append(f"feed page {pages + 1}: {type(exc).__name__}{f' {status}' if status else ''}"); break
        for item in page.get("items") or []:
            if not isinstance(item, dict): continue
            meta = item.get("_feed_entry") or {}; uuid = _clean(meta.get("uuid") or item.get("id"))
            if uuid: candidates[uuid] = item
        next_url = page.get("next_url"); pages += 1
    jobs: list[dict] = []
    for uuid, item in reversed(list(candidates.items())):
        meta = item.get("_feed_entry") or {}
        if str(meta.get("status") or "").upper() != "ACTIVE": continue
        header_title = _clean(meta.get("title") or item.get("title"))
        if not _relevant_title(header_title): continue
        detail_url = _absolute_api_url(str(item.get("url") or f"/api/v1/feedentry/{item.get('id')}"))
        try:
            response = requests.get(detail_url, headers=_auth_headers(token), timeout=35); response.raise_for_status(); detail = response.json(); ad = detail.get("json") or detail.get("ad_content") or {}
            if not isinstance(ad, dict): raise ValueError("NAV detail JSON missing")
        except Exception as exc:
            errors.append(f"detail {uuid}: {type(exc).__name__}"); continue
        title = _clean(ad.get("title") or ad.get("jobtitle") or header_title)
        if not _relevant_title(title): continue
        employer = ad.get("employer") or {}; company = _clean(employer.get("name") if isinstance(employer, dict) else "") or (_clean(employer.get("businessName")) if isinstance(employer, dict) else "")
        description = _clean(BeautifulSoup(str(ad.get("description") or ""), "html.parser").get_text(" ")); location = _location(ad)
        public_url = _clean(ad.get("link") or ad.get("sourceurl") or ad.get("applicationUrl")) or PUBLIC_JOB_BASE + uuid
        job_id = hashlib.sha256(f"arbeidsplassen-no|{uuid}".encode()).hexdigest()[:16]
        jobs.append({"job_id": job_id, "canonical_company_id": "", "company": company or _clean(meta.get("businessName")) or "Employer not stated", "title": title, "description": description, "description_en": "", "translation_status": "pending", "market": "Norway", "location": location, "priority_locations": location, "job_url": public_url, "source_url": public_url, "source_id": "arbeidsplassen-no", "date_posted": _clean(ad.get("published")), "discovered_at": now.isoformat(), "last_seen_at": now.isoformat(), "relevance_score": 1, "matched_terms": "official NAV vacancy feed", "verification": "official NAV Job Vacancy Feed", "status": "Open", "alternate_job_urls": "", "duplicate_count": 0, "calibration_score": "", "calibration_note": ""})
        if len(jobs) >= max_details: break
    return jobs, errors
