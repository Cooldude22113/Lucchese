"""
integrations/sheets/prices_reader.py
Raw ingredient prices and per-meal cost calculation (Rule 11).

Reads the RawPrice sheet and joins it against recipe ingredients to estimate the
ingredient cost and supplier split of each meal.
"""

from __future__ import annotations

from integrations.google.sheets_client import get_values
from integrations.sheets.recipes_reader import get_recipes


def get_raw_prices() -> dict:
    """Fetch raw ingredient prices keyed by lowercased product name."""
    try:
        values = get_values("RawPrice!A2:G500")
    except Exception as e:
        print(f"Error fetching raw prices: {e}")
        return {}

    prices: dict = {}
    for row in values:
        if not row or not row[0]:
            continue
        product_name = row[0].lower().strip()
        prices[product_name] = {
            "product":       row[0] if len(row) > 0 else "",
            "supplier":      row[1] if len(row) > 1 else "",
            "price_inc_vat": row[2] if len(row) > 2 else None,
            "notes":         row[3] if len(row) > 3 else "",
            "parsed_notes":  row[4] if len(row) > 4 else "",
            "total_kg":      row[5] if len(row) > 5 else None,
            "price_per_kg":  row[6] if len(row) > 6 else None,
        }
    return prices


def calculate_meal_costs(sheet_names: list[str] | None = None) -> dict:
    """
    Calculate total ingredient cost per meal, tracking suppliers.
    Returns {meal_name: {standard_cost, bulking_cost, *_suppliers, missing_prices}}.
    """
    if sheet_names is None:
        sheet_names = ["Standard Recipe", "Bulking Recipes"]

    raw_prices = get_raw_prices()
    meal_costs: dict = {}

    for sheet_name in sheet_names:
        try:
            meals = get_recipes(sheet_name)
            for meal_name, meal in meals.items():
                cost_key = "standard_cost" if sheet_name == "Standard Recipe" else "bulking_cost"
                supplier_key = (
                    "standard_suppliers" if sheet_name == "Standard Recipe" else "bulking_suppliers"
                )

                total_cost = 0
                supplier_breakdown: dict = {}
                missing_prices: list = []

                for ing in meal["ingredients"]:
                    ing_name = ing["ingredient"].lower().strip()
                    weight_g = float(ing["weight_g"] or 0) if ing["weight_g"] else 0

                    matched = None
                    for raw_name, price_data in raw_prices.items():
                        if raw_name in ing_name or ing_name in raw_name:
                            matched = price_data
                            break

                    if matched and matched["price_per_kg"]:
                        try:
                            price_per_kg = float(matched["price_per_kg"])
                            cost = (weight_g / 1000) * price_per_kg
                            total_cost += cost
                            supplier = matched["supplier"] or "Unknown"
                            supplier_breakdown[supplier] = supplier_breakdown.get(supplier, 0) + cost
                        except Exception:
                            missing_prices.append(ing_name)
                    elif weight_g > 0:
                        missing_prices.append(ing_name)

                if meal_name not in meal_costs:
                    meal_costs[meal_name] = {}
                meal_costs[meal_name][cost_key] = round(total_cost, 2)
                meal_costs[meal_name][supplier_key] = {
                    k: round(v, 2) for k, v in supplier_breakdown.items()
                }
                if missing_prices:
                    meal_costs[meal_name]["missing_prices"] = missing_prices
        except Exception as e:
            print(f"Error calculating costs for {sheet_name}: {e}")

    return meal_costs


def get_margins() -> dict:
    """Meal margins by calculating costs from the RawPrice sheet."""
    return calculate_meal_costs()
