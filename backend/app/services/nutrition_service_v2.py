# backend/app/services/nutrition_service_v2.py
from __future__ import annotations

import csv
import os
import re
from difflib import get_close_matches
from typing import Dict, List, Tuple, Optional

# 讓 analyze_and_calc 可以直接呼叫視覺分析
from app.services.openai_client import vision_analyze_base64

# === CSV 欄位鍵 ===
NAME_KEYS = ("name", "食品名稱", "食材", "canonical_zh")
CANON_KEYS = ("canonical", "標準名", "英文名")
KCAL_KEYS = ("kcal", "熱量(kcal)", "熱量", "能量kcal")
PROT_KEYS = ("protein_g", "蛋白質(g)", "蛋白質", "蛋白")
FAT_KEYS = ("fat_g", "脂肪(g)", "脂肪")
CARB_KEYS = ("carb_g", "碳水(g)", "碳水化合物", "碳水")

# === 英中別名（原始） ===
ALIAS_RAW: Dict[str, str] = {
    # 常見蔬菜
    "cucumber": "小黃瓜",
    "cucumbers": "小黃瓜",
    "carrot": "紅蘿蔔",
    "red pepper": "紅甜椒",
    "sweet pepper": "紅甜椒",
    "spring onion": "蔥花",
    "green onion": "蔥花",
    "scallion": "蔥花",

    # 豆類 / 盤菜
    "silken tofu": "嫩豆腐",
    "firm tofu": "板豆腐",
    "shredded tofu": "豆干絲",
    "bean curd strips": "豆干絲",
    "bean curd threads": "豆干絲",
    "tofu strips": "豆干絲",
    "dried tofu strips": "豆干絲",

    # 湯料 / 日式
    "miso soup": "味噌湯",
    "miso paste": "味噌",
    "wakame": "海帶芽",
    "dashi": "高湯",
    "broth": "高湯",
    "vegetarian broth": "素食高湯",

    # 其他
    "katsuobushi": "柴魚片",
    "bonito flakes": "柴魚片",
}

# === 內建預設(per-100g)營養值（CSV 找不到時使用） ===
# 來源：以你提供截圖/一般資料推估的合理近似，用於容錯。若 CSV 補齊會自動覆蓋。
DEFAULTS_PER100: Dict[str, Dict[str, float]] = {
    # 豆干絲：你 150 g 例子 255.1 kcal, P 27.5, F 12.9, C 7.2  ->  per100 近似
    "shredded tofu": {"kcal": 170.1, "protein_g": 18.3, "fat_g": 8.6, "carb_g": 4.8},

    # 味噌（糊）：你 10 g 例子 21.5 kcal, P 1.1, F 0.5, C 3.3 -> per100
    "miso paste": {"kcal": 215.0, "protein_g": 11.0, "fat_g": 5.0, "carb_g": 33.0},

    # 海帶芽（泡發）粗估：低熱量
    "wakame": {"kcal": 45.0, "protein_g": 3.0, "fat_g": 0.5, "carb_g": 9.0},

    # 高湯（含素高湯）：你 200 g 例子 34 kcal, C 8 g -> per100 近似
    "dashi": {"kcal": 17.0, "protein_g": 0.0, "fat_g": 0.0, "carb_g": 4.0},
    "vegetarian broth": {"kcal": 17.0, "protein_g": 0.0, "fat_g": 0.0, "carb_g": 4.0},
}

# ---------- 小工具 ----------

def _strip_parens(s: str) -> str:
    """去掉中英文括號內容。"""
    if not s:
        return s
    return re.sub(r"[（(].*?[)）]", "", s).strip()

def _norm(s: str) -> str:
    s = (s or "").strip().lower()
    s = re.sub(r"[\s_-]+", "", s)
    # 簡單單複數
    if len(s) > 3 and s.endswith("es"):
        s = s[:-2]
    elif len(s) > 3 and s.endswith("s"):
        s = s[:-1]
    return s

# 正規化別名表
_ALIAS_NORM: Dict[str, str] = {}
for k, v in ALIAS_RAW.items():
    _ALIAS_NORM[_norm(k)] = v
    k2 = _strip_parens(k)
    if k2:
        _ALIAS_NORM[_norm(k2)] = v

def _alias_to_zh(name: str) -> str:
    if not name:
        return name
    key = _norm(name)
    if key in _ALIAS_NORM:
        return _ALIAS_NORM[key]
    k2 = _norm(_strip_parens(name))
    return _ALIAS_NORM.get(k2, name)

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

def _load_csv(path: str) -> List[dict]:
    with open(path, "r", encoding="utf-8") as f:
        return [dict(r) for r in csv.DictReader(f)]

_FOODS: List[dict] = []

def _ensure_loaded():
    """多路徑容錯載入 foods_tw.csv"""
    global _FOODS
    if _FOODS:
        return
    cands = [
        os.path.join(os.path.dirname(__file__), "..", "data", "foods_tw.csv"),
        os.path.join(os.getcwd(), "backend", "app", "data", "foods_tw.csv"),
        os.path.join(os.getcwd(), "app", "data", "foods_tw.csv"),
        os.path.join(os.getcwd(), "data", "foods_tw.csv"),
    ]
    for p in map(os.path.normpath, cands):
        if os.path.exists(p):
            _FOODS = _load_csv(p)
            break
    if not _FOODS:
        raise FileNotFoundError("foods_tw.csv not found in common locations.")

def _names_for_row(r: dict) -> List[str]:
    zh = (_col(r, NAME_KEYS, "") or "").strip()
    en = (_col(r, CANON_KEYS, "") or "").strip()
    out: List[str] = []
    if zh:
        out.append(zh)
        zha = _ALIAS_NORM.get(_norm(zh))
        if zha and zha != zh:
            out.append(zha)
    if en:
        out.append(en)
        from_alias = _ALIAS_NORM.get(_norm(en)) or _ALIAS_NORM.get(_norm(_strip_parens(en)))
        if from_alias:
            out.append(from_alias)
    # 去重
    seen = set()
    dedup: List[str] = []
    for n in out:
        k = _norm(n)
        if k and k not in seen:
            seen.add(k)
            dedup.append(n)
    return dedup

def _fuzzy_find(name: str, cutoff: float = 0.66) -> Optional[dict]:
    _ensure_loaded()
    key = _norm(name)
    if not key:
        return None
    cand: List[Tuple[str, dict]] = []
    for r in _FOODS:
        for n in _names_for_row(r):
            cand.append((_norm(n), r))
    corpus = [c[0] for c in cand if c[0]]
    hits = get_close_matches(key, corpus, n=1, cutoff=cutoff)
    if hits:
        target = hits[0]
        for k, r in cand:
            if k == target:
                return r
    return None

def _find_row(name: str) -> Optional[dict]:
    _ensure_loaded()
    if not name:
        return None
    key = _norm(name)
    key2 = _norm(_strip_parens(name))
    for r in _FOODS:
        for n in _names_for_row(r):
            kn = _norm(n)
            if kn == key or kn == key2:
                return r
    # alias
    zh_alias = _alias_to_zh(name)
    if zh_alias and zh_alias != name:
        for r in _FOODS:
            for n in _names_for_row(r):
                if _norm(n) == _norm(zh_alias):
                    return r
    # fuzzy
    return _fuzzy_find(name)

def _coerce_items(items):
    if isinstance(items, dict):
        return [items]
    if not isinstance(items, list):
        return []
    return items

def _defaults_row_for(canonical_en: str) -> Optional[dict]:
    """若 CSV 找不到，回傳一個內建的 per-100g 資料列（與 CSV 欄位相容）。"""
    if not canonical_en:
        return None
    key = _norm(canonical_en)
    # 映射成我們 DEFAULTS 的 key
    for k in DEFAULTS_PER100.keys():
        if _norm(k) == key:
            per100 = DEFAULTS_PER100[k]
            return {
                "canonical": k,
                "英文名": k,
                "name": _alias_to_zh(k),
                "食品名稱": _alias_to_zh(k),
                "kcal": per100["kcal"],
                "protein_g": per100["protein_g"],
                "fat_g": per100["fat_g"],
                "carb_g": per100["carb_g"],
            }
    return None

def calc(items: List[Dict], include_garnish: bool = False):
    """
    items: [{'name':..., 'canonical':..., 'weight_g':..., 'is_garnish':bool}, ...]
    return: (enriched_items, totals)
    """
    _ensure_loaded()
    items = _coerce_items(items)

    enriched: List[Dict] = []
    totals = dict(kcal=0.0, protein_g=0.0, fat_g=0.0, carb_g=0.0)

    for it in items:
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
        cano = str(it.get("canonical") or "").strip()

        # 先嘗試 CSV，找不到再用內建預設
        row = _find_row(nm) or _find_row(cano) or _find_row(_alias_to_zh(cano))
        if row is None:
            row = _defaults_row_for(cano)

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

            label = _col(row, NAME_KEYS) or _alias_to_zh(_col(row, CANON_KEYS, "") or nm or cano)
            canonical = _col(row, CANON_KEYS, cano or nm)
        else:
            kcal = p = f = c = 0.0
            matched = False
            label = _alias_to_zh(nm or cano) or (nm or cano)
            canonical = cano or nm

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

    totals = {k: round(v, 1) for k, v in totals.items()}
    return enriched, totals

# 供路由直接使用：完成「影像→食材→計算」
def analyze_and_calc(image_b64: str, include_garnish: bool = False):
    vision = vision_analyze_base64(image_b64)
    items = list(vision.get("items") or [])
    enriched, totals = calc(items, include_garnish=include_garnish)
    return {
        "model": vision.get("model"),
        "vision_error": vision.get("error"),
        "items_raw": items,
        "items_enriched": enriched,
        "totals": totals,
    }
