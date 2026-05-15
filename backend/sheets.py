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

def get_menu_context(query: str) -> str:
    query_lower = query.lower()
    context_parts = []

    standard = get_recipes('Standard Recipe')
    bulking = get_recipes('Bulking Recipes')

    # Full menu list
    if any(w in query_lower for w in ['menu', 'meals', 'all', 'list']):
        lines = ["Current menu:"]
        for meal_name in standard.keys():
            lines.append(f"  - {meal_name}")
        context_parts.append("\n".join(lines))
    
    # Comparison queries — pass all meal totals
    if any(w in query_lower for w in ['highest', 'lowest', 'most', 'least', 'best', 'compare']):
        standard = get_recipes('Standard Recipe')
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

    return "\n\n".join(context_parts)