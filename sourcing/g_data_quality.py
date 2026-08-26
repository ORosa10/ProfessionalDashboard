from __future__ import annotations

import re

INVALID_COMPANY_PATTERNS = [
    r"^\s*$",
    r"^\s*employer not stated\s*$",
    r"^\s*linkedin\s*$",
    r"^\s*nabídka\s+pracovní\s+nabídka",
    r"^\s*poslat\s+nabídku\s+na\s+e-mail",
    r"^\s*navštivte\s+naše\s+sociální\s+sítě",
    r"^\s*práce\s+v\s+oboru",
    r"^\s*firmenprofil\+?\s*firmenprofil",
]

INVALID_TITLE_PATTERNS = [
    r"^\s*[\d\s.,’']+\s+jobs?\s+für\s+deine\s+suche\s*$",
    r"^\s*[\d\s.,’']+\s+jobs?\s+for\s+your\s+search\s*$",
    r"^\s*jobs?\s+für\s+deine\s+suche\s*$",
    r"^\s*search results?\s*$",
]


def invalid_company_name(value: object) -> bool:
    text = str(value or "").strip()
    return any(re.search(pattern, text, flags=re.IGNORECASE) for pattern in INVALID_COMPANY_PATTERNS)


def invalid_job_title(value: object) -> bool:
    text = str(value or "").strip()
    if not text:
        return True
    return any(re.search(pattern, text, flags=re.IGNORECASE) for pattern in INVALID_TITLE_PATTERNS)
