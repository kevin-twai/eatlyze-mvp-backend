from __future__ import annotations
import os
import csv
from typing import Dict, List, Tuple

# --- 欄位鍵定義 ---
NAME_KEYS = ("name", "食品名稱", "食材", "canonical", "別名")
KCAL_KEYS = ("kcal", "熱量(kcal)", "熱量", "能量kcal")
PROT_KEYS = ("protein_g", "蛋白質(g)", "蛋白質", "蛋白")
FAT_KEYS  = ("fat_g", "脂肪(g)", "脂肪")
CARB_KEYS = ("carb_g", "碳水(g)", "碳水化合物", "碳水")

# --- 英中別名對照表 ---
ALIAS_MAP = {
    "chicken": "雞肉",
    "beef": "牛肉",
    "pork": "豬肉",
    "fish": "魚肉",
    "egg": "雞蛋",
    "soft-boiled egg": "半熟蛋",
    "pumpkin": "南瓜",
    "carrot": "胡蘿蔔",
    "eggplant": "茄子",
    "green pepper": "青椒",
    "bell pepper": "青椒",
    "baby corn": "玉米筍",
    "small corn": "玉米筍",
    "lotus root": "蓮藕",
    "potato": "馬鈴薯",
    "curry sauce": "咖哩醬",
    "rice": "白飯",
    "broccoli": "花椰菜",
    "bok choy": "青江菜",
    "onion": "洋蔥",
    "garlic": "蒜頭",
    # 中文同義
    "小玉米": "玉米筍",
    "青花菜": "花椰菜",
    "玉米": "玉米筍"
}

# --- 工具函式 ---
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

_FOODS: List[dict] = []

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
            break
    if not _FOODS:
        raise FileNotFoundError("foods_tw.csv not found in common locations.")

def _norm(s: str) -> str:
    return str(s).strip().lower()

def _alias(s: str) -> str:
    """若別名表有對應則回傳中文名稱"""
    return ALIAS_MAP.get(_norm(s), s)

def _find_food(name: str) -> dict | None:
    """名稱模糊比對"""
    _ensure_loaded()
    key = _norm(name)
    for r in _FOODS:
        nm = _col(r, NAME_KEYS, "")
        if _norm(nm) == key:
            return r
    for r in _FOODS:
        nm = _col(r, NAME_KEYS, "")
        if key in _norm(nm):
            return r
    return None

def _try_find_by_candidates(names: list[str]) -> dict | None:
    """同時嘗試原名與別名"""
    for nm in names:
        if not nm:
            continue
        row = _find_food(nm)
        if row:
            return row
        alt = _alias(nm)
        if alt != nm:
            row = _find_food(alt)
            if row:
                return row
    return None

def _coerce_items(items):
    """確保 items 是 list[dict]"""
    if isinstance(items, dict):
        return [items]
    if not isinstance(items, list):
        return []
    return items

# --- 主函式 ---
def calc(items: List[Dict], include_garnish: bool = False) -> Tuple[List[Dict], Dict]:
    """
    items: [{'name':..., 'canonical':..., 'weight_g':..., 'is_garnish':bool}, ...]
    return: (enriched_items, totals)
    """
    _ensure_loaded()
    items = _coerce_items(items)

    enriched = []
    totals = dict(kcal=0.0, protein_g=0.0, fat_g=0.0, carb_g=0.0)

    for it in items or []:
        if not include_garnish and bool(it.get("is_garnish")):
            out = {**it, "kcal": 0.0, "protein_g": 0.0, "fat_g": 0.0, "carb_g": 0.0, "matched": False}
            enriched.append(out)
            continue

        nm_name = str(it.get("name") or "").strip()
        nm_cano = str(it.get("canonical") or "").strip()

        # name 與 canonical 都嘗試（含別名）
        row = _try_find_by_candidates([nm_name, nm_cano])

        w = _as_float(it.get("weight_g", 0.0), 0.0)
        if w < 0:
            w = 0.0

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
