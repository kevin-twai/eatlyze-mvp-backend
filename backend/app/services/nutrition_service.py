# backend/app/services/nutrition_service.py
from __future__ import annotations
import os
import re
import csv
from typing import Dict, List, Tuple
from difflib import get_close_matches

# =========================
# 欄位鍵定義（容錯）
# =========================
NAME_KEYS  = ("name", "食品名稱", "食材", "canonical_zh")
CANON_KEYS = ("canonical", "標準名", "英文名")
KCAL_KEYS  = ("kcal", "熱量(kcal)", "熱量", "能量kcal")
PROT_KEYS  = ("protein_g", "蛋白質(g)", "蛋白質", "蛋白")
FAT_KEYS   = ("fat_g", "脂肪(g)", "脂肪")
CARB_KEYS  = ("carb_g", "碳水(g)", "碳水化合物", "碳水")

# =========================
# 英→中 別名表（原始）
# =========================
ALIAS_MAP: Dict[str, str] = {
    # 肉類/蛋
    "chicken": "雞肉",
    "beef": "牛肉",
    "pork": "豬肉",
    "fish": "魚肉",
    "egg": "雞蛋",
    "egg white": "蛋白",
    "boiled egg": "水煮蛋",
    "soft-boiled egg": "半熟蛋",

    # 蔬菜
    "pumpkin": "南瓜",
    "carrot": "胡蘿蔔",
    "eggplant": "茄子",
    "mushroom": "蘑菇",
    "onion": "洋蔥",
    "parsley": "巴西里",
    "garlic": "蒜頭",
    "broccoli": "花椰菜",

    # 青椒/甜椒類常見寫法
    "green pepper": "青椒",
    "bell pepper": "青椒",
    "green bell pepper": "青椒",
    "sweet pepper": "青椒",
    "shishito pepper": "青椒",

    # 玉米筍
    "baby corn": "玉米筍",
    "small corn": "玉米筍",

    # 蓮藕
    "lotus root": "蓮藕",

    # 醬料/主食
    "curry sauce": "咖哩醬",
    "rice": "白飯",

    # 中文同義（保險）
    "小玉米": "玉米筍",
    "青花菜": "花椰菜",
    "玉米": "玉米筍",
}

# =========================
# 正規化工具
# =========================
# 括號與裝飾，像 "Onion (garnish)", "[...]", "【...】"
_STRIP_PARENS_RE = re.compile(r"[\(\[\{（【].*?[\)\]\}）】]")
# 去除非單字/空白的符號
_NON_WORD_RE     = re.compile(r"[^\w\s]+")

def _strip_decorations(s: str) -> str:
    """去掉 ()[]{}（中英）中的裝飾字，並清掉多餘標點與連續空白"""
    s = _STRIP_PARENS_RE.sub("", s or "")
    s = _NON_WORD_RE.sub(" ", s)
    return " ".join(s.split())

def _norm(s: str) -> str:
    """
    名稱正規化：小寫、去裝飾、去空白/連字號/底線、簡單單複數處理。
    用於比對與別名快取鍵。
    """
    s = (s or "").strip().lower()
    s = _strip_decorations(s)
    for ch in (" ", "-", "_"):
        s = s.replace(ch, "")
    if s.endswith("es") and len(s) > 3:
        s = s[:-2]
    elif s.endswith("s") and len(s) > 3:
        s = s[:-1]
    return s

# 正規化別名表（查表一律用正規化）
_NORM_ALIAS: Dict[str, str] = { _norm(k): v for k, v in ALIAS_MAP.items() }

def _alias_to_zh(name: str) -> str:
    """正規化後查別名表，查不到就回原字串"""
    return _NORM_ALIAS.get(_norm(name), name)

# =========================
# CSV 載入
# =========================
def _load_food_table(csv_path: str) -> List[dict]:
    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        return [dict(r) for r in reader]

_FOODS: List[dict] = []

def _ensure_loaded():
    """從常見位置嘗試載入 foods_tw.csv"""
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

# =========================
# 比對候選（變體生成）
# =========================
def _variants(name: str) -> List[str]:
    """
    針對一個輸入產生多種可比對候選（去裝飾、去形容詞、別名中文等）
    - green bell pepper -> ["green bell pepper", "bell pepper", "green pepper", "pepper", "青椒"]
    - Onion (garnish)  -> ["Onion", "洋蔥"]
    """
    raw = _strip_decorations(name or "")
    v = {raw}

    low = raw.lower()
    if "pepper" in low:
        base = low
        for w in ("green", "red", "yellow", "sweet", "bell"):
            base = base.replace(f"{w} ", "").replace(f" {w}", "")
        base = " ".join(base.split())
        if base:
            v.add(base)               # "pepper"
        v.add(low.replace("bell ", ""))   # green pepper
        v.add(low.replace(" sweet", ""))  # bell pepper
        v.add(low.replace(" green", ""))  # bell pepper
        v.add("pepper")

    # 直接別名映到中文
    v.add(_alias_to_zh(raw))

    return [x for x in v if x]

def _all_names_for_row(r: dict) -> List[str]:
    """
    此列可被比對的所有名稱（中文、英文、別名中文、變體）
    """
    zh = _col(r, NAME_KEYS, "")
    en = _col(r, CANON_KEYS, "")
    names = [zh, en]

    if en:
        zh_from_alias = _NORM_ALIAS.get(_norm(en))
        if zh_from_alias:
            names.append(zh_from_alias)

    # 對每個已知名再產出變體以提升命中率
    for n in list(names):
        names.extend(_variants(n))

    # 去重保序
    seen = set()
    out = []
    for n in names:
        if n and n not in seen:
            out.append(n)
            seen.add(n)
    return out

# =========================
# 檢索
# =========================
def _col(row: dict, keys: Tuple[str, ...], default=None):
    for k in keys:
        if k in row and row[k] not in (None, ""):
            return row[k]
    return default

def _find_food(name: str) -> dict | None:
    """
    檢索流程：
      1) 多候選 exact（正規化後）—最可信
      2) 保守 fuzzy（只有在 exact 皆失敗時，才用高門檻啟用）
    """
    _ensure_loaded()
    # 準備輸入候選（原始去裝飾優先）
    candidates_to_try = _variants(name)
    front = _strip_decorations(name or "")
    if front:
        candidates_to_try.insert(0, front)

    # 1) exact（對每個候選都試一次）
    norm_inputs = [ _norm(n) for n in candidates_to_try if n ]
    for r in _FOODS:
        row_norms = { _norm(n) for n in _all_names_for_row(r) }
        if any(inp in row_norms for inp in norm_inputs):
            return r

    # 2) fuzzy（保守：cutoff 高、且只取第一個）
    # 準備 corpus
    corpus = []
    bucket: List[tuple[str, dict]] = []
    for r in _FOODS:
        for n in _all_names_for_row(r):
            nn = _norm(n)
            corpus.append(nn)
            bucket.append((nn, r))

    # 逐一對輸入候選做 fuzzy；命中第一個就回
    for s in norm_inputs:
        if not s:
            continue
        # cutoff 越高越嚴格（0.86~0.9 之間都可；越高越安全但漏抓機率增）
        hits = get_close_matches(s, corpus, n=1, cutoff=0.88)
        if hits:
            hit = hits[0]
            for nn, r in bucket:
                if nn == hit:
                    return r

    return None

# =========================
# 計算
# =========================
def _as_float(x, default=0.0):
    try:
        return float(str(x).strip())
    except Exception:
        return default

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

    enriched: List[Dict] = []
    totals = dict(kcal=0.0, protein_g=0.0, fat_g=0.0, carb_g=0.0)

    for it in items or []:
        # 配菜可排除計算
        if not include_garnish and bool(it.get("is_garnish")):
            out = {
                **it,
                "kcal": 0.0, "protein_g": 0.0, "fat_g": 0.0, "carb_g": 0.0,
                "matched": False,
                "label": it.get("name") or it.get("canonical"),
            }
            enriched.append(out)
            continue

        # 名稱採用「去裝飾後」再比對，減少 OnIon (garnish) 類干擾
        nm_name = _strip_decorations(str(it.get("name") or ""))
        nm_cano = _strip_decorations(str(it.get("canonical") or ""))

        row = (
            _find_food(nm_name)
            or _find_food(nm_cano)
            or _find_food(_alias_to_zh(nm_cano))
        )

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

            # 顯示中文：CSV 中文；若無則用別名表把英文映中文
            label = _col(row, NAME_KEYS) or _alias_to_zh(_col(row, CANON_KEYS, "") or nm_name or nm_cano)
            canonical = _col(row, CANON_KEYS, nm_cano or nm_name)
        else:
            kcal = p = f = c = 0.0
            matched = False
            label = _alias_to_zh(nm_name or nm_cano) or (nm_name or nm_cano)
            canonical = nm_cano or nm_name

        out = {
            **it,
            "label": label,          # 前端顯示（中文）
            "canonical": canonical,  # 後端對齊用
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
