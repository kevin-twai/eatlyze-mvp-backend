# backend/app/services/nutrition_service_v2.py
from __future__ import annotations

import os, csv, re
from typing import Dict, List, Tuple, Optional
from difflib import get_close_matches

# 欄位鍵
NAME_KEYS  = ("name", "食品名稱", "食材", "canonical_zh")
CANON_KEYS = ("canonical", "標準名", "英文名")
KCAL_KEYS  = ("kcal", "熱量(kcal)", "熱量", "能量kcal")
PROT_KEYS  = ("protein_g", "蛋白質(g)", "蛋白質", "蛋白")
FAT_KEYS   = ("fat_g", "脂肪(g)", "脂肪")
CARB_KEYS  = ("carb_g", "碳水(g)", "碳水化合物", "碳水")

# 配菜忽略門檻（若 include_garnish=False 時才生效）
GARNISH_IGNORE_GRAMS = 5.0

# 常見別名（可視需要擴增）
ALIAS_RAW = {
    "cucumber": "小黃瓜",
    "carrot": "紅蘿蔔",
    "shredded tofu": "豆干絲",
    "tofu strip": "豆干絲",
    "tofu threads": "豆干絲",
    "bell pepper": "甜椒",
}

def _strip_parens(s: str) -> str:
    return re.sub(r"\(.*?\)", "", s or "").strip()

def _norm(s: str) -> str:
    s = (s or "").strip().lower()
    for ch in (" ", "-", "_"):
        s = s.replace(ch, "")
    if s.endswith("es") and len(s) > 3:
        s = s[:-2]
    elif s.endswith("s") and len(s) > 3:
        s = s[:-1]
    return s

# 正規化別名表
NORM_ALIAS: Dict[str, str] = {}
for k, v in ALIAS_RAW.items():
    NORM_ALIAS[_norm(k)] = v
    k2 = _strip_parens(k)
    if k2 and _norm(k2) not in NORM_ALIAS:
        NORM_ALIAS[_norm(k2)] = v

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

def _load_foods(csv_path: str) -> List[dict]:
    with open(csv_path, "r", encoding="utf-8") as f:
        rdr = csv.DictReader(f)
        return [dict(r) for r in rdr]

_FOODS: List[dict] = []

def _ensure_loaded():
    global _FOODS
    if _FOODS:
        return
    cands = [
        os.path.join(os.path.dirname(__file__), "..", "data", "foods_tw.csv"),
        os.path.join(os.getcwd(), "backend", "app", "data", "foods_tw.csv"),
        os.path.join(os.getcwd(), "app", "data", "foods_tw.csv"),
    ]
    for p in cands:
        p = os.path.normpath(p)
        if os.path.exists(p):
            _FOODS = _load_foods(p)
            break
    if not _FOODS:
        raise FileNotFoundError("foods_tw.csv not found")

def _display_label(name: str, canonical: str) -> str:
    # 優先 CSV 的中文，否則用別名把英文轉中文
    return name or NORM_ALIAS.get(_norm(canonical), canonical)

def _names_for_row(r: dict) -> List[str]:
    zh = _col(r, NAME_KEYS, "") or ""
    en = _col(r, CANON_KEYS, "") or ""
    names = [zh, en]
    alias = NORM_ALIAS.get(_norm(en))
    if alias:
        names.append(alias)
    # 去重
    got, seen = [], set()
    for n in names:
        k = _norm(n)
        if k and k not in seen:
            seen.add(k); got.append(n)
    return got

def _fuzzy_find(key: str, cutoff: float = 0.7) -> Optional[dict]:
    key = _norm(key)
    cands = []
    for r in _FOODS:
        for n in _names_for_row(r):
            cands.append((_norm(n), r))
    pool = [c[0] for c in cands if c[0]]
    hits = get_close_matches(key, pool, n=1, cutoff=cutoff)
    if not hits:
        return None
    hit = hits[0]
    for n, r in cands:
        if n == hit:
            return r
    return None

def _find_food(name_or_canonical: str) -> Optional[dict]:
    _ensure_loaded()
    if not name_or_canonical:
        return None
    key = _norm(name_or_canonical)
    key2 = _norm(_strip_parens(name_or_canonical))
    for r in _FOODS:
        for n in _names_for_row(r):
            kn = _norm(n)
            if kn == key or kn == key2:
                return r
    return _fuzzy_find(name_or_canonical, cutoff=0.7)

def _coerce_list(x):
    if isinstance(x, list): return x
    if isinstance(x, dict): return [x]
    return []

def calc(items: List[Dict], include_garnish: bool = True):
    """
    include_garnish=True -> 一律計入配菜營養
    若 include_garnish=False，且 is_garnish=True 且 weight < 門檻，才忽略。
    """
    _ensure_loaded()
    items = _coerce_list(items)
    out, totals = [], dict(kcal=0.0, protein_g=0.0, fat_g=0.0, carb_g=0.0)

    for it in items:
        it = dict(it or {})
        w = _as_float(it.get("weight_g", 0), 0.0)
        nm = (it.get("name") or "").strip()
        cano = (it.get("canonical") or "").strip()

        # 忽略條件（只有在 include_garnish=False 且 重量小於門檻 才忽略）
        if not include_garnish and bool(it.get("is_garnish")) and w < GARNISH_IGNORE_GRAMS:
            out.append({
                **it, "label": it.get("name") or it.get("canonical"),
                "kcal": 0.0, "protein_g": 0.0, "fat_g": 0.0, "carb_g": 0.0,
                "matched": False
            })
            continue

        row = _find_food(nm) or _find_food(cano)
        if row:
            per100_kcal = _as_float(_col(row, KCAL_KEYS, 0))
            per100_p    = _as_float(_col(row, PROT_KEYS, 0))
            per100_f    = _as_float(_col(row, FAT_KEYS, 0))
            per100_c    = _as_float(_col(row, CARB_KEYS, 0))
            ratio = w / 100.0
            kcal = round(per100_kcal * ratio, 1)
            p    = round(per100_p * ratio, 1)
            f    = round(per100_f * ratio, 1)
            c    = round(per100_c * ratio, 1)
            lbl  = _display_label(_col(row, NAME_KEYS, ""), _col(row, CANON_KEYS, cano))
            matched = True
        else:
            kcal = p = f = c = 0.0
            lbl = _display_label(nm, cano)
            matched = False

        out.append({
            **it, "label": lbl,
            "kcal": kcal, "protein_g": p, "fat_g": f, "carb_g": c,
            "matched": matched
        })

        totals["kcal"]      += kcal
        totals["protein_g"] += p
        totals["fat_g"]     += f
        totals["carb_g"]    += c

    for k in totals:
        if isinstance(totals[k], float):
            totals[k] = round(totals[k], 1)
    return out, totals
