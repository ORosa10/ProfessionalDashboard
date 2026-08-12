from __future__ import annotations

import re

import pandas as pd


def _text(row: pd.Series) -> str:
    parts = [
        str(row.get("title", "")),
        str(row.get("description_display", "")),
        str(row.get("description_en", "")),
        str(row.get("description", "")),
        str(row.get("matched_terms", "")),
        str(row.get("calibration_note", "")),
    ]
    return " ".join(parts).lower()


def _has_any(text: str, terms: list[str] | tuple[str, ...]) -> bool:
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


def personal_fit_signals(row: pd.Series) -> dict[str, object]:
    """Return transparent personal-fit signals used by both sourcing and the UI.

    The score is only a ranking aid. It deliberately does not hard-exclude roles; the
    user's Interested/Maybe/Pass feedback remains the stronger learning signal.
    """
    text = _text(row)
    title = str(row.get("title", "")).lower()
    score = 50
    positives: list[str] = []
    concerns: list[str] = []
    constraints: list[str] = []

    # Stronger CV / experience fit.
    if _has_any(text, ["treasury", "liquidity", "cash management", "financial risk", "market risk"]):
        positives.append("strong treasury/risk fit")
        score += 14
    if _has_any(text, ["derivative", "valuation", "pricing", "hedge accounting", "hedging"]):
        positives.append("valuation/derivatives experience relevant")
        score += 12
    if _has_any(text, ["investment", "portfolio", "private equity", "m&a", "transaction", "corporate finance"]):
        positives.append("investment/transaction experience relevant")
        score += 7
    if _has_any(text, ["financial modelling", "financial modeling", "analytics", "data analysis", "quantitative"]):
        positives.append("analytical/modelling fit")
        score += 7
    if _has_any(title, ["senior consultant", "financial due diligence", "finance transformation", "strategy & execution"]):
        positives.append("seniority/topic resembles early positive feedback")
        score += 5
    if _has_any(title, ["controller", "controlling"]):
        positives.append("controlling remains a viable exploration lane")
        score += 3

    # Soft positives: useful but intentionally small.
    if _has_any(text, ["fx", "foreign exchange", "interest rate", "irs", "commodity", "capital markets", "financial markets"]):
        positives.append("some markets exposure")
        score += 4
    if _has_any(text, ["python", " r ", "r programming", "sql"]):
        positives.append("Python/R/SQL relevant")
        score += 4
    if _has_any(text, ["bloomberg", "refinitiv", "reuters", "eikon"]):
        positives.append("market-data tools match")
        score += 3
    if _has_any(text, ["cfa", "frm", "financial risk manager", "chartered financial analyst"]):
        positives.append("CFA/FRM explicitly valued")
        score += 4
    if _has_any(text, ["lead team", "team lead", "people management", "manage a team", "line management", "mentor", "manage junior"]):
        positives.append("people-management opportunity")
        score += 4
    if _has_any(text, ["client presentation", "present to client", "client meetings", "client-facing", "stakeholder presentation"]):
        positives.append("client-facing without being purely internal")
        score += 2
    if _has_any(text, ["hybrid", "home office", "work from home", "flexible working"]):
        positives.append("hybrid/flexible setup mentioned")
        score += 2

    # Concerns / dislikes.
    if _has_any(text, ["compliance", "regulatory reporting", "regulatory compliance", "aml", "kyc", "financial crime"]):
        concerns.append("regulatory/compliance-heavy content")
        score -= 18
    if _has_any(text, ["corporate tax", "international tax", "tax compliance", "tax reporting", "tax technology"]):
        concerns.append("tax-heavy content; early feedback is consistently negative")
        score -= 14
    if _has_any(text, ["human resources", "talent acquisition", "recruiting", "internal services", "reward leader"]):
        concerns.append("HR/internal-services content; weak fit in early feedback")
        score -= 14
    if _has_any(text, ["sap s/4hana", "sap finance", "sap fi/co", "dynamics 365 finance"]):
        concerns.append("platform-specific experience may be missing")
        score -= 6
    if _has_any(text, ["pure accounting", "financial accounting", "statutory accounting"]):
        concerns.append("accounting-heavy rather than analytical finance")
        score -= 4
    if _has_any(text, ["business development", "sales target", "origination", "new business generation", "revenue target"]):
        concerns.append("meaningful sales/business-development component")
        score -= 8
    if _has_any(text, ["ifrs reporting", "statutory reporting", "financial reporting", "technical accounting"]):
        concerns.append("accounting/reporting-heavy content")
        score -= 7
    if _has_any(text, ["software engineer", "quant researcher", "quantitative researcher", "machine learning engineer"]):
        concerns.append("may be more technically demanding than preferred")
        score -= 8
    if _has_any(text, ["intern", "graduate programme", "graduate program", "entry level", "working student", "werkstudent"]):
        concerns.append("likely too junior")
        score -= 18
    if _has_any(title, ["assistant director", "associate director"]):
        concerns.append("likely above target seniority; topic may still be relevant")
        score -= 14
    elif _has_any(title, ["senior manager", "director", "head of "]):
        concerns.append("likely well above target seniority")
        score -= 18

    language = _language_flag(text)
    if language:
        constraints.append(language)
        score -= 28
    elif _has_any(text, ["very good german", "good german", "working knowledge of german", "german advantageous", "german preferred"]):
        positives.append("German requirement looks manageable")
        score += 1

    return {
        "score": max(0, min(100, score)),
        "positives": list(dict.fromkeys(positives)),
        "concerns": list(dict.fromkeys(concerns)),
        "constraints": list(dict.fromkeys(constraints)),
        "has_hard_constraint": bool(constraints),
    }


def personal_fit_score(row: pd.Series) -> int:
    return int(personal_fit_signals(row)["score"])


def build_personal_fit_summary(row: pd.Series) -> str:
    signals = personal_fit_signals(row)
    positives = list(signals["positives"])[:4]
    concerns = list(signals["concerns"])[:3]
    constraints = list(signals["constraints"])[:2]

    parts: list[str] = []
    if positives:
        parts.append("Positives: " + "; ".join(positives))
    if concerns:
        parts.append("Concerns: " + "; ".join(concerns))
    if constraints:
        parts.append("Constraints: " + "; ".join(constraints))
    if not parts:
        parts.append("No strong personal-fit signal detected from the available description")

    # Salary stays separate from role fit and becomes explicit once a salary estimate exists.
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
