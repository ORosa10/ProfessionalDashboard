"""Jobbsafari Norway retrieval adapter for Workstream G."""
from __future__ import annotations

import hashlib
import json
import re
import time
from datetime import datetime, timezone
from urllib.parse import quote, urljoin

import requests
from bs4 import BeautifulSoup

BASE = "https://jobbsafari.no"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "nb-NO,nb;q=0.9,en;q=0.8",
}
MARKERS = ("treasury", "finance", "financial", "finans", "controller", "corporate finance", "investment", "investering", "portfolio", "risk", "risiko", "liquidity", "likvid", "cash management", "capital markets", "asset management", "valuation")


def _clean(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def extract_links(html: str, limit: int) -> list[str]:
    soup = BeautifulSoup(html, "html.parser"); found = []
    for a in soup.find_all("a", href=True):
        href = str(a.get("href") or "").split("?", 1)[0]
        if not href.startswith("/jobb/"): continue
        full = urljoin(BASE, href)
        if full not in found: found.append(full)
        if len(found) >= limit: break
    return found


def _jsonld(html: str) -> dict | None:
    soup = BeautifulSoup(html, "html.parser")
    for node in soup.select('script[type="application/ld+json"]'):
        try: value = json.loads(node.string or node.get_text())
        except Exception: continue
        values = value if isinstance(value, list) else [value]
        for item in values:
            if isinstance(item, dict) and item.get("@type") == "JobPosting": return item
    return None


def discover_jobbsafari_no(queries: list[str], per_query: int, max_details: int) -> tuple[list[dict], list[str]]:
    now = datetime.now(timezone.utc).isoformat(); candidates: dict[str, set[str]] = {}; errors = []
    for query in queries:
        try:
            r = requests.get(BASE + "/ledige-stillinger", params={"sok": query}, headers=HEADERS, timeout=35); r.raise_for_status()
            for link in extract_links(r.text, per_query): candidates.setdefault(link, set()).add(query)
        except Exception as exc:
            status = getattr(getattr(exc, "response", None), "status_code", ""); errors.append(f"search {query}: {type(exc).__name__}{f' {status}' if status else ''}")
        time.sleep(0.08)
    jobs = []
    for url, matched in list(candidates.items())[:max_details]:
        try:
            r = requests.get(url, headers=HEADERS, timeout=35); r.raise_for_status(); soup = BeautifulSoup(r.text, "html.parser"); item = _jsonld(r.text)
            if item:
                title = _clean(item.get("title")); org = item.get("hiringOrganization") or {}; company = _clean(org.get("name")) if isinstance(org, dict) else ""; desc = _clean(BeautifulSoup(str(item.get("description") or ""), "html.parser").get_text(" ")); date_posted = _clean(item.get("datePosted"))
            else:
                h1 = soup.find("h1"); title = _clean(h1.get_text(" ") if h1 else ""); company = "Employer not stated"; desc = _clean(soup.get_text(" "))[:16000]; date_posted = ""
            if not title or not any(m in title.lower() for m in MARKERS): continue
        except Exception as exc:
            errors.append(f"detail {url.rsplit('/', 1)[-1]}: {type(exc).__name__}"); continue
        job_id = hashlib.sha256(f"jobbsafari-no|{url}".encode()).hexdigest()[:16]
        jobs.append({"job_id": job_id, "canonical_company_id": "", "company": company or "Employer not stated", "title": title, "description": desc, "description_en": "", "translation_status": "pending", "market": "Norway", "location": "Norway", "priority_locations": "Norway", "job_url": url, "source_url": url, "source_id": "jobbsafari-no", "date_posted": date_posted, "discovered_at": now, "last_seen_at": now, "relevance_score": len(matched), "matched_terms": "; ".join(sorted(matched)), "verification": "verified Jobbsafari Norway vacancy detail", "status": "Open", "alternate_job_urls": "", "duplicate_count": 0, "calibration_score": "", "calibration_note": ""})
    return jobs, errors
