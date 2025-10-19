# backend/app/services/nutrition_service.py
from __future__ import annotations
import os, csv
from typing import Dict, List, Tuple
from difflib import get_close_matches

# --- 欄位鍵定義 ---
NAME_KEYS = ("name", "食品名稱", "食材", "canonical_zh")
CANON_KEYS = ("canonical", "標準名", "英文名")
KCAL_KEYS = ("kcal", "熱量(kcal)", "熱量", "能量kcal")
PROT_KEYS = ("protein_g", "蛋白質(g)", "蛋白質", "蛋白")
FAT_KEYS  = ("fat_g", "脂肪(g)", "脂肪")
CARB_KEYS = ("carb_g", "碳水(g)", "碳水化合物", "碳水")

# --- 英中別名對照表（可再擴充） ---
ALIAS_MAP = {
    # 肉類/蛋
    "chicken": "雞肉", "beef": "牛肉", "pork": "豬肉", "fish": "魚肉", "egg": "雞蛋",
    "egg white": "蛋白", "soft-boiled egg": "半熟蛋",
    # 蔬菜
    "pumpkin": "南瓜", "carrot": "胡蘿蔔", "eggplant": "茄子",
    "green pepper": "青椒", "bell pepper": "青椒",
    "baby corn": "玉米筍", "small corn": "玉米筍",
    "lotus root": "蓮藕", "onion": "洋葱", "garlic": "蒜頭",
    # 醬料/主食
    "curry sauce": "咖哩醬", "rice": "白飯",
    # 中文同義
    "小玉米": "玉米筍", "青花菜": "花椰菜", "玉米": "玉米筍",
}

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

def _norm(s: str) -> str:
    s = (s or "").strip().lower()
    # 去掉空白/連字號/底線
    for ch in [" ", "-", "_"]:
        s = s.replace(ch, "")
    # 英文字尾單純 s 複數處理（簡單）
    if s.endswith("es") and len(s) > 3:
        s = s[:-2]
    elif s.endswith("s") and len(s) > 3:
        s = s[:-1]
    return s

def _alias_to_zh(name: str) -> str:
    return ALIAS_MAP.get(_norm(name), name)

def _load_food_table(csv_path: str) -> List[dict]:
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

def _all_names_for_row(r: dict) -> List[str]:
    zh = _col(r, NAME_KEYS, "")
    en = _col(r, CANON_KEYS, "")
    names = [zh, en]
    # 加入別名映射（若有）
    if en:
        zh_from_alias = ALIAS_MAP.get(_norm(en))
        if zh_from_alias:
            names.append(zh_from_alias)
    return [n for n in names if n]

def _find_food(name: str) -> dict | None:
    _ensure_loaded()
    key = _norm(name)
    if not key:
        return None

    # 1) exact match（中/英）
    for r in _FOODS:
        for n in _all_names_for_row(r):
            if _norm(n) == key:
                return r

    # 2) fuzzy match
    candidates = []
    for r in _FOODS:
        for n in _all_names_for_row(r):
            candidates.append((_norm(n), r))
    corpus = [c[0] for c in candidates]
    hits = get_close_matches(key, corpus, n=1, cutoff=0.86)
    if hits:
        hit = hits[0]
        for norm_name, r in candidates:
            if norm_name == hit:
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
    enriched_items 會多一個 'label'（中文顯示名）
    """
    _ensure_loaded()
    items = _coerce_items(items)

    enriched = []
    totals = dict(kcal=0.0, protein_g=0.0, fat_g=0.0, carb_g=0.0)

    for it in items or []:
        if not include_garnish and bool(it.get("is_garnish")):
            out = {**it, "kcal": 0.0, "protein_g": 0.0, "fat_g": 0.0, "carb_g": 0.0, "matched": False, "label": it.get("name") or it.get("canonical")}
            enriched.append(out)
            continue

        nm_name = str(it.get("name") or "").strip()
        nm_cano = str(it.get("canonical") or "").strip()
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

            # 顯示名：CSV 中的中文 name；若無則從別名把英文轉中文
            label = _col(row, NAME_KEYS) or _alias_to_zh(_col(row, CANON_KEYS, "") or nm_name or nm_cano)
            canonical = _col(row, CANON_KEYS, nm_cano or nm_name)
        else:
            kcal = p = f = c = 0.0
            matched = False
            label = _alias_to_zh(nm_name or nm_cano) or (nm_name or nm_cano)
            canonical = nm_cano or nm_name

        out = {
            **it,
            "label": label,          # ← 前端顯示這個
            "canonical": canonical,  # ← 後端對齊用
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
