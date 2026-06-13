"""
business_logic/meal_prep/meal_normaliser.py
Meal-name normalisation rule (Rule 10: pure, testable domain logic).
"""

from __future__ import annotations


def normalise_meal_name(name: str) -> str:
    """Normalise for comparison — handles & vs and, case, and whitespace."""
    return name.lower().replace(" & ", " and ").replace("&", "and").strip()
