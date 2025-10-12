from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from notion_client import Client
import os

router = APIRouter()

NOTION_API_KEY = os.getenv("NOTION_API_KEY")
NOTION_DATABASE_ID = os.getenv("NOTION_DATABASE_ID")

PROP_MAP = {
    "日期": "日期",
    "餐別": "餐別",
    "食物清單": "食物清單",
    "AI建議": "AI建議",
    "熱量估算": "熱量估算",
    "蛋白質(g)": "蛋白質(g)",
    "脂肪(g)": "脂肪(g)",
    "碳水(g)": "碳水(g)",
    "圖片連結": "圖片連結",
}
def P(name: str) -> str:
    return PROP_MAP.get(name, name)

class NotionLogItem(BaseModel):
    canonical: str
    weight_g: float
    kcal: float
    protein_g: float
    fat_g: float
    carb_g: float

class NotionLogRequest(BaseModel):
    date: str
    meal: str
    items: list[NotionLogItem]
    total: dict
    image_url: str | None = None
    notes: str | None = None

@router.post("/notion/log")
def notion_log(req: NotionLogRequest):
    if not NOTION_API_KEY or not NOTION_DATABASE_ID:
        raise HTTPException(status_code=500, detail="Notion 環境變數未設定")
    client = Client(auth=NOTION_API_KEY)
    items_text = "、".join([f"{x.canonical}：{int(x.weight_g)} g" for x in req.items])
    props = {
        P("日期"): {"date": {"start": req.date}},
        P("餐別"): {"select": {"name": req.meal}},
        P("熱量估算"): {"number": float(req.total.get("kcal", 0))},
        P("蛋白質(g)"): {"number": float(req.total.get("protein_g", 0))},
        P("脂肪(g)"): {"number": float(req.total.get("fat_g", 0))},
        P("碳水(g)"): {"number": float(req.total.get("carb_g", 0))},
        P("食物清單"): {"rich_text": [{"text": {"content": items_text}}]},
        P("AI建議"): {"rich_text": [{"text": {"content": req.notes or ""}}]},
    }
    if req.image_url:
        props[P("圖片連結")] = {"url": req.image_url}
    try:
        res = client.pages.create(parent={"database_id": NOTION_DATABASE_ID}, properties=props)
        return {"success": True, "page_id": res.get("id")}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Notion 寫入失敗: {e}")