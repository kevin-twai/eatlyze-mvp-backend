# backend/app/routers/analyze.py
from __future__ import annotations

from typing import List, Optional
from pydantic import BaseModel
from fastapi import APIRouter, HTTPException

from app.services.openai_client import vision_analyze_base64
from app.services import nutrition_service_v2 as nutrition

router = APIRouter(prefix="", tags=["analyze"])


class AnalyzeImageReq(BaseModel):
    image_b64: str  # data:image/jpeg;base64,.... 或純 base64


class AnalyzeItem(BaseModel):
    name: Optional[str] = None
    canonical: Optional[str] = None
    weight_g: float = 0.0
    is_garnish: bool = False


class AnalyzeResp(BaseModel):
    items: List[AnalyzeItem]
    totals: dict


@router.post("/analyze/image", response_model=AnalyzeResp)
async def analyze_image(req: AnalyzeImageReq):
    """
    1) 用 Vision 從圖片抓食材 (name/canonical/weight_g/is_garnish)
    2) 丟給營養計算：這裡預設 include_garnish=True（把配菜也算進去）
    """
    try:
        vision = await vision_analyze_base64(req.image_b64)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Vision analyze failed: {e}")

    items = vision.get("items") or []
    enriched, totals = nutrition.calc(items, include_garnish=True)

    # 轉型到 Pydantic
    items_out = [AnalyzeItem(**it) for it in enriched]
    return AnalyzeResp(items=items_out, totals=totals)
