from __future__ import annotations

import re
from typing import Any

import pandas as pd


def _text(row: pd.Series) -> str:
    parts = [
        str(row.get("title", "")),
        str(row.get("description_display", "")),
        str(row.get("description", "")),
        str(row.get("matched_terms", "")),
        str(row.get("calibration_note", "")),
    ]
    return " ".join(parts).lower()


def _has_any(text: str, terms: list[str]) -> bool:
    return any(term in text for term in terms)


def _language_flag(text: str) -> str | None:
    german_required = re.search(
        r"(fluent|native|c1|c2|business fluent|verhandlungssicher)[^\.\n]{0,35}(german|deutsch)|"
        r"(german|deutsch)[^\.\n]{0,35}(fluent|native|c1|c2|business fluent|verhandlungssicher)",
        text,
    )
    if german_required:
        return "German fluent/C1/native appears required — red flag"

    other_languages = ["french", "français", "spanish", "español", "italian", "italiano", "dutch", "nederlands"]
    for language in other_languages:
        if re.search(
            rf"(fluent|native|c1|c2|business fluent)[^\.\n]{{0,35}}{re.escape(language)}|"
            rf"{re.escape(language)}[^\.\n]{{0,35}}(fluent|native|c1|c2|business fluent)",
            text,
        ):
            return f"Fluent/C1/native {language.title()} appears required — red flag"
    return None


def build_personal_fit_summary(row: pd.Series) -> str:
    text = _text(row)
    positives: list[str] = []
    concerns: list[str] = []
    constraints: list[str] = []

    # Stronger semantic fit signals from the user's CV / experience.
    if _has_any(text, ["treasury", "liquidity", "cash management", "financial risk", "market risk"]):
        positives.append("strong treasury/risk fit")
    if _has_any(text, ["derivative", "valuation", "pricing", "hedge accounting", "hedging"]):
        positives.append("valuation/derivatives experience relevant")
    if _has_any(text, ["fx", "foreign exchange", "interest rate", "irs", "commodity", "capital markets", "financial markets"]):
        positives.append("some markets exposure")
    if _has_any(text, ["python", " r ", "r programming", "sql"]):
        positives.append("Python/R/SQL relevant")
    if _has_any(text, ["bloomberg", "refinitiv", "reuters", "eikon"]):
        positives.append("market-data tools match")
    if _has_any(text, ["cfa", "frm", "financial risk manager", "chartered financial analyst"]):
        positives.append("CFA/FRM explicitly valued")
    if _has_any(text, ["lead team", "team lead", "people management", "manage a team", "line management", "mentor"]):
        positives.append("people-management opportunity")
    if _has_any(text, ["client presentation", "present to client", "client meetings", "client-facing", "stakeholder presentation"]):
        positives.append("client-facing without being purely internal")
    if _has_any(text, ["hybrid", "home office", "work from home", "flexible working"]):
        positives.append("hybrid/flexible setup mentioned")

    # Concerns / dislikes.
    if _has_any(text, ["compliance", "regulatory reporting", "regulatory compliance", "aml", "kyc", "financial crime"]):
        concerns.append("regulatory/compliance-heavy content")
    if _has_any(text, ["business development", "sales target", "origination", "new business generation", "revenue target"]):
        concerns.append("meaningful sales/business-development component")
    if _has_any(text, ["ifrs reporting", "statutory reporting", "financial reporting", "technical accounting"]):
        concerns.append("accounting/reporting-heavy content")
    if _has_any(text, ["software engineer", "quant researcher", "quantitative researcher", "machine learning engineer"]):
        concerns.append("may be more technically demanding than preferred")

    language = _language_flag(text)
    if language:
        constraints.append(language)
    elif _has_any(text, ["very good german", "good german", "working knowledge of german", "german advantageous", "german preferred"]):
        positives.append("German requirement looks manageable")

    # Keep outputs concise and avoid duplicate-like messages.
    positives = list(dict.fromkeys(positives))[:4]
    concerns = list(dict.fromkeys(concerns))[:3]
    constraints = list(dict.fromkeys(constraints))[:2]

    parts: list[str] = []
    if positives:
        parts.append("Positives: " + "; ".join(positives))
    if concerns:
        parts.append("Concerns: " + "; ".join(concerns))
    if constraints:
        parts.append("Constraints: " + "; ".join(constraints))
    if not parts:
        parts.append("No strong personal-fit signal detected from the available description")

    # Salary is deliberately separate from role fit. It will be populated once a
    # salary estimate/range exists for the opportunity.
    salary_min = pd.to_numeric(row.get("salary_est_min_local", None), errors="coerce")
    salary_max = pd.to_numeric(row.get("salary_est_max_local", None), errors="coerce")
    salary_target = pd.to_numeric(row.get("salary_target_local", None), errors="coerce")
    currency = str(row.get("salary_currency", "")).strip()
    if pd.notna(salary_target) and salary_target > 0 and (pd.notna(salary_min) or pd.notna(salary_max)):
        midpoint: float | None = None
        if pd.notna(salary_min) and pd.notna(salary_max):
            midpoint = (float(salary_min) + float(salary_max)) / 2
            range_text = f"{float(salary_min):,.0f}–{float(salary_max):,.0f} {currency}".strip()
        elif pd.notna(salary_min):
            midpoint = float(salary_min)
            range_text = f"from {float(salary_min):,.0f} {currency}".strip()
        else:
            midpoint = float(salary_max)
            range_text = f"up to {float(salary_max):,.0f} {currency}".strip()

        if midpoint is not None:
            gap = midpoint / float(salary_target) - 1
            if gap >= 0.10:
                verdict = "above target"
            elif gap <= -0.10:
                verdict = "below target"
            else:
                verdict = "around target"
            parts.append(
                f"Salary: estimated {range_text} vs. target {float(salary_target):,.0f} {currency} → {verdict}"
            )
    else:
        parts.append("Salary: unknown")

    return " | ".join(parts)
