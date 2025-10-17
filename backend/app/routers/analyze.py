# backend/app/routers/analyze.py
from __future__ import annotations

import base64
import json
from typing import Any, Dict, List
from fastapi import APIRouter, UploadFile, File, HTTPException

from ..services.openai_client import vision_analyze_base64
from ..services import nutrition_service

router = APIRouter(prefix="/analyze", tags=["analyze"])

def _ok(data=None) -> Dict[str, Any]:
    return {"status": "ok", "reason": None, "debug": None, "data": data}

@router.post("/image")
async def analyze_image(file: UploadFile = File(...)):
    # 1) 讀入檔案、轉 base64
    raw = await file.read()
    img_b64 = base64.b64encode(raw).decode("utf-8")

    # 2) 叫 OpenAI Vision
    try:
        items = await vision_analyze_base64(img_b64)  # list[dict]
    except RuntimeError as e:
        msg = str(e)
        # 將供應商/後端暫時性問題回 503，前端可友善提示
        if msg.startswith("openai_http_"):
            code = int(msg.split("_")[-1]) if msg.split("_")[-1].isdigit() else 500
            if code >= 500:
                raise HTTPException(status_code=503, detail="Vision service temporarily unavailable")
        # 其它錯誤
        raise HTTPException(status_code=502, detail="Vision analysis failed")

    # 3) 容錯：有些模型回字串（已在 client 解析），但仍保險檢查
    if isinstance(items, str):
        try:
            items = json.loads(items)
        except Exception:
            items = []

    if not isinstance(items, list):
        items = []

    # 4) 計算營養（即使空陣列也回合法格式）
    try:
        enriched, totals = nutrition_service.calc(items)
    except Exception:
        # 任何計算失敗，回空值避免 500
        enriched = []
        totals = {"kcal": 0, "protein_g": 0, "fat_g": 0, "carb_g": 0}

    # 5) 回傳
    return _ok({"items": enriched, "summary": {"totals": totals}})
