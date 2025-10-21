# backend/app/services/nutrition_service_v2.py
from __future__ import annotations

import csv
import os
import re
from typing import Dict, List, Tuple, Optional
from difflib import get_close_matches

# ------------- 共用欄位鍵 -------------
NAME_KEYS = ("name", "食品名稱", "食材", "canonical_zh")
CANON_KEYS = ("canonical", "標準名", "英文名")
KCAL_KEYS  = ("kcal", "熱量(kcal)", "熱量", "能量kcal")
PROT_KEYS  = ("protein_g", "蛋白質(g)", "蛋白質", "蛋白")
FAT_KEYS   = ("fat_g", "脂肪(g)", "脂肪")
CARB_KEYS  = ("carb_g", "碳水(g)", "碳水化合物", "碳水")

# ------------- 別名與正規化 -------------
ALIAS_MAP: Dict[str, str] = {
    # cucumber / 小黃瓜 / 胡瓜
    "cucumber": "小黃瓜", "japanese cucumber": "小黃瓜", "胡瓜": "小黃瓜", "小黃瓜": "小黃瓜",

    # shredded tofu / 豆乾絲
    "shredded tofu": "豆乾絲", "tofu strips": "豆乾絲", "bean curd strips": "豆乾絲",
    "bean curd shreds": "豆乾絲", "豆干絲": "豆乾絲", "豆乾絲": "豆乾絲",

    # tamagoyaki / 玉子燒
    "tamagoyaki": "玉子燒", "dashimaki tamago": "玉子燒", "dashimaki": "玉子燒",

    # basics
    "carrot": "紅蘿蔔", "onion": "洋蔥", "garlic": "蒜頭",
    "bell pepper": "甜椒", "green pepper": "青椒", "red bell pepper": "紅甜椒",
    "egg": "雞蛋", "white rice": "白飯", "soy sauce": "醬油", "dashi": "高湯",
}

# 中文→canonical（CSV 用）
CANON_NORMALIZE: Dict[str, str] = {
    "小黃瓜": "cucumber",
    "豆乾絲": "shredded tofu",
    "玉子燒": "tamagoyaki",  # 後面會拆解，不直接計算
    "紅蘿蔔": "carrot",
    "洋蔥": "onion",
    "蒜頭": "garlic",
    "甜椒": "bell pepper",
    "青椒": "green pepper",
    "紅甜椒": "red bell pepper",
    "雞蛋": "egg",
    "白飯": "white rice",
    "醬油": "soy sauce",
    "高湯": "dashi",
}


def _strip_parens(text: str) -> str:
    return re.sub(r"\(.*?\)", "", text or "").strip()


def _norm(s: str) -> str:
    s = (s or "").strip().lower()
    for ch in (" ", "-", "_"):
        s = s.replace(ch, "")
    if s.endswith("es") and len(s) > 3:
        s = s[:-2]
    elif s.endswith("s") and len(s) > 3:
        s = s[:-1]
    return s


def _alias_to_zh(name: str) -> str:
    key = _norm(name)
    if key in ALIAS_MAP:
        return ALIAS_MAP[key]
    key2 = _norm(_strip_parens(name))
    return ALIAS_MAP.get(key2, name)


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


# ------------- 讀 CSV -------------
CSV_PATHS = [
    os.path.join(os.path.dirname(__file__), "..", "data", "foods_tw.csv"),
    os.path.join(os.getcwd(), "backend", "app", "data", "foods_tw.csv"),
    os.path.join(os.getcwd(), "app", "data", "foods_tw.csv"),
]

_FOODS: List[dict] = []


def _load_food_table(csv_path: str) -> List[dict]:
    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        return [dict(r) for r in reader]


def _ensure_loaded():
    global _FOODS
    if _FOODS:
        return
    for p in CSV_PATHS:
        p = os.path.normpath(p)
        if os.path.exists(p):
            _FOODS = _load_food_table(p)
            break
    if not _FOODS:
        raise FileNotFoundError("foods_tw.csv not found.")


# ------------- 名稱集合（for exact / fuzzy） -------------
def _all_names_for_row(r: dict) -> List[str]:
    zh = (_col(r, NAME_KEYS, "") or "").strip()
    en = (_col(r, CANON_KEYS, "") or "").strip()
    names = []
    if zh:
        names.append(zh)
    if en:
        names.append(en)
        zh_from_alias = ALIAS_MAP.get(_norm(en)) or ALIAS_MAP.get(_norm(_strip_parens(en)))
        if zh_from_alias:
            names.append(zh_from_alias)
    # 去重
    out, seen = [], set()
    for n in names:
        k = _norm(n)
        if k and k not in seen:
            seen.add(k); out.append(n)
    return out


def _fuzzy_find(name: str, pool: Optional[List[dict]] = None, cutoff: float = 0.65) -> Optional[dict]:
    if not name:
        return None
    pool = pool or _FOODS
    key = _norm(name)
    if not key:
        return None
    candidates: List[tuple[str, dict]] = []
    for r in pool:
        for n in _all_names_for_row(r):
            candidates.append((_norm(n), r))
    corpus = [c[0] for c in candidates if c[0]]
    if not corpus:
        return None
    hits = get_close_matches(key, corpus, n=1, cutoff=cutoff)
    if hits:
        hit = hits[0]
        for k, r in candidates:
            if k == hit:
                return r
    return None


def _find_food(name: str) -> Optional[dict]:
    _ensure_loaded()
    if not name:
        return None
    k1 = _norm(name)
    k2 = _norm(_strip_parens(name))
    for r in _FOODS:
        for n in _all_names_for_row(r):
            kn = _norm(n)
            if kn == k1 or kn == k2:
                return r
    return _fuzzy_find(name, _FOODS, 0.65)


def _normalize_item(it: dict) -> dict:
    """把 name/canonical 正規化：中文→canonical、英文別名→中文→canonical"""
    nm_name = (it.get("name") or "").strip()
    nm_cano = (it.get("canonical") or "").strip()
    label_zh = _alias_to_zh(nm_name or nm_cano)
    cano = CANON_NORMALIZE.get(label_zh, (nm_cano or nm_name)).lower()
    it["name"] = label_zh
    it["canonical"] = cano
    return it


# ------------- 規則：小菜不要誤當配菜 -------------
def _fix_garnish(items: List[dict]) -> List[dict]:
    mains = [it for it in items if not it.get("is_garnish")]
    if len(items) <= 3 and len(mains) <= 2:
        for it in items:
            if it.get("is_garnish") and it.get("canonical") in {
                "cucumber", "carrot", "shredded tofu", "onion", "garlic"
            }:
                it["is_garnish"] = False
    return items


# ------------- 規則：玉子燒拆解 -------------
def _expand_composite(items: List[dict]) -> List[dict]:
    out: List[dict] = []
    for it in items:
        cano = (it.get("canonical") or "").lower()
        if cano in {"tamagoyaki", "dashimaki tamago", "dashimaki"}:
            w = _as_float(it.get("weight_g"), 60.0)
            out.append({**it, "name": "雞蛋", "canonical": "egg", "weight_g": round(w * 0.80, 1), "is_garnish": False})
            out.append({**it, "name": "高湯", "canonical": "dashi", "weight_g": round(w * 0.15, 1), "is_garnish": False})
            out.append({**it, "name": "醬油", "canonical": "soy sauce", "weight_g": round(w * 0.05, 1), "is_garnish": False})
        else:
            out.append(it)
    return out


def _coerce_items(items):
    if isinstance(items, dict):
        return [items]
    if not isinstance(items, list):
        return []
    return items


# ------------- 主流程：計算 -------------
def calc(items: List[dict], include_garnish: bool = False):
    """
    items: [{'name','canonical','weight_g','is_garnish'}...]
    return: (enriched_items, totals)
    """
    _ensure_loaded()
    items = _coerce_items(items)
    items = [_normalize_item(i) for i in items]
    items = _expand_composite(items)
    items = _fix_garnish(items)

    enriched: List[dict] = []
    totals = dict(kcal=0.0, protein_g=0.0, fat_g=0.0, carb_g=0.0)

    for it in items:
        if not include_garnish and bool(it.get("is_garnish")):
            enriched.append({
                **it, "kcal": 0.0, "protein_g": 0.0, "fat_g": 0.0, "carb_g": 0.0,
                "matched": False, "label": it.get("name") or it.get("canonical")
            })
            continue

        nm_name = str(it.get("name") or "")
        nm_cano = str(it.get("canonical") or "")
        row = _find_food(nm_name) or _find_food(nm_cano) or _find_food(_alias_to_zh(nm_cano))

        w = _as_float(it.get("weight_g"), 0.0)
        if w < 0: w = 0.0

        if row:
            per100_kcal = _as_float(_col(row, KCAL_KEYS, 0))
            per100_p    = _as_float(_col(row, PROT_KEYS, 0))
            per100_f    = _as_float(_col(row, FAT_KEYS,  0))
            per100_c    = _as_float(_col(row, CARB_KEYS, 0))
            ratio = w / 100.0 if w else 0.0
            kcal = round(per100_kcal * ratio, 1)
            p    = round(per100_p    * ratio, 1)
            f    = round(per100_f    * ratio, 1)
            c    = round(per100_c    * ratio, 1)
            matched = True
            label = _col(row, NAME_KEYS) or _alias_to_zh(_col(row, CANON_KEYS, "") or nm_name or nm_cano)
            canonical = _col(row, CANON_KEYS, nm_cano or nm_name)
        else:
            kcal = p = f = c = 0.0
            matched = False
            label = _alias_to_zh(nm_name or nm_cano) or (nm_name or nm_cano)
            canonical = nm_cano or nm_name

        out = {
            **it,
            "label": label,
            "canonical": (canonical or "").lower(),
            "kcal": kcal, "protein_g": p, "fat_g": f, "carb_g": c,
            "matched": matched,
        }
        enriched.append(out)

        totals["kcal"]      += kcal
        totals["protein_g"] += p
        totals["fat_g"]     += f
        totals["carb_g"]    += c

    totals = {k: (round(v, 1) if isinstance(v, float) else v) for k, v in totals.items()}
    return enriched, totals
