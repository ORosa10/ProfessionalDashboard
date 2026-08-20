"""jobs.ch retrieval adapter for Workstream G."""
from __future__ import annotations

import hashlib
import json
import re
import time
from datetime import datetime, timezone
from urllib.parse import quote, urljoin

import requests
from bs4 import BeautifulSoup

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; ProfessionalDashboard/0.4; +https://github.com/ORosa10/ProfessionalDashboard)"
}

TITLE_MARKERS = (
    "treasury", "fp&a", "finance", "financial", "finanz", "controller",
    "controlling", "corporate finance", "corporate development", "m&a",
    "valuation", "investment", "portfolio", "risk", "restructuring",
    "liquidity", "cash management", "transaction", "private equity",
    "asset management",
)


def _clean(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _relevant_title(value: object) -> bool:
    title = _clean(value).lower()
    return any(marker in title for marker in TITLE_MARKERS)


def _stable_id(external_id: str, url: str) -> str:
    return hashlib.sha256(f"jobs-ch|{external_id or url}".encode("utf-8")).hexdigest()[:16]


def extract_jobs_ch_links(html: str, limit: int) -> list[str]:
    soup = BeautifulSoup(html, "html.parser")
    found: list[str] = []
    for anchor in soup.find_all("a", href=True):
        href = str(anchor.get("href") or "")
        if "/vacancies/detail/" not in href:
            continue
        full = urljoin("https://www.jobs.ch", href.split("#", 1)[0])
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
            str(address.get(key) or "")
            for key in ("addressLocality", "addressRegion", "addressCountry")
            if address.get(key)
        )
        if text:
            bits.append(_clean(text))
    return "; ".join(dict.fromkeys(bits)) or "Switzerland"


def discover_jobs_ch(queries: list[str], per_query: int, max_details: int) -> tuple[list[dict], list[str]]:
    now = datetime.now(timezone.utc).isoformat()
    candidates: dict[str, set[str]] = {}
    errors: list[str] = []
    for query in queries:
        try:
            response = requests.get(
                "https://www.jobs.ch/en/vacancies/?term=" + quote(query),
                headers=HEADERS,
                timeout=35,
            )
            response.raise_for_status()
            links = extract_jobs_ch_links(response.text, per_query)
            if not links:
                errors.append(f"search {query}: no detail links")
            for link in links:
                candidates.setdefault(link, set()).add(query)
        except Exception as exc:
            errors.append(f"search {query}: {type(exc).__name__}")
        time.sleep(0.15)

    jobs: list[dict] = []
    for url, matched in list(candidates.items())[:max_details]:
        try:
            response = requests.get(url, headers=HEADERS, timeout=35)
            response.raise_for_status()
            item = _jobposting(response.text)
            if not item:
                raise ValueError("JobPosting JSON-LD missing")
        except Exception as exc:
            errors.append(f"detail {url.rstrip('/').rsplit('/', 1)[-1]}: {type(exc).__name__}")
            continue
        title = _clean(item.get("title"))
        if not title or not _relevant_title(title):
            continue
        organization = item.get("hiringOrganization") or {}
        if not isinstance(organization, dict):
            organization = {}
        identifier = item.get("identifier") or ""
        external_id = _clean(identifier.get("value")) if isinstance(identifier, dict) else _clean(identifier)
        description = _clean(BeautifulSoup(str(item.get("description") or ""), "html.parser").get_text(" "))
        location = _location(item)
        jobs.append({
            "job_id": _stable_id(external_id, url),
            "canonical_company_id": "",
            "company": _clean(organization.get("name")) or "Employer not stated",
            "title": title,
            "description": description,
            "description_en": "",
            "translation_status": "pending",
            "market": "Switzerland",
            "location": location,
            "priority_locations": location,
            "job_url": url,
            "source_url": url,
            "source_id": "jobs-ch",
            "date_posted": _clean(item.get("datePosted")),
            "discovered_at": now,
            "last_seen_at": now,
            "relevance_score": len(matched),
            "matched_terms": "; ".join(sorted(matched)),
            "verification": "verified jobs.ch JobPosting JSON-LD",
            "status": "Open",
            "alternate_job_urls": "",
            "duplicate_count": 0,
            "calibration_score": "",
            "calibration_note": "",
        })
        time.sleep(0.15)
    return jobs, errors
