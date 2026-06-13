"""
business_logic/property/deal_parser.py
Parse a free-text property deal into structured inputs (Rule 10).

Extracts price, monthly rent, room count, and strategy from messages like
"3 bed Basildon £200k asking, £1,200/month rent, single let". Returns (data, error)
so the caller surfaces the same guidance messages the original endpoint produced.
"""

from __future__ import annotations

import re


def parse_deal(text: str) -> tuple[dict | None, str | None]:
    """
    Returns (parsed, None) on success or (None, error_message) on failure.

    parsed keys: price (int), monthly_rent (int), rooms (int|None),
                 is_hmo (bool), is_r2r (bool)
    """
    t = text.lower()

    # Find all £ amounts — handles £200k, £200,000, £1,200, £950.
    amounts = []
    for m in re.finditer(r"£([\d,]+)(k)?", t):
        val = int(m.group(1).replace(",", ""))
        if m.group(2):
            val *= 1000
        amounts.append((m.start(), val))

    if not amounts:
        return None, (
            "I need at least a purchase price and monthly rent. "
            "Try: 'analyse deal: 3 bed Basildon £200k asking, £1,200/month rent, single let'"
        )

    # Price = largest amount.
    price = max(amounts, key=lambda x: x[1])[1]

    # Rent = amount near rent/month keywords, else smallest other amount.
    rent_match = re.search(r"£([\d,]+)(k)?\s*(?:/month|pcm|per month|month|rent|/mo)", t)
    if rent_match:
        monthly_rent = int(rent_match.group(1).replace(",", ""))
        if rent_match.group(2):
            monthly_rent *= 1000
    else:
        others = [v for _, v in amounts if v != price]
        monthly_rent = min(others) if others else None

    if not monthly_rent:
        return None, "I need an expected monthly rent to analyse this deal."

    # Rooms and strategy.
    rooms_match = re.search(r"(\d+)\s*(?:bed|room|bedroom)", t)
    rooms = int(rooms_match.group(1)) if rooms_match else None
    is_hmo = "hmo" in t or (rooms is not None and rooms >= 4)
    is_r2r = "r2r" in t or "rent to rent" in t

    # HMO: treat a small figure as per-room rent and scale by room count.
    if is_hmo and rooms and monthly_rent < 2000:
        monthly_rent = monthly_rent * rooms

    if not price and not is_r2r:
        return None, (
            "I need a purchase price to analyse this deal. "
            "Try: 'analyse deal: 3 bed Basildon £200k asking, £1,200/month rent, single let'"
        )

    return {
        "price": price,
        "monthly_rent": monthly_rent,
        "rooms": rooms,
        "is_hmo": is_hmo,
        "is_r2r": is_r2r,
    }, None
