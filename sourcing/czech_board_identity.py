from __future__ import annotations

import re

from bs4 import BeautifulSoup

from sourcing.g_data_quality import invalid_company_name


_GENERIC_PAGE_BRANDS = {
    "jobs.cz",
    "prace.cz",
    "práce.cz",
    "alma career",
    "...kde jinde.",
    "kde jinde",
}

_RECRUITER_PAGE_BRANDS = {
    "grafton.cz",
    "grafton recruitment",
    "manpower",
    "r4u",
    "hays",
    "hays czech republic",
}


def _clean(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _valid_company(value: object) -> str:
    company = _clean(value).strip(" |–—-")
    if not company or invalid_company_name(company):
        return ""
    if company.lower() in _GENERIC_PAGE_BRANDS | _RECRUITER_PAGE_BRANDS:
        return ""
    return company[:180]


def _company_from_vacancy_text(text: str) -> str:
    patterns = (
        r"Kam vám můžeme nabídku .*? u (.+?) poslat\?",
        r"Informace o pozici\s+Společnost\s+(.+?)(?=\s+(?:Required education|Required languages|Listed in|Employment form|Contract duration|Employer type|Odpovědět))",
        r"Detail nabídky\s+.*?\s+Společnost\s+(.+?)(?=\s+(?:Odpovědět|Required education|Required languages|Listed in|Employment form))",
    )
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            company = _valid_company(match.group(1))
            if company:
                return company
    return ""


def _company_from_page_brand(soup: BeautifulSoup) -> str:
    candidates: list[str] = []
    if soup.title:
        candidates.append(_clean(soup.title.get_text(" ", strip=True)))
    for selector in ('meta[property="og:title"]', 'meta[name="twitter:title"]'):
        node = soup.select_one(selector)
        if node:
            candidates.append(_clean(node.get("content")))

    for title in candidates:
        match = re.search(
            r"^(?:Detail pozice|Position detail|Vacancy detail)\s*[|–—-]\s*(.+?)$",
            title,
            flags=re.IGNORECASE,
        )
        if match:
            company = _valid_company(match.group(1))
            if company:
                return company
    return ""


def recover_czech_board_company(source_id: str, html: str, current_company: object = "") -> str:
    """Recover employer identity without guessing from generic navigation text."""
    existing = _valid_company(current_company)
    if existing:
        return existing
    if source_id not in {"jobs-cz", "prace-cz"}:
        return ""

    soup = BeautifulSoup(html, "html.parser")
    text = _clean(soup.get_text(" ", strip=True))

    company = _company_from_vacancy_text(text)
    if company:
        return company

    company = _company_from_page_brand(soup)
    if company:
        return company

    if "Skupiny ČEZ" in text or "Skupině ČEZ" in text:
        return "ČEZ Group"

    return ""
