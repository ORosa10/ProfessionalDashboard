from __future__ import annotations

import pandas as pd

from personal_fit import build_personal_fit_summary, personal_fit_signals
from sourcing import big4_pilot


# These terms extend the existing discovery vocabulary. They are deliberately broad
# and mostly affect which individual vacancy links get inspected first when a career
# site exposes more candidates than the crawler can visit in one run.
PERSONA_DISCOVERY_TERMS = (
    "liquidity",
    "cash management",
    "financial risk",
    "market risk",
    "derivatives",
    "hedging",
    "hedge accounting",
    "pricing",
    "financial markets",
    "capital markets",
    "fx",
    "interest rate",
    "commodity",
    "financial modelling",
    "financial modeling",
    "analytics",
    "data analysis",
    "python",
    "sql",
    "bloomberg",
    "refinitiv",
    "reuters",
    "cfa",
    "frm",
    "controlling",
)


def _apply_personal_fit_ranking() -> None:
    path = big4_pilot.JOBS_PATH
    if not path.exists() or path.stat().st_size == 0:
        return

    jobs = pd.read_csv(path).fillna("")
    if jobs.empty:
        return

    fit_scores: list[int] = []
    fit_constraints: list[str] = []
    fit_summaries: list[str] = []
    priority_scores: list[float] = []
    original_calibration: list[float] = []

    for _, row in jobs.iterrows():
        signals = personal_fit_signals(row)
        fit_score = int(signals["score"])
        calibration = pd.to_numeric(row.get("calibration_score", 50), errors="coerce")
        calibration = float(calibration) if pd.notna(calibration) else 50.0

        # Personal fit is now the larger input to sourcing priority. Existing
        # calibration remains useful while user feedback is still sparse.
        priority = 0.65 * fit_score + 0.35 * calibration

        fit_scores.append(fit_score)
        fit_constraints.append("Yes" if signals["has_hard_constraint"] else "No")
        fit_summaries.append(build_personal_fit_summary(row))
        priority_scores.append(round(priority, 1))
        original_calibration.append(calibration)

    jobs["personal_fit_score"] = fit_scores
    jobs["personal_fit_constraint"] = fit_constraints
    jobs["personal_fit_summary"] = fit_summaries
    jobs["base_calibration_score"] = original_calibration
    jobs["sourcing_priority_score"] = priority_scores

    # jobs_ui currently orders new jobs using calibration_score. Feed the combined
    # sourcing priority into that existing ordering field so personal fit affects what
    # the user sees first without turning any signal into a hard exclusion.
    jobs["calibration_score"] = jobs["sourcing_priority_score"]

    sort_cols = [
        col
        for col in ["sourcing_priority_score", "personal_fit_score", "last_seen_at"]
        if col in jobs.columns
    ]
    jobs = jobs.sort_values(sort_cols, ascending=[False] * len(sort_cols))
    jobs.to_csv(path, index=False)


def main() -> None:
    big4_pilot.ROLE_TERMS = tuple(
        dict.fromkeys((*big4_pilot.ROLE_TERMS, *PERSONA_DISCOVERY_TERMS))
    )
    big4_pilot.main()
    _apply_personal_fit_ranking()


if __name__ == "__main__":
    main()
