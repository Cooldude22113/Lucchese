from googleapiclient.discovery import build
from google.oauth2 import service_account

SCOPES = ['https://www.googleapis.com/auth/spreadsheets.readonly']
CREDENTIALS_FILE = 'credentials.json'
SPREADSHEET_ID = '18wRNdcKcrXmK4xNqS1G3_Hn2fRhD_YTli83-ac6o_mk'

creds = service_account.Credentials.from_service_account_file(
    CREDENTIALS_FILE, scopes=SCOPES)
service = build('sheets', 'v4', credentials=creds)
sheet = service.spreadsheets()

def get_ingredients():
    result = sheet.values().get(
        spreadsheetId=SPREADSHEET_ID,
        range='Ingredients!A2:H200'
    ).execute()
    values = result.get('values', [])
    ingredients = []
    for row in values:
        if not row or not row[0]:
            continue
        ingredients.append({
            'name':         row[0] if len(row) > 0 else '',
            'brand':        row[1] if len(row) > 1 else '',
            'allergens':    row[2] if len(row) > 2 else '',
            'kcal_per_100g': row[3] if len(row) > 3 else '',
            'protein':      row[4] if len(row) > 4 else '',
            'carbs':        row[5] if len(row) > 5 else '',
            'fat':          row[6] if len(row) > 6 else '',
            'raw_factor':   row[7] if len(row) > 7 else '',
        })
    return ingredients

def get_recipes(sheet_name='Standard Recipe'):
    result = sheet.values().get(
        spreadsheetId=SPREADSHEET_ID,
        range=f'{sheet_name}!A2:K500'
    ).execute()
    values = result.get('values', [])
    meals = {}
    for row in values:
        if not row or not row[0]:
            continue
        meal_name = row[0]
        if meal_name not in meals:
            meals[meal_name] = {'name': meal_name, 'ingredients': []}
        meals[meal_name]['ingredients'].append({
            'category':   row[1] if len(row) > 1 else '',
            'ingredient': row[2] if len(row) > 2 else '',
            'weight_g':   row[3] if len(row) > 3 else '',
            'kcal':       row[5] if len(row) > 5 else '',
            'protein':    row[6] if len(row) > 6 else '',
            'carbs':      row[7] if len(row) > 7 else '',
            'fat':        row[8] if len(row) > 8 else '',
            'allergens':  row[9] if len(row) > 9 else '',
            'notes':      row[10] if len(row) > 10 else '',
        })
    return meals

def cross_reference_ingredients(sheets_to_check: list[str] | None = None, similarity_threshold: float = 0.8) -> dict:
    """
    Compare raw ingredients against recipe ingredients.
    Returns missing ingredients (in recipes but not in raw ingredients list).

    sheets_to_check: list of recipe sheet names, defaults to ['Standard Recipe', 'Bulking Recipes']
    similarity_threshold: how closely names must match (0-1, 1 is exact). 0.8 catches "Chicken Breast" vs "Chicken breast"
    """
    from difflib import SequenceMatcher

    if sheets_to_check is None:
        sheets_to_check = ['Standard Recipe', 'Bulking Recipes']

    # Get raw ingredients — normalize names for comparison
    raw_ingredients = get_ingredients()
    raw_names = {ing['name'].lower().strip() for ing in raw_ingredients}

    # Extract all unique ingredient names from recipes
    recipe_ingredients = set()
    for sheet_name in sheets_to_check:
        try:
            meals = get_recipes(sheet_name)
            for meal in meals.values():
                for ing in meal['ingredients']:
                    if ing['ingredient'].strip():
                        recipe_ingredients.add(ing['ingredient'].lower().strip())
        except Exception as e:
            print(f"Error fetching from {sheet_name}: {e}")
            continue

    # Find missing ingredients using fuzzy matching
    missing = []
    for recipe_ing in sorted(recipe_ingredients):
        # Check if there's a close match in raw ingredients
        best_match = max(
            ((SequenceMatcher(None, recipe_ing, raw_name).ratio(), raw_name)
             for raw_name in raw_names),
            default=(0, None)
        )

        if best_match[0] < similarity_threshold:
            missing.append({
                'ingredient': recipe_ing,
                'best_match': best_match[1],
                'match_score': round(best_match[0], 2)
            })

    return {
        'missing_count': len(missing),
        'missing_ingredients': missing,
        'sheets_checked': sheets_to_check,
        'total_raw_ingredients': len(raw_names),
        'total_recipe_ingredients': len(recipe_ingredients),
    }


def get_raw_prices() -> dict:
    """Fetch raw ingredient prices from RawPrice sheet. Returns {product_name: price_data}"""
    try:
        result = sheet.values().get(
            spreadsheetId=SPREADSHEET_ID,
            range='RawPrice!A2:G500'
        ).execute()
        values = result.get('values', [])
        prices = {}
        for row in values:
            if not row or not row[0]:
                continue
            product_name = row[0].lower().strip()
            prices[product_name] = {
                'product': row[0] if len(row) > 0 else '',
                'supplier': row[1] if len(row) > 1 else '',
                'price_inc_vat': row[2] if len(row) > 2 else None,
                'notes': row[3] if len(row) > 3 else '',
                'parsed_notes': row[4] if len(row) > 4 else '',
                'total_kg': row[5] if len(row) > 5 else None,
                'price_per_kg': row[6] if len(row) > 6 else None,
            }
        return prices
    except Exception as e:
        print(f"Error fetching raw prices: {e}")
        return {}

def calculate_meal_costs(sheet_names: list[str] | None = None) -> dict:
    """Calculate total ingredient cost for each meal, tracking suppliers. Returns {meal_name: {standard_cost, bulking_cost, suppliers}}"""
    if sheet_names is None:
        sheet_names = ['Standard Recipe', 'Bulking Recipes']

    raw_prices = get_raw_prices()
    meal_costs = {}

    for sheet_name in sheet_names:
        try:
            meals = get_recipes(sheet_name)
            for meal_name, meal in meals.items():
                cost_key = 'standard_cost' if sheet_name == 'Standard Recipe' else 'bulking_cost'
                supplier_key = 'standard_suppliers' if sheet_name == 'Standard Recipe' else 'bulking_suppliers'

                total_cost = 0
                supplier_breakdown = {}  # {supplier: total_cost}
                missing_prices = []

                for ing in meal['ingredients']:
                    ing_name = ing['ingredient'].lower().strip()
                    weight_g = float(ing['weight_g'] or 0) if ing['weight_g'] else 0

                    # Try to find exact or close match in raw prices
                    matched = None
                    for raw_name, price_data in raw_prices.items():
                        if raw_name in ing_name or ing_name in raw_name:
                            matched = price_data
                            break

                    if matched and matched['price_per_kg']:
                        try:
                            price_per_kg = float(matched['price_per_kg'])
                            cost = (weight_g / 1000) * price_per_kg
                            total_cost += cost

                            # Track supplier breakdown
                            supplier = matched['supplier'] or 'Unknown'
                            supplier_breakdown[supplier] = supplier_breakdown.get(supplier, 0) + cost
                        except:
                            missing_prices.append(ing_name)
                    elif weight_g > 0:
                        missing_prices.append(ing_name)

                if meal_name not in meal_costs:
                    meal_costs[meal_name] = {}
                meal_costs[meal_name][cost_key] = round(total_cost, 2)
                meal_costs[meal_name][supplier_key] = {k: round(v, 2) for k, v in supplier_breakdown.items()}
                if missing_prices:
                    meal_costs[meal_name]['missing_prices'] = missing_prices
        except Exception as e:
            print(f"Error calculating costs for {sheet_name}: {e}")

    return meal_costs

def get_margins() -> dict:
    """Fetch meal margins by calculating costs from RawPrice sheet."""
    return calculate_meal_costs()


def get_menu_context(query: str) -> str:
    query_lower = query.lower()
    context_parts = []

    standard = get_recipes('Standard Recipe')
    bulking = get_recipes('Bulking Recipes')

    # Full menu list — ALWAYS include
    lines = ["Current menu (all meals):"]
    for meal_name in standard.keys():
        lines.append(f"  - {meal_name}")
    context_parts.append("\n".join(lines))

    # Comparison queries — pass all meal totals
    if any(w in query_lower for w in ['highest', 'lowest', 'most', 'least', 'best', 'compare']):
        lines = ["All meal totals (standard):"]
        for meal_name, meal in standard.items():
            total_kcal    = sum(float(i['kcal'] or 0)    for i in meal['ingredients'] if i['kcal'])
            total_protein = sum(float(i['protein'] or 0) for i in meal['ingredients'] if i['protein'])
            total_carbs   = sum(float(i['carbs'] or 0)   for i in meal['ingredients'] if i['carbs'])
            total_fat     = sum(float(i['fat'] or 0)     for i in meal['ingredients'] if i['fat'])
            lines.append(f"  - {meal_name}: {total_kcal:.0f} kcal | {total_protein:.1f}g protein | {total_carbs:.1f}g carbs | {total_fat:.1f}g fat")
        context_parts.append("\n".join(lines))

    # Specific meal macros
    for meal_name, meal in standard.items():
        if any(word in query_lower for word in meal_name.lower().split()):
            total_kcal = total_protein = total_carbs = total_fat = 0
            ingredient_lines = []

            for i in meal['ingredients']:
                ingredient_lines.append(
                    f"  - {i['ingredient']} {i['weight_g']}g ({i['category']})"
                )
                try:
                    total_kcal    += float(i['kcal'] or 0)
                    total_protein += float(i['protein'] or 0)
                    total_carbs   += float(i['carbs'] or 0)
                    total_fat     += float(i['fat'] or 0)
                except:
                    pass

            # Also get bulking totals
            bulking_kcal = bulking_protein = bulking_carbs = bulking_fat = 0
            if meal_name in bulking:
                for i in bulking[meal_name]['ingredients']:
                    try:
                        bulking_kcal    += float(i['kcal'] or 0)
                        bulking_protein += float(i['protein'] or 0)
                        bulking_carbs   += float(i['carbs'] or 0)
                        bulking_fat     += float(i['fat'] or 0)
                    except:
                        pass

            lines = [
                f"Recipe: {meal_name}",
                f"Ingredients:",
            ] + ingredient_lines + [
                f"",
                f"STANDARD MACROS (total for meal):",
                f"  Calories: {total_kcal:.0f} kcal",
                f"  Protein:  {total_protein:.1f}g",
                f"  Carbs:    {total_carbs:.1f}g",
                f"  Fat:      {total_fat:.1f}g",
                f"",
                f"BULKING MACROS (total for meal):",
                f"  Calories: {bulking_kcal:.0f} kcal",
                f"  Protein:  {bulking_protein:.1f}g",
                f"  Carbs:    {bulking_carbs:.1f}g",
                f"  Fat:      {bulking_fat:.1f}g",
            ]
            context_parts.append("\n".join(lines))

    # Allergen queries
    if any(w in query_lower for w in [
        'allergen', 'contains', 'tree nut', 'tree nuts', 'nuts',
        'sulphur', 'sulfur', 'dioxide', 'soybean', 'soybeans', 'soy',
        'sesame', 'peanut', 'peanuts', 'mustard', 'mollusc', 'molluscs',
        'milk', 'dairy', 'lupin', 'fish', 'egg', 'eggs',
        'crustacean', 'crustaceans', 'gluten', 'celery'
    ]):
        ingredients = get_ingredients()
        lines = ["Allergen information by ingredient:"]
        for i in ingredients:
            if i['allergens']:
                lines.append(f"  - {i['name']}: {i['allergens']}")
        context_parts.append("\n".join(lines))

    # Cross-reference raw vs recipe ingredients
    if any(w in query_lower for w in ['missing', 'cross-reference', 'raw ingredients', 'cross reference']):
        xref = cross_reference_ingredients()
        lines = [f"Missing ingredients (in recipes but not in raw ingredients list):"]
        if xref['missing_ingredients']:
            for item in xref['missing_ingredients']:
                lines.append(f"  - {item['ingredient']} (closest match: {item['best_match']} at {item['match_score']*100:.0f}% similarity)")
        else:
            lines.append("  ✓ All recipe ingredients are in the raw ingredients list")
        lines.extend([
            f"",
            f"Stats: {xref['total_recipe_ingredients']} total recipe ingredients, {xref['total_raw_ingredients']} raw ingredients available"
        ])
        context_parts.append("\n".join(lines))

    # Meal margins and pricing
    if any(w in query_lower for w in ['margin', 'profit', 'price', 'cost', 'pricing', 'supplier']):
        costs = get_margins()
        if costs:
            lines = ["Meal ingredient costs and suppliers:"]
            for meal_name in sorted(costs.keys()):
                c = costs[meal_name]
                lines.append(f"  {meal_name}:")
                if 'standard_cost' in c:
                    lines.append(f"    Standard cost: £{c['standard_cost']:.2f}")
                    if 'standard_suppliers' in c and c['standard_suppliers']:
                        suppliers = c['standard_suppliers']
                        for supplier, cost in sorted(suppliers.items(), key=lambda x: x[1], reverse=True):
                            pct = (cost / c['standard_cost'] * 100) if c['standard_cost'] > 0 else 0
                            lines.append(f"      • {supplier}: £{cost:.2f} ({pct:.0f}%)")
                if 'bulking_cost' in c:
                    lines.append(f"    Bulking cost: £{c['bulking_cost']:.2f}")
                    if 'bulking_suppliers' in c and c['bulking_suppliers']:
                        suppliers = c['bulking_suppliers']
                        for supplier, cost in sorted(suppliers.items(), key=lambda x: x[1], reverse=True):
                            pct = (cost / c['bulking_cost'] * 100) if c['bulking_cost'] > 0 else 0
                            lines.append(f"      • {supplier}: £{cost:.2f} ({pct:.0f}%)")
                if 'missing_prices' in c and c['missing_prices']:
                    lines.append(f"    ⚠ No prices for: {', '.join(c['missing_prices'][:3])}")
            context_parts.append("\n".join(lines))

    return "\n\n".join(context_parts)