# backend/app/routers/analyze.py
from __future__ import annotations
import os
import base64
import uuid
from fastapi import APIRouter, File, UploadFile
from fastapi.responses import JSONResponse

from app.services.openai_client import vision_analyze_base64
from app.services import nutrition_service as nutrition

router = APIRouter(prefix="/analyze", tags=["Analyze"])

BASE_URL = os.getenv("BASE_URL", "https://eatlyze-backend.onrender.com")
UPLOAD_DIR = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "uploads"))
os.makedirs(UPLOAD_DIR, exist_ok=True)

@router.post("/image")
async def analyze_image(file: UploadFile = File(...)):
    raw = await file.read()

    # 存到本機 uploads 供前端 <img> 顯示
    filename = f"{uuid.uuid4().hex}_{file.filename}"
    filepath = os.path.join(UPLOAD_DIR, filename)
    with open(filepath, "wb") as f:
        f.write(raw)
    image_url = f"{BASE_URL}/image/{filename}"

    # Vision 分析
    img_b64 = base64.b64encode(raw).decode("utf-8")
    try:
        parsed = await vision_analyze_base64(img_b64)  # {"items":[{"name":...}]}
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)

    # 強化：預設包含配料（避免全部被過濾掉）
    enriched, totals = nutrition.calc(parsed.get("items", []), include_garnish=True)

    return {"image_url": image_url, "items": enriched, "summary": totals}
