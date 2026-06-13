"""
api/routes/business_routes.py
Thin HTTP layer for business-domain endpoints (Rule 2):
  POST /shopify/add-meal   — create standard + bulking Shopify products for a meal
  GET  /cross-reference    — raw vs recipe ingredient gap check
  GET  /deal/analyse       — property deal analysis

All logic lives in business_logic/** and integrations/**.
"""

from __future__ import annotations

from fastapi import APIRouter

from api.schemas.business import ShopifyMealRequest
from business_logic.meal_prep.shopify_meal_builder import add_meal
from business_logic.property.deal_calculator import analyse_deal
from integrations.sheets.cross_reference import cross_reference_ingredients

router = APIRouter()


@router.post("/shopify/add-meal")
async def add_meal_to_shopify(req: ShopifyMealRequest):
    """Create standard and bulking Shopify products for a meal in the recipe sheet."""
    error, result = await add_meal(req.meal_name.strip())
    if error:
        return {"error": error}
    return {
        "success": True,
        "meal": result["matched"],
        "standard_macros": result["standard_macros"],
        "bulking_macros": result["bulking_macros"],
        "products_created": result["created"],
    }


@router.get("/cross-reference")
def cross_reference(sheets: str = None, threshold: float = 0.8):
    """Cross-reference raw ingredients against recipe ingredients."""
    try:
        sheets_list = [s.strip() for s in sheets.split(",")] if sheets else None
        return cross_reference_ingredients(sheets_list, threshold)
    except Exception as e:
        return {"error": str(e)}


@router.get("/deal/analyse")
def deal_analyse_get(q: str):
    """Quick GET deal analysis: /deal/analyse?q=3+bed+£200k+£1200/month"""
    return {"result": analyse_deal(q)}
