# backend/app/services/nutrition_service_v2.py
from __future__ import annotations

import os
from typing import Dict, List, Tuple, Optional
from difflib import get_close_matches

from .nutrition_service import calc as calc_v1  # 直接沿用你 v1 的 calc（有 CSV 查表）

# —— 這裡維持你原本的一組 alias（簡化示例，實務上你可延用 v1 的 alias）——
NAME_ALIASES = {
    "miso soup": "味噌湯",
    "miso": "味噌",
    "tofu": "豆腐",
    "green onion": "蔥",
    "spring onion": "蔥",
    "scallion": "蔥",
    "dashi": "高湯",
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

def _alias(s: str) -> str:
    key = _norm(s)
    for k, v in NAME_ALIASES.items():
        if _norm(k) == key:
            return v
    return s

# ====== 這是「保底：看到味噌湯就自動補項目」 ======
def _fallback_items_for_miso_soup() -> List[Dict]:
    # 份量你可依照實務再調整
    return [
        {"name": "味噌", "canonical": "miso paste", "weight_g": 15, "is_garnish": False},
        {"name": "豆腐", "canonical": "tofu", "weight_g": 30, "is_garnish": False},
        {"name": "蔥", "canonical": "green onion", "weight_g": 5, "is_garnish": True},
        {"name": "高湯", "canonical": "dashi", "weight_g": 200, "is_garnish": False},
    ]

def _looks_like_miso_soup(items: List[Dict]) -> bool:
    """只要任一 item 名稱/標準名出現 miso soup / 味噌湯，就視為味噌湯場景"""
    tokens = []
    for it in items:
        tokens.extend([it.get("name",""), it.get("canonical","")])
    tokens = [(_alias(t) or "").lower() for t in tokens]
    joined = " ".join(tokens)
    return ("miso soup" in joined) or ("味噌湯" in joined)

# ====== 主要對外 API ======
def analyze_and_calc(vision_items: List[Dict], include_garnish: bool = False):
    """
    vision_items: 由 openai_client 視覺模型回來的 items（name/canonical/weight_g/is_garnish）
    流程：
      1) 若 items 為空 -> 回傳空結果
      2) 若判定像味噌湯 -> 自動補一組保底 items 與原 items 合併
      3) 丟給 v1.calc（會與 CSV/FUZZY 對表得出營養）
    """
    items = vision_items[:] if isinstance(vision_items, list) else []

    # 補：味噌湯保底
    try:
        if _looks_like_miso_soup(items):
            items = _fallback_items_for_miso_soup()  # 先用保底覆蓋；也可選擇 extend
    except Exception:
        pass

    enriched, totals = calc_v1(items, include_garnish=include_garnish)
    return enriched, totals
