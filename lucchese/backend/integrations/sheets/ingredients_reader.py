"""
integrations/sheets/ingredients_reader.py
Read the raw Ingredients sheet (Rule 11).
"""

from __future__ import annotations

from integrations.google.sheets_client import get_values


def get_ingredients() -> list[dict]:
    """Return the raw ingredient rows from the Ingredients sheet."""
    values = get_values("Ingredients!A2:H200")
    ingredients = []
    for row in values:
        if not row or not row[0]:
            continue
        ingredients.append({
            "name":          row[0] if len(row) > 0 else "",
            "brand":         row[1] if len(row) > 1 else "",
            "allergens":     row[2] if len(row) > 2 else "",
            "kcal_per_100g": row[3] if len(row) > 3 else "",
            "protein":       row[4] if len(row) > 4 else "",
            "carbs":         row[5] if len(row) > 5 else "",
            "fat":           row[6] if len(row) > 6 else "",
            "raw_factor":    row[7] if len(row) > 7 else "",
        })
    return ingredients
