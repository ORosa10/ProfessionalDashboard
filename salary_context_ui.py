from __future__ import annotations

from pathlib import Path

import math
import pandas as pd
import streamlit as st

DATA_DIR = Path(__file__).parent / "data"


def _load_context() -> pd.DataFrame:
    df = pd.read_csv(DATA_DIR / "salary_context.csv").fillna("")
    for col in [
        "average_monthly_local",
        "median_monthly_local",
        "p10_monthly_local",
        "p25_monthly_local",
        "p75_monthly_local",
        "p80_monthly_local",
        "p90_monthly_local",
        "p99_monthly_local",
    ]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


def _fmt_local(value: float | None, currency: str) -> str:
    if value is None or pd.isna(value):
        return "—"
    symbols = {"GBP": "£", "EUR": "€", "CHF": "CHF ", "SEK": "SEK ", "DKK": "DKK ", "NOK": "NOK ", "CZK": "Kč "}
    text = f"{value:,.0f}".replace(",", " ")
    return f"{symbols.get(currency, currency + ' ')}{text}" if currency != "CZK" else f"{text} Kč"


def _interpolated_percentile(monthly_salary: float, row: pd.Series) -> float | None:
    anchors = []
    for percentile, col in [
        (10, "p10_monthly_local"),
        (25, "p25_monthly_local"),
        (50, "median_monthly_local"),
        (75, "p75_monthly_local"),
        (80, "p80_monthly_local"),
        (90, "p90_monthly_local"),
        (99, "p99_monthly_local"),
    ]:
        value = row.get(col)
        if pd.notna(value) and float(value) > 0:
            anchors.append((float(value), float(percentile)))

    anchors = sorted(set(anchors))
    if len(anchors) >= 2:
        if monthly_salary <= anchors[0][0]:
            return max(1.0, anchors[0][1] * monthly_salary / anchors[0][0])
        for (v1, p1), (v2, p2) in zip(anchors, anchors[1:]):
            if v1 <= monthly_salary <= v2:
                # Salary distributions are skewed; interpolate in log salary space.
                weight = (math.log(monthly_salary) - math.log(v1)) / (math.log(v2) - math.log(v1))
                return p1 + weight * (p2 - p1)
        v1, p1 = anchors[-2]
        v2, p2 = anchors[-1]
        if monthly_salary > v2:
            slope = (p2 - p1) / max(math.log(v2) - math.log(v1), 1e-9)
            return min(99.8, p2 + slope * (math.log(monthly_salary) - math.log(v2)))

    # Fallback when official percentile anchors are not available: infer a rough
    # log-normal distribution from official mean + median. This is deliberately
    # labelled approximate in the UI.
    mean = row.get("average_monthly_local")
    median = row.get("median_monthly_local")
    if pd.notna(mean) and pd.notna(median) and mean > median > 0:
        sigma_sq = 2 * math.log(float(mean) / float(median))
        if sigma_sq > 0:
            sigma = math.sqrt(sigma_sq)
            z = (math.log(monthly_salary) - math.log(float(median))) / sigma
            return 100 * 0.5 * (1 + math.erf(z / math.sqrt(2)))
    return None


def render_salary_context(city: str, currency: str, annual_gross_local: float) -> None:
    context = _load_context()
    match = context[context["city"] == city]
    if match.empty:
        return

    row = match.iloc[0]
    monthly_salary = annual_gross_local / 12
    average = row["average_monthly_local"]
    median = row["median_monthly_local"]
    percentile = _interpolated_percentile(monthly_salary, row)

    st.subheader("Salary position in the local market")
    c1, c2, c3 = st.columns(3)
    c1.metric("Gross / month", _fmt_local(monthly_salary, currency))

    if pd.notna(average) and average > 0:
        c2.metric(
            f"Vs average — {row['scope']}",
            f"{monthly_salary / average:.1f}×",
            f"avg {_fmt_local(average, currency)}",
        )
    elif pd.notna(median) and median > 0:
        c2.metric(
            f"Vs median — {row['scope']}",
            f"{monthly_salary / median:.1f}×",
            f"median {_fmt_local(median, currency)}",
        )
    else:
        c2.metric("Vs local average", "—")

    if percentile is not None:
        c3.metric("Approx. salary percentile", f"P{percentile:.0f}")
    else:
        c3.metric("Approx. salary percentile", "—")

    median_text = _fmt_local(median, currency) if pd.notna(median) else "—"
    st.caption(
        f"Reference: {row['source_label']} · scope: {row['scope']} · median: {median_text}. "
        "Percentile is an indicative interpolation of the latest published wage distribution; "
        "where detailed percentile anchors are unavailable it is intentionally left blank or estimated from mean/median only."
    )
