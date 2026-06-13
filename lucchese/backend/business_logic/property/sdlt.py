"""
business_logic/property/sdlt.py
Stamp Duty Land Tax for investment property (Rule 10: pure, testable rule).

Includes the 3% additional-property surcharge across all bands.
"""

from __future__ import annotations


def calc_sdlt(price: int) -> float:
    """SDLT due on an investment-property purchase at the given price."""
    if price <= 125_000:
        return price * 0.03
    elif price <= 250_000:
        return 125_000 * 0.03 + (price - 125_000) * 0.05
    elif price <= 925_000:
        return 125_000 * 0.03 + 125_000 * 0.05 + (price - 250_000) * 0.08
    else:
        return (
            125_000 * 0.03
            + 125_000 * 0.05
            + 675_000 * 0.08
            + (price - 925_000) * 0.13
        )
