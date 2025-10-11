import os, csv
from typing import List, Dict

DATA_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "..", "data", "foods_tw.csv")

def _load_foods():
    foods = []
    with open(DATA_PATH, newline='', encoding='utf-8') as f:
        for row in csv.DictReader(f):
            row['unit_g'] = float(row['unit_g'])
            row['kcal_per_100g'] = float(row['kcal_per_100g'])
            row['protein_g_per_100g'] = float(row['protein_g_per_100g'])
            row['fat_g_per_100g'] = float(row['fat_g_per_100g'])
            row['carb_g_per_100g'] = float(row['carb_g_per_100g'])
            foods.append(row)
    return foods

FOODS = _load_foods()

def lookup_food(name: str):
    for r in FOODS:
        if r['name'] == name:
            return r
    low = name.lower()
    for r in FOODS:
        if low in r['name'].lower():
            return r
    return None

def summarize_items(items: List[Dict]):
    summary = []
    totals = {"kcal": 0.0, "protein_g": 0.0, "fat_g": 0.0, "carb_g": 0.0}
    for it in items:
        name = it["name"]
        grams = float(it.get("grams", 0))
        found = lookup_food(name)
        if not found:
            summary.append({
                "name": name, "grams": grams, "matched": False,
                "kcal": None, "protein_g": None, "fat_g": None, "carb_g": None
            })
            continue
        kcal = found["kcal_per_100g"] * grams / 100.0
        protein = found["protein_g_per_100g"] * grams / 100.0
        fat = found["fat_g_per_100g"] * grams / 100.0
        carb = found["carb_g_per_100g"] * grams / 100.0

        totals["kcal"] += kcal
        totals["protein_g"] += protein
        totals["fat_g"] += fat
        totals["carb_g"] += carb

        summary.append({
            "name": name, "grams": grams, "matched": True,
            "kcal": round(kcal, 1),
            "protein_g": round(protein, 1),
            "fat_g": round(fat, 1),
            "carb_g": round(carb, 1)
        })
    for k in totals:
        totals[k] = round(totals[k], 1)
    return {"items": summary, "totals": totals}
