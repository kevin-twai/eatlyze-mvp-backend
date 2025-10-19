# backend/app/services/nutrition_service.py
from __future__ import annotations
import os
import csv
from typing import Dict, List, Tuple
from difflib import get_close_matches

# === 欄位鍵定義（容錯） ===
NAME_KEYS  = ("name", "食品名稱", "食材", "canonical_zh")
CANON_KEYS = ("canonical", "標準名", "英文名")
KCAL_KEYS  = ("kcal", "熱量(kcal)", "熱量", "能量kcal")
PROT_KEYS  = ("protein_g", "蛋白質(g)", "蛋白質", "蛋白")
FAT_KEYS   = ("fat_g", "脂肪(g)", "脂肪")
CARB_KEYS  = ("carb_g", "碳水(g)", "碳水化合物", "碳水")

# === 英中別名 / 規格化對照 ===
# 1) 顯示用中文名稱（若 CSV 沒中文就用這個）
ALIAS_ZH_MAP = {
    # 肉/蛋
    "chicken": "雞肉",
    "beef": "牛肉",
    "pork": "豬肉",
    "fish": "魚肉",
    "egg": "雞蛋",
    "eggwhite": "蛋白",
    "softboiledegg": "半熟蛋",
    "boiledegg": "水煮蛋",  # 顯示中文想用「水煮蛋」

    # 蔬菜
    "pumpkin": "南瓜",
    "carrot": "胡蘿蔔",
    "eggplant": "茄子",
    "greenpepper": "青椒",
    "bellpepper": "青椒",
    "babycorn": "玉米筍",
    "smallcorn": "玉米筍",
    "lotusroot": "蓮藕",
    "onion": "洋蔥",
    "garlic": "蒜頭",

    # 醬料/主食
    "currysauce": "咖哩醬",
    "rice": "白飯",

    # 常見中文字面同義
    "小玉米": "玉米筍",
    "青花菜": "花椰菜",
    "玉米": "玉米筍",
}

# 2) 查表用「標準鍵」：把輸入映射到 CSV 會有的關鍵名（英文或中文）
#    例如「boiled egg」→ 用「egg」那一列計算營養（想要獨立行就請在 CSV 加一列）
CANON_ALIAS = {
    "boiledegg": "egg",        # 用雞蛋的營養值
    "eggwhite": "egg white",
    "smallcorn": "baby corn",
    "bellpepper": "green pepper",
}

# 3) 內建「後備」每 100g 營養表（CSV 沒有時用）
FALLBACK_ROWS = {
    # 近似數據來源：USDA/通用資料；只做應急用，建議長期還是放進 CSV
    "babycorn": {  # 生 baby corn（玉米筍）約值
        "name": "玉米筍", "canonical": "baby corn",
        "kcal": 26.0, "protein_g": 1.7, "fat_g": 0.2, "carb_g": 5.2,
    },
    "currysauce": {  # 一般咖哩醬（調理用）示意
        "name": "咖哩醬", "canonical": "curry sauce",
        "kcal": 110.0, "protein_g": 2.0, "fat_g": 7.0, "carb_g": 9.0,
    },
    # 如果你希望水煮蛋用雞蛋值，可不放 fallback；這裡示範映射到 egg
    # "boiledegg": {...}
}

# ============== 共用小工具 ==============

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
    # 去空白/連字號/底線
    for ch in [" ", "-", "_"]:
        s = s.replace(ch, "")
    # 去掉常見標點
    for ch in [",", ".", "(", ")", "’", "'", "“", "”"]:
        s = s.replace(ch, "")
    # 英文複數單純化
    if s.endswith("es") and len(s) > 3:
        s = s[:-2]
    elif s.endswith("s") and len(s) > 3:
        s = s[:-1]
    return s

def _alias_to_zh(name: str) -> str:
    return ALIAS_ZH_MAP.get(_norm(name), name)

def _alias_to_canonical(name: str) -> str:
    """把輸入字串轉成用來查表的『標準鍵』（英文或中文都可）"""
    key = _norm(name)
    return CANON_ALIAS.get(key, name)

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
    # 若英文名亦能對到中文別名，加入候選
    if en:
        zh_from_alias = ALIAS_ZH_MAP.get(_norm(en))
        if zh_from_alias:
            names.append(zh_from_alias)
    return [n for n in names if n]

def _find_food_in_csv(name: str) -> dict | None:
    """只在 CSV 內找（精準→模糊）"""
    _ensure_loaded()
    key = _norm(name)
    if not key:
        return None

    # 1) 精準比對
    for r in _FOODS:
        for n in _all_names_for_row(r):
            if _norm(n) == key:
                return r

    # 2) 模糊比對
    corpus: List[tuple[str, dict]] = []
    for r in _FOODS:
        for n in _all_names_for_row(r):
            corpus.append((_norm(n), r))
    keys = [c[0] for c in corpus]
    hits = get_close_matches(key, keys, n=1, cutoff=0.86)
    if hits:
        hit = hits[0]
        for nk, r in corpus:
            if nk == hit:
                return r
    return None

def _find_food(name: str) -> dict | None:
    """
    綜合查找流程：
      1. 原字 → CSV
      2. 標準鍵（CANON_ALIAS）→ CSV
      3. 後備資料（FALLBACK_ROWS）
    """
    # 1) 直接 CSV
    row = _find_food_in_csv(name)
    if row:
        return row

    # 2) 用標準鍵再找一次 CSV
    canon = _alias_to_canonical(name)
    if canon and canon != name:
        row = _find_food_in_csv(canon)
        if row:
            return row

    # 3) 後備資料
    fb_key = _norm(name)
    if fb_key in FALLBACK_ROWS:
        return FALLBACK_ROWS[fb_key]
    canon_fb_key = _norm(_alias_to_canonical(name))
    if canon_fb_key in FALLBACK_ROWS:
        return FALLBACK_ROWS[canon_fb_key]

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
    enriched_items 會多 'label'（中文顯示名）
    """
    _ensure_loaded()
    items = _coerce_items(items)

    enriched = []
    totals = dict(kcal=0.0, protein_g=0.0, fat_g=0.0, carb_g=0.0)

    for it in items or []:
        if not include_garnish and bool(it.get("is_garnish")):
            out = {
                **it, "kcal": 0.0, "protein_g": 0.0, "fat_g": 0.0, "carb_g": 0.0,
                "matched": False, "label": it.get("name") or it.get("canonical")
            }
            enriched.append(out)
            continue

        nm_name = str(it.get("name") or "").strip()
        nm_cano = str(it.get("canonical") or "").strip()

        # 優先：原名 → 標準名 → 中文別名
        query_order = [
            nm_name,
            nm_cano,
            _alias_to_canonical(nm_name),
            _alias_to_canonical(nm_cano),
            _alias_to_zh(nm_name),
            _alias_to_zh(nm_cano),
        ]
        row = None
        for q in query_order:
            if not q:
                continue
            row = _find_food(q)
            if row:
                break

        w = _as_float(it.get("weight_g", 0.0), 0.0)
        if w < 0:
            w = 0.0

        if row:
            per100_kcal = _as_float(_col(row, KCAL_KEYS, row.get("kcal", 0)))
            per100_p    = _as_float(_col(row, PROT_KEYS, row.get("protein_g", 0)))
            per100_f    = _as_float(_col(row, FAT_KEYS,  row.get("fat_g", 0)))
            per100_c    = _as_float(_col(row, CARB_KEYS, row.get("carb_g", 0)))
            ratio = w / 100.0 if w else 0.0
            kcal = round(per100_kcal * ratio, 1)
            p    = round(per100_p    * ratio, 1)
            f    = round(per100_f    * ratio, 1)
            c    = round(per100_c    * ratio, 1)
            matched = True

            # 顯示名：CSV 的中文名稱；若沒中文則依別名中文；再不行用原名
            label_csv = _col(row, NAME_KEYS)
            label = label_csv or _alias_to_zh(_col(row, CANON_KEYS, "") or nm_name or nm_cano)
            canonical = _col(row, CANON_KEYS, nm_cano or nm_name)
        else:
            # 沒找到
            kcal = p = f = c = 0.0
            matched = False
            label = _alias_to_zh(nm_name or nm_cano) or (nm_name or nm_cano)
            canonical = nm_cano or nm_name

        out = {
            **it,
            "label": label,          # 前端可直接顯示中文
            "canonical": canonical,  # 標準名/英文名
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
