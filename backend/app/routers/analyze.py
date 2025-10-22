# backend/app/routers/analyze.py
from __future__ import annotations

import base64
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, UploadFile, File, Form, Body
from pydantic import BaseModel

# 你的視覺辨識與營養計算模組
# - 若你只有 v1，請把下一行改成：from app.services import nutrition_service as nutrition
from app.services.openai_client import vision_analyze_base64
try:
    from app.services import nutrition_service_v2 as nutrition
except Exception:
    from app.services import nutrition_service as nutrition  # 後備

router = APIRouter()


# --------- 請求/回應模型 ---------
class AnalyzeImageJSON(BaseModel):
    image_base64: Optional[str] = None  # 建議前端傳這個欄位
    image_b64: Optional[str] = None     # 也接受舊欄位名稱
    # 其它你要傳給模型的選項可加在這裡（如：lang, topk...）


class AnalyzeResult(BaseModel):
    items: List[Dict[str, Any]]
    totals: Dict[str, Any]


@router.get("/ping")
def ping():
    return {"pong": True}


# 1) JSON 版：POST /analyze/image
#    允許 body 傳 image_base64 / image_b64
@router.post("/image", response_model=AnalyzeResult)
def analyze_image_json(payload: AnalyzeImageJSON = Body(...)) -> AnalyzeResult:
    b64 = payload.image_base64 or payload.image_b64
    if not b64:
        raise HTTPException(status_code=422, detail="image_base64 (or image_b64) is required")

    # 呼叫視覺模型拿到辨識結果（食材列表）
    try:
        result = vision_analyze_base64(b64)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"vision error: {e}")

    items = result.get("items") or []

    # 丟給營養模組做對齊與加總
    try:
        enriched_items, totals = nutrition.calc(items, include_garnish=False)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"nutrition error: {e}")

    return AnalyzeResult(items=enriched_items, totals=totals)


# 2) Multipart 版：POST /analyze/image-multipart
#    前端用 <input type="file"> 上傳圖片會走這個
@router.post("/image-multipart", response_model=AnalyzeResult)
async def analyze_image_multipart(file: UploadFile = File(...)) -> AnalyzeResult:
    # 讀檔並轉 base64
    data = await file.read()
    b64 = base64.b64encode(data).decode("utf-8")

    try:
        result = vision_analyze_base64(b64)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"vision error: {e}")

    items = result.get("items") or []

    try:
        enriched_items, totals = nutrition.calc(items, include_garnish=False)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"nutrition error: {e}")

    return AnalyzeResult(items=enriched_items, totals=totals)
