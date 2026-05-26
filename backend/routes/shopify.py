"""
routes/shopify.py
─────────────────
Shopify and menu-related endpoints:

  POST /shopify/add-meal      — create standard + bulking products on Shopify
  GET  /cross-reference       — check raw ingredients vs recipe ingredients

Also exposes add_meal() as a callable for routes/chat.py's
inline "shopify add <meal>" command intercept.

Depends on shared state injected via init_shopify_state().
Pure data helpers (calc_macros, normalise_meal_name) have no side effects
and are safe to import directly if needed elsewhere.
"""

from fastapi import APIRouter
from pydantic import BaseModel
from sheets import get_recipes, cross_reference_ingredients
from shopify_api import create_meal_products as _create_meal_products

router = APIRouter()

# ── Request model ─────────────────────────────────────────────────────────────
class ShopifyMealRequest(BaseModel):
    meal_name: str


# ── Pure helpers ──────────────────────────────────────────────────────────────
def normalise_meal_name(name: str) -> str:
    """Normalise for comparison — handles & vs and, case, whitespace."""
    return name.lower().replace(' & ', ' and ').replace('&', 'and').strip()


def calc_macros(meal: dict) -> dict:
    """Sum macro totals across all ingredients in a meal."""
    totals = {"kcal": 0.0, "protein": 0.0, "carbs": 0.0, "fat": 0.0}
    for ingredient in meal["ingredients"]:
        for key in totals:
            try:
                totals[key] += float(ingredient.get(key) or 0)
            except (ValueError, TypeError):
                pass
    return totals


# ── Core add-meal logic (used by endpoint AND chat intercept) ─────────────────
async def add_meal(meal_name: str) -> tuple[str | None, dict | None]:
    """
    Look up meal in Sheets, calculate macros, push to Shopify.
    Returns (error_string, None) on failure or (None, result_dict) on success.

    Result dict:
        matched         — exact meal name as it appears in Sheets
        standard_macros — macro totals for standard portion
        bulking_macros  — macro totals for bulking portion
        created         — list of Shopify product dicts returned by shopify_api
    """
    standard_recipes = get_recipes("Standard Recipe")
    bulking_recipes  = get_recipes("Bulking Recipes")

    matched = next(
        (m for m in standard_recipes if normalise_meal_name(m) == normalise_meal_name(meal_name)),
        None
    )

    if not matched:
        return (
            f"Couldn't find '{meal_name}' in the recipe sheet. "
            f"Check the exact meal name and try again.",
            None
        )

    standard_macros = calc_macros(standard_recipes[matched])
    bulking_macros  = (
        calc_macros(bulking_recipes[matched])
        if matched in bulking_recipes
        else standard_macros
    )

    created = await _create_meal_products(matched, standard_macros, bulking_macros)

    return None, {
        "matched":         matched,
        "standard_macros": standard_macros,
        "bulking_macros":  bulking_macros,
        "created":         created,
    }


# ── POST /shopify/add-meal ────────────────────────────────────────────────────
@router.post("/shopify/add-meal")
async def add_meal_to_shopify(req: ShopifyMealRequest):
    """
    Create standard and bulking Shopify products for a given meal name.
    Meal must exist in the Standard Recipe sheet.
    """
    error, result = await add_meal(req.meal_name.strip())

    if error:
        return {"error": error}

    return {
        "success":          True,
        "meal":             result["matched"],
        "standard_macros":  result["standard_macros"],
        "bulking_macros":   result["bulking_macros"],
        "products_created": result["created"],
    }


# ── GET /cross-reference ──────────────────────────────────────────────────────
@router.get("/cross-reference")
def cross_reference(sheets: str = None, threshold: float = 0.8):
    """
    Cross-reference raw ingredients list against recipe ingredients.
    Surfaces anything used in a recipe that isn't in the raw ingredients sheet —
    useful for catching supplier gaps before a cook.

    Query params:
        sheets    — comma-separated sheet names to check
                    (default: both Standard Recipe and Bulking Recipes)
        threshold — fuzzy match similarity threshold 0–1 (default: 0.8)
    """
    try:
        sheets_list = (
            [s.strip() for s in sheets.split(",")]
            if sheets else None
        )
        return cross_reference_ingredients(sheets_list, threshold)
    except Exception as e:
        return {"error": str(e)}
