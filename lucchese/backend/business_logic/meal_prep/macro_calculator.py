"""
business_logic/meal_prep/macro_calculator.py
Macro totals for a meal (Rule 10: pure, testable domain logic).
"""

from __future__ import annotations


def calc_macros(meal: dict) -> dict:
    """Sum kcal/protein/carbs/fat across all ingredients in a meal."""
    totals = {"kcal": 0.0, "protein": 0.0, "carbs": 0.0, "fat": 0.0}
    for ingredient in meal["ingredients"]:
        for key in totals:
            try:
                totals[key] += float(ingredient.get(key) or 0)
            except (ValueError, TypeError):
                pass
    return totals
