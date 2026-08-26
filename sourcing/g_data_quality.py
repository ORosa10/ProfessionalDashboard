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

# These are deliberately stems because German/Nordic finance words are commonly
# compounded (Finanzanalyst, finansanalytiker, økonom...). Other markers should
# respect token boundaries so e.g. "valuation" never matches "evaluation".
FINANCE_MARKER_STEMS = {"finanz", "finans", "økonom"}


def invalid_company_name(value: object) -> bool:
    text = str(value or "").strip()
    return any(re.search(pattern, text, flags=re.IGNORECASE) for pattern in INVALID_COMPANY_PATTERNS)


def invalid_job_title(value: object) -> bool:
    text = str(value or "").strip()
    if not text:
        return True
    return any(re.search(pattern, text, flags=re.IGNORECASE) for pattern in INVALID_TITLE_PATTERNS)


def finance_marker_present(text: object, marker: object) -> bool:
    haystack = str(text or "").lower()
    needle = str(marker or "").lower().strip()
    if not needle:
        return False
    if needle in FINANCE_MARKER_STEMS:
        return needle in haystack
    # Permit simple plural forms while preventing substring collisions such as
    # valuation/evaluation. This also works for phrases and markers containing &.
    pattern = rf"(?<!\w){re.escape(needle)}(?:s|es)?(?!\w)"
    return re.search(pattern, haystack, flags=re.IGNORECASE) is not None


def any_finance_marker(text: object, markers: tuple[str, ...] | list[str]) -> bool:
    return any(finance_marker_present(text, marker) for marker in markers)
