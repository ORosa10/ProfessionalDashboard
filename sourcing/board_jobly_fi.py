"""Jobly Finland retrieval adapter for Workstream G."""
from __future__ import annotations

import hashlib
import json
import re
import time
from datetime import datetime, timezone
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; ProfessionalDashboard/0.4; +https://github.com/ORosa10/ProfessionalDashboard)"
}
TITLE_MARKERS = (
    "treasury", "cash management", "finance", "financial", "controller", "controlling",
    "corporate finance", "corporate development", "investment", "portfolio", "risk",
    "valuation", "transaction", "asset management", "capital", "markets",
)


def _clean(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _relevant(value: object) -> bool:
    title = _clean(value).lower()
    return any(marker in title for marker in TITLE_MARKERS)


def extract_jobly_links(html: str, limit: int) -> list[str]:
    soup = BeautifulSoup(html, "html.parser")
    found: list[str] = []
    pattern = re.compile(r"^/(?:en/)?job/[^?#]+-\d+/?$")
    for anchor in soup.find_all("a", href=True):
        href = str(anchor.get("href") or "")
        if not pattern.search(href):
            continue
        full = urljoin("https://www.jobly.fi", href)
        if full not in found:
            found.append(full)
        if len(found) >= limit:
            break
    return found


def _jobposting(html: str) -> dict | None:
    soup = BeautifulSoup(html, "html.parser")
    for node in soup.select('script[type="application/ld+json"]'):
        try:
            value = json.loads(node.string or node.get_text())
        except (json.JSONDecodeError, TypeError):
            continue
        values = value if isinstance(value, list) else [value]
        for item in values:
            if isinstance(item, dict) and item.get("@type") == "JobPosting":
                return item
            if isinstance(item, dict) and isinstance(item.get("@graph"), list):
                for nested in item["@graph"]:
                    if isinstance(nested, dict) and nested.get("@type") == "JobPosting":
                        return nested
    return None


def _location(item: dict) -> str:
    locations = item.get("jobLocation") or []
    if isinstance(locations, dict):
        locations = [locations]
    bits: list[str] = []
    for loc in locations:
        if not isinstance(loc, dict):
            continue
        address = loc.get("address") or loc
        if not isinstance(address, dict):
            continue
        text = ", ".join(
            str(address.get(k) or "")
            for k in ("addressLocality", "addressRegion", "addressCountry")
            if address.get(k)
        )
        if text:
            bits.append(_clean(text))
    return "; ".join(dict.fromkeys(bits)) or "Finland"


def discover_jobly(per_query: int, max_details: int) -> tuple[list[dict], list[str]]:
    now = datetime.now(timezone.utc).isoformat()
    errors: list[str] = []
    try:
        response = requests.get("https://www.jobly.fi/en/jobs/finance", headers=HEADERS, timeout=35)
        response.raise_for_status()
        links = extract_jobly_links(response.text, max(per_query * 6, max_details))
    except Exception as exc:
        return [], [f"search finance: {type(exc).__name__}"]

    jobs: list[dict] = []
    for url in links[:max_details]:
        try:
            response = requests.get(url, headers=HEADERS, timeout=35)
            response.raise_for_status()
            item = _jobposting(response.text)
            if not item:
                raise ValueError("JobPosting JSON-LD missing")
        except Exception as exc:
            errors.append(f"detail {url.rsplit('/', 1)[-1][:50]}: {type(exc).__name__}")
            continue
        title = _clean(item.get("title"))
        if not title or not _relevant(title):
            continue
        org = item.get("hiringOrganization") or {}
        if not isinstance(org, dict):
            org = {}
        identifier = item.get("identifier") or ""
        external_id = _clean(identifier.get("value")) if isinstance(identifier, dict) else _clean(identifier)
        description = _clean(BeautifulSoup(str(item.get("description") or ""), "html.parser").get_text(" "))
        job_id = hashlib.sha256(f"jobly-fi|{external_id or url}".encode("utf-8")).hexdigest()[:16]
        jobs.append({
            "job_id": job_id,
            "canonical_company_id": "",
            "company": _clean(org.get("name")) or "Employer not stated",
            "title": title,
            "description": description,
            "description_en": "",
            "translation_status": "pending",
            "market": "Finland",
            "location": _location(item),
            "priority_locations": _location(item),
            "job_url": url,
            "source_url": url,
            "source_id": "jobly-fi",
            "date_posted": _clean(item.get("datePosted")),
            "discovered_at": now,
            "last_seen_at": now,
            "relevance_score": 1,
            "matched_terms": "finance category",
            "verification": "verified jobly.fi JobPosting JSON-LD",
            "status": "Open",
            "alternate_job_urls": "",
            "duplicate_count": 0,
            "calibration_score": "",
            "calibration_note": "",
        })
        time.sleep(0.12)
    return jobs, errors
