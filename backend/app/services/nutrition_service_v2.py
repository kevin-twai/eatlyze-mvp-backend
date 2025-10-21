# backend/app/services/nutrition_service_v2.py
from __future__ import annotations
import os, csv, json, re
from typing import Dict, List, Tuple, Optional
from difflib import get_close_matches
from .semvec import SemanticIndex

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
CSV_PATH = os.path.join(DATA_DIR, "foods_tw.csv")
ONTO_PATH = os.path.join(DATA_DIR, "food_ontology.json")
IDX_PATH = os.path.join(DATA_DIR, "sem_index.pkl")

NAME_KEYS  = ("name", "食品名稱", "食材")
CANON_KEYS = ("canonical", "標準名", "英文名")
KCAL_KEYS  = ("kcal", "熱量(kcal)", "熱量")
PROT_KEYS  = ("protein_g", "蛋白質(g)", "蛋白質")
FAT_KEYS   = ("fat_g", "脂肪(g)", "脂肪")
CARB_KEYS  = ("carb_g", "碳水(g)", "碳水化合物")

def _norm(s: str) -> str:
    s = (s or "").strip().lower()
    for ch in [" ", "-", "_"]:
        s = s.replace(ch, "")
    if s.endswith("es"): s = s[:-2]
    elif s.endswith("s"): s = s[:-1]
    return s

def _as_float(x, default=0.0):
    try:
        return float(str(x).strip())
    except Exception:
        return default

class NutritionMatcher:
    def __init__(self):
        self._foods = []
        self._alias = {}
        self._onto = {}
        self._idx = SemanticIndex()
        self._load_all()

    def _load_all(self):
        with open(CSV_PATH, "r", encoding="utf-8") as f:
            self._foods = list(csv.DictReader(f))
        with open(ONTO_PATH, "r", encoding="utf-8") as f:
            self._onto = json.load(f)
        self._idx.load(IDX_PATH)
        self._alias = self._build_alias(self._onto["root"])

    def _build_alias(self, node):
        out = {}
        aliases = [node.get("name_zh"), node.get("name_en")] + (node.get("aliases") or [])
        for a in aliases:
            if a: out[_norm(a)] = node.get("name_zh") or node.get("name_en")
        for ch in node.get("children", []) or []:
            out.update(self._build_alias(ch))
        return out

    def _find_food(self, name: str):
        key = _norm(name)
        for r in self._foods:
            if _norm(r.get("canonical", "")) == key or _norm(r.get("name", "")) == key:
                return r
        # alias map
        if key in self._alias:
            alias = self._alias[key]
            for r in self._foods:
                if _norm(r.get("name", "")) == _norm(alias):
                    return r
        # fuzzy
        names = [_norm(r.get("name", "")) for r in self._foods]
        hits = get_close_matches(key, names, n=1, cutoff=0.85)
        if hits:
            for r in self._foods:
                if _norm(r.get("name", "")) == hits[0]:
                    return r
        # semantic
        if self._idx:
            results = self._idx.query(name, top_k=3)
            for res in results:
                can = res.get("canonical")
                for r in self._foods:
                    if _norm(r.get("canonical", "")) == _norm(can):
                        return r
        return None

    def calc(self, items: List[Dict]):
        enriched, totals = [], dict(kcal=0, protein_g=0, fat_g=0, carb_g=0)
        for it in items:
            name = it.get("name") or it.get("canonical")
            weight = _as_float(it.get("weight_g", 0))
            row = self._find_food(name)
            if row:
                kcal = _as_float(row.get("kcal", 0)) * weight / 100
                p = _as_float(row.get("protein_g", 0)) * weight / 100
                f = _as_float(row.get("fat_g", 0)) * weight / 100
                c = _as_float(row.get("carb_g", 0)) * weight / 100
                enriched.append({**it, "label": row.get("name"), "kcal": kcal, "protein_g": p, "fat_g": f, "carb_g": c, "matched": True})
                totals["kcal"] += kcal
                totals["protein_g"] += p
                totals["fat_g"] += f
                totals["carb_g"] += c
            else:
                enriched.append({**it, "label": name, "matched": False})
        return enriched, {k: round(v, 1) for k, v in totals.items()}

nutrition = NutritionMatcher()
def calc(items): return nutrition.calc(items)