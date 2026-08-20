"""HTML search adapters for Workstream G national/commercial job boards.

These adapters only do retrieval/verification. They intentionally do not decide
personal fit: downstream Workstream C remains the semantic decision layer.
"""
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

FINANCE_TITLE_MARKERS = (
    "treasury", "fp&a", "finance", "financial", "finans", "finanz", "controller",
    "controlling", "corporate finance", "corporate development", "m&a",
    "valuation", "bewertung", "investment", "investering", "portfolio", "risk", "risiko",
    "restructuring", "turnaround", "liquidity", "likviditet", "liquidität", "cash management",
    "transaction", "private equity", "asset management", "förvaltare",
)


def _clean(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _logical(value: object) -> str:
    return re.sub(r"[^a-z0-9à-ž]+", " ", _clean(value).lower()).strip()


def _relevant_title(value: object) -> bool:
    title = _logical(value)
    return any(_logical(marker) in title for marker in FINANCE_TITLE_MARKERS)


def _stable_id(source_id: str, external_id: str, url: str) -> str:
    raw = f"{source_id}|{external_id or url}".encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:16]


def extract_html_search_links(source_id: str, html: str, limit: int) -> list[str]:
    """Extract likely vacancy-detail links from a board search-result page."""
    soup = BeautifulSoup(html, "html.parser")
    if source_id == "jobs-cz":
        base = "https://www.jobs.cz"
        predicates = ("/rpd/", "/prace/")
    elif source_id == "prace-cz":
        base = "https://www.prace.cz"
        predicates = ("/nabidka/",)
    elif source_id == "stepstone-at":
        base = "https://www.stepstone.at"
        predicates = ("/stellenangebote--",)
    elif source_id == "jobbsafari-se":
        base = "https://jobbsafari.se"
        predicates = ("/jobb/",)
    else:
        raise ValueError(f"Unsupported HTML board source: {source_id}")

    found: list[str] = []
    for anchor in soup.find_all("a", href=True):
        href = str(anchor.get("href") or "")
        if not any(marker in href for marker in predicates):
            continue
        if source_id == "jobs-cz" and "/rpd/" not in href:
            classes = " ".join(anchor.get("class") or [])
            data_attrs = " ".join(f"{k}={v}" for k, v in anchor.attrs.items())
            if "job" not in (classes + " " + data_attrs).lower():
                continue
        full = urljoin(base, href.split("#", 1)[0].split("?utm_", 1)[0])
        if full not in found:
            found.append(full)
        if len(found) >= limit:
            break
    return found


def _jsonld_jobposting(html: str) -> dict | None:
    soup = BeautifulSoup(html, "html.parser")
    for node in soup.select('script[type="application/ld+json"]'):
        raw = node.string or node.get_text()
        try:
            value = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            continue
        candidates = value if isinstance(value, list) else [value]
        for item in candidates:
            if isinstance(item, dict) and item.get("@type") == "JobPosting":
                return item
            if isinstance(item, dict) and isinstance(item.get("@graph"), list):
                for nested in item["@graph"]:
                    if isinstance(nested, dict) and nested.get("@type") == "JobPosting":
                        return nested
    return None


def _location(item: dict, fallback: str) -> str:
    locations = item.get("jobLocation") or []
    if isinstance(locations, dict):
        locations = [locations]
    bits: list[str] = []
    for location in locations:
        if not isinstance(location, dict):
            continue
        address = location.get("address") or location
        if not isinstance(address, dict):
            continue
        text = ", ".join(
            str(address.get(key) or "")
            for key in ("addressLocality", "addressRegion", "addressCountry")
            if address.get(key)
        )
        if text:
            bits.append(_clean(text))
    return "; ".join(dict.fromkeys(bits)) or fallback


def _description(item: dict) -> str:
    html = str(item.get("description") or "")
    return _clean(BeautifulSoup(html, "html.parser").get_text(" "))


def _search_url(source_id: str, query: str) -> str:
    if source_id == "jobs-cz":
        return "https://www.jobs.cz/prace/?q%5B%5D=" + quote(query)
    if source_id == "prace-cz":
        return "https://www.prace.cz/nabidky/?searchString=" + quote(query)
    if source_id == "stepstone-at":
        slug = re.sub(r"[^a-z0-9]+", "-", query.lower()).strip("-")
        return f"https://www.stepstone.at/jobs/{slug}"
    if source_id == "jobbsafari-se":
        return "https://jobbsafari.se/lediga-jobb?sok=" + quote(query)
    raise ValueError(f"Unsupported HTML board source: {source_id}")


def discover_html_jsonld_board(
    source_id: str,
    market: str,
    queries: list[str],
    per_query: int,
    max_details: int,
) -> tuple[list[dict], list[str]]:
    """Discover search results and verify each retained role via JobPosting JSON-LD."""
    now = datetime.now(timezone.utc).isoformat()
    candidates: dict[str, set[str]] = {}
    errors: list[str] = []

    for query in queries:
        try:
            response = requests.get(_search_url(source_id, query), headers=HEADERS, timeout=35)
            response.raise_for_status()
            links = extract_html_search_links(source_id, response.text, per_query)
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
            item = _jsonld_jobposting(response.text)
            if not item:
                raise ValueError("JobPosting JSON-LD missing")
        except Exception as exc:
            errors.append(f"detail {url.rsplit('/', 1)[-1][:50]}: {type(exc).__name__}")
            continue

        title = _clean(item.get("title"))
        if not title or not _relevant_title(title):
            continue
        organization = item.get("hiringOrganization") or {}
        if not isinstance(organization, dict):
            organization = {}
        external_id = _clean(item.get("identifier"))
        if isinstance(item.get("identifier"), dict):
            external_id = _clean(item["identifier"].get("value"))
        location = _location(item, market)
        jobs.append({
            "job_id": _stable_id(source_id, external_id, url),
            "canonical_company_id": "",
            "company": _clean(organization.get("name")) or "Employer not stated",
            "title": title,
            "description": _description(item),
            "description_en": "",
            "translation_status": "pending",
            "market": market,
            "location": location,
            "priority_locations": location,
            "job_url": url,
            "source_url": url,
            "source_id": source_id,
            "date_posted": _clean(item.get("datePosted")),
            "discovered_at": now,
            "last_seen_at": now,
            "relevance_score": len(matched),
            "matched_terms": "; ".join(sorted(matched)),
            "verification": f"verified {source_id} JobPosting JSON-LD",
            "status": "Open",
            "alternate_job_urls": "",
            "duplicate_count": 0,
            "calibration_score": "",
            "calibration_note": "",
        })
        time.sleep(0.15)
    return jobs, errors
