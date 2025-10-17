# backend/app/routers/analyze.py
from __future__ import annotations
import base64, json, logging
from fastapi import APIRouter, UploadFile, File, HTTPException

from ..services.openai_client import vision_analyze_base64
from ..services import nutrition_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/analyze", tags=["analyze"])

def _ok(data=None):
    return {"status": "ok", "reason": None, "debug": None, "data": data}

@router.post("/image")
async def analyze_image(file: UploadFile = File(...)):
    raw = await file.read()
    img_b64 = base64.b64encode(raw).decode("utf-8")

    try:
        parsed = await vision_analyze_base64(img_b64)  # {"items":[...]}
        items = parsed.get("items", [])
    except Exception as e:
        logger.exception("vision_analyze_base64 failed")
        raise HTTPException(status_code=502, detail="Vision analysis failed")

    if not isinstance(items, list):
        raise HTTPException(status_code=400, detail="Vision did not return an items list")

    # 計算營養
    try:
        enriched, totals = nutrition_service.calc(items)
    except Exception:
        logger.exception("nutrition calc failed")
        raise HTTPException(status_code=500, detail="Nutrition calculation failed")

    return _ok({"items": enriched, "summary": {"totals": totals}})
