# backend/app/routers/analyze.py（節錄：/analyze/image handler 內的關鍵段落）
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from app.services.openai_client import vision_analyze_base64
from app.services.nutrition_service_v2 import analyze_and_calc

router = APIRouter()

class ImageReq(BaseModel):
    image_b64: str

@router.post("/image")
async def analyze_image(req: ImageReq):
    vis = vision_analyze_base64(req.image_b64)

    # 可能包含 reason/raw，方便你在 Network 面板看
    items = vis.get("items") or []
    reason = vis.get("reason")

    if not items and reason:
        # 直接回傳可見的錯誤資訊（前端可顯示「請重新拍攝」的建議）
        return {"items": [], "totals": {"kcal": 0, "protein_g": 0, "fat_g": 0, "carb_g": 0}, "reason": reason}

    enriched, totals = analyze_and_calc(items, include_garnish=True)
    return {"items": enriched, "totals": totals}
