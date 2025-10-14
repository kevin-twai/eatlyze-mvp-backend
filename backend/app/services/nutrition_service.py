# backend/app/services/nutrition_service.py
from __future__ import annotations

import os
import csv
from typing import Dict, List, Tuple

# 允許多種欄名（你現有 CSV 欄位可能略有不同）
NAME_KEYS = ("name", "食品名稱", "食材", "canonical", "別名")
KCAL_KEYS = ("kcal", "熱量(kcal)", "熱量", "能量kcal")
PROT_KEYS = ("protein_g", "蛋白質(g)", "蛋白質", "蛋白")
FAT_KEYS  = ("fat_g", "脂肪(g)", "脂肪")
CARB_KEYS = ("carb_g", "碳水(g)", "碳水化合物", "碳水")

def _col(row: dict, keys: Tuple[str, ...], default=None):
    for k in keys:
        if k in row and row[k] not in (None, ""):
            return row[k]
    return default

def _as_float(x, default=0.0):
    try:
        return float(str(x).strip())
    except Exception:
        return default

def _load_food_table(csv_path: str) -> List[dict]:
    if not os.path.exists(csv_path):
        raise FileNotFoundError(f"foods csv not found: {csv_path}")
    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        return [dict(r) for r in reader]

# --- 單例緩存：只載一次 ---
_FOODS: List[dict] = []
def _ensure_loaded():
    global _FOODS
    if _FOODS:
        return
    # 盡量相容多種部署路徑
    candidates = [
        os.path.join(os.path.dirname(__file__), "..", "data", "foods_tw.csv"),
        os.path.join(os.getcwd(), "backend", "app", "data", "foods_tw.csv"),
        os.path.join(os.getcwd(), "app", "data", "foods_tw.csv"),
    ]
    for p in candidates:
        p = os.path.normpath(p)
        if os.path.exists(p):
            _FOODS = _load_food_table(p)
            break
    if not _FOODS:
        raise FileNotFoundError("foods_tw.csv not found in common locations.")

def _norm(s: str) -> str:
    return str(s).strip().lower()

def _find_food(name: str) -> dict | None:
    """最簡匹配：先 canonical 完全比對，再次之用 name 欄做包含/等值"""
    _ensure_loaded()
    key = _norm(name)
    # 先完全比對
    for r in _FOODS:
        nm = _col(r, NAME_KEYS, "")
        if _norm(nm) == key:
            return r
    # 再嘗試包含（避免名稱略有出入）
    for r in _FOODS:
        nm = _col(r, NAME_KEYS, "")
        if key in _norm(nm):
            return r
    return None

def calc(items: List[Dict]) -> Tuple[List[Dict], Dict]:
    """
    items: [{'name':..., 'canonical':..., 'weight_g':...}, ...]
    return: (enriched_items, totals)
    enriched_items: 每項加上 kcal/protein_g/fat_g/carb_g
    totals: {'kcal':..., 'protein_g':..., 'fat_g':..., 'carb_g':...}
    """
    _ensure_loaded()

    enriched = []
    totals = dict(kcal=0.0, protein_g=0.0, fat_g=0.0, carb_g=0.0)

    for it in items or []:
        nm = it.get("canonical") or it.get("name") or ""
        w = _as_float(it.get("weight_g", 0.0), 0.0)

        row = _find_food(nm)
        if row:
            per100_kcal = _as_float(_col(row, KCAL_KEYS, 0))
            per100_p    = _as_float(_col(row, PROT_KEYS, 0))
            per100_f    = _as_float(_col(row, FAT_KEYS,  0))
            per100_c    = _as_float(_col(row, CARB_KEYS, 0))
            ratio       = w / 100.0
            kcal = round(per100_kcal * ratio, 1)
            p    = round(per100_p    * ratio, 1)
            f    = round(per100_f    * ratio, 1)
            c    = round(per100_c    * ratio, 1)
            matched = True
        else:
            kcal = p = f = c = 0.0
            matched = False

        out = {
            **it,
            "kcal": kcal,
            "protein_g": p,
            "fat_g": f,
            "carb_g": c,
            "matched": matched,
        }
        enriched.append(out)
        totals["kcal"]      += kcal
        totals["protein_g"] += p
        totals["fat_g"]     += f
        totals["carb_g"]    += c

    # 四捨五入統整
    totals = {k: (round(v, 1) if isinstance(v, float) else v) for k, v in totals.items()}
    return enriched, totals