"""Academic Work adapters for Denmark and Finland (Workstream G)."""
from __future__ import annotations

import hashlib
import json
import re
import time
from datetime import datetime, timezone
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from sourcing.g_data_quality import any_finance_marker

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/151 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9,da;q=0.8,fi;q=0.7",
}

CONFIG = {
    "academicwork-dk": {
        "market": "Denmark",
        "base": "https://www.academicwork.dk",
        "listing": "https://www.academicwork.dk/en/jobs",
        "detail_patterns": (r"^/(?:en/jobs|ledige-stillinger)/j/[^?#]+/[A-Z0-9]+/?$",),
    },
    "academicwork-fi": {
        "market": "Finland",
        "base": "https://www.academicwork.fi",
        "listing": "https://www.academicwork.fi/en/jobs",
        "detail_patterns": (r"^/(?:en/jobs|avoimet-tyopaikat)/j/[^?#]+/[A-Z0-9]+/?$",),
    },
}

TITLE_MARKERS = (
    "treasury", "cash management", "liquidity", "finance", "financial", "controller",
    "corporate finance", "corporate development", "investment", "portfolio", "risk",
    "valuation", "transaction", "capital markets", "asset management", "fp&a",
    "rahoitus", "talous", "finans", "økonomi",
)


def _clean(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _relevant(title: str, description: str = "") -> bool:
    """Academic Work is broad: require a target-finance signal in the title."""
    return any_finance_marker(title, TITLE_MARKERS)


def extract_academicwork_links(source_id: str, html: str, limit: int) -> list[str]:
    cfg = CONFIG[source_id]
    soup = BeautifulSoup(html, "html.parser")
    found: list[str] = []
    for anchor in soup.find_all("a", href=True):
        href = str(anchor.get("href") or "").split("#", 1)[0].split("?", 1)[0]
        if not any(re.match(pattern, href, flags=re.I) for pattern in cfg["detail_patterns"]):
            continue
        full = urljoin(cfg["base"], href)
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


def _location_from_jsonld(item: dict, fallback: str) -> str:
    locations = item.get("jobLocation") or []
    if isinstance(locations, dict):
        locations = [locations]
    out: list[str] = []
    for loc in locations:
        if not isinstance(loc, dict):
            continue
        address = loc.get("address") or loc
        if isinstance(address, dict):
            text = ", ".join(str(address.get(k) or "") for k in ("addressLocality", "addressRegion", "addressCountry") if address.get(k))
            if text:
                out.append(_clean(text))
    return "; ".join(dict.fromkeys(out)) or fallback


def _visible_detail(html: str, market: str) -> tuple[str, str, str, str, str]:
    soup = BeautifulSoup(html, "html.parser")
    h1 = soup.find("h1")
    title = _clean(h1.get_text(" ", strip=True) if h1 else "")
    text = soup.get_text("\n", strip=True)

    def label_value(labels: tuple[str, ...]) -> str:
        for label in labels:
            match = re.search(rf"(?:^|\n){re.escape(label)}\s*:?\s*\n?([^\n]+)", text, flags=re.I)
            if match:
                value = _clean(match.group(1))
                if value and value.lower() != label.lower():
                    return value
        return ""

    company = label_value(("Company", "Virksomhed", "Yritys")) or "Employer not stated"
    location = label_value(("Location", "Lokation", "Sijainti")) or market
    description = _clean(soup.get_text(" ", strip=True))[:18000]
    return title, company, location, description, ""


def discover_academicwork(source_id: str, max_details: int) -> tuple[list[dict], list[str]]:
    cfg = CONFIG[source_id]
    errors: list[str] = []
    now = datetime.now(timezone.utc).isoformat()
    try:
        response = requests.get(cfg["listing"], headers=HEADERS, timeout=35)
        response.raise_for_status()
        links = extract_academicwork_links(source_id, response.text, max(max_details * 2, 50))
        if not links:
            errors.append("listing: no detail links")
    except Exception as exc:
        return [], [f"listing: {type(exc).__name__}: {exc}"]

    jobs: list[dict] = []
    for url in links:
        if len(jobs) >= max_details:
            break
        try:
            response = requests.get(url, headers=HEADERS, timeout=35)
            response.raise_for_status()
            item = _jobposting(response.text)
            if item:
                title = _clean(item.get("title"))
                org = item.get("hiringOrganization") or {}
                company = _clean(org.get("name")) if isinstance(org, dict) else ""
                description = _clean(BeautifulSoup(str(item.get("description") or ""), "html.parser").get_text(" "))
                location = _location_from_jsonld(item, str(cfg["market"]))
                date_posted = _clean(item.get("datePosted"))
            else:
                title, company, location, description, date_posted = _visible_detail(response.text, str(cfg["market"]))
            if not title:
                raise ValueError("title missing")
        except Exception as exc:
            errors.append(f"detail {url.rsplit('/', 1)[-1]}: {type(exc).__name__}")
            continue
        if not _relevant(title, description):
            continue
        external_id = url.rstrip("/").rsplit("/", 1)[-1]
        jobs.append({
            "job_id": hashlib.sha256(f"{source_id}|{external_id}".encode("utf-8")).hexdigest()[:16],
            "canonical_company_id": "",
            "company": company or "Employer not stated",
            "title": title,
            "description": description,
            "description_en": "",
            "translation_status": "pending",
            "market": cfg["market"],
            "location": location or cfg["market"],
            "priority_locations": location or cfg["market"],
            "job_url": url,
            "source_url": url,
            "source_id": source_id,
            "date_posted": date_posted,
            "discovered_at": now,
            "last_seen_at": now,
            "relevance_score": 1,
            "matched_terms": "Academic Work finance title",
            "verification": f"verified {source_id} vacancy detail",
            "status": "Open",
            "alternate_job_urls": "",
            "duplicate_count": 0,
            "calibration_score": "",
            "calibration_note": "",
        })
        time.sleep(0.08)
    return jobs, errors
