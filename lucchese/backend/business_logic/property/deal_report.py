"""
business_logic/property/deal_report.py
Render a property deal analysis to markdown (Rule 10).

Pure formatting from already-computed inputs/metrics. Two strategies: rent-to-rent
and BTL/HMO.
"""

from __future__ import annotations


def render_r2r(price: int, monthly_rent: int) -> str:
    """Render the rent-to-rent analysis."""
    landlord_rent = price or 0
    gross_monthly = monthly_rent
    expenses = gross_monthly * 0.15  # bills/maintenance estimate
    net_monthly = gross_monthly - landlord_rent - expenses

    lines = ["**Deal Analysis**\n"]
    lines += [
        "**Strategy:** Rent to Rent",
        f"**Rent paid to landlord:** £{landlord_rent:,}/month",
        f"**Income from tenants:** £{gross_monthly:,}/month",
        f"**Estimated expenses (bills/maintenance):** £{expenses:,.0f}/month",
        f"**Net monthly cashflow:** £{net_monthly:,.0f}/month",
        f"**Annual profit:** £{net_monthly * 12:,.0f}",
        "",
        f"**Verdict:** {'✓ Positive cashflow — worth exploring' if net_monthly > 0 else '✗ Negative cashflow — numbers dont stack'}",
    ]
    return "\n".join(lines)


def render_btl(price: int, monthly_rent: int, is_hmo: bool, m: dict) -> str:
    """Render the BTL/HMO analysis from computed metrics dict `m`."""
    gross_yield = m["gross_yield"]
    cost_pct = m["cost_pct"]
    monthly_cashflow = m["monthly_cashflow"]
    passes_stress = m["passes_stress"]

    lines = ["**Deal Analysis**\n"]
    lines += [
        f"**Strategy:** {'HMO' if is_hmo else 'Single Let'}",
        f"**Purchase price:** £{price:,}",
        f"**Monthly rent:** £{monthly_rent:,}",
        "",
        "**Yield**",
        f"Gross yield: {gross_yield:.1f}%",
        f"Net yield (after {int(cost_pct * 100)}% costs): {m['net_yield']:.1f}%",
        f"{'✓ Strong yield' if gross_yield >= 8 else '✓ Decent yield' if gross_yield >= 6 else '⚠ Low yield — check numbers'} for {'HMO' if is_hmo else 'single let'}",
        "",
        "**Mortgage (75% LTV, interest only)**",
        f"Loan amount: £{m['loan']:,.0f}",
        f"Deposit required: £{m['deposit']:,.0f}",
        f"Monthly mortgage (~{m['mortgage_rate'] * 100:.1f}%): £{m['monthly_mortgage']:,.0f}",
        f"Stress test rate ({m['stress_test_rate'] * 100:.0f}%): £{m['stress_mortgage']:,.0f}/month",
        f"Stress test coverage: {m['stress_coverage']:.2f}x {'✓ Passes' if passes_stress else '✗ Fails — lender may decline'}",
        "",
        "**Monthly Cashflow**",
        f"Rent: £{monthly_rent:,}",
        f"Mortgage: -£{m['monthly_mortgage']:,.0f}",
        f"Running costs: -£{m['monthly_costs']:,.0f}",
        f"Net cashflow: £{monthly_cashflow:,.0f}/month {'✓' if monthly_cashflow > 0 else '✗'}",
        f"Annual cashflow: £{monthly_cashflow * 12:,.0f}",
        "",
        "**Upfront Costs**",
        f"Deposit (25%): £{m['deposit']:,.0f}",
        f"SDLT (inc. 3% surcharge): £{m['sdlt']:,.0f}",
        "Legal/valuation (est.): £2,000",
        f"Total cash required: £{m['total_cash']:,.0f}",
        "",
        "**Equity Release Angle**",
        "To fund this deposit via remortgage, the existing property needs",
        f"at least £{m['equity_needed']:,.0f} available equity (at 75% LTV).",
        "",
        "**Verdict**",
    ]

    issues: list[str] = []
    positives: list[str] = []

    if gross_yield >= 8:
        positives.append("strong gross yield")
    elif gross_yield >= 6:
        positives.append("decent gross yield")
    else:
        issues.append(f"low gross yield of {gross_yield:.1f}%")

    if monthly_cashflow > 200:
        positives.append("solid monthly cashflow")
    elif monthly_cashflow > 0:
        positives.append("positive but thin cashflow")
    else:
        issues.append("negative cashflow")

    if not passes_stress:
        issues.append("fails lender stress test — income may need to be higher or deposit larger")

    if issues:
        lines.append(f"⚠ Concerns: {', '.join(issues)}")
    if positives:
        lines.append(f"✓ Positives: {', '.join(positives)}")

    if monthly_cashflow > 0 and passes_stress and gross_yield >= 6:
        lines.append("\n**Overall: Worth pursuing — book a viewing and get broker involved.**")
    elif monthly_cashflow > 0 and gross_yield >= 5:
        lines.append("\n**Overall: Marginal — negotiate the price down or find ways to increase rent.**")
    else:
        lines.append("\n**Overall: Hard to make work at this price — move on or negotiate hard.**")

    return "\n".join(lines)
