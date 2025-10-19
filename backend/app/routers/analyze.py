# backend/app/routers/analyze.py
from __future__ import annotations

import os
import uuid
import base64
import logging
from asyncio import Semaphore

from fastapi import APIRouter, File, UploadFile
from fastapi.responses import JSONResponse

from app.services.openai_client import vision_analyze_base64
from app.services import nutrition_service as nutrition

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/analyze", tags=["Analyze"])

# ---- 併發限流：同一實例同時只跑 1 個 Vision 請求 ----
_limiter = Semaphore(1)

# ---- 檔案儲存與對外 URL ----
BASE_URL = os.getenv("BASE_URL", "https://eatlyze-backend.onrender.com")
UPLOAD_DIR = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "uploads"))
os.makedirs(UPLOAD_DIR, exist_ok=True)


@router.post("/image")
async def analyze_image(file: UploadFile = File(...)):
    # 將所有邏輯包在 limiter 內，避免同時觸發 429
    async with _limiter:
        # 1) 讀取原始檔案 bytes
        raw = await file.read()

        # 2) 先存檔（供前端 <img src> 使用）
        filename = f"{uuid.uuid4().hex}_{file.filename}"
        filepath = os.path.join(UPLOAD_DIR, filename)
        try:
            with open(filepath, "wb") as f:
                f.write(raw)
        except Exception as e:
            logger.exception("save_upload_failed")
            return JSONResponse({"error": f"save upload failed: {e}"}, status_code=500)

        image_url = f"{BASE_URL}/image/{filename}"

        # 3) 轉 base64 給 Vision
        img_b64 = base64.b64encode(raw).decode("utf-8")

        # 4) 呼叫 Vision（內部已有 retry / JSON 清洗）
        try:
            parsed = await vision_analyze_base64(img_b64)  # 預期 {"items":[...]}
        except Exception as e:
            logger.exception("vision_analyze_base64 failed")
            return JSONResponse({"error": "Vision analysis failed", "detail": str(e)}, status_code=502)

        # 5) 取出 items 並計算營養（不含 garnish）
        items = []
        if isinstance(parsed, dict):
            items = parsed.get("items") or parsed.get("data", {}).get("items") or []

        logger.info("[analyze] vision parsed items (len=%s): %s", len(items) if items else 0, items)

        try:
            enriched, totals = nutrition.calc(items or [], include_garnish=True)
        except Exception as e:
            logger.exception("nutrition calc failed")
            return JSONResponse({"error": "Nutrition calculation failed", "detail": str(e)}, status_code=500)

        logger.info("[analyze] nutrition totals: %s", totals)

        # 6) 回傳前端期望的扁平格式（image_url / items / summary）
        return {
            "image_url": image_url,
            "items": enriched,
            "summary": totals,
        }
