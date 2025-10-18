# backend/app/routers/analyze.py
from __future__ import annotations
import base64
from fastapi import APIRouter, File, UploadFile
from fastapi.responses import JSONResponse

from app.services.openai_client import vision_analyze_base64
from app.services import nutrition_service as nutrition
from app.services.storage import store_image_and_get_url  # ← 新增

router = APIRouter(prefix="/analyze", tags=["Analyze"])


@router.post("/image")
async def analyze_image(file: UploadFile = File(...)):
    # 讀原始 bytes
    raw = await file.read()
    # 先把圖片放到你選的儲存（R2 / Imgur / Local），拿到可公開的 URL
    image_url = store_image_and_get_url(raw, file.filename)

    # Base64 丟 Vision
    img_b64 = base64.b64encode(raw).decode("utf-8")

    try:
        parsed = await vision_analyze_base64(img_b64)  # {"items":[...]}
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)

    enriched, totals = nutrition.calc(parsed.get("items", []), include_garnish=False)

    return {
        "image_url": image_url,
        "items": enriched,
        "summary": totals,
    }
