"""
routes/deal.py
──────────────
Property deal analysis endpoint.
Pure logic — no shared state, no DB, no AI calls.
Triggered by: "analyse deal: ..." or "analyze deal: ..."
"""

import re
from fastapi import APIRouter

router = APIRouter()

# ── Rates — update these as market changes ────────────────────────────────────
MORTGAGE_RATE    = 0.055   # 5.5% interest-only BTL rate
STRESS_TEST_RATE = 0.080   # 8% — standard lender stress test


# ── SDLT calculator (investment property, includes 3% surcharge) ──────────────
def _calc_sdlt(price: int) -> float:
    if price <= 125_000:
        return price * 0.03
    elif price <= 250_000:
        return 125_000 * 0.03 + (price - 125_000) * 0.05
    elif price <= 925_000:
        return 125_000 * 0.03 + 125_000 * 0.05 + (price - 250_000) * 0.08
    else:
        return 125_000 * 0.03 + 125_000 * 0.05 + 675_000 * 0.08 + (price - 925_000) * 0.13


# ── Core analyser ─────────────────────────────────────────────────────────────
def analyse_deal(text: str) -> str:
    t = text.lower()

    # Find all £ amounts — handles £200k, £200,000, £1,200, £950
    amounts = []
    for m in re.finditer(r'£([\d,]+)(k)?', t):
        val = int(m.group(1).replace(',', ''))
        if m.group(2):
            val *= 1000
        amounts.append((m.start(), val))

    if not amounts:
        return (
            "I need at least a purchase price and monthly rent. "
            "Try: 'analyse deal: 3 bed Basildon £200k asking, £1,200/month rent, single let'"
        )

    # Price = largest amount
    price = max(amounts, key=lambda x: x[1])[1]

    # Rent = amount near rent/month keywords, else smallest amount
    rent_match = re.search(r'£([\d,]+)(k)?\s*(?:/month|pcm|per month|month|rent|/mo)', t)
    if rent_match:
        monthly_rent = int(rent_match.group(1).replace(',', ''))
        if rent_match.group(2):
            monthly_rent *= 1000
    else:
        others = [v for _, v in amounts if v != price]
        monthly_rent = min(others) if others else None

    if not monthly_rent:
        return "I need an expected monthly rent to analyse this deal."

    # Detect rooms and strategy
    rooms_match = re.search(r'(\d+)\s*(?:bed|room|bedroom)', t)
    rooms  = int(rooms_match.group(1)) if rooms_match else None
    is_hmo = 'hmo' in t or (rooms and rooms >= 4)
    is_r2r = 'r2r' in t or 'rent to rent' in t

    # HMO: multiply per-room rent by room count if it looks like a per-room figure
    if is_hmo and rooms and monthly_rent < 2000:
        monthly_rent = monthly_rent * rooms

    if not price and not is_r2r:
        return (
            "I need a purchase price to analyse this deal. "
            "Try: 'analyse deal: 3 bed Basildon £200k asking, £1,200/month rent, single let'"
        )

    lines = ["**Deal Analysis**\n"]

    # ── Rent to Rent ──────────────────────────────────────────────────────────
    if is_r2r:
        landlord_rent  = price or 0
        gross_monthly  = monthly_rent
        expenses       = gross_monthly * 0.15   # bills/maintenance estimate
        net_monthly    = gross_monthly - landlord_rent - expenses
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

    # ── BTL / HMO ────────────────────────────────────────────────────────────
    annual_rent  = monthly_rent * 12
    gross_yield  = (annual_rent / price) * 100

    cost_pct     = 0.35 if is_hmo else 0.25   # HMO costs more to run
    annual_costs = annual_rent * cost_pct
    net_annual   = annual_rent - annual_costs
    net_yield    = (net_annual / price) * 100

    loan              = price * 0.75
    deposit           = price * 0.25
    monthly_mortgage  = (loan * MORTGAGE_RATE) / 12
    stress_mortgage   = (loan * STRESS_TEST_RATE) / 12
    monthly_costs     = annual_costs / 12
    monthly_cashflow  = monthly_rent - monthly_mortgage - monthly_costs

    sdlt              = _calc_sdlt(price)
    total_cash        = deposit + sdlt + 2_000   # legal/valuation estimate

    stress_coverage   = monthly_rent / stress_mortgage
    passes_stress     = stress_coverage >= 1.25   # most lenders require 125%

    equity_needed     = deposit   # what you need from remortgaging elsewhere

    lines += [
        f"**Strategy:** {'HMO' if is_hmo else 'Single Let'}",
        f"**Purchase price:** £{price:,}",
        f"**Monthly rent:** £{monthly_rent:,}",
        "",
        "**Yield**",
        f"Gross yield: {gross_yield:.1f}%",
        f"Net yield (after {int(cost_pct * 100)}% costs): {net_yield:.1f}%",
        f"{'✓ Strong yield' if gross_yield >= 8 else '✓ Decent yield' if gross_yield >= 6 else '⚠ Low yield — check numbers'} for {'HMO' if is_hmo else 'single let'}",
        "",
        "**Mortgage (75% LTV, interest only)**",
        f"Loan amount: £{loan:,.0f}",
        f"Deposit required: £{deposit:,.0f}",
        f"Monthly mortgage (~{MORTGAGE_RATE * 100:.1f}%): £{monthly_mortgage:,.0f}",
        f"Stress test rate ({STRESS_TEST_RATE * 100:.0f}%): £{stress_mortgage:,.0f}/month",
        f"Stress test coverage: {stress_coverage:.2f}x {'✓ Passes' if passes_stress else '✗ Fails — lender may decline'}",
        "",
        "**Monthly Cashflow**",
        f"Rent: £{monthly_rent:,}",
        f"Mortgage: -£{monthly_mortgage:,.0f}",
        f"Running costs: -£{monthly_costs:,.0f}",
        f"Net cashflow: £{monthly_cashflow:,.0f}/month {'✓' if monthly_cashflow > 0 else '✗'}",
        f"Annual cashflow: £{monthly_cashflow * 12:,.0f}",
        "",
        "**Upfront Costs**",
        f"Deposit (25%): £{deposit:,.0f}",
        f"SDLT (inc. 3% surcharge): £{sdlt:,.0f}",
        "Legal/valuation (est.): £2,000",
        f"Total cash required: £{total_cash:,.0f}",
        "",
        "**Equity Release Angle**",
        f"To fund this deposit via remortgage, the existing property needs",
        f"at least £{equity_needed:,.0f} available equity (at 75% LTV).",
        "",
        "**Verdict**",
    ]

    issues    = []
    positives = []

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


# ── FastAPI endpoint ───────────────────────────────────────────────────────────
@router.get("/deal/analyse")
def deal_analyse_get(q: str):
    """
    Quick GET version for testing: /deal/analyse?q=3+bed+£200k+£1200/month
    """
    return {"result": analyse_deal(q)}
