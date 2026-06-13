"""
business_logic/meal_prep/meal_lookup.py
Match a requested meal name against the recipe set (Rule 10).
"""

from __future__ import annotations

from business_logic.meal_prep.meal_normaliser import normalise_meal_name


def find_meal(meal_name: str, recipes: dict) -> str | None:
    """
    Return the exact recipe key matching meal_name (normalised), or None.
    `recipes` is the {meal_name: {...}} mapping from recipes_reader.get_recipes().
    """
    target = normalise_meal_name(meal_name)
    return next(
        (m for m in recipes if normalise_meal_name(m) == target),
        None,
    )
