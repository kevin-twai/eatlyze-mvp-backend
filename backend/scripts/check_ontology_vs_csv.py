# backend/scripts/check_ontology_vs_csv.py
from __future__ import annotations
import csv, json, os, sys, argparse
from collections import Counter
from typing import List, Dict, Tuple

# 與服務端一致的正規化：小寫、去空白/連字號/底線、簡單複數處理
def norm(s: str) -> str:
    s = (s or "").strip().lower()
    for ch in (" ", "-", "_"):
        s = s.replace(ch, "")
    if len(s) > 3 and s.endswith("es"):
        s = s[:-2]
    elif len(s) > 3 and s.endswith("s"):
        s = s[:-1]
    return s

CSV_CANON_KEYS = ("canonical", "英文名", "標準名")

def load_csv_canons(csv_path: str) -> Tuple[List[str], List[Dict[str, str]]]:
    rows: List[Dict[str, str]] = []
    canons: List[str] = []
    with open(csv_path, "r", encoding="utf-8") as f:
        r = csv.DictReader(f)
        for row in r:
            rows.append(row)
            val = None
            for k in CSV_CANON_KEYS:
                if k in row and row[k]:
                    val = row[k]
                    break
            if val:
                canons.append(val)
    return canons, rows

def load_ontology(onto_path: str) -> List[Dict]:
    with open(onto_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, list):
        raise ValueError("food_ontology.json 須為 list[dict]")
    return data

def main():
    ap = argparse.ArgumentParser(description="Compare ontology canonical with foods_tw.csv")
    ap.add_argument("--csv",  default="backend/app/data/foods_tw.csv")
    ap.add_argument("--onto", default="backend/app/data/food_ontology.json")
    ap.add_argument("--emit-missing-template", default="backend/app/data/missing_from_csv_template.csv",
                    help="把 ontology 缺少於 CSV 的項目輸出成可補檔模板")
    args = ap.parse_args()

    csv_path  = os.path.abspath(args.csv)
    onto_path = os.path.abspath(args.onto)
    print(f"[path] CSV  : {csv_path}")
    print(f"[path] ONTO : {onto_path}")

    canons_csv_raw, csv_rows = load_csv_canons(csv_path)
    canons_csv_norm = [norm(c) for c in canons_csv_raw if c]

    onto = load_ontology(onto_path)
    canons_onto_raw = [it.get("canonical", "") for it in onto if isinstance(it, dict)]
    canons_onto_norm = [norm(c) for c in canons_onto_raw if c]

    # 重複檢查
    dup_csv  = [c for c, n in Counter(canons_csv_norm).items() if n > 1]
    dup_onto = [c for c, n in Counter(canons_onto_norm).items() if n > 1]

    # 差集
    not_in_csv  = sorted({c for c in canons_onto_norm if c and c not in set(canons_csv_norm)})
    not_in_onto = sorted({c for c in canons_csv_norm  if c and c not in set(canons_onto_norm)})

    print("\n=== 結果 Summary ===")
    print(f"CSV canonical 總數       : {len(canons_csv_raw)}")
    print(f"Ontology canonical 總數  : {len(canons_onto_raw)}")
    print(f"CSV 重複 (norm)          : {len(dup_csv)}")
    print(f"Ontology 重複 (norm)     : {len(dup_onto)}")
    print(f"Ontology 但 CSV 缺少     : {len(not_in_csv)}")
    print(f"CSV 但 Ontology 缺少     : {len(not_in_onto)}")

    if dup_csv:
        print("\n[CSV 重複]")
        for c in dup_csv:
            print(" -", c)
    if dup_onto:
        print("\n[Ontology 重複]")
        for c in dup_onto:
            print(" -", c)

    if not_in_csv:
        print("\n[Ontology 有、CSV 沒有]（建議補進 foods_tw.csv）")
        for c in not_in_csv:
            # 找回原字樣，方便人眼
            raw = next((r for r in canons_onto_raw if norm(r) == c), c)
            print(" -", raw)

        # 產生模板 CSV，便於一次補進去
        tpl_path = os.path.abspath(args.emit_missing_template)
        os.makedirs(os.path.dirname(tpl_path), exist_ok=True)
        with open(tpl_path, "w", encoding="utf-8", newline="") as f:
            w = csv.writer(f)
            w.writerow(["name","canonical","kcal","protein_g","fat_g","carb_g"])
            for c in not_in_csv:
                raw = next((r for r in canons_onto_raw if norm(r) == c), c)
                # 預留空值，讓你填寫實際營養
                w.writerow(["", raw, "", "", "", ""])
        print(f"\n→ 已輸出補檔模板：{tpl_path}")

    if not_in_onto:
        print("\n[CSV 有、Ontology 沒有]（可視需要補進 ontology）")
        # 把原 CSV 欄位回推出來，方便你複製貼上
        seen = set()
        for row in csv_rows:
            val = None
            for k in CSV_CANON_KEYS:
                if k in row and row[k]:
                    val = row[k]
                    break
            if not val:
                continue
            if norm(val) in set(not_in_onto) and norm(val) not in seen:
                seen.add(norm(val))
                print(f' - 建議 ontology 範例：{{"id":"auto_{norm(val)}","name_zh":"{row.get("name","")}",'
                      f'"name_en":"{val}","canonical":"{val}","aliases":[], "category":"未分類"}}')

if __name__ == "__main__":
    sys.exit(main())
