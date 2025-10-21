# backend/app/services/nutrition_service_v2.py
from __future__ import annotations

import csv
import os
from difflib import get_close_matches
from typing import Dict, List, Tuple, Optional

# ---- 欄位鍵定義 ----
NAME_KEYS  = ("name", "食品名稱", "食材", "canonical_zh")
CANON_KEYS = ("canonical", "標準名", "英文名")
KCAL_KEYS  = ("kcal", "熱量(kcal)", "熱量", "能量kcal")
PROT_KEYS  = ("protein_g", "蛋白質(g)", "蛋白質", "蛋白")
FAT_KEYS   = ("fat_g", "脂肪(g)", "脂肪")
CARB_KEYS  = ("carb_g", "碳水(g)", "碳水化合物", "碳水")

# ---- 常用別名（英文→中文）----
ALIAS_MAP = {
    # 蔬菜類
    "cucumber": "小黃瓜",
    "cucumbers": "小黃瓜",
    "persian cucumber": "小黃瓜",
    "japanese cucumber": "小黃瓜",

    "carrot": "紅蘿蔔",
    "carrots": "紅蘿蔔",

    "green pepper": "青椒",
    "bell pepper": "青椒",
    "green bell pepper": "青椒",
    "red bell pepper": "紅甜椒",

    "onion": "洋蔥",
    "white onion": "白洋蔥",
    "garlic": "蒜頭",
    "ginger": "薑",

    # 豆腐/豆干
    "tofu": "豆腐",
    "silken tofu": "嫩豆腐",
    "firm tofu": "板豆腐",
    "dried tofu": "豆干",
    "tofu strips": "豆干絲",
    "tofu shreds": "豆干絲",
    "bean curd strips": "豆干絲",
    "bean curd": "豆干",
    "bean curd sheet": "豆皮",

    # 其他常見
    "bonito flakes": "柴魚片",
    "katsuobushi": "柴魚片",
    "soy sauce": "醬油",
    "sweet soy sauce": "甜醬油",
    "sweet and sour sauce": "糖醋醬",
    "teriyaki sauce": "照燒醬",
    "oyster sauce": "蠔油",
    "hoisin sauce": "海鮮醬",

    "century egg": "皮蛋",
    "black egg": "皮蛋",

    "rice": "白飯",
    "white rice": "白飯",
    "noodles": "麵",
    "ramen noodles": "拉麵",
    "udon": "烏龍麵",
    "soba noodles": "蕎麥麵",

    "salmon": "鮭魚",
    "fish": "魚肉",
    "chicken breast": "雞胸肉",
}

def _norm(s: str) -> str:
    s = (s or "").strip().lower()
    for ch in (" ", "-", "_"):
        s = s.replace(ch, "")
    if s.endswith("es") and len(s) > 3:
        s = s[:-2]
    elif s.endswith("s") and len(s) > 3:
        s = s[:-1]
    return s

_NORM_ALIAS = {_norm(k): v for k, v in ALIAS_MAP.items()}


def _col(r: dict, keys: Tuple[str, ...], default=None):
    for k in keys:
        if k in r and r[k] not in (None, ""):
            return r[k]
    return default


def _as_float(x, default=0.0):
    try:
        return float(str(x).strip())
    except Exception:
        return default


def _load_csv(csv_path: str) -> List[dict]:
    with open(csv_path, "r", encoding="utf-8") as f:
        return [dict(row) for row in csv.DictReader(f)]


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
            _FOODS = _load_csv(p)
            break
    if not _FOODS:
        raise FileNotFoundError("foods_tw.csv not found")


def _all_names(r: dict) -> List[str]:
    zh = (_col(r, NAME_KEYS, "") or "").strip()
    en = (_col(r, CANON_KEYS, "") or "").strip()
    names = []
    if zh:
        names.append(zh)
    if en:
        names.append(en)
        alias_zh = _NORM_ALIAS.get(_norm(en))
        if alias_zh:
            names.append(alias_zh)
    # 去重
    out, seen = [], set()
    for n in names:
        k = _norm(n)
        if k and k not in seen:
            seen.add(k)
            out.append(n)
    return out


def _find_food(name: str) -> Optional[dict]:
    _ensure_loaded()
    if not name:
        return None
    key = _norm(name)

    # exact
    for r in _FOODS:
        for n in _all_names(r):
            if _norm(n) == key:
                return r

    # alias zh
    alias_zh = _NORM_ALIAS.get(key)
    if alias_zh:
        for r in _FOODS:
            if _norm(_col(r, NAME_KEYS, "") or "") == _norm(alias_zh):
                return r

    # fuzzy（略鬆）
    candidates = []
    for r in _FOODS:
        for n in _all_names(r):
            candidates.append((_norm(n), r))
    corpus = [c[0] for c in candidates]
    hits = get_close_matches(key, corpus, n=1, cutoff=0.82)
    if hits:
        h = hits[0]
        for k2, r in candidates:
            if k2 == h:
                return r
    return None


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

        nm = str(it.get("name") or "").strip()
        ca = str(it.get("canonical") or "").strip()

        row = _find_food(nm) or _find_food(ca)
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

            label = _col(row, NAME_KEYS) or ALIAS_MAP.get(_norm(ca), nm or ca)
            canonical = _col(row, CANON_KEYS, ca or nm)
        else:
            kcal = p = f = c = 0.0
            matched = False
            # 沒有對上 CSV，也至少用別名中文顯示，避免英文落地
            label = ALIAS_MAP.get(_norm(nm or ca), nm or ca)
            canonical = ca or nm

        out = {
            **it,
            "label": label,
            "canonical": canonical,
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
