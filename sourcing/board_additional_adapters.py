"""Additional server-rendered board adapters for Workstream G.

These sources are kept separate from the generic adapter because their search
URL and detail patterns are board-specific. Retrieval only; semantic fit stays
in Workstream C.
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

TITLE_MARKERS = (
    "treasury", "fp&a", "finance", "financial", "controller", "controlling",
    "corporate finance", "corporate development", "m&a", "valuation", "investment",
    "portfolio", "risk", "restructuring", "liquidity", "cash management",
    "transaction", "private equity", "asset management", "markets",
)


def _clean(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _relevant_title(value: object) -> bool:
    title = _clean(value).lower()
    return any(marker in title for marker in TITLE_MARKERS)


def _stable_id(source_id: str, external_id: str, url: str) -> str:
    return hashlib.sha256(f"{source_id}|{external_id or url}".encode("utf-8")).hexdigest()[:16]


def extract_additional_links(source_id: str, html: str, limit: int) -> list[str]:
    soup = BeautifulSoup(html, "html.parser")
    if source_id == "cv-library-uk":
        base = "https://www.cv-library.co.uk"
        pattern = re.compile(r"^/job/\d+/[^?#]+")
    elif source_id == "jobup-ch":
        base = "https://www.jobup.ch"
        pattern = re.compile(r"^/(?:en|fr)/jobs/detail/[0-9a-f-]+/?", re.I)
    else:
        raise ValueError(f"Unsupported additional board: {source_id}")

    found: list[str] = []
    for anchor in soup.find_all("a", href=True):
        href = str(anchor.get("href") or "")
        if not pattern.search(href):
            continue
        full = urljoin(base, href.split("#", 1)[0].split("?", 1)[0])
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


def _location(item: dict, fallback: str) -> str:
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
    return "; ".join(dict.fromkeys(bits)) or fallback


def _search_url(source_id: str, query: str) -> str:
    if source_id == "cv-library-uk":
        slug = re.sub(r"[^a-z0-9]+", "-", query.lower()).strip("-")
        return f"https://www.cv-library.co.uk/{slug}-jobs"
    if source_id == "jobup-ch":
        return "https://www.jobup.ch/en/jobs/?term=" + quote(query)
    raise ValueError(source_id)


def discover_additional_board(
    source_id: str,
    market: str,
    queries: list[str],
    per_query: int,
    max_details: int,
) -> tuple[list[dict], list[str]]:
    now = datetime.now(timezone.utc).isoformat()
    candidates: dict[str, set[str]] = {}
    errors: list[str] = []
    for query in queries:
        try:
            response = requests.get(_search_url(source_id, query), headers=HEADERS, timeout=35)
            response.raise_for_status()
            links = extract_additional_links(source_id, response.text, per_query)
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
            errors.append(f"detail {url.rstrip('/').rsplit('/', 1)[-1][:50]}: {type(exc).__name__}")
            continue
        title = _clean(item.get("title"))
        if not title or not _relevant_title(title):
            continue
        org = item.get("hiringOrganization") or {}
        if not isinstance(org, dict):
            org = {}
        identifier = item.get("identifier") or ""
        external_id = _clean(identifier.get("value")) if isinstance(identifier, dict) else _clean(identifier)
        description = _clean(BeautifulSoup(str(item.get("description") or ""), "html.parser").get_text(" "))
        location = _location(item, market)
        jobs.append({
            "job_id": _stable_id(source_id, external_id, url),
            "canonical_company_id": "",
            "company": _clean(org.get("name")) or "Employer not stated",
            "title": title,
            "description": description,
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
