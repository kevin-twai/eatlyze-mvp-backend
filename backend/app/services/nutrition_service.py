# backend/app/services/nutrition_service.py
from __future__ import annotations

import csv
import os
import re
from difflib import get_close_matches
from typing import Dict, List, Tuple, Optional

# ---- 欄位鍵定義 ----
NAME_KEYS  = ("name", "食品名稱", "食材", "canonical_zh")
CANON_KEYS = ("canonical", "標準名", "英文名")
KCAL_KEYS  = ("kcal", "熱量(kcal)", "熱量", "能量kcal")
PROT_KEYS  = ("protein_g", "蛋白質(g)", "蛋白質", "蛋白")
FAT_KEYS   = ("fat_g", "脂肪(g)", "脂肪")
CARB_KEYS  = ("carb_g", "碳水(g)", "碳水化合物", "碳水")

# ---- 英中別名（原始表）----
ALIAS_MAP_RAW: Dict[str, str] = {
    # 肉/蛋/乳
    "chicken": "雞肉",
    "beef": "牛肉",
    "pork": "豬肉",
    "lamb": "羊肉",
    "fish": "魚肉",
    "egg": "雞蛋",
    "egg white": "蛋白",
    "soft-boiled egg": "半熟蛋",
    "boiled egg": "水煮蛋",
    "black egg": "皮蛋",
    "century egg": "皮蛋",
    "century eggs": "皮蛋",

    # 豆/豆製品
    "tofu": "豆腐",
    "silken tofu": "嫩豆腐",
    "firm tofu": "板豆腐",

    # 蔬菜
    "pumpkin": "南瓜",
    "carrot": "胡蘿蔔",
    "eggplant": "茄子",
    "green pepper": "青椒",
    "bell pepper": "青椒",
    "green bell pepper": "青椒",
    "red bell pepper": "紅甜椒",
    "onion": "洋蔥",
    "garlic": "蒜頭",
    "broccoli": "花椰菜",
    "baby corn": "玉米筍",
    "small corn": "玉米筍",
    "mushroom": "蘑菇",
    "shiitake": "香菇",
    "enoki": "金針菇",
    "shishito pepper": "獅子唐椒",
    "parsley": "巴西里",

    # 海藻/海鮮調料
    "nori": "海苔",
    "nori seaweed": "海苔",

    # 日式配料
    "katsuobushi": "柴魚片",
    "dried bonito flakes": "柴魚片",
    "bonito flakes": "柴魚片",
    "katsuobushi (dried bonito flakes)": "柴魚片",

    # 醬/醬料
    "soy sauce": "醬油",
    "sweet soy sauce": "甜醬油",
    "sweet and sour sauce": "糖醋醬",
    "teriyaki sauce": "照燒醬",
    "oyster sauce": "蠔油",
    "hoisin sauce": "海鮮醬",

    # 麵/主食
    "soba noodles": "蕎麥麵",
    "udon": "烏龍麵",
    "ramen noodles": "拉麵",
    "white rice": "白飯",
    "rice": "白飯",
}

# ---------- 小工具 ----------
def _strip_parens(text: str) -> str:
    """去掉括號與括號內的內容：'black egg (century egg)' -> 'black egg'"""
    return re.sub(r"\(.*?\)", "", text or "").strip()

def _norm(s: str) -> str:
    """小寫、去空白/連字號/底線、簡單複數處理"""
    s = (s or "").strip().lower()
    for ch in (" ", "-", "_"):
        s = s.replace(ch, "")
    if s.endswith("es") and len(s) > 3:
        s = s[:-2]
    elif s.endswith("s") and len(s) > 3:
        s = s[:-1]
    return s

# 建立：正規化的別名表（含去括號版本）
_NORM_ALIAS: Dict[str, str] = {}
for k, v in ALIAS_MAP_RAW.items():
    _NORM_ALIAS[_norm(k)] = v
    k2 = _strip_parens(k)
    if k2 and _norm(k2) not in _NORM_ALIAS:
        _NORM_ALIAS[_norm(k2)] = v

def _alias_to_zh(name: str) -> str:
    """先去括號再查別名表；查不到回傳原字串"""
    if not name:
        return name
    key = _norm(name)
    if key in _NORM_ALIAS:
        return _NORM_ALIAS[key]
    key2 = _norm(_strip_parens(name))
    return _NORM_ALIAS.get(key2, name)

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
    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        return [dict(r) for r in reader]

_FOODS: List[dict] = []

def _ensure_loaded():
    """嘗試在多個常見路徑載入 foods_tw.csv"""
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

def _all_names_for_row(r: dict) -> List[str]:
    """此資料列可用於比對的所有名稱（中文/英文/別名中文）"""
    zh = (_col(r, NAME_KEYS, "") or "").strip()
    en = (_col(r, CANON_KEYS, "") or "").strip()

    names = []
    if zh:
        names.append(zh)
        # 若 CSV 中文在別名表中（極少見），也加入
        zh_alias = _NORM_ALIAS.get(_norm(zh))
        if zh_alias and zh_alias != zh:
            names.append(zh_alias)

    if en:
        names.append(en)
        # 若英文可映射中文，也加入
        zh_from_alias = _NORM_ALIAS.get(_norm(en)) or _NORM_ALIAS.get(_norm(_strip_parens(en)))
        if zh_from_alias:
            names.append(zh_from_alias)

    # 去重
    dedup: List[str] = []
    seen: set[str] = set()
    for n in names:
        k = _norm(n)
        if k and k not in seen:
            seen.add(k)
            dedup.append(n)
    return dedup

def _fuzzy_find(name: str, pool: Optional[List[dict]] = None, cutoff: float = 0.65) -> Optional[dict]:
    """更寬鬆的模糊匹配，預設 cutoff=0.65"""
    if not name:
        return None
    pool = pool or _FOODS
    key = _norm(name)
    if not key:
        return None

    candidates: List[Tuple[str, dict]] = []
    for r in pool:
        for n in _all_names_for_row(r):
            candidates.append((_norm(n), r))

    corpus = [c[0] for c in candidates if c[0]]
    if not corpus:
        return None

    hits = get_close_matches(key, corpus, n=1, cutoff=cutoff)
    if hits:
        hit = hits[0]
        for norm_name, r in candidates:
            if norm_name == hit:
                return r
    return None

def _find_food(name: str) -> Optional[dict]:
    _ensure_loaded()
    if not name:
        return None

    # exact（中文/英文/別名中文）
    key = _norm(name)
    key2 = _norm(_strip_parens(name))
    for r in _FOODS:
        for n in _all_names_for_row(r):
            kn = _norm(n)
            if kn == key or kn == key2:
                return r

    # fuzzy
    return _fuzzy_find(name, _FOODS, cutoff=0.65)

def _coerce_items(items):
    if isinstance(items, dict):
        return [items]
    if not isinstance(items, list):
        return []
    return items

def calc(items: List[Dict], include_garnish: bool = False):
    """
    items: [{'name':..., 'canonical':..., 'weight_g':..., 'is_garnish':bool}, ...]
    回傳: (enriched_items, totals)
    enriched_items 會多一個 'label'（中文顯示名，盡量用中文）
    """
    _ensure_loaded()
    items = _coerce_items(items)

    enriched: List[Dict] = []
    totals = dict(kcal=0.0, protein_g=0.0, fat_g=0.0, carb_g=0.0)

    for it in items or []:
        if not include_garnish and bool(it.get("is_garnish")):
            out = {
                **it,
                "kcal": 0.0, "protein_g": 0.0, "fat_g": 0.0, "carb_g": 0.0,
                "matched": False,
                "label": it.get("name") or it.get("canonical"),
            }
            enriched.append(out)
            continue

        nm_name = str(it.get("name") or "").strip()
        nm_cano = str(it.get("canonical") or "").strip()

        # 優先順序：name → canonical → canonical 的中文別名
        row = _find_food(nm_name) or _find_food(nm_cano) or _find_food(_alias_to_zh(nm_cano))

        w = _as_float(it.get("weight_g", 0.0), 0.0)
        if w < 0:
            w = 0.0

        if row:
            per100_kcal = _as_float(_col(row, KCAL_KEYS, 0))
            per100_p    = _as_float(_col(row, PROT_KEYS, 0))
            per100_f    = _as_float(_col(row, FAT_KEYS,  0))
            per100_c    = _as_float(_col(row, CARB_KEYS, 0))
            ratio = w / 100.0
            kcal = round(per100_kcal * ratio, 1)
            p    = round(per100_p    * ratio, 1)
            f    = round(per100_f    * ratio, 1)
            c    = round(per100_c    * ratio, 1)
            matched = True

            # 顯示名：CSV 中文；若無則用別名把英文映為中文
            label = _col(row, NAME_KEYS) or _alias_to_zh(_col(row, CANON_KEYS, "") or nm_name or nm_cano)
            canonical = _col(row, CANON_KEYS, nm_cano or nm_name)
        else:
            kcal = p = f = c = 0.0
            matched = False
            label = _alias_to_zh(nm_name or nm_cano) or (nm_name or nm_cano)
            canonical = nm_cano or nm_name

        out = {
            **it,
            "label": label,          # 前端顯示
            "canonical": canonical,  # 對齊用
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
