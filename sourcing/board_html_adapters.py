"""HTML search adapters for Workstream G national/commercial job boards.

Retrieval/verification only. Personal fit remains downstream in Workstream C.
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

from sourcing.czech_board_identity import recover_czech_board_company
from sourcing.g_data_quality import invalid_company_name

HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9,de;q=0.8,cs;q=0.8",
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
    soup = BeautifulSoup(html, "html.parser")
    if source_id == "jobs-cz":
        base, predicates = "https://www.jobs.cz", ("/rpd/",)
    elif source_id == "prace-cz":
        base, predicates = "https://www.prace.cz", ("/nabidka/",)
    elif source_id == "stepstone-at":
        base, predicates = "https://www.stepstone.at", ("/stellenangebote--",)
    elif source_id == "stepstone-de":
        base, predicates = "https://www.stepstone.de", ("/stellenangebote--",)
    elif source_id == "karriere-at":
        base, predicates = "https://www.karriere.at", ("/jobs/",)
    elif source_id == "stellenanzeigen-de":
        base, predicates = "https://www.stellenanzeigen.de", ("/job/",)
    elif source_id == "willhaben-at":
        base, predicates = "https://www.willhaben.at", ("/jobs/job/",)
    elif source_id == "jobbsafari-se":
        base, predicates = "https://jobbsafari.se", ("/jobb/",)
    else:
        raise ValueError(f"Unsupported HTML board source: {source_id}")

    found: list[str] = []
    for anchor in soup.find_all("a", href=True):
        href = str(anchor.get("href") or "")
        if not any(marker in href for marker in predicates):
            continue
        if source_id == "karriere-at" and not re.search(r"/jobs/\d+(?:[/?#]|$)", href):
            continue
        clean_href = href.split("#", 1)[0]
        # Jobs.cz/Prace.cz append search-context parameters that can change the
        # returned detail document. Store and fetch the canonical vacancy URL.
        if source_id in {"jobs-cz", "prace-cz"}:
            clean_href = clean_href.split("?", 1)[0]
        else:
            clean_href = clean_href.split("?utm_", 1)[0]
        full = urljoin(base, clean_href)
        if full not in found:
            found.append(full)
        if len(found) >= limit:
            break
    return found


def _jsonld_jobposting(html: str) -> dict | None:
    soup = BeautifulSoup(html, "html.parser")
    for node in soup.select('script[type="application/ld+json"]'):
        try:
            value = json.loads(node.string or node.get_text())
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


def _fallback_detail(html: str) -> dict | None:
    soup = BeautifulSoup(html, "html.parser")
    h1 = soup.find("h1")
    title = _clean(h1.get_text(" ", strip=True) if h1 else "")
    if not title:
        meta = soup.find("meta", attrs={"property": "og:title"})
        title = _clean(meta.get("content") if meta else "")
    if not title:
        return None
    company = ""
    # Generic fallback is useful for many boards, but Czech Jobs/Prace identity
    # is subsequently revalidated from vacancy-specific text/page branding.
    for selector in ("[class*=company]", "[class*=employer]", "h2", "h3"):
        for node in soup.select(selector):
            candidate = _clean(node.get_text(" ", strip=True))
            if candidate and candidate != title and not invalid_company_name(candidate):
                company = candidate[:180]
                break
        if company:
            break
    return {
        "title": title,
        "hiringOrganization": {"name": company or "Employer not stated"},
        "description": _clean(soup.get_text(" ", strip=True))[:16000],
        "identifier": "",
        "datePosted": "",
        "jobLocation": [],
    }


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
        text = ", ".join(str(address.get(k) or "") for k in ("addressLocality", "addressRegion", "addressCountry") if address.get(k))
        if text:
            bits.append(_clean(text))
    return "; ".join(dict.fromkeys(bits)) or fallback


def _description(item: dict) -> str:
    return _clean(BeautifulSoup(str(item.get("description") or ""), "html.parser").get_text(" "))


def _slug(query: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", query.lower()).strip("-")


def _search_url(source_id: str, query: str) -> str:
    if source_id == "jobs-cz":
        return "https://www.jobs.cz/prace/?q%5B%5D=" + quote(query)
    if source_id == "prace-cz":
        return "https://www.prace.cz/nabidky/finance-a-ekonomika/"
    if source_id == "stepstone-at":
        return f"https://www.stepstone.at/jobs/{_slug(query)}"
    if source_id == "stepstone-de":
        return f"https://www.stepstone.de/jobs/{_slug(query)}"
    if source_id == "karriere-at":
        return f"https://www.karriere.at/jobs/{_slug(query)}"
    if source_id == "stellenanzeigen-de":
        return f"https://www.stellenanzeigen.de/jobs/{_slug(query)}/"
    if source_id == "willhaben-at":
        return f"https://www.willhaben.at/jobs/suche/{_slug(query)}"
    if source_id == "jobbsafari-se":
        return "https://jobbsafari.se/lediga-jobb?sok=" + quote(query)
    raise ValueError(f"Unsupported HTML board source: {source_id}")


def discover_html_jsonld_board(source_id: str, market: str, queries: list[str], per_query: int, max_details: int) -> tuple[list[dict], list[str]]:
    now = datetime.now(timezone.utc).isoformat()
    candidates: dict[str, set[str]] = {}
    errors: list[str] = []
    search_queries = ["finance-category"] if source_id == "prace-cz" else queries
    for query in search_queries:
        try:
            response = requests.get(_search_url(source_id, query), headers=HEADERS, timeout=35)
            response.raise_for_status()
            link_limit = max_details if source_id == "prace-cz" else per_query
            links = extract_html_search_links(source_id, response.text, link_limit)
            if not links:
                errors.append(f"search {query}: no detail links")
            for link in links:
                candidates.setdefault(link, set()).add(query)
        except Exception as exc:
            status = getattr(getattr(exc, "response", None), "status_code", "")
            errors.append(f"search {query}: {type(exc).__name__}{f' {status}' if status else ''}")
        time.sleep(0.12)

    jobs: list[dict] = []
    for url, matched in list(candidates.items())[:max_details]:
        try:
            response = requests.get(url, headers=HEADERS, timeout=35)
            response.raise_for_status()
            item = _jsonld_jobposting(response.text)
            used_fallback = item is None
            if used_fallback:
                item = _fallback_detail(response.text)
            if not item:
                raise ValueError("job detail missing")
        except Exception as exc:
            errors.append(f"detail {url.rsplit('/', 1)[-1][:50]}: {type(exc).__name__}")
            continue
        title = _clean(item.get("title"))
        if not title or not _relevant_title(title):
            continue
        organization = item.get("hiringOrganization") or {}
        if not isinstance(organization, dict):
            organization = {}
        company = _clean(organization.get("name"))
        if source_id in {"jobs-cz", "prace-cz"} and (used_fallback or invalid_company_name(company)):
            # Do not trust generic h2/h3 navigation text on Czech branded
            # microsites. Recover only from explicit vacancy labels/page brand.
            company = recover_czech_board_company(
                source_id,
                response.text,
                "" if used_fallback else company,
            )
        if invalid_company_name(company):
            company = "Employer not stated"
        identifier = item.get("identifier") or ""
        external_id = _clean(identifier.get("value")) if isinstance(identifier, dict) else _clean(identifier)
        location = _location(item, market)
        jobs.append({
            "job_id": _stable_id(source_id, external_id, url), "canonical_company_id": "",
            "company": company or "Employer not stated", "title": title,
            "description": _description(item), "description_en": "", "translation_status": "pending",
            "market": market, "location": location, "priority_locations": location,
            "job_url": url, "source_url": url, "source_id": source_id,
            "date_posted": _clean(item.get("datePosted")), "discovered_at": now, "last_seen_at": now,
            "relevance_score": len(matched), "matched_terms": "; ".join(sorted(matched)),
            "verification": f"verified {source_id} vacancy detail", "status": "Open",
            "alternate_job_urls": "", "duplicate_count": 0, "calibration_score": "", "calibration_note": "",
        })
        time.sleep(0.12)
    return jobs, errors
