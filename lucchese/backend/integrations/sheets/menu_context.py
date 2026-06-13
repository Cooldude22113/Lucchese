"""
integrations/sheets/menu_context.py
Assemble query-relevant menu context from the Sheets data (Rule 11).

Builds a text block for the chat system prompt: always the full menu list, plus
conditional sections (totals comparison, specific meal macros, allergens,
cross-reference, margins) selected by keywords in the user's query.
"""

from __future__ import annotations

from integrations.sheets.cross_reference import cross_reference_ingredients
from integrations.sheets.prices_reader import get_margins
from integrations.sheets.ingredients_reader import get_ingredients
from integrations.sheets.recipes_reader import get_recipes


def get_menu_context(query: str) -> str:
    query_lower = query.lower()
    context_parts: list[str] = []

    standard = get_recipes("Standard Recipe")
    bulking = get_recipes("Bulking Recipes")

    # Full menu list — ALWAYS include.
    lines = ["Current menu (all meals):"]
    for meal_name in standard.keys():
        lines.append(f"  - {meal_name}")
    context_parts.append("\n".join(lines))

    # Comparison queries — pass all meal totals.
    if any(w in query_lower for w in ["highest", "lowest", "most", "least", "best", "compare"]):
        lines = ["All meal totals (standard):"]
        for meal_name, meal in standard.items():
            total_kcal    = sum(float(i["kcal"] or 0)    for i in meal["ingredients"] if i["kcal"])
            total_protein = sum(float(i["protein"] or 0) for i in meal["ingredients"] if i["protein"])
            total_carbs   = sum(float(i["carbs"] or 0)   for i in meal["ingredients"] if i["carbs"])
            total_fat     = sum(float(i["fat"] or 0)     for i in meal["ingredients"] if i["fat"])
            lines.append(
                f"  - {meal_name}: {total_kcal:.0f} kcal | {total_protein:.1f}g protein | "
                f"{total_carbs:.1f}g carbs | {total_fat:.1f}g fat"
            )
        context_parts.append("\n".join(lines))

    # Specific meal macros.
    for meal_name, meal in standard.items():
        if any(word in query_lower for word in meal_name.lower().split()):
            total_kcal = total_protein = total_carbs = total_fat = 0
            ingredient_lines = []

            for i in meal["ingredients"]:
                ingredient_lines.append(
                    f"  - {i['ingredient']} {i['weight_g']}g ({i['category']})"
                )
                try:
                    total_kcal    += float(i["kcal"] or 0)
                    total_protein += float(i["protein"] or 0)
                    total_carbs   += float(i["carbs"] or 0)
                    total_fat     += float(i["fat"] or 0)
                except Exception:
                    pass

            bulking_kcal = bulking_protein = bulking_carbs = bulking_fat = 0
            if meal_name in bulking:
                for i in bulking[meal_name]["ingredients"]:
                    try:
                        bulking_kcal    += float(i["kcal"] or 0)
                        bulking_protein += float(i["protein"] or 0)
                        bulking_carbs   += float(i["carbs"] or 0)
                        bulking_fat     += float(i["fat"] or 0)
                    except Exception:
                        pass

            lines = [
                f"Recipe: {meal_name}",
                "Ingredients:",
            ] + ingredient_lines + [
                "",
                "STANDARD MACROS (total for meal):",
                f"  Calories: {total_kcal:.0f} kcal",
                f"  Protein:  {total_protein:.1f}g",
                f"  Carbs:    {total_carbs:.1f}g",
                f"  Fat:      {total_fat:.1f}g",
                "",
                "BULKING MACROS (total for meal):",
                f"  Calories: {bulking_kcal:.0f} kcal",
                f"  Protein:  {bulking_protein:.1f}g",
                f"  Carbs:    {bulking_carbs:.1f}g",
                f"  Fat:      {bulking_fat:.1f}g",
            ]
            context_parts.append("\n".join(lines))

    # Allergen queries.
    if any(w in query_lower for w in [
        "allergen", "contains", "tree nut", "tree nuts", "nuts",
        "sulphur", "sulfur", "dioxide", "soybean", "soybeans", "soy",
        "sesame", "peanut", "peanuts", "mustard", "mollusc", "molluscs",
        "milk", "dairy", "lupin", "fish", "egg", "eggs",
        "crustacean", "crustaceans", "gluten", "celery",
    ]):
        ingredients = get_ingredients()
        lines = ["Allergen information by ingredient:"]
        for i in ingredients:
            if i["allergens"]:
                lines.append(f"  - {i['name']}: {i['allergens']}")
        context_parts.append("\n".join(lines))

    # Cross-reference raw vs recipe ingredients.
    if any(w in query_lower for w in ["missing", "cross-reference", "raw ingredients", "cross reference"]):
        xref = cross_reference_ingredients()
        lines = ["Missing ingredients (in recipes but not in raw ingredients list):"]
        if xref["missing_ingredients"]:
            for item in xref["missing_ingredients"]:
                lines.append(
                    f"  - {item['ingredient']} (closest match: {item['best_match']} "
                    f"at {item['match_score']*100:.0f}% similarity)"
                )
        else:
            lines.append("  ✓ All recipe ingredients are in the raw ingredients list")
        lines.extend([
            "",
            f"Stats: {xref['total_recipe_ingredients']} total recipe ingredients, "
            f"{xref['total_raw_ingredients']} raw ingredients available",
        ])
        context_parts.append("\n".join(lines))

    # Meal margins and pricing.
    if any(w in query_lower for w in ["margin", "profit", "price", "cost", "pricing", "supplier"]):
        costs = get_margins()
        if costs:
            lines = ["Meal ingredient costs and suppliers:"]
            for meal_name in sorted(costs.keys()):
                c = costs[meal_name]
                lines.append(f"  {meal_name}:")
                if "standard_cost" in c:
                    lines.append(f"    Standard cost: £{c['standard_cost']:.2f}")
                    if c.get("standard_suppliers"):
                        for supplier, cost in sorted(c["standard_suppliers"].items(), key=lambda x: x[1], reverse=True):
                            pct = (cost / c["standard_cost"] * 100) if c["standard_cost"] > 0 else 0
                            lines.append(f"      • {supplier}: £{cost:.2f} ({pct:.0f}%)")
                if "bulking_cost" in c:
                    lines.append(f"    Bulking cost: £{c['bulking_cost']:.2f}")
                    if c.get("bulking_suppliers"):
                        for supplier, cost in sorted(c["bulking_suppliers"].items(), key=lambda x: x[1], reverse=True):
                            pct = (cost / c["bulking_cost"] * 100) if c["bulking_cost"] > 0 else 0
                            lines.append(f"      • {supplier}: £{cost:.2f} ({pct:.0f}%)")
                if c.get("missing_prices"):
                    lines.append(f"    ⚠ No prices for: {', '.join(c['missing_prices'][:3])}")
            context_parts.append("\n".join(lines))

    return "\n\n".join(context_parts)
