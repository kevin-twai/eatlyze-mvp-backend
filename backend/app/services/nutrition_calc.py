
import os
import pandas as pd
from typing import List, Dict

DATA_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "..", "data", "foods_tw.csv")
DF = pd.read_csv(DATA_PATH)

def lookup_food(name: str):
    row = DF[DF["name"] == name]
    if row.empty:
        row = DF[DF["name"].str.contains(name, case=False, na=False)]
    if row.empty:
        return None
    return row.iloc[0].to_dict()

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
            "kcal": round(kcal, 1), "protein_g": round(protein, 1),
            "fat_g": round(fat, 1), "carb_g": round(carb, 1)
        })
    for k in totals:
        totals[k] = round(totals[k], 1)
    return {"items": summary, "totals": totals}
