"""
integrations/sheets/recipes_reader.py
Read recipe sheets into per-meal ingredient lists (Rule 11).
"""

from __future__ import annotations

from integrations.google.sheets_client import get_values


def get_recipes(sheet_name: str = "Standard Recipe") -> dict:
    """
    Return {meal_name: {"name", "ingredients": [...]}} for a recipe sheet.
    Rows are grouped by meal name (column A).
    """
    values = get_values(f"{sheet_name}!A2:K500")
    meals: dict = {}
    for row in values:
        if not row or not row[0]:
            continue
        meal_name = row[0]
        if meal_name not in meals:
            meals[meal_name] = {"name": meal_name, "ingredients": []}
        meals[meal_name]["ingredients"].append({
            "category":   row[1] if len(row) > 1 else "",
            "ingredient": row[2] if len(row) > 2 else "",
            "weight_g":   row[3] if len(row) > 3 else "",
            "kcal":       row[5] if len(row) > 5 else "",
            "protein":    row[6] if len(row) > 6 else "",
            "carbs":      row[7] if len(row) > 7 else "",
            "fat":        row[8] if len(row) > 8 else "",
            "allergens":  row[9] if len(row) > 9 else "",
            "notes":      row[10] if len(row) > 10 else "",
        })
    return meals
