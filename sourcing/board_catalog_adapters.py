"""Config-driven HTML catalogue adapters for Workstream G.

Retrieval only; downstream C remains responsible for semantic fit.
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
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9,de;q=0.8,da;q=0.8,fi;q=0.8,no;q=0.8,sv;q=0.8",
}
TITLE_MARKERS = (
    "treasury", "finance", "financial", "finans", "finanz", "fp&a", "controller",
    "controlling", "corporate finance", "corporate development", "m&a", "valuation",
    "investment", "investering", "portfolio", "risk", "liquidity", "cash management",
    "transaction", "private equity", "asset management", "equity research", "credit",
    "rahoitus", "talouspäällikkö", "økonomi", "økonom", "analyse", "analytiker", "regnskab",
)
CONFIG = {
    "startupjobs-cz": {"market": "Czechia", "base": "https://www.startupjobs.cz", "listing": "https://www.startupjobs.cz/nabidky/finance", "patterns": (r"/nabidka/\d+/",)},
    "cocuma-cz": {"market": "Czechia", "base": "https://www.cocuma.cz", "listing": "https://www.cocuma.cz/jobs/", "patterns": (r"/job/",)},
    "jobwinner-ch": {"market": "Switzerland", "base": "https://www.jobwinner.ch", "listing": "https://www.jobwinner.ch/de/jobs?q={query}", "patterns": (r"/job/\d+",)},
    "nzz-jobs-ch": {"market": "Switzerland", "base": "https://jobs.nzz.ch", "listing": "https://jobs.nzz.ch/", "patterns": (r"/job/",)},
    "jobserve-uk": {"market": "United Kingdom", "base": "https://www.jobserve.com", "listing": "https://www.jobserve.com/gb/en/search-jobs-in-Greater-London%2C-London%2C-United-Kingdom/", "patterns": (r"/search-jobs-in-.+?/[A-Z0-9-]+/", r"/job-in-.+?/")},
    "jobbland-se": {"market": "Sweden", "base": "https://jobbland.se", "listing": "https://jobbland.se/lediga-jobb/kategori/ekonomi", "patterns": (r"/jobb/",)},
    "ledigajobb-se": {"market": "Sweden", "base": "https://ledigajobb.se", "listing": "https://ledigajobb.se/pr/finance-business-partner-jobb", "patterns": (r"/jobb/",)},
    "finansavisen-no": {"market": "Norway", "base": "https://www.finansavisen.no", "listing": "https://www.finansavisen.no/stillinger", "patterns": (r"/stillinger/", r"/jobb/")},
    "jobbank-dk": {"market": "Denmark", "base": "https://jobbank.dk", "listing": "https://jobbank.dk/job/?key={query}", "fallback_listing": "https://jobbank.dk/job/", "patterns": (r"/job/\d+",)},
    "jobdanmark-dk": {"market": "Denmark", "base": "https://jobdanmark.dk", "listing": "https://jobdanmark.dk/", "patterns": (r"/job/",)},
    "jobunivers-dk": {"market": "Denmark", "base": "https://www.jobunivers.dk", "listing": "https://www.jobunivers.dk/job/finans-oekonomi-og-regnskab/", "patterns": (r"[?&]job=\d+",)},
    "barona-fi": {"market": "Finland", "base": "https://www.baronacareers.com", "listing": "https://www.baronacareers.com/fi/fi/job/finance-accounting", "patterns": (r"/fi/fi/jobs/",)},
}


def _clean(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _stable_id(source_id: str, url: str) -> str:
    return hashlib.sha256(f"{source_id}|{url}".encode()).hexdigest()[:16]


def _relevant(title: str, description: str = "") -> bool:
    text = f"{title} {description}".lower(); return any(marker in text for marker in TITLE_MARKERS)


def _jobposting(html: str) -> dict | None:
    soup = BeautifulSoup(html, "html.parser")
    for node in soup.select('script[type="application/ld+json"]'):
        try: value = json.loads(node.string or node.get_text())
        except (json.JSONDecodeError, TypeError): continue
        queue = value if isinstance(value, list) else [value]
        for item in queue:
            if isinstance(item, dict) and item.get("@type") == "JobPosting": return item
            if isinstance(item, dict) and isinstance(item.get("@graph"), list):
                for nested in item["@graph"]:
                    if isinstance(nested, dict) and nested.get("@type") == "JobPosting": return nested
    return None


def extract_catalog_links(source_id: str, html: str, limit: int) -> list[str]:
    cfg = CONFIG[source_id]; soup = BeautifulSoup(html, "html.parser"); found: list[str] = []
    for anchor in soup.find_all("a", href=True):
        href = str(anchor.get("href") or "")
        if not any(re.search(pattern, href, flags=re.I) for pattern in cfg["patterns"]): continue
        full = urljoin(cfg["base"], href.split("#", 1)[0])
        if full.rstrip("/") in {str(cfg["listing"]).rstrip("/"), str(cfg.get("fallback_listing", "")).rstrip("/")}: continue
        if full not in found: found.append(full)
        if len(found) >= limit: break
    return found


def _fallback_detail(html: str) -> tuple[str, str, str, str]:
    soup = BeautifulSoup(html, "html.parser"); h1 = soup.find("h1"); title = _clean(h1.get_text(" ") if h1 else "")
    if not title:
        meta = soup.find("meta", attrs={"property": "og:title"}); title = _clean(meta.get("content") if meta else "")
    company = ""
    for selector in ("[class*=company]", "[class*=employer]", "h2", "h3"):
        node = soup.select_one(selector); candidate = _clean(node.get_text(" ")) if node else ""
        if candidate and candidate != title: company = candidate[:180]; break
    return title, company or "Employer not stated", "", _clean(soup.get_text(" "))[:16000]


def _from_jsonld(item: dict) -> tuple[str, str, str, str, str]:
    title = _clean(item.get("title")); org = item.get("hiringOrganization") or {}; company = _clean(org.get("name")) if isinstance(org, dict) else ""; desc = _clean(BeautifulSoup(str(item.get("description") or ""), "html.parser").get_text(" ")); locations = item.get("jobLocation") or []
    if isinstance(locations, dict): locations = [locations]
    locs = []
    for loc in locations:
        if isinstance(loc, dict):
            address = loc.get("address") or loc
            if isinstance(address, dict):
                text = ", ".join(str(address.get(k) or "") for k in ("addressLocality", "addressRegion", "addressCountry") if address.get(k))
                if text: locs.append(_clean(text))
    return title, company or "Employer not stated", "; ".join(dict.fromkeys(locs)), desc, _clean(item.get("datePosted"))


def extract_detail_fields(source_id: str, html: str) -> tuple[str, str, str, str, str]:
    """Extract one vacancy detail with source-specific integrity safeguards.

    Jobbland pages can contain multiple job-related structured fragments and
    recommendation/tag text below the actual vacancy. The visible page H1 is the
    authoritative title for the current detail URL, so prefer it over a possibly
    misleading JSON-LD JobPosting title while retaining JSON-LD metadata for the
    employer, location, description and date.
    """
    item = _jobposting(html)
    if item:
        title, company, location, description, date_posted = _from_jsonld(item)
    else:
        title, company, location, description = _fallback_detail(html)
        date_posted = ""

    if source_id == "jobbland-se":
        soup = BeautifulSoup(html, "html.parser")
        h1 = soup.find("h1")
        visible_title = _clean(h1.get_text(" ") if h1 else "")
        if visible_title:
            title = visible_title
    return title, company, location, description, date_posted


def _get_listing(url: str) -> requests.Response:
    response = requests.get(url, headers=HEADERS, timeout=35); response.raise_for_status(); return response


def discover_catalog_board(source_id: str, queries: list[str], per_query: int, max_details: int) -> tuple[list[dict], list[str]]:
    cfg = CONFIG[source_id]; now = datetime.now(timezone.utc).isoformat(); template = str(cfg["listing"]); query_list = queries if "{query}" in template else [""]; candidates: dict[str, set[str]] = {}; errors: list[str] = []
    for query in query_list:
        listing = template.format(query=quote(query))
        try:
            response = _get_listing(listing); limit = per_query if "{query}" in template else max_details; links = extract_catalog_links(source_id, response.text, limit)
            if not links and cfg.get("fallback_listing"):
                response = _get_listing(str(cfg["fallback_listing"])); links = extract_catalog_links(source_id, response.text, max_details)
            if not links: errors.append(f"search {query or 'catalog'}: no detail links")
            for link in links: candidates.setdefault(link, set()).add(query or "catalog")
        except Exception as exc:
            if cfg.get("fallback_listing"):
                try:
                    response = _get_listing(str(cfg["fallback_listing"]))
                    for link in extract_catalog_links(source_id, response.text, max_details): candidates.setdefault(link, set()).add(query or "catalog")
                    continue
                except Exception: pass
            status = getattr(getattr(exc, "response", None), "status_code", ""); errors.append(f"search {query or 'catalog'}: {type(exc).__name__}{f' {status}' if status else ''}")
        time.sleep(0.08)
    jobs: list[dict] = []
    for url, matched in list(candidates.items())[:max_details]:
        try:
            response = requests.get(url, headers=HEADERS, timeout=35); response.raise_for_status()
            title, company, location, description, date_posted = extract_detail_fields(source_id, response.text)
            if not title: raise ValueError("title missing")
        except Exception as exc:
            errors.append(f"detail {url[-60:]}: {type(exc).__name__}"); continue
        if not _relevant(title, description[:2500]): continue
        location = location or str(cfg["market"])
        jobs.append({"job_id": _stable_id(source_id, url), "canonical_company_id": "", "company": company, "title": title, "description": description, "description_en": "", "translation_status": "pending", "market": cfg["market"], "location": location, "priority_locations": location, "job_url": url, "source_url": url, "source_id": source_id, "date_posted": date_posted, "discovered_at": now, "last_seen_at": now, "relevance_score": len(matched), "matched_terms": "; ".join(sorted(matched)), "verification": f"verified {source_id} HTML detail", "status": "Open", "alternate_job_urls": "", "duplicate_count": 0, "calibration_score": "", "calibration_note": ""})
        time.sleep(0.08)
    return jobs, errors
