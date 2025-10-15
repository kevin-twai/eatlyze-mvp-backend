
from __future__ import annotations
import os, csv, json
from typing import Dict, List, Tuple, Optional

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
        s = str(x).strip().replace(",", "")
        return float(s)
    except Exception:
        return default

def _load_food_table(csv_path: str) -> List[dict]:
    if not os.path.exists(csv_path):
        raise FileNotFoundError(f"foods csv not found: {csv_path}")
    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        return [dict(r) for r in reader]

_FOODS: List[dict] = []
_FOOD_IDX: dict = {}

def _build_index():
    global _FOOD_IDX
    _FOOD_IDX = {}
    for r in _FOODS:
        nm = _col(r, NAME_KEYS, "")
        if nm:
            _FOOD_IDX[str(nm).strip().lower()] = r

def _ensure_loaded():
    global _FOODS
    if _FOODS:
        return
    candidates = [
        os.path.join(os.path.dirname(__file__), "..", "data", "foods_tw.csv"),
        os.path.join(os.getcwd(), "backend", "app", "data", "foods_tw.csv"),
        os.path.join(os.getcwd(), "app", "data", "foods_tw.csv"),
    ]
    for p in candidates:
        p = os.path.normpath(p)
        if os.path.exists(p):
            _FOODS = _load_food_table(p)
            _build_index()
            break
    if not _FOODS:
        raise FileNotFoundError("foods_tw.csv not found in common locations.")

def reload_foods(custom_path: Optional[str] = None):
    global _FOODS
    if custom_path:
        _FOODS = _load_food_table(custom_path)
        _build_index()
        return
    _FOODS.clear()
    _ensure_loaded()

def _norm(s: str) -> str:
    return str(s).strip().lower()

def _find_food(name: str) -> dict | None:
    _ensure_loaded()
    key = _norm(name)
    if key in _FOOD_IDX:
        return _FOOD_IDX[key]
    for r in _FOODS:
        nm = _col(r, NAME_KEYS, "")
        if key in _norm(nm):
            return r
    return None

def _coerce_items(items) -> List[Dict]:
    if isinstance(items, str):
        items = json.loads(items)
    if not isinstance(items, list):
        raise ValueError("items must be list")
    if any(not isinstance(x, dict) for x in items):
        raise ValueError("each item must be object")
    return items

def calc(items, include_garnish: bool = False):
    _ensure_loaded()
    items = _coerce_items(items)

    enriched = []
    totals = dict(kcal=0.0, protein_g=0.0, fat_g=0.0, carb_g=0.0)

    for it in items or []:
        if not include_garnish and bool(it.get("is_garnish")):
            out = {**it, "kcal": 0.0, "protein_g": 0.0, "fat_g": 0.0, "carb_g": 0.0, "matched": False}
            enriched.append(out)
            continue

        nm = it.get("canonical") or it.get("name") or ""
        w = _as_float(it.get("weight_g", 0.0), 0.0)
        if w < 0:
            w = 0.0

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

    totals = {k: (round(v, 1) if isinstance(v, float) else v) for k, v in totals.items()}
    return enriched, totals
