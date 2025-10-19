# backend/app/routers/analyze.py
from __future__ import annotations
import base64
from fastapi import APIRouter, File, UploadFile, HTTPException
from fastapi.responses import JSONResponse
from app.services.openai_client import vision_analyze_base64
from app.services import nutrition_service as nutrition

router = APIRouter(prefix="/analyze", tags=["Analyze"])

@router.post("/image")
async def analyze_image(file: UploadFile = File(...)):
    raw = await file.read()
    img_b64 = base64.b64encode(raw).decode("utf-8")

    try:
        parsed = await vision_analyze_base64(img_b64)  # {"items":[...]}
    except Exception as e:
        # 轉 502，避免回 500 造成前端不易處理
        return JSONResponse({"error": str(e)}, status_code=502)

    try:
        enriched, totals = nutrition.calc(parsed.get("items", []), include_garnish=True)
    except Exception as e:
        raise HTTPException(status_code=500, detail="Nutrition calculation failed") from e

    return {"items": enriched, "summary": totals}
