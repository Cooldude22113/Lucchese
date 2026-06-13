"""
integrations/sheets/cross_reference.py
Cross-reference recipe ingredients against the raw ingredients list (Rule 11).

Surfaces anything used in a recipe that has no close match in the raw ingredients
sheet — useful for catching supplier gaps before a cook.
"""

from __future__ import annotations

from difflib import SequenceMatcher

from integrations.sheets.ingredients_reader import get_ingredients
from integrations.sheets.recipes_reader import get_recipes


def cross_reference_ingredients(
    sheets_to_check: list[str] | None = None,
    similarity_threshold: float = 0.8,
) -> dict:
    """
    Compare raw ingredients against recipe ingredients via fuzzy name matching.
    Returns the missing ingredients plus summary counts.
    """
    if sheets_to_check is None:
        sheets_to_check = ["Standard Recipe", "Bulking Recipes"]

    raw_ingredients = get_ingredients()
    raw_names = {ing["name"].lower().strip() for ing in raw_ingredients}

    recipe_ingredients: set[str] = set()
    for sheet_name in sheets_to_check:
        try:
            meals = get_recipes(sheet_name)
            for meal in meals.values():
                for ing in meal["ingredients"]:
                    if ing["ingredient"].strip():
                        recipe_ingredients.add(ing["ingredient"].lower().strip())
        except Exception as e:
            print(f"Error fetching from {sheet_name}: {e}")
            continue

    missing = []
    for recipe_ing in sorted(recipe_ingredients):
        best_match = max(
            ((SequenceMatcher(None, recipe_ing, raw_name).ratio(), raw_name)
             for raw_name in raw_names),
            default=(0, None),
        )
        if best_match[0] < similarity_threshold:
            missing.append({
                "ingredient": recipe_ing,
                "best_match": best_match[1],
                "match_score": round(best_match[0], 2),
            })

    return {
        "missing_count": len(missing),
        "missing_ingredients": missing,
        "sheets_checked": sheets_to_check,
        "total_raw_ingredients": len(raw_names),
        "total_recipe_ingredients": len(recipe_ingredients),
    }
