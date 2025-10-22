# backend/app/routers/analyze.py
from __future__ import annotations
import os
import uuid
import base64
from fastapi import APIRouter, File, UploadFile
from fastapi.responses import JSONResponse

from app.services.openai_client import vision_analyze_base64
from app.services import nutrition_service_v2 as nutrition  # ← 用 v2
from fastapi import HTTPException

router = APIRouter(prefix="/analyze", tags=["Analyze"])

# 將檔案存在 backend/app/uploads
UPLOAD_DIR = os.path.join(os.path.dirname(__file__), "..", "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

BASE_URL = os.getenv("BASE_URL", "https://eatlyze-backend.onrender.com")

def _ok(data=None):
    return {"status": "ok", "data": data, "reason": None, "debug": None}

@router.post("/image")
async def analyze_image(file: UploadFile = File(...)):
    # 讀檔
    raw = await file.read()

    # 存檔供前端預覽
    filename = f"{uuid.uuid4().hex}.jpg"
    path = os.path.join(UPLOAD_DIR, filename)
    with open(path, "wb") as f:
        f.write(raw)
    image_url = f"{BASE_URL}/image/{filename}"

    # Vision
    img_b64 = base64.b64encode(raw).decode("utf-8")
    parsed = await vision_analyze_base64(img_b64)  # 永遠回 dict，至少有 items

    items = parsed.get("items", [])
    # 營養計算（不中斷）
    try:
        enriched, totals = nutrition.calc(items, include_garnish=False)
    except Exception as e:
        # 萬一 CSV/程式有狀況，也不要 500
        enriched, totals = [], {"kcal": 0.0, "protein_g": 0.0, "fat_g": 0.0, "carb_g": 0.0}
        print(f"[analyze] nutrition calc error: {e}")

    # 回 200，不要 502
    return _ok({
        "image_url": image_url,
        "items": enriched,
        "summary": totals,
        "vision_error": parsed.get("error"),
    })
