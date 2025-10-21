#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
自動補營養值工具 v3（整合台灣 FDA 食品資料庫）
--------------------------------------------------
優先順序：
  1️⃣ NUTRITION_REF 精準補值
  2️⃣ Ontology 分類平均補值
  3️⃣ 連線台灣食藥署 FDA 食品營養成分開放資料 API
  4️⃣ 自動備份 CSV，支援快取避免重複查詢
"""

import csv
import json
import os
import requests
from datetime import datetime

CSV_PATH = "backend/app/data/foods_tw.csv"
ONTO_PATH = "backend/app/data/food_ontology.json"
CACHE_PATH = "backend/app/data/fda_cache.json"

FDA_API_URL = "https://data.fda.gov.tw/opendata/exportDataList.do?method=ExportDataList&InfoId=17"  # 食品營養成分資料集

# --------------------------------------------------
# 🧠 內建營養參考資料（與前一版相同）
NUTRITION_REF = {
    "chicken breast": {"kcal": 165, "protein_g": 31, "fat_g": 3.6, "carb_g": 0},
    "beef steak": {"kcal": 250, "protein_g": 26, "fat_g": 17, "carb_g": 0},
    "salmon": {"kcal": 208, "protein_g": 20, "fat_g": 13, "carb_g": 0},
    "yellowback sea bream": {"kcal": 118, "protein_g": 20, "fat_g": 3, "carb_g": 0},
    "silken tofu": {"kcal": 55, "protein_g": 5, "fat_g": 3, "carb_g": 1},
    "firm tofu": {"kcal": 144, "protein_g": 15, "fat_g": 8, "carb_g": 2},
    "egg": {"kcal": 143, "protein_g": 13, "fat_g": 9.5, "carb_g": 0.7},
    "boiled egg": {"kcal": 155, "protein_g": 13, "fat_g": 11, "carb_g": 1},
    "century egg": {"kcal": 140, "protein_g": 12, "fat_g": 10, "carb_g": 1},
    "white rice": {"kcal": 130, "protein_g": 2.7, "fat_g": 0.3, "carb_g": 28},
    "broccoli": {"kcal": 34, "protein_g": 2.8, "fat_g": 0.4, "carb_g": 6.6},
    "soy sauce": {"kcal": 53, "protein_g": 8, "fat_g": 0, "carb_g": 5},
}

CATEGORY_AVG = {
    "魚類": {"kcal": 150, "protein_g": 20, "fat_g": 8, "carb_g": 0},
    "肉類": {"kcal": 230, "protein_g": 25, "fat_g": 15, "carb_g": 0},
    "豆製品": {"kcal": 100, "protein_g": 10, "fat_g": 6, "carb_g": 3},
    "蔬菜": {"kcal": 35, "protein_g": 2, "fat_g": 0.5, "carb_g": 6},
    "主食": {"kcal": 130, "protein_g": 3, "fat_g": 0.5, "carb_g": 28},
    "醬料": {"kcal": 80, "protein_g": 2, "fat_g": 1, "carb_g": 10},
    "蛋類": {"kcal": 150, "protein_g": 13, "fat_g": 10, "carb_g": 1},
}

# --------------------------------------------------
def norm(s: str) -> str:
    s = (s or "").strip().lower()
    for ch in (" ", "-", "_"):
        s = s.replace(ch, "")
    return s

def load_json(path):
    if not os.path.exists(path):
        return {}
    with open(path, "r", encoding="utf-8") as f:
        try:
            return json.load(f)
        except:
            return {}

def save_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def backup_csv(path):
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    bak = f"{path}.bak.{ts}"
    with open(path, "rb") as src, open(bak, "wb") as dst:
        dst.write(src.read())
    print(f"🧳 已備份 CSV：{bak}")

def fetch_from_fda(keyword: str):
    """呼叫台灣 FDA API，尋找最接近的食材資料"""
    try:
        resp = requests.get(FDA_API_URL, timeout=15)
        if resp.status_code != 200:
            return None
        data = resp.text.splitlines()
        keyword = keyword.strip().lower()
        for line in data:
            if keyword in line.lower():
                cols = line.split(",")
                if len(cols) >= 6:
                    try:
                        kcal = float(cols[2])
                        protein = float(cols[3])
                        fat = float(cols[4])
                        carb = float(cols[5])
                        return {"kcal": kcal, "protein_g": protein, "fat_g": fat, "carb_g": carb}
                    except:
                        continue
        return None
    except Exception as e:
        print(f"[FDA] 無法取得資料: {e}")
        return None

def fill_values():
    cache = load_json(CACHE_PATH)
    ontology = load_json(ONTO_PATH)

    if not os.path.exists(CSV_PATH):
        raise FileNotFoundError(f"❌ 找不到 CSV：{CSV_PATH}")

    with open(CSV_PATH, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        fieldnames = [h.lstrip("\ufeff") for h in reader.fieldnames]
        rows = [dict(r) for r in reader]

    ref_norm = {norm(k): v for k, v in NUTRITION_REF.items()}
    onto_norm = {norm(d.get("canonical", "")): d for d in ontology if isinstance(d, dict)}
    updated = 0

    for r in rows:
        key = norm(r.get("canonical", ""))
        if not key:
            continue
        def is_empty(x): return x in ("", None, "0", "0.0", 0, 0.0)

        ref = ref_norm.get(key)
        if not ref:
            onto = onto_norm.get(key)
            if onto:
                cat = onto.get("category")
                ref = CATEGORY_AVG.get(cat)

        if not ref:
            if key in cache:
                ref = cache[key]
            else:
                fda = fetch_from_fda(r.get("name", "") or r.get("canonical", ""))
                if fda:
                    cache[key] = fda
                    ref = fda
                    print(f"🔍 從 FDA 取得資料: {r.get('canonical')} -> {fda}")

        if not ref:
            continue

        for k in ["kcal", "protein_g", "fat_g", "carb_g"]:
            if is_empty(r.get(k)):
                r[k] = str(ref[k])
                updated += 1

    if updated == 0:
        print("✅ 沒有需要補值的項目。")
        return

    backup_csv(CSV_PATH)
    with open(CSV_PATH, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    save_json(CACHE_PATH, cache)
    print(f"✅ 已更新 {CSV_PATH}，共補入 {updated} 個欄位。")
    print(f"🗃️ 快取已同步到 {CACHE_PATH}")

if __name__ == "__main__":
    fill_values()
