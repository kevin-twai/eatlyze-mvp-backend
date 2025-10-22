# backend/app/services/nutrition_service_v2.py
from __future__ import annotations

import csv
import os
import re
from difflib import get_close_matches
from typing import Dict, List, Tuple, Optional

# ---- 欄位鍵定義 ----
NAME_KEYS = ("name", "食品名稱", "食材", "canonical_zh")
CANON_KEYS = ("canonical", "標準名", "英文名")
KCAL_KEYS = ("kcal", "熱量(kcal)", "熱量", "能量kcal")
PROT_KEYS = ("protein_g", "蛋白質(g)", "蛋白質", "蛋白")
FAT_KEYS = ("fat_g", "脂肪(g)", "脂肪")
CARB_KEYS = ("carb_g", "碳水(g)", "碳水化合物", "碳水")

# ---- 英中別名（原始）----
ALIAS_MAP_RAW: Dict[str, str] = {
    # 豆/豆製品
    "shredded tofu": "豆乾絲",
    "dry tofu shreds": "豆乾絲",
    "tofu shreds": "豆乾絲",
    "bean curd strips": "豆乾絲",
    "tofu": "豆腐",
    "silken tofu": "嫩豆腐",
    "firm tofu": "板豆腐",

    # 蔬菜
    "carrot": "胡蘿蔔",
    "shredded carrot": "胡蘿蔔",
    "cucumber": "小黃瓜",
    "japanese cucumber": "小黃瓜",
    "taiwanese cucumber": "小黃瓜",
    "gourd": "小黃瓜",  # 保守指向小黃瓜

    "red chili": "紅辣椒",
    "red bell pepper": "紅甜椒",

    # 醬料/其他
    "soy sauce": "醬油",
    "dashi": "高湯",
    "egg": "雞蛋",
}

# 常見「處理/切法」詞，拿掉以利對表
PREP_TOKENS = ("shredded", "sliced", "diced", "minced", "julienned")


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


def _strip_prep_words(s: str) -> str:
    tokens = (s or "").strip().lower().split()
    tokens = [t for t in tokens if t not in PREP_TOKENS]
    out = " ".join(tokens)
    return out if out else s


# 建立正規化別名表
_NORM_ALIAS: Dict[str, str] = {}
for k, v in ALIAS_MAP_RAW.items():
    _NORM_ALIAS[_norm(k)] = v
    k2 = _strip_parens(k)
    nk2 = _norm(k2)
    if k2 and nk2 not in _NORM_ALIAS:
        _NORM_ALIAS[nk2] = v


def _alias_to_zh(name: str) -> str:
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
    zh = (_col(r, NAME_KEYS, "") or "").strip()
    en = (_col(r, CANON_KEYS, "") or "").strip()

    names: List[str] = []
    if zh:
        names.append(zh)
        zh_alias = _NORM_ALIAS.get(_norm(zh))
        if zh_alias and zh_alias != zh:
            names.append(zh_alias)

    if en:
        names.append(en)
        zh_from_alias = _NORM_ALIAS.get(_norm(en)) or _NORM_ALIAS.get(_norm(_strip_parens(en)))
        if zh_from_alias:
            names.append(zh_from_alias)

    # 去重
    out, seen = [], set()
    for n in names:
        k = _norm(n)
        if k and k not in seen:
            seen.add(k)
            out.append(n)
    return out


def _fuzzy_find(name: str, pool: Optional[List[dict]] = None, cutoff: float = 0.72) -> Optional[dict]:
    if not name:
        return None
    pool = pool or _FOODS
    key = _norm(name)
    if not key:
        return None

    cands: List[Tuple[str, dict]] = []
    for r in pool:
        for n in _all_names_for_row(r):
            cands.append((_norm(n), r))

    corpus = [c[0] for c in cands if c[0]]
    if not corpus:
        return None

    hits = get_close_matches(key, corpus, n=1, cutoff=cutoff)
    if hits:
        hit = hits[0]
        for norm_name, r in cands:
            if norm_name == hit:
                return r
    return None


def _find_food(name: str) -> Optional[dict]:
    _ensure_loaded()
    if not name:
        return None

    # 清掉切法字
    name = _strip_prep_words(name)
    # exact
    key = _norm(name)
    key2 = _norm(_strip_parens(name))
    for r in _FOODS:
        for n in _all_names_for_row(r):
            kn = _norm(n)
            if kn == key or kn == key2:
                return r
    # fuzzy
    return _fuzzy_find(name, _FOODS, cutoff=0.72)


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
                "kcal": 0.0,
                "protein_g": 0.0,
                "fat_g": 0.0,
                "carb_g": 0.0,
                "matched": False,
                "label": it.get("name") or it.get("canonical"),
            }
            enriched.append(out)
            continue

        nm_name = str(it.get("name") or "").strip()
        nm_cano = str(it.get("canonical") or "").strip()

        # strip prep words
        nm_name = _strip_prep_words(nm_name)
        nm_cano = _strip_prep_words(nm_cano)

        row = _find_food(nm_name) or _find_food(nm_cano) or _find_food(_alias_to_zh(nm_cano))

        w = _as_float(it.get("weight_g", 0.0), 0.0)
        if w < 0:
            w = 0.0

        if row:
            per100_kcal = _as_float(_col(row, KCAL_KEYS, 0))
            per100_p = _as_float(_col(row, PROT_KEYS, 0))
            per100_f = _as_float(_col(row, FAT_KEYS, 0))
            per100_c = _as_float(_col(row, CARB_KEYS, 0))
            ratio = w / 100.0
            kcal = round(per100_kcal * ratio, 1)
            p = round(per100_p * ratio, 1)
            f = round(per100_f * ratio, 1)
            c = round(per100_c * ratio, 1)
            matched = True

            label = _col(row, NAME_KEYS) or _alias_to_zh(
                _col(row, CANON_KEYS, "") or nm_name or nm_cano
            )
            canonical = _col(row, CANON_KEYS, nm_cano or nm_name)
        else:
            kcal = p = f = c = 0.0
            matched = False
            label = _alias_to_zh(nm_name or nm_cano) or (nm_name or nm_cano)
            canonical = nm_cano or nm_name

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

        totals["kcal"] += kcal
        totals["protein_g"] += p
        totals["fat_g"] += f
        totals["carb_g"] += c

    totals = {k: (round(v, 1) if isinstance(v, float) else v) for k, v in totals.items()}
    return enriched, totals
