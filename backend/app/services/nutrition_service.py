# backend/app/services/nutrition_service.py
from __future__ import annotations
import os, csv
from typing import Dict, List, Tuple, Optional
from difflib import get_close_matches

# ===== 1) 欄位鍵定義 =====
NAME_KEYS  = ("name", "食品名稱", "食材", "canonical_zh")
CANON_KEYS = ("canonical", "標準名", "英文名")
KCAL_KEYS  = ("kcal", "熱量(kcal)", "熱量", "能量kcal")
PROT_KEYS  = ("protein_g", "蛋白質(g)", "蛋白質", "蛋白")
FAT_KEYS   = ("fat_g", "脂肪(g)", "脂肪")
CARB_KEYS  = ("carb_g", "碳水(g)", "碳水化合物", "碳水")

# ===== 2) 英中別名（原始表） =====
# key 一律用英文常見稱呼；值為顯示的中文
ALIAS_MAP_RAW: Dict[str, str] = {
    # 肉/蛋/乳
    "chicken": "雞肉", "beef": "牛肉", "pork": "豬肉", "fish": "魚肉",
    "egg": "雞蛋", "egg white": "蛋白", "boiled egg": "水煮蛋",
    "soft-boiled egg": "半熟蛋", "century egg": "皮蛋",

    # 豆製品
    "tofu": "豆腐（板豆腐）",
    "silken tofu": "嫩豆腐",
    "firm tofu": "豆干",

    # 蔬菜
    "pumpkin": "南瓜", "carrot": "胡蘿蔔", "eggplant": "茄子",
    "green pepper": "青椒", "bell pepper": "甜椒",
    "red bell pepper": "紅甜椒",
    "baby corn": "玉米筍", "small corn": "玉米筍",
    "lotus root": "蓮藕", "onion": "洋蔥", "garlic": "蒜頭",
    "broccoli": "花椰菜", "mushroom": "蘑菇", "shiitake": "香菇",
    "green onions": "蔥", "spring onion": "青蔥", "scallion": "青蔥",
    "parsley": "巴西里", "cilantro": "香菜", "coriander": "香菜",

    # 海味/調味
    "bonito flakes": "柴魚片",
    "nori seaweed": "海苔",
    "wasabi": "山葵/哇沙米",

    # 醬料與主食
    "soy sauce": "醬油",
    "sweet soy sauce": "甜醬油",
    "kecap manis": "甜醬油",
    "miso soup": "味噌湯",
    "soba noodles": "蕎麥麵",
}

# ===== 3) 名稱正規化（小寫、去空白/連字號/底線、簡單單複數） =====
def _norm(s: str) -> str:
    s = (s or "").strip().lower()
    for ch in [" ", "-", "_", "（", "）", "(", ")"]:
        s = s.replace(ch, "")
    # 簡單單複數處理
    if s.endswith("es") and len(s) > 3:
        s = s[:-2]
    elif s.endswith("s") and len(s) > 3:
        s = s[:-1]
    return s

# 預先建立「正規化別名表」，查找一律用正規化後的鍵
_NORM_ALIAS: Dict[str, str] = { _norm(k): v for k, v in ALIAS_MAP_RAW.items() }

# ===== 4) CSV 載入 =====
def _load_food_table(csv_path: str) -> List[dict]:
    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        return [dict(r) for r in reader]

_FOODS: List[dict] = []

def _ensure_loaded() -> None:
    """嘗試在常見路徑載入 foods_tw.csv（只載一次）"""
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

# ===== 5) 小工具 =====
def _col(row: dict, keys: Tuple[str, ...], default=None):
    for k in keys:
        if k in row and row[k] not in (None, ""):
            return row[k]
    return default

def _as_float(x, default=0.0) -> float:
    try:
        return float(str(x).strip())
    except Exception:
        return default

def _alias_to_zh(name: str) -> str:
    """英→中別名；查不到就回傳原字串"""
    return _NORM_ALIAS.get(_norm(name), name)

def _all_names_for_row(r: dict) -> List[str]:
    """此列在比對時可用的所有名稱（中文 + 英文 + 別名中文）"""
    zh = _col(r, NAME_KEYS, "")
    en = _col(r, CANON_KEYS, "")
    names = [zh, en]
    if en:
        zh_from_alias = _NORM_ALIAS.get(_norm(en))
        if zh_from_alias:
            names.append(zh_from_alias)
    return [n for n in names if n]

def _exact_find(name: str) -> Optional[dict]:
    key = _norm(name)
    if not key:
        return None
    for r in _FOODS:
        for n in _all_names_for_row(r):
            if _norm(n) == key:
                return r
    return None

def _fuzzy_find(name: str, pool: Optional[List[dict]] = None, cutoff: float = 0.78) -> Optional[dict]:
    """在 (中文/英文/別名) 的正規化集合上做 fuzzy。cutoff 0~1，越高越嚴格。"""
    pool = pool or _FOODS
    target = _norm(name)
    if not target:
        return None

    candidates = []   # [(norm_name, row), ...]
    for r in pool:
        for n in _all_names_for_row(r):
            candidates.append((_norm(n), r))

    corpus = [c[0] for c in candidates]
    hits = get_close_matches(target, corpus, n=1, cutoff=cutoff)
    if hits:
        hit = hits[0]
        for norm_name, r in candidates:
            if norm_name == hit:
                return r
    return None

def _find_food(name: str) -> Optional[dict]:
    """先 exact，再 alias，再 fuzzy"""
    # exact
    row = _exact_find(name)
    if row:
        return row
    # alias 中文
    alias_zh = _alias_to_zh(name)
    if alias_zh != name:
        row = _exact_find(alias_zh)
        if row:
            return row
    # fuzzy
    return _fuzzy_find(name)

# ===== 6) 主計算 =====
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
    enriched_items 多 'label'(中文顯示)、'matched'(是否命中)
    """
    _ensure_loaded()
    items = _coerce_items(items)

    enriched: List[Dict] = []
    totals = dict(kcal=0.0, protein_g=0.0, fat_g=0.0, carb_g=0.0)

    for it in items or []:
        # 1) 配菜可選擇忽略
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

        # 2) 對照順序：name -> canonical -> canonical的中文別名
        row = (
            _find_food(nm_name) or
            _find_food(nm_cano) or
            _find_food(_alias_to_zh(nm_cano))
        )

        # 3) 重量與計算
        w = _as_float(it.get("weight_g", 0.0), 0.0)
        if w < 0:  # 安全處理
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

            label = _col(row, NAME_KEYS) or _alias_to_zh(_col(row, CANON_KEYS, "") or nm_name or nm_cano)
            canonical = _col(row, CANON_KEYS, nm_cano or nm_name)
            matched = True
        else:
            # 查無 → 以 0 佔位，但 label 盡量用中文別名
            kcal = p = f = c = 0.0
            label = _alias_to_zh(nm_name or nm_cano) or (nm_name or nm_cano)
            canonical = nm_cano or nm_name
            matched = False

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
