"""Official/public national vacancy sources for Workstream G.

Prefer these over commercial board scraping where a sustainable public data
source exists. Retrieval only; semantic fit stays in Workstream C.
"""
from __future__ import annotations

import gzip
import hashlib
import re
from datetime import datetime, timezone
from urllib.parse import quote, urljoin

import ijson
import requests
from bs4 import BeautifulSoup

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; ProfessionalDashboard/0.5; +https://github.com/ORosa10/ProfessionalDashboard)"
}

TITLE_MARKERS = (
    "treasury", "cash management", "liquidity", "finance", "financial", "controller",
    "controlling", "corporate finance", "corporate development", "m&a", "valuation",
    "investment", "portfolio", "risk", "restructuring", "transaction", "asset management",
    "capital markets", "financial instruments", "derivatives", "hedging",
)


def _clean(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _relevant_title(value: object) -> bool:
    title = _clean(value).lower()
    return any(marker in title for marker in TITLE_MARKERS)


def _stable_id(source_id: str, external_id: str, url: str) -> str:
    return hashlib.sha256(f"{source_id}|{external_id or url}".encode("utf-8")).hexdigest()[:16]


def discover_mpsv(max_details: int) -> tuple[list[dict], list[str]]:
    """Stream the official full Czech vacancy dataset without loading it into RAM."""
    source_id = "mpsv-open-data-cz"
    data_url = "https://data.mpsv.cz/od/soubory/volna-mista/volna-mista.json.gz"
    dataset_url = "https://data.mpsv.cz/web/data/volna-mista-za-celou-cr"
    now = datetime.now(timezone.utc).isoformat()
    jobs: list[dict] = []
    errors: list[str] = []
    try:
        response = requests.get(data_url, headers=HEADERS, stream=True, timeout=90)
        response.raise_for_status()
        response.raw.decode_content = False
        with gzip.GzipFile(fileobj=response.raw) as fh:
            for item in ijson.items(fh, "polozky.item"):
                title_obj = item.get("pozadovanaProfese") or {}
                title = _clean(title_obj.get("cs") if isinstance(title_obj, dict) else title_obj)
                if not _relevant_title(title):
                    continue
                employer = item.get("zamestnavatel") or {}
                company = _clean(employer.get("nazev") if isinstance(employer, dict) else "") or "Employer not stated"
                info = item.get("upresnujiciInformace") or {}
                description = _clean(info.get("cs") if isinstance(info, dict) else info)
                place = item.get("mistoVykonuPrace") or {}
                location = "Czechia"
                if isinstance(place, dict):
                    location = _clean(place.get("adresaText")) or ""
                    workplaces = place.get("pracoviste") or []
                    if not location and workplaces:
                        names = [_clean(w.get("nazev")) for w in workplaces if isinstance(w, dict) and w.get("nazev")]
                        location = "; ".join(dict.fromkeys(names))
                    location = location or "Czechia"
                external_id = _clean(item.get("portalId") or item.get("id") or item.get("referencniCislo"))
                employer_url = _clean(item.get("urlAdresa"))
                job_url = employer_url or dataset_url
                jobs.append({
                    "job_id": _stable_id(source_id, external_id, job_url),
                    "canonical_company_id": "",
                    "company": company,
                    "title": title,
                    "description": description,
                    "description_en": "",
                    "translation_status": "pending",
                    "market": "Czechia",
                    "location": location,
                    "priority_locations": location,
                    "job_url": job_url,
                    "source_url": dataset_url,
                    "source_id": source_id,
                    "date_posted": _clean(item.get("datumVlozeni")),
                    "discovered_at": now,
                    "last_seen_at": now,
                    "relevance_score": 1,
                    "matched_terms": "official MPSV vacancy dataset",
                    "verification": "official MPSV/ÚP open-data vacancy",
                    "status": "Open",
                    "alternate_job_urls": "",
                    "duplicate_count": 0,
                    "calibration_score": "",
                    "calibration_note": "",
                })
                if len(jobs) >= max_details:
                    break
    except Exception as exc:
        errors.append(f"dataset: {type(exc).__name__}: {exc}")
    return jobs, errors


def extract_findajob_links(html: str, limit: int) -> list[str]:
    soup = BeautifulSoup(html, "html.parser")
    found: list[str] = []
    for anchor in soup.find_all("a", href=True):
        href = str(anchor.get("href") or "")
        if not re.match(r"^/details/\d+$", href):
            continue
        full = urljoin("https://findajob.dwp.gov.uk", href)
        if full not in found:
            found.append(full)
        if len(found) >= limit:
            break
    return found


def _label_value(text: str, label: str) -> str:
    match = re.search(rf"{re.escape(label)}\s*:\s*([^\n]+)", text, flags=re.I)
    return _clean(match.group(1)) if match else ""


def _findajob_detail(url: str) -> dict | None:
    response = requests.get(url, headers=HEADERS, timeout=35)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")
    h1 = soup.find("h1")
    title = _clean(h1.get_text(" ", strip=True) if h1 else "")
    if not title:
        return None
    text = soup.get_text("\n", strip=True)
    company = _label_value(text, "Company") or "Employer not stated"
    location = _label_value(text, "Location") or "United Kingdom"
    date_posted = _label_value(text, "Posting date")
    summary_heading = next((h for h in soup.find_all(["h2", "h3"]) if _clean(h.get_text()).lower() == "summary"), None)
    description_parts: list[str] = []
    if summary_heading:
        for node in summary_heading.find_all_next():
            if node is summary_heading:
                continue
            if node.name in {"h1", "h2"}:
                break
            if node.name in {"p", "li"}:
                value = _clean(node.get_text(" ", strip=True))
                if value and value not in description_parts:
                    description_parts.append(value)
    return {
        "title": title,
        "company": company,
        "location": location,
        "date_posted": date_posted,
        "description": _clean(" ".join(description_parts)),
    }


def discover_findajob(queries: list[str], per_query: int, max_details: int) -> tuple[list[dict], list[str]]:
    source_id = "findajob-uk"
    now = datetime.now(timezone.utc).isoformat()
    candidates: dict[str, set[str]] = {}
    errors: list[str] = []
    for query in queries:
        try:
            response = requests.get(
                "https://findajob.dwp.gov.uk/search",
                params={"q": query, "pp": min(50, max(10, per_query))},
                headers=HEADERS,
                timeout=35,
            )
            response.raise_for_status()
            links = extract_findajob_links(response.text, per_query)
            if not links:
                errors.append(f"search {query}: no detail links")
            for link in links:
                candidates.setdefault(link, set()).add(query)
        except Exception as exc:
            errors.append(f"search {query}: {type(exc).__name__}")

    jobs: list[dict] = []
    for url, matched in list(candidates.items())[:max_details]:
        try:
            item = _findajob_detail(url)
            if not item:
                raise ValueError("detail parse failed")
        except Exception as exc:
            errors.append(f"detail {url.rsplit('/', 1)[-1]}: {type(exc).__name__}")
            continue
        if not _relevant_title(item["title"]):
            continue
        external_id = url.rsplit("/", 1)[-1]
        jobs.append({
            "job_id": _stable_id(source_id, external_id, url),
            "canonical_company_id": "",
            "company": item["company"],
            "title": item["title"],
            "description": item["description"],
            "description_en": item["description"],
            "translation_status": "original-en",
            "market": "United Kingdom",
            "location": item["location"],
            "priority_locations": item["location"],
            "job_url": url,
            "source_url": url,
            "source_id": source_id,
            "date_posted": item["date_posted"],
            "discovered_at": now,
            "last_seen_at": now,
            "relevance_score": len(matched),
            "matched_terms": "; ".join(sorted(matched)),
            "verification": "official DWP Find a job vacancy detail",
            "status": "Open",
            "alternate_job_urls": "",
            "duplicate_count": 0,
            "calibration_score": "",
            "calibration_note": "",
        })
    return jobs, errors
