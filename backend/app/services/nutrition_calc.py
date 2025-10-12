import os, csv, re
from typing import List, Dict, Optional

DATA_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "..", "data", "foods_tw.csv")

SYNONYMS = [
    (r"咖哩雞|雞腿|雞肉", "雞胸肉"),
    (r"白飯|米飯|飯", "白飯"),
    (r"南瓜", "南瓜"),
    (r"胡蘿蔔|紅蘿蔔|蘿蔔", "胡蘿蔔"),
    (r"茄子|矮瓜|茄", "茄子"),
    (r"青椒|甜椒|青色椒|青椒", "青椒"),
    (r"玉米筍|玉米荀|baby corn|玉米", "玉米筍"),
    (r"蓮藕|藕", "蓮藕"),
    (r"溫泉蛋|糖心蛋|溏心蛋|半熟蛋|水波蛋", "雞蛋"),
]

def _load_foods():
    foods = []
    with open(DATA_PATH, newline='', encoding='utf-8') as f:
        for row in csv.DictReader(f):
            for k in ["unit_g","kcal_per_100g","protein_g_per_100g","fat_g_per_100g","carb_g_per_100g"]:
                row[k] = float(row[k])
            foods.append(row)
    return foods

FOODS = _load_foods()

def _normalize_name(name: str) -> str:
    n = name.strip()
    for pattern, target in SYNONYMS:
        if re.search(pattern, n):
            return target
    return n

def lookup_food(name: str) -> Optional[Dict]:
    target = _normalize_name(name)
    for r in FOODS:
        if r['name'] == target:
            return r
    low = target.lower()
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
            summary.append({"name": name, "grams": grams, "matched": False, "kcal": None, "protein_g": None, "fat_g": None, "carb_g": None})
            continue
        kcal = found["kcal_per_100g"] * grams / 100.0
        protein = found["protein_g_per_100g"] * grams / 100.0
        fat = found["fat_g_per_100g"] * grams / 100.0
        carb = found["carb_g_per_100g"] * grams / 100.0
        totals["kcal"] += kcal; totals["protein_g"] += protein; totals["fat_g"] += fat; totals["carb_g"] += carb
        summary.append({"name": _normalize_name(name), "grams": grams, "matched": True, "kcal": round(kcal,1), "protein_g": round(protein,1), "fat_g": round(fat,1), "carb_g": round(carb,1)})
    for k in totals: totals[k] = round(totals[k],1)
    return {"items": summary, "totals": totals}
