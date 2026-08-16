"""Build a diverse calibration shortlist from a sector's sourced jobs file.

Generalizes the original Big-Four-only script (which stays as the default
CLI invocation for backward compatibility) so any sector with a
data/jobs_<sector>_staging.csv snapshot can get its own shortlist the same
way PE and Consulting did: a batch small enough to actually rate (default
target 20, auto-scaled down if the sector doesn't have that many open
roles yet), split into Likely-fit / Boundary / Exploration cohorts, picked
for diversity across company/market/theme/seniority rather than just top-N
by score.

Usage:
    python -m sourcing.build_calibration_batch \
        --jobs data/jobs_corporate_staging.csv \
        --output data/corporate_calibration_shortlist.csv \
        --batch-id corporate-calibration-01 \
        --total 20
"""
from __future__ import annotations

import argparse
import re
from collections import Counter
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_JOBS_PATH = ROOT / "data" / "jobs_staging.csv"
FEEDBACK_PATH = ROOT / "data" / "job_feedback.csv"
DEFAULT_OUTPUT_PATH = ROOT / "data" / "job_calibration_batch.csv"
DEFAULT_BATCH_ID = "big4-calibration-01"

THEMES = (
    ("Treasury / Risk / Markets", r"treasury|liquidity|market risk|financial risk|capital markets?|derivative|hedg|commodity|funding"),
    ("Transactions / M&A", r"m&a|transaction|deal advisory|due diligence|corporate finance|valuation|restructur|turnaround"),
    ("FP&A / Controlling", r"fp&a|financial planning|business controlling|controller|controlling|commercial finance"),
    ("Finance transformation", r"finance transformation|cfo advisory|finance function|enterprise performance|performance management"),
    ("Data / Analytics", r"data analy|analytics|business intelligence|data strategy|financial model|data scien"),
    ("Strategy / Consulting", r"strategy|management consulting|business consulting|operating model|transformation"),
    ("ERP / Finance technology", r"sap|dynamics|erp|oracle finance|technology consulting"),
    ("Accounting / Reporting", r"accounting|financial reporting|ifrs|audit|assurance"),
    ("Tax / Compliance", r"\btax\b|transfer pricing|compliance|regulatory reporting|aml|kyc"),
)


def classify_theme(row: pd.Series) -> str:
    title = str(row.get("title", "")).lower()
    for name, pattern in THEMES:
        if re.search(pattern, title):
            return name
    text = f"{title} {row.get('description_en', '')}".lower()
    for name, pattern in THEMES:
        if re.search(pattern, text):
            return name
    return "Other finance"


def classify_seniority(title: str) -> str:
    value = str(title).lower()
    if re.search(r"\b(junior|intern|internship|graduate|working student|werkstudent|praktikum|trainee)\b", value):
        return "Junior / entry"
    if re.search(r"\b(director|head of|partner)\b", value) or re.search(r"senior\W*manager", value):
        return "Senior leadership"
    if re.search(r"\bmanager\b", value):
        return "Manager"
    if re.search(r"\b(consultant|analyst|associate|specialist|controller)\b", value):
        return "Core professional"
    return "Unclear / other"


def title_key(title: str) -> str:
    value = str(title).lower()
    value = re.sub(r"\b(stockholm|malmö|malmo|göteborg|gothenburg|zurich|vienna|prague|london)\b", "", value)
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return " ".join(value.split())


def _diverse_pick(
    candidates: pd.DataFrame,
    count: int,
    cohort: str,
    selected: list[pd.Series],
) -> list[pd.Series]:
    remaining = {str(row.job_id): row for _, row in candidates.iterrows()}
    company_counts = Counter(str(row.company) for row in selected)
    market_counts = Counter(str(row.market) for row in selected)
    theme_counts = Counter(str(row.theme) for row in selected)
    seniority_counts = Counter(str(row.seniority_band) for row in selected)
    selected_titles = Counter(title_key(str(row.title)) for row in selected)
    chosen: list[pd.Series] = []

    while remaining and len(chosen) < count:
        def rank(row: pd.Series) -> tuple[float, str]:
            fit = float(pd.to_numeric(row.get("personal_fit_score", 50), errors="coerce") or 50)
            if cohort == "Likely fit":
                base = fit
            elif cohort == "Boundary":
                base = 70 - abs(fit - 52)
            else:
                base = 85 - fit * 0.45
            diversity = (
                max(0, 12 - company_counts[row.company]) * 1.8
                + max(0, 7 - market_counts[row.market]) * 1.5
                + max(0, 4 - theme_counts[row.theme]) * 2.3
                + max(0, 6 - seniority_counts[row.seniority_band]) * 0.8
            )
            concentration_penalty = (
                max(0, company_counts[row.company] - 12) * 25
                + max(0, market_counts[row.market] - 9) * 22
                + max(0, theme_counts[row.theme] - 7) * 18
                + selected_titles[title_key(row.title)] * 60
            )
            return base + diversity - concentration_penalty, str(row.job_id)

        best = max(remaining.values(), key=rank)
        chosen.append(best)
        company_counts[best.company] += 1
        market_counts[best.market] += 1
        theme_counts[best.theme] += 1
        seniority_counts[best.seniority_band] += 1
        selected_titles[title_key(best.title)] += 1
        remaining.pop(str(best.job_id))
    return chosen


def build_batch(
    jobs_path: Path = DEFAULT_JOBS_PATH,
    batch_id: str = DEFAULT_BATCH_ID,
    total: int = 50,
    likely_share: float = 0.6,
    boundary_share: float = 0.24,
) -> pd.DataFrame:
    """Build a diverse calibration shortlist of up to `total` opportunities.

    `total` auto-scales down to whatever is actually available (minus
    already-reviewed and non-open roles) -- a small sector with only 6 open
    roles gets a 6-row batch, not an error.
    """
    jobs = pd.read_csv(jobs_path).fillna("")
    feedback = pd.read_csv(FEEDBACK_PATH).fillna("") if FEEDBACK_PATH.exists() else pd.DataFrame()
    reviewed = set(
        feedback.loc[feedback.get("feedback", pd.Series(dtype=str)).ne("Unrated"), "opportunity_id"]
    ) if not feedback.empty else set()
    jobs = jobs[~jobs["job_id"].isin(reviewed)].copy()
    jobs = jobs[jobs["status"].replace("", "Open").eq("Open")].copy()
    jobs = jobs[
        ~jobs["title"].str.lower().str.contains(
            r"initiativbewerbung|open application|general application|talent community",
            regex=True,
        )
    ].copy()
    jobs["theme"] = jobs.apply(classify_theme, axis=1)
    jobs["seniority_band"] = jobs["title"].map(classify_seniority)
    if "personal_fit_score" in jobs.columns:
        jobs["fit"] = pd.to_numeric(jobs["personal_fit_score"], errors="coerce").fillna(50)
    else:
        jobs["fit"] = 50
    if "personal_fit_constraint" in jobs.columns:
        jobs["constraint"] = jobs["personal_fit_constraint"].astype(str).eq("Yes")
    else:
        jobs["constraint"] = False

    available = len(jobs)
    target_total = min(total, available)
    likely_target = max(1, round(target_total * likely_share)) if target_total else 0
    boundary_target = max(0, round(target_total * boundary_share)) if target_total > likely_target else 0
    exploration_target = max(0, target_total - likely_target - boundary_target)

    likely = jobs[
        jobs["fit"].ge(55)
        & ~jobs["constraint"]
        & jobs["seniority_band"].isin(["Core professional", "Manager", "Unclear / other"])
        & ~jobs["theme"].isin(["Tax / Compliance", "Accounting / Reporting"])
        & ~jobs["title"].str.lower().str.contains(
            r"human resources|\bhr\b|talent acquisition|recruit|cyber security|cloud security",
            regex=True,
        )
    ]
    boundary = jobs[
        ~jobs["job_id"].isin(likely["job_id"])
        & (
            jobs["fit"].between(38, 68)
            | jobs["theme"].isin(["ERP / Finance technology", "Accounting / Reporting"])
            | jobs["seniority_band"].eq("Senior leadership")
        )
    ]
    exploration = jobs[
        ~jobs["job_id"].isin(set(likely["job_id"]) | set(boundary["job_id"]))
    ]

    selected: list[pd.Series] = []
    cohorts: list[tuple[str, int, pd.DataFrame]] = [
        ("Likely fit", likely_target, likely),
        ("Boundary", boundary_target, boundary),
        ("Exploration", exploration_target, exploration),
    ]
    rows: list[dict] = []
    for cohort, target, pool in cohorts:
        if target <= 0:
            continue
        picks = _diverse_pick(pool, target, cohort, selected)
        selected.extend(picks)
        for pick in picks:
            rows.append(
                {
                    "batch_id": batch_id,
                    "display_order": len(rows) + 1,
                    "opportunity_id": pick.job_id,
                    "cohort": cohort,
                    "theme": pick.theme,
                    "seniority_band": pick.seniority_band,
                    "selection_reason": (
                        "Plausible match to test" if cohort == "Likely fit"
                        else "Boundary case to clarify preferences" if cohort == "Boundary"
                        else "Exploration case to avoid overfitting"
                    ),
                }
            )
    # Top up from whatever's left if cohort pools ran dry before hitting
    # target_total (small sectors can have a lopsided theme/seniority mix).
    if len(rows) < target_total:
        remaining_pool = jobs[~jobs["job_id"].isin(row["opportunity_id"] for row in rows)]
        picks = _diverse_pick(remaining_pool, target_total - len(rows), "Exploration", selected)
        for pick in picks:
            rows.append(
                {
                    "batch_id": batch_id,
                    "display_order": len(rows) + 1,
                    "opportunity_id": pick.job_id,
                    "cohort": "Exploration",
                    "theme": pick.theme,
                    "seniority_band": pick.seniority_band,
                    "selection_reason": "Exploration case to avoid overfitting",
                }
            )
    result = pd.DataFrame(rows)
    if not result.empty and result["opportunity_id"].duplicated().any():
        raise RuntimeError("Calibration batch must not contain duplicate opportunities")
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--jobs", type=Path, default=DEFAULT_JOBS_PATH)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH)
    parser.add_argument("--batch-id", default=DEFAULT_BATCH_ID)
    parser.add_argument("--total", type=int, default=50)
    args = parser.parse_args()
    batch = build_batch(args.jobs, args.batch_id, args.total)
    batch.to_csv(args.output, index=False)
    print(f"Stored {len(batch)} opportunities in {args.output.name}")


if __name__ == "__main__":
    main()
