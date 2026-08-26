from __future__ import annotations

import re
from urllib.parse import urlparse, urlunparse

import pandas as pd

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


def normalise_vacancy_url(value: object) -> str:
    """Return a stable URL key without tracking parameters/fragments."""
    raw = str(value or "").strip()
    if not raw:
        return ""
    parsed = urlparse(raw)
    if not parsed.scheme or not parsed.netloc:
        return raw.rstrip("/").lower()
    return urlunparse((parsed.scheme.lower(), parsed.netloc.lower(), parsed.path.rstrip("/"), "", "", ""))


def quality_flags(row: object) -> list[str]:
    """Identify blocking identity/detail issues without changing the role."""
    get = row.get if hasattr(row, "get") else lambda key, default="": default
    flags: list[str] = []
    if invalid_job_title(get("title", "")):
        flags.append("missing_or_invalid_title")
    if invalid_company_name(get("company", "")):
        flags.append("missing_or_invalid_company")
    if not normalise_vacancy_url(get("job_url", "")):
        flags.append("missing_job_url")
    description = str(get("description_en", "") or get("description", "") or "").strip()
    if len(description) < 160:
        flags.append("thin_description")
    return flags


def audit_g_frame(frame: pd.DataFrame) -> pd.DataFrame:
    """Create a deterministic per-role quality report for any G lane."""
    if frame.empty:
        return pd.DataFrame(columns=["opportunity_id", "source_id", "quality_status", "quality_flags"])
    out = frame.copy().fillna("")
    if "job_id" in out.columns and "opportunity_id" not in out.columns:
        out["opportunity_id"] = out["job_id"]
    for col in ("opportunity_id", "source_id"):
        if col not in out.columns:
            out[col] = ""
    out["quality_flags"] = out.apply(lambda row: ";".join(quality_flags(row)), axis=1)
    out["quality_status"] = out["quality_flags"].map(lambda value: "review" if value else "ready")
    return out[["opportunity_id", "source_id", "quality_status", "quality_flags"]]


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
