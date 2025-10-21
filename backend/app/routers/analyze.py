# backend/app/routers/analyze.py
from __future__ import annotations

import base64
from fastapi import APIRouter, File, UploadFile
from fastapi.responses import JSONResponse

from app.services.openai_client import vision_analyze_base64
from app.services import nutrition_service_v2 as nutrition
from app.services.storage import store_image_and_get_url

router = APIRouter(prefix="/analyze", tags=["Analyze"])


@router.post("/image")
async def analyze_image(file: UploadFile = File(...)):
    # 讀入原始 bytes
    raw = await file.read()

    # 存檔取可公開 URL
    image_url = store_image_and_get_url(raw, file.filename)

    # 轉 base64 給 Vision
    img_b64 = base64.b64encode(raw).decode("utf-8")

    try:
        # Vision -> {"items":[...]}
        parsed = await vision_analyze_base64(img_b64)
    except Exception as e:
        # 失敗時仍回傳 image_url，前端可以顯示照片
        return JSONResponse(
            {"error": f"vision failed: {e}", "image_url": image_url, "items": [], "summary": {"kcal": 0, "protein_g": 0, "fat_g": 0, "carb_g": 0}},
            status_code=502,
        )

    # 營養計算（不將「配菜/裝飾」計算入內）
    enriched, totals = nutrition.calc(parsed.get("items", []), include_garnish=False)

    return {
        "image_url": image_url,
        "items": enriched,
        "summary": totals,
    }
