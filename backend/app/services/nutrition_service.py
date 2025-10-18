# backend/app/services/nutrition_service.py
from __future__ import annotations

import os
import csv
from typing import Dict, List, Tuple, Any

# --- 欄位鍵定義（相容中英文 CSV 欄名） ---
NAME_KEYS = ("name", "食品名稱", "食材", "canonical", "別名")
KCAL_KEYS = ("kcal", "熱量(kcal)", "熱量", "能量kcal")
PROT_KEYS = ("protein_g", "蛋白質(g)", "蛋白質", "蛋白")
FAT_KEYS  = ("fat_g", "脂肪(g)", "脂肪")
CARB_KEYS = ("carb_g", "碳水(g)", "碳水化合物", "碳水")

# --- 英→中／中→英常見別名 ---
ALIASES = {
    # 英文 → 規範英文
    "beef": "beef",
    "chicken": "chicken",
    "pork": "pork",
    "fish": "fish",
    "egg": "egg",
    "soft-boiled egg": "egg",
    "onion": "onion",
    "garlic": "garlic",
    "carrot": "carrot",
    "eggplant": "eggplant",
    "pumpkin": "pumpkin",
    "green pepper": "green pepper",
    "bell pepper": "green pepper",
    "shishito pepper": "green pepper",
    "lotus root": "lotus root",
    "daikon": "daikon",
    "radish": "daikon",
    "baby corn": "baby corn",
    "small corn": "baby corn",
    "curry sauce": "curry sauce",
    "rice": "rice",

    # 中文 → 規範英文
    "牛肉": "beef",
    "雞肉": "chicken",
    "豬肉": "pork",
    "魚肉": "fish",
    "雞蛋": "egg",
    "半熟蛋": "egg",
    "洋蔥": "onion",
    "蒜頭": "garlic",
    "胡蘿蔔": "carrot",
    "紅蘿蔔": "carrot",
    "茄子": "eggplant",
    "南瓜": "pumpkin",
    "青椒": "green pepper",
    "甜椒": "green pepper",
    "蓮藕": "lotus root",
    "白蘿蔔": "daikon",
    "蘿蔔": "daikon",
    "玉米筍": "baby corn",
    "小玉米": "baby corn",
    "咖哩醬": "curry sauce",
    "白飯": "rice",
    "青花菜": "broccoli",
    "花椰菜": "broccoli",
    "青江菜": "bok choy",
}

# 反向：規範英文 → 常見中文（只用於顯示時可選；查表仍用英文規範）
ALIASES_ZH = {
    "beef": "牛肉",
    "chicken": "雞肉",
    "pork": "豬肉",
    "fish": "魚肉",
    "egg": "雞蛋",
    "onion": "洋蔥",
    "garlic": "蒜頭",
    "carrot": "胡蘿蔔",
    "eggplant": "茄子",
    "pumpkin": "南瓜",
    "green pepper": "青椒",
    "lotus root": "蓮藕",
    "daikon": "白蘿蔔",
    "baby corn": "玉米筍",
    "curry sauce": "咖哩醬",
    "rice": "白飯",
    "broccoli": "花椰菜",
    "bok choy": "青江菜",
}

# ---------- 小工具 ----------
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

def _norm(s: Any) -> str:
    """大小寫不敏感、去空白、去括號內容（含全形）、移除尾端複數 s"""
    if s is None:
        return ""
    s = str(s)
    # 全形括號 -> 半形
    s = s.replace("（", "(").replace("）", ")")
    # 去掉括號內補充
    if "(" in s:
        s = s.split("(", 1)[0]
    s = s.strip().lower()
    # 去掉尾端 's'（簡單複數）但保留 'egg' 等單字
    if len(s) > 2 and s.endswith("s"):
        s = s[:-1]
    return s

def _to_canonical_en(s: str) -> str:
    """將中英各種名稱映射到『規範英文』；若找不到則回傳正規化後字串"""
    n = _norm(s)
    return ALIASES.get(n, n)  # 先做別名映射，再回傳

# ---------- CSV 載入與索引 ----------
_FOODS_ROWS: List[dict] = []
_INDEX: Dict[str, dict] = {}  # norm_key → row

def _load_food_table(csv_path: str) -> List[dict]:
    if not os.path.exists(csv_path):
        raise FileNotFoundError(f"foods csv not found: {csv_path}")
    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        return [dict(r) for r in reader]

def _ensure_loaded():
    global _FOODS_ROWS, _INDEX
    if _INDEX:
        return

    candidates = [
        os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "data", "foods_tw.csv")),
        os.path.normpath(os.path.join(os.getcwd(), "backend", "app", "data", "foods_tw.csv")),
        os.path.normpath(os.path.join(os.getcwd(), "app", "data", "foods_tw.csv")),
    ]
    path = None
    for p in candidates:
        if os.path.exists(p):
            path = p
            break
    if not path:
        raise FileNotFoundError("foods_tw.csv not found in common locations.")

    _FOODS_ROWS = _load_food_table(path)

    # 建立索引：以「規範英文名稱」與「原始名稱正規化」都建 key
    for r in _FOODS_ROWS:
        raw_name = _col(r, NAME_KEYS, "")
        if not raw_name:
            continue
        norm_raw = _norm(raw_name)
        canon_en = _to_canonical_en(raw_name)

        # 主鍵：規範英文
        _INDEX.setdefault(canon_en, r)
        # 次鍵：原始正規化（避免 CSV 寫的是中文或別字）
        _INDEX.setdefault(norm_raw, r)

    # 額外：把常見中文映射到英文規範後也指向同 row（若 CSV 裡只有中文名）
    for key, row in list(_INDEX.items()):
        # key 可能是英文或中文；取其 canonical 再回掛一次
        canon_en = _to_canonical_en(key)
        _INDEX.setdefault(canon_en, row)

def _find_food_by_keys(candidates: List[str]) -> dict | None:
    """依序以多個 key 嘗試查找（規範英文 & 正規化字串），最後再做『包含』模糊"""
    _ensure_loaded()

    # 先精準索引
    for name in candidates:
        if not name:
            continue
        canon = _to_canonical_en(name)
        if canon in _INDEX:
            return _INDEX[canon]
        n = _norm(name)
        if n in _INDEX:
            return _INDEX[n]

    # 最後再做「包含」搜尋（避免誤傷，僅在前述失敗時）
    for name in candidates:
        if not name:
            continue
        n = _norm(name)
        for k, row in _INDEX.items():
            if n and n in k:
                return row
    return None

# ---------- 主函式 ----------
def _coerce_items(items):
    if isinstance(items, dict):
        return [items]
    if not isinstance(items, list):
        return []
    return items

def calc(items: List[Dict], include_garnish: bool = False) -> Tuple[List[Dict], Dict]:
    """
    items: [{'name':..., 'canonical':..., 'weight_g':..., 'is_garnish':bool}, ...]
    return: (enriched_items, totals)
    """
    _ensure_loaded()
    items = _coerce_items(items)

    enriched: List[Dict[str, Any]] = []
    totals = dict(kcal=0.0, protein_g=0.0, fat_g=0.0, carb_g=0.0)

    for it in items or []:
        if not include_garnish and bool(it.get("is_garnish")):
            enriched.append({**it, "kcal": 0.0, "protein_g": 0.0, "fat_g": 0.0, "carb_g": 0.0, "matched": False})
            continue

        nm_name = str(it.get("name") or "").strip()
        nm_cano = str(it.get("canonical") or "").strip()

        row = _find_food_by_keys([nm_cano, nm_name])  # 先 canonical，再 name
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
