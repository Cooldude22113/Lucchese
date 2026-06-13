"""
business_logic/meal_prep/shopify_meal_builder.py
Coordinate building a meal's Shopify products from Sheets data (Rule 10 domain
rule + Rule 11 integrations).

Looks the meal up in Sheets, computes standard/bulking macros, and pushes the
products to Shopify. Returns (error_string, None) on failure or (None, result)
on success, so callers (route or chat intercept) handle both uniformly.
"""

from __future__ import annotations

from business_logic.meal_prep.macro_calculator import calc_macros
from business_logic.meal_prep.meal_lookup import find_meal
from integrations.sheets.recipes_reader import get_recipes
from integrations.shopify.meal_products import create_meal_products


async def add_meal(meal_name: str) -> tuple[str | None, dict | None]:
    """
    Look up meal in Sheets, calculate macros, push to Shopify.

    Returns:
      (error, None)  on failure
      (None, result) on success, where result has keys:
        matched, standard_macros, bulking_macros, created
    """
    standard_recipes = get_recipes("Standard Recipe")
    bulking_recipes = get_recipes("Bulking Recipes")

    matched = find_meal(meal_name, standard_recipes)
    if not matched:
        return (
            f"Couldn't find '{meal_name}' in the recipe sheet. "
            f"Check the exact meal name and try again.",
            None,
        )

    standard_macros = calc_macros(standard_recipes[matched])
    bulking_macros = (
        calc_macros(bulking_recipes[matched])
        if matched in bulking_recipes
        else standard_macros
    )

    created = await create_meal_products(matched, standard_macros, bulking_macros)

    return None, {
        "matched": matched,
        "standard_macros": standard_macros,
        "bulking_macros": bulking_macros,
        "created": created,
    }
