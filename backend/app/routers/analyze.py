# backend/app/routers/analyze.py
from __future__ import annotations

import base64
from fastapi import APIRouter, UploadFile, File
from ..services.openai_client import vision_analyze_base64
from ..services import nutrition_service

router = APIRouter(prefix="/analyze", tags=["analyze"])

def _ok(data=None):
    return {"status": "ok", "reason": None, "debug": None, "data": data}

@router.post("/image")
async def analyze_image(file: UploadFile = File(...)):
    # 1) 讀檔 -> base64
    raw = await file.read()
    img_b64 = base64.b64encode(raw).decode("utf-8")

    # 2) Vision 辨識 -> items: [{name, canonical?, weight_g, ...}, ...]
    vision_res = await vision_analyze_base64(img_b64)
    # 視你的 openai_client 回傳結構而定，這裡假設結果在 vision_res["items"]
    items = vision_res.get("items") if isinstance(vision_res, dict) else vision_res

    if not items:
        # 仍回 ok，但給空結果，前端會顯示建議
        return _ok({"items": [], "summary": {"totals": {"kcal": 0, "protein_g": 0, "fat_g": 0, "carb_g": 0}}})

    # 3) 計算營養值（依 weight_g 換算）
    enriched, totals = nutrition_service.calc(items)

    # 4) 回傳：每項帶 kcal/P/F/C，並附 summary
    return _ok({"items": enriched, "summary": {"totals": totals}})
