import os
from typing import Dict, Any
from notion_client import Client

NOTION_API_KEY = os.getenv("NOTION_API_KEY")
NOTION_DATABASE_ID = os.getenv("NOTION_DATABASE_ID")

def create_food_log(payload: Dict[str, Any]) -> Dict[str, Any]:
    if not NOTION_API_KEY or not NOTION_DATABASE_ID:
        return {"ok": False, "error": "Missing NOTION_API_KEY or NOTION_DATABASE_ID"}
    client = Client(auth=NOTION_API_KEY)

    items_text = "\n".join([
        f"- {it.get('name')} {it.get('grams','?')}g（{it.get('kcal','-')}kcal / P{it.get('protein_g','-')}/F{it.get('fat_g','-')}/C{it.get('carb_g','-')}）"
        for it in payload.get("items", [])
    ])
    totals = payload.get("totals", {})
    notes = payload.get("notes", "")

    props = {
        "日期": {"date": {"start": payload.get("date")}},
        "餐別": {"select": {"name": payload.get("meal", "未分類")}},
        "熱量估算": {"number": totals.get("kcal")},
        "蛋白質(g)": {"number": totals.get("protein_g")},
        "脂肪(g)": {"number": totals.get("fat_g")},
        "碳水(g)": {"number": totals.get("carb_g")},
        "食物清單": {"rich_text": [{"text": {"content": items_text[:1900]}}]},
        "AI建議": {"rich_text": [{"text": {"content": notes[:1900]}}]},
        "圖片連結": {"url": payload.get("image_url")},
    }

    res = client.pages.create(parent={"database_id": NOTION_DATABASE_ID}, properties=props)
    return {"ok": True, "notion_page_id": res.get("id")}
