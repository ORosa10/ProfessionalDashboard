"""The Hub Nordic startup/scale-up retrieval adapter for Workstream G."""
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
    "treasury", "fp&a", "finance", "financial", "controller", "corporate finance",
    "investment", "portfolio", "risk", "liquidity", "capital", "valuation",
    "strategy", "markets",
)


def _clean(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def extract_thehub_links(html: str, limit: int) -> list[str]:
    soup = BeautifulSoup(html, "html.parser")
    found: list[str] = []
    for anchor in soup.find_all("a", href=True):
        href = str(anchor.get("href") or "")
        if not re.match(r"^/jobs/[0-9a-f]{12,}$", href, re.I):
            continue
        full = urljoin("https://thehub.io", href)
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
    locs = item.get("jobLocation") or []
    if isinstance(locs, dict):
        locs = [locs]
    bits: list[str] = []
    for loc in locs:
        if not isinstance(loc, dict):
            continue
        address = loc.get("address") or loc
        if isinstance(address, dict):
            text = ", ".join(str(address.get(k) or "") for k in ("addressLocality", "addressCountry") if address.get(k))
            if text:
                bits.append(_clean(text))
    return "; ".join(dict.fromkeys(bits)) or "Nordics"


def discover_thehub(max_details: int) -> tuple[list[dict], list[str]]:
    now = datetime.now(timezone.utc).isoformat()
    errors: list[str] = []
    links: list[str] = []
    for page in range(1, 6):
        try:
            response = requests.get("https://thehub.io/jobs", params={"page": page}, headers=HEADERS, timeout=35)
            response.raise_for_status()
            for link in extract_thehub_links(response.text, 100):
                if link not in links:
                    links.append(link)
        except Exception as exc:
            errors.append(f"page {page}: {type(exc).__name__}")
        time.sleep(0.12)

    jobs: list[dict] = []
    for url in links[:max_details]:
        try:
            response = requests.get(url, headers=HEADERS, timeout=35)
            response.raise_for_status()
            item = _jobposting(response.text)
            if not item:
                raise ValueError("JobPosting JSON-LD missing")
        except Exception as exc:
            errors.append(f"detail {url.rsplit('/', 1)[-1]}: {type(exc).__name__}")
            continue
        title = _clean(item.get("title"))
        if not any(marker in title.lower() for marker in TITLE_MARKERS):
            continue
        org = item.get("hiringOrganization") or {}
        if not isinstance(org, dict):
            org = {}
        description = _clean(BeautifulSoup(str(item.get("description") or ""), "html.parser").get_text(" "))
        external_id = url.rstrip("/").rsplit("/", 1)[-1]
        location = _location(item)
        jobs.append({
            "job_id": hashlib.sha256(f"thehub|{external_id}".encode("utf-8")).hexdigest()[:16],
            "canonical_company_id": "",
            "company": _clean(org.get("name")) or "Employer not stated",
            "title": title,
            "description": description,
            "description_en": "",
            "translation_status": "pending",
            "market": "Nordics",
            "location": location,
            "priority_locations": location,
            "job_url": url,
            "source_url": url,
            "source_id": "thehub",
            "date_posted": _clean(item.get("datePosted")),
            "discovered_at": now,
            "last_seen_at": now,
            "relevance_score": 1,
            "matched_terms": "Nordic startup finance exploration",
            "verification": "verified The Hub JobPosting JSON-LD",
            "status": "Open",
            "alternate_job_urls": "",
            "duplicate_count": 0,
            "calibration_score": "",
            "calibration_note": "",
        })
        time.sleep(0.1)
    return jobs, errors
