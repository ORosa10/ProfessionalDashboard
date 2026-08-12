from __future__ import annotations

from pathlib import Path

import pandas as pd
import streamlit as st

from salary_context_ui import render_salary_context

DATA_DIR = Path(__file__).parent / "data"
BASE_TARGET_SAVINGS_CZK = 500_000
SAVINGS_LEVELS = [250_000, 500_000, 750_000, 1_000_000]


def _load_city_profiles() -> pd.DataFrame:
    df = pd.read_csv(DATA_DIR / "cost_of_living.csv").fillna("")
    numeric_cols = [
        "fx_czk",
        "housing_czk",
        "living_czk",
        "transport_czk",
        "prague_trips_czk",
        "mandatory_extra_czk",
        "net_ratio",
        "living_index_vs_prague",
        "benchmark_gross_annual_local",
    ]
    for col in numeric_cols:
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0.0)

    df["total_costs_czk"] = (
        df["housing_czk"]
        + df["living_czk"]
        + df["transport_czk"]
        + df["prague_trips_czk"]
        + df["mandatory_extra_czk"]
    )
    return df


def _load_salary_context() -> pd.DataFrame:
    path = DATA_DIR / "salary_context.csv"
    if not path.exists():
        return pd.DataFrame()
    df = pd.read_csv(path).fillna("")
    for col in ["average_monthly_local", "median_monthly_local"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


def _money_czk(value: float) -> str:
    return f"{value:,.0f} Kč".replace(",", " ")


def _local(value: float | None, currency: str) -> str:
    if value is None or pd.isna(value):
        return "—"
    symbols = {"GBP": "£", "EUR": "€", "CHF": "CHF ", "SEK": "SEK ", "DKK": "DKK ", "NOK": "NOK ", "CZK": "Kč "}
    text = f"{value:,.0f}".replace(",", " ")
    return f"{symbols.get(currency, currency + ' ')}{text}" if currency != "CZK" else f"{text} Kč"


def _gap_pct(target: float, reference: float | None) -> str:
    if reference is None or pd.isna(reference) or float(reference) <= 0:
        return "—"
    gap = (float(target) / float(reference) - 1) * 100
    return f"{gap:+.0f}%"


def _add_target_columns(view: pd.DataFrame, annual_savings: float) -> pd.DataFrame:
    view = view.copy()
    monthly_savings = annual_savings / 12
    view["required_net_czk"] = view["total_costs_czk"] + monthly_savings
    view["target_gross_monthly_czk"] = view["required_net_czk"] / view["net_ratio"]
    view["target_gross_monthly_local"] = view["target_gross_monthly_czk"] / view["fx_czk"]
    view["target_gross_annual_local"] = view["target_gross_monthly_local"] * 12
    return view


def render_cost_of_living() -> None:
    st.markdown('<div class="eyebrow">Opportunity Radar</div>', unsafe_allow_html=True)
    st.title("Cost of Living & Salary")
    st.markdown(
        '<p class="muted">Salary targeting based on how much you can actually save after living costs.</p>',
        unsafe_allow_html=True,
    )

    with st.expander("Lifestyle profile used in the model"):
        st.markdown(
            """
            - **Housing:** own room in a shared flat; value-oriented but not bottom-end quality; suburbs are fine with good access to work.
            - **Food:** cheaper supermarkets without sacrificing normal food quality; eating out mainly work lunches plus occasional takeaway.
            - **Leisure:** low spend; little nightlife/alcohol; low-cost sport, outdoors and trips.
            - **Transport:** cheapest practical option, including walking/cycling where sensible and safe.
            - **Prague trips:** roughly twice a month, but cost is city-specific by realistic transport mode.
            - Holidays, discretionary shopping and an extra emergency reserve are **outside** this model.
            """
        )
        st.caption(
            "The 'Běžný život' row is not manually guessed city by city. Prague is the personal basket baseline; "
            "other cities are scaled using Jul-2026 Expatistan food-price comparisons, cross-checked against current Numbeo city prices."
        )

    profiles = _load_city_profiles()
    salary_context = _load_salary_context()
    salary_context_by_city = salary_context.set_index("city") if not salary_context.empty else pd.DataFrame()

    left, right = st.columns([1, 2])
    annual_savings = left.number_input(
        "Target annual savings (CZK)",
        min_value=0,
        max_value=2_000_000,
        value=BASE_TARGET_SAVINGS_CZK,
        step=50_000,
    )
    default_cities = profiles["city"].tolist()
    selected = right.multiselect("Cities", default_cities, default=default_cities)
    view = profiles[profiles["city"].isin(selected)].copy()

    if view.empty:
        st.info("Select at least one city.")
        return

    view = _add_target_columns(view, annual_savings)
    monthly_savings = annual_savings / 12

    rows: dict[str, dict[str, str]] = {}
    for _, r in view.iterrows():
        city = r["city"]
        currency = r["currency"]
        if not salary_context.empty and city in salary_context_by_city.index:
            context_row = salary_context_by_city.loc[city]
            average_local = context_row.get("average_monthly_local")
            median_local = context_row.get("median_monthly_local")
        else:
            average_local = None
            median_local = None

        target_local = r["target_gross_monthly_local"]
        rows[city] = {
            "Bydlení vč. utilities": _money_czk(r["housing_czk"]),
            "Běžný život": _money_czk(r["living_czk"]),
            "Místní doprava": _money_czk(r["transport_czk"]),
            "Cesty do Prahy": _money_czk(r["prague_trips_czk"]),
            "Zdravotní / povinné extra": _money_czk(r["mandatory_extra_czk"]),
            "Celkové náklady": _money_czk(r["total_costs_czk"]),
            "Cíl úspor": _money_czk(monthly_savings),
            "Potřebný net income": _money_czk(r["required_net_czk"]),
            "Target gross / měsíc v CZK": _money_czk(r["target_gross_monthly_czk"]),
            "Target gross / měsíc lokálně": _local(target_local, currency),
            "Target gross / rok lokálně": _local(r["target_gross_annual_local"], currency),
            "Průměrný gross / měsíc lokálně": _local(average_local, currency),
            "Target vs průměr": _gap_pct(target_local, average_local),
            "Medián gross / měsíc lokálně": _local(median_local, currency),
            "Target vs medián": _gap_pct(target_local, median_local),
        }

    comparison = pd.DataFrame(rows)
    st.dataframe(comparison, width="stretch", height=min(760, 38 * (len(comparison) + 2)))

    st.caption(
        "Planning model, not a payroll calculator. Housing assumes an own room in a shared flat and includes utilities. "
        "Net/gross conversion uses a city/country planning ratio calibrated around the relevant salary range. "
        "Average and median salary rows use the latest reference statistics available in salary_context.csv; target gaps show how far the required monthly gross is above (+) or below (-) those references."
    )

    st.subheader("Test a salary")
    a, b = st.columns(2)
    city = a.selectbox("City", view["city"].tolist(), key="salary_test_city")
    row = view[view["city"] == city].iloc[0]
    default_salary = int(round(row["target_gross_annual_local"] / 1000) * 1000)
    annual_gross_local = b.number_input(
        f"Annual gross salary ({row['currency']})",
        min_value=0,
        value=default_salary,
        step=1000,
        key="salary_test_gross",
    )

    gross_monthly_czk = annual_gross_local * row["fx_czk"] / 12
    estimated_net_czk = gross_monthly_czk * row["net_ratio"]
    estimated_savings_czk = estimated_net_czk - row["total_costs_czk"]
    estimated_annual_savings = estimated_savings_czk * 12
    target_ratio = estimated_annual_savings / annual_savings if annual_savings > 0 else 1.0

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Estimated net / month", _money_czk(estimated_net_czk))
    c2.metric("Estimated savings / month", _money_czk(estimated_savings_czk))
    c3.metric("Estimated savings / year", _money_czk(estimated_annual_savings))
    c4.metric("Vs selected target", f"{target_ratio * 100:.0f}%")

    st.progress(max(0.0, min(target_ratio / 1.5, 1.0)))
    if target_ratio >= 1.25:
        st.success("Salary viability: Well above benchmark")
    elif target_ratio >= 1.05:
        st.success("Salary viability: Above benchmark")
    elif target_ratio >= 0.90:
        st.info("Salary viability: Around benchmark")
    elif target_ratio >= 0.70:
        st.warning("Salary viability: Below benchmark")
    else:
        st.error("Salary viability: Well below benchmark")

    render_salary_context(city, row["currency"], annual_gross_local)

    st.subheader(f"Savings ladder — {city}")
    ladder_rows = []
    one_city = profiles[profiles["city"] == city].copy()
    for target in SAVINGS_LEVELS:
        calc = _add_target_columns(one_city, target).iloc[0]
        ladder_rows.append({
            "Annual savings target": _money_czk(target),
            "Required gross / year": _local(calc["target_gross_annual_local"], calc["currency"]),
            "Required gross / month": _local(calc["target_gross_monthly_local"], calc["currency"]),
        })
    st.dataframe(pd.DataFrame(ladder_rows), hide_index=True, width="stretch")

    with st.expander("City assumptions & source scaling"):
        detail = view[[
            "city",
            "country",
            "currency",
            "fx_czk",
            "housing_czk",
            "living_czk",
            "living_index_vs_prague",
            "transport_czk",
            "prague_trips_czk",
            "mandatory_extra_czk",
            "net_ratio",
            "notes",
        ]].copy()
        st.dataframe(detail, hide_index=True, width="stretch")
