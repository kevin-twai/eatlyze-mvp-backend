#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
同步工具：把 ontology 中缺少於 foods_tw.csv 的 canonical 直接補進 CSV。
- 互動確認或 --yes 全自動
- --dry-run 僅預覽
- 自動備份 CSV
"""

from __future__ import annotations
import argparse
import csv
import json
import os
import re
import sys
from datetime import datetime
from typing import Dict, List, Tuple

# 預設路徑（可用參數覆蓋）
DEFAULT_CSV = os.path.join("backend", "app", "data", "foods_tw.csv")
DEFAULT_JSON = os.path.join("backend", "app", "data", "food_ontology.json")

# CSV 欄位（保持和現有 nutrition_service 相容）
REQUIRED_FIELDS = ["name", "canonical", "kcal", "protein_g", "fat_g", "carb_g"]

def norm(s: str) -> str:
    s = (s or "").strip().lower()
    for ch in (" ", "-", "_"):
        s = s.replace(ch, "")
    if s.endswith("es") and len(s) > 3:
        s = s[:-2]
    elif s.endswith("s") and len(s) > 3:
        s = s[:-1]
    return s

def strip_parens(text: str) -> str:
    return re.sub(r"\(.*?\)", "", text or "").strip()

def load_ontology(path: str) -> List[dict]:
    if not os.path.exists(path):
        raise FileNotFoundError(f"Ontology not found: {path}")
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, list):
        raise ValueError("food_ontology.json 必須是 list[dict]")
    # 規範化部份欄位
    cleaned = []
    for i, item in enumerate(data):
        if not isinstance(item, dict):
            continue
        itm = dict(item)
        itm["canonical"] = itm.get("canonical") or itm.get("name_en") or itm.get("name_zh")
        if not itm.get("canonical"):
            # 略過沒有 canonical 的節點
            continue
        itm["name_zh"] = itm.get("name_zh") or ""
        itm["name_en"] = itm.get("name_en") or itm["canonical"]
        cleaned.append(itm)
    return cleaned

def load_csv(path: str) -> Tuple[List[dict], List[str]]:
    if not os.path.exists(path):
        raise FileNotFoundError(f"CSV not found: {path}")
    with open(path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = [dict(r) for r in reader]
        fields = list(reader.fieldnames or [])
    # 檢查欄位
    missing = [c for c in REQUIRED_FIELDS if c not in fields]
    if missing:
        raise ValueError(f"CSV 欄位缺少 {missing}，目前欄位={fields}")
    return rows, fields

def backup_csv(path: str) -> str:
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    bak = f"{path}.bak.{ts}"
    with open(path, "rb") as src, open(bak, "wb") as dst:
        dst.write(src.read())
    return bak

def parse_defaults(def_str: str | None) -> Dict[str, str]:
    # "kcal=0 protein_g=0 fat_g=0 carb_g=0"
    defaults = {"kcal": "0", "protein_g": "0", "fat_g": "0", "carb_g": "0"}
    if not def_str:
        return defaults
    for tok in def_str.split():
        if "=" in tok:
            k, v = tok.split("=", 1)
            k = k.strip()
            v = v.strip()
            if k in defaults:
                defaults[k] = v
    return defaults

def main():
    ap = argparse.ArgumentParser(description="Sync ontology canonical into foods_tw.csv")
    ap.add_argument("--csv", default=DEFAULT_CSV, help=f"CSV 檔路徑 (default: {DEFAULT_CSV})")
    ap.add_argument("--ontology", default=DEFAULT_JSON, help=f"Ontology JSON 路徑 (default: {DEFAULT_JSON})")
    ap.add_argument("--dry-run", action="store_true", help="僅顯示將新增的項目，不寫入檔案")
    ap.add_argument("--yes", action="store_true", help="不互動，直接寫檔（跳過逐項確認）")
    ap.add_argument("--defaults", type=str, default="kcal=0 protein_g=0 fat_g=0 carb_g=0",
                    help='新增列預設值，例如：--defaults "kcal=0 protein_g=0 fat_g=0 carb_g=0"')
    args = ap.parse_args()

    csv_path = args.csv
    json_path = args.ontology
    defaults = parse_defaults(args.defaults)

    # 載入
    onto = load_ontology(json_path)
    rows, fields = load_csv(csv_path)

    # 取現有 canonical 集合
    csv_canon_norm = {norm(r.get("canonical", "")) for r in rows if r.get("canonical")}
    # 找 ontology 缺項
    missing: List[dict] = []
    for o in onto:
        cano = o["canonical"]
        if norm(cano) not in csv_canon_norm:
            name_zh = o.get("name_zh") or ""
            name_en = o.get("name_en") or cano
            # CSV 的 "name" 欄用中文優先，沒有就英文
            display_name = name_zh or name_en
            missing.append({
                "name": display_name,
                "canonical": cano,
                "kcal": defaults["kcal"],
                "protein_g": defaults["protein_g"],
                "fat_g": defaults["fat_g"],
                "carb_g": defaults["carb_g"],
            })

    if not missing:
        print("✅ 沒有缺項需要同步。CSV 已涵蓋 ontology 的 canonical。")
        return

    print(f"🔎 發現 {len(missing)} 個 ontology canonical 不在 CSV：")
    for i, m in enumerate(missing, 1):
        print(f"  {i:>2}. name='{m['name']}', canonical='{m['canonical']}', kcal={m['kcal']} P={m['protein_g']} F={m['fat_g']} C={m['carb_g']}")

    if args.dry_run:
        print("\n💡 --dry-run 模式，不會寫檔。")
        return

    # 互動或自動確認
    if not args.yes:
        ans = input("\n要把以上項目直接 append 到 CSV 嗎？[y/N] ").strip().lower()
        if ans not in ("y", "yes"):
            print("已取消，不做變更。")
            return

    # 備份
    bak = backup_csv(csv_path)
    print(f"🧳 已備份 CSV：{bak}")

    # 寫入（保持原欄位順序）
    try:
        with open(csv_path, "a", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fields)
            # 逐筆 append
            for m in missing:
                writer.writerow({k: m.get(k, "") for k in fields})
        print(f"✅ 已寫入 CSV：{csv_path}，新增 {len(missing)} 筆。")
    except Exception as e:
        print(f"❌ 寫入失敗：{e}\n嘗試回復備份...")
        # 回復備份
        with open(bak, "rb") as src, open(csv_path, "wb") as dst:
            dst.write(src.read())
        print("↩️ 已回復原始 CSV。")
        sys.exit(1)

if __name__ == "__main__":
    main()