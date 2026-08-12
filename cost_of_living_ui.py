from __future__ import annotations

from pathlib import Path

import pandas as pd
import streamlit as st

DATA_DIR = Path(__file__).parent / "data"
BASE_TARGET_SAVINGS_CZK = 500_000


def _load_city_profiles() -> pd.DataFrame:
    df = pd.read_csv(DATA_DIR / "cost_of_living.csv").fillna("")
    numeric_cols = [
        "fx_czk",
        "housing_czk",
        "living_czk",
        "transport_czk",
        "prague_trips_czk",
        "mandatory_extra_czk",
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
    base_required_net = df["total_costs_czk"] + BASE_TARGET_SAVINGS_CZK / 12
    base_gross_monthly_czk = df["benchmark_gross_annual_local"] * df["fx_czk"] / 12
    df["calibrated_net_ratio"] = (base_required_net / base_gross_monthly_czk).clip(lower=0.35, upper=0.90)
    return df


def _money_czk(value: float) -> str:
    return f"{value:,.0f} Kč".replace(",", " ")


def _local(value: float, currency: str) -> str:
    symbols = {"GBP": "£", "EUR": "€", "CHF": "CHF ", "SEK": "SEK ", "DKK": "DKK ", "NOK": "NOK ", "CZK": "Kč "}
    symbol = symbols.get(currency, f"{currency} ")
    if currency in {"GBP", "EUR", "CHF"}:
        text = f"{value:,.0f}"
    else:
        text = f"{value:,.0f}"
    text = text.replace(",", " ")
    return f"{symbol}{text}" if currency not in {"CZK"} else f"{text} Kč"


def render_cost_of_living() -> None:
    st.markdown('<div class="eyebrow">Opportunity Radar</div>', unsafe_allow_html=True)
    st.title("Cost of Living & Salary")
    st.markdown(
        '<p class="muted">Compare cities by the salary required to hit a savings target. '
        'Current lifestyle assumption: own room in a shared flat and a relatively modest everyday lifestyle.</p>',
        unsafe_allow_html=True,
    )

    profiles = _load_city_profiles()

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

    monthly_savings = annual_savings / 12
    view["required_net_czk"] = view["total_costs_czk"] + monthly_savings
    view["target_gross_monthly_czk"] = view["required_net_czk"] / view["calibrated_net_ratio"]
    view["target_gross_monthly_local"] = view["target_gross_monthly_czk"] / view["fx_czk"]
    view["target_gross_annual_local"] = view["target_gross_monthly_local"] * 12

    rows: dict[str, dict[str, str]] = {}
    for _, r in view.iterrows():
        city = r["city"]
        currency = r["currency"]
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
            "Target gross / měsíc lokálně": _local(r["target_gross_monthly_local"], currency),
            "Target gross / rok lokálně": _local(r["target_gross_annual_local"], currency),
        }

    comparison = pd.DataFrame(rows)
    st.dataframe(comparison, width="stretch", height=min(620, 38 * (len(comparison) + 2)))

    st.caption(
        "Planning model, not a payroll calculator. Housing assumes an own room in a shared flat; "
        "utilities are included in housing. Gross targets use city-specific calibrated net/gross ratios "
        "around the current benchmark and are intended for opportunity screening rather than tax filing."
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
    estimated_net_czk = gross_monthly_czk * row["calibrated_net_ratio"]
    estimated_savings_czk = estimated_net_czk - row["total_costs_czk"]
    estimated_annual_savings = estimated_savings_czk * 12

    c1, c2, c3 = st.columns(3)
    c1.metric("Estimated net / month", _money_czk(estimated_net_czk))
    c2.metric("Estimated savings / month", _money_czk(estimated_savings_czk))
    c3.metric("Estimated savings / year", _money_czk(estimated_annual_savings))

    if estimated_annual_savings >= annual_savings * 1.10:
        st.success("Salary viability: Above benchmark")
    elif estimated_annual_savings >= annual_savings * 0.90:
        st.info("Salary viability: Around benchmark")
    else:
        st.warning("Salary viability: Probably below benchmark")

    with st.expander("City assumptions"):
        detail = view[[
            "city",
            "country",
            "currency",
            "fx_czk",
            "housing_czk",
            "living_czk",
            "transport_czk",
            "prague_trips_czk",
            "mandatory_extra_czk",
            "notes",
        ]].copy()
        st.dataframe(detail, hide_index=True, width="stretch")
