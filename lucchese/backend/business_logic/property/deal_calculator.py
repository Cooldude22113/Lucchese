"""
business_logic/property/deal_calculator.py
Property deal financial model + entry point (Rule 10: pure, testable rule).

Owns the market rates and the BTL/HMO financial computation, then delegates text
formatting to deal_report. analyse_deal() is the single public entry point used by
the route and the chat "analyse deal:" intercept.
"""

from __future__ import annotations

from business_logic.property.deal_parser import parse_deal
from business_logic.property.deal_report import render_btl, render_r2r
from business_logic.property.sdlt import calc_sdlt

# ── Market rates — update as the market changes ───────────────────────────────
MORTGAGE_RATE = 0.055    # 5.5% interest-only BTL rate
STRESS_TEST_RATE = 0.080  # 8% — standard lender stress test


def compute_btl(price: int, monthly_rent: int, is_hmo: bool) -> dict:
    """Compute the full set of BTL/HMO metrics for a deal."""
    annual_rent = monthly_rent * 12
    gross_yield = (annual_rent / price) * 100

    cost_pct = 0.35 if is_hmo else 0.25  # HMO costs more to run
    annual_costs = annual_rent * cost_pct
    net_annual = annual_rent - annual_costs
    net_yield = (net_annual / price) * 100

    loan = price * 0.75
    deposit = price * 0.25
    monthly_mortgage = (loan * MORTGAGE_RATE) / 12
    stress_mortgage = (loan * STRESS_TEST_RATE) / 12
    monthly_costs = annual_costs / 12
    monthly_cashflow = monthly_rent - monthly_mortgage - monthly_costs

    sdlt = calc_sdlt(price)
    total_cash = deposit + sdlt + 2_000  # legal/valuation estimate

    stress_coverage = monthly_rent / stress_mortgage
    passes_stress = stress_coverage >= 1.25  # most lenders require 125%

    return {
        "mortgage_rate": MORTGAGE_RATE,
        "stress_test_rate": STRESS_TEST_RATE,
        "annual_rent": annual_rent,
        "gross_yield": gross_yield,
        "cost_pct": cost_pct,
        "annual_costs": annual_costs,
        "net_yield": net_yield,
        "loan": loan,
        "deposit": deposit,
        "monthly_mortgage": monthly_mortgage,
        "stress_mortgage": stress_mortgage,
        "monthly_costs": monthly_costs,
        "monthly_cashflow": monthly_cashflow,
        "sdlt": sdlt,
        "total_cash": total_cash,
        "stress_coverage": stress_coverage,
        "passes_stress": passes_stress,
        "equity_needed": deposit,  # to fund the deposit via remortgage
    }


def analyse_deal(text: str) -> str:
    """Parse free text into a deal and return a markdown analysis (or guidance)."""
    data, error = parse_deal(text)
    if error:
        return error

    if data["is_r2r"]:
        return render_r2r(data["price"], data["monthly_rent"])

    metrics = compute_btl(data["price"], data["monthly_rent"], data["is_hmo"])
    return render_btl(data["price"], data["monthly_rent"], data["is_hmo"], metrics)
