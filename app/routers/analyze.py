
from __future__ import annotations
import base64, logging
from typing import Any, Dict, List
from fastapi import APIRouter, UploadFile, File, HTTPException
from ..services.openai_client import vision_analyze_base64
from ..services import nutrition_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/analyze", tags=["analyze"])

def _ok(data=None): return {"status":"ok","reason":None,"debug":None,"data":data}

@router.post("/image")
async def analyze_image(file: UploadFile = File(...)):
    raw = await file.read()
    if not raw:
        raise HTTPException(400, "empty file")
    img_b64 = base64.b64encode(raw).decode("utf-8")

    try:
        items = await vision_analyze_base64(img_b64)  # list[dict]
    except Exception as e:
        logger.exception("vision_analyze_base64 failed")
        raise HTTPException(502, "Vision analysis failed") from e

    if not isinstance(items, list) or any(not isinstance(x, dict) for x in items):
        logger.error("items_not_list_of_dicts_after_vision: %r", items)
        return _ok({"items": [], "summary": {"totals": {"kcal": 0, "protein_g": 0, "fat_g": 0, "carb_g": 0}}})

    fixed: List[Dict[str, Any]] = []
    for it in items:
        name = str(it.get("name") or "").strip()
        canonical = str(it.get("canonical") or name).strip()
        try:
            weight_g = float(it.get("weight_g", 0) or 0)
        except Exception:
            weight_g = 0.0
        is_garnish = bool(it.get("is_garnish", False))
        fixed.append({"name": name, "canonical": canonical, "weight_g": weight_g, "is_garnish": is_garnish})

    try:
        enriched, totals = nutrition_service.calc(fixed)
    except Exception as e:
        logger.exception("nutrition calc failed")
        raise HTTPException(500, "Nutrition calculation failed") from e

    return _ok({"items": enriched, "summary": {"totals": totals}})
