# backend/scripts/build_index.py
from __future__ import annotations

import os
import sys
import json
import pickle
from typing import List, Dict

# === 自動定位路徑：把 backend/ 放進 sys.path，才能 import app.services ===
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))                 # .../backend/scripts
BACKEND_DIR = os.path.abspath(os.path.join(CURRENT_DIR, ".."))           # .../backend
PROJECT_ROOT = os.path.abspath(os.path.join(BACKEND_DIR, ".."))          # .../

for p in (BACKEND_DIR, PROJECT_ROOT):
    if p not in sys.path:
        sys.path.insert(0, p)

# 檢查目標檔案是否存在（debug 資訊）
print(f"[path] CURRENT_DIR = {CURRENT_DIR}")
print(f"[path] BACKEND_DIR  = {BACKEND_DIR}")
print(f"[path] PROJECT_ROOT = {PROJECT_ROOT}")
print(f"[path] has app/services/semvec.py? {os.path.exists(os.path.join(BACKEND_DIR,'app','services','semvec.py'))}")

# === 匯入語意索引 ===
from app.services.semvec import SemanticIndex  # now resolvable

# === 檔案路徑 ===
ONTO_PATH = os.path.join(BACKEND_DIR, "app", "data", "food_ontology.json")
OUT_PATH  = os.path.join(BACKEND_DIR, "app", "data", "sem_index.pkl")

def load_ontology(path: str) -> List[Dict]:
    if not os.path.exists(path):
        raise FileNotFoundError(f"❌ Ontology not found: {path}")
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, list):
        raise ValueError("❌ food_ontology.json 應該是 list[dict]")
    return data

def main():
    print(f"[build] loading ontology: {ONTO_PATH}")
    items = load_ontology(ONTO_PATH)

    # 精簡要嵌入的欄位
    slim_items: List[Dict] = []
    for it in items:
        slim_items.append({
            "label": it.get("label") or it.get("name") or it.get("canonical") or "",
            "canonical": it.get("canonical") or "",
            "aliases": ", ".join(it.get("aliases", [])) if isinstance(it.get("aliases"), list) else it.get("aliases", ""),
            "category": it.get("category") or "",
            "kcal": it.get("kcal"),
            "protein_g": it.get("protein_g"),
            "fat_g": it.get("fat_g"),
            "carb_g": it.get("carb_g"),
        })

    idx = SemanticIndex()  # 會使用環境變數 OPENAI_API_KEY
    idx.build(slim_items)

    payload = {
        "labels": idx.labels(),
        "embeddings": idx.embeddings(),
        "items": idx.items(),
        "model": idx.model_name,
    }

    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    with open(OUT_PATH, "wb") as f:
        pickle.dump(payload, f)

    print(f"[build] ✅ index saved to {OUT_PATH}, total {len(payload['labels'])} items.")

if __name__ == "__main__":
    main()
