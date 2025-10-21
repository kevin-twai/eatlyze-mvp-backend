# backend/app/routers/analyze.py
from __future__ import annotations

from fastapi import APIRouter, UploadFile, File, HTTPException
from fastapi.responses import JSONResponse
from app.services.openai_client import vision_analyze_base64
from app.services import nutrition_service_v2 as nutrition  # ⬅ 使用 v2
import base64

router = APIRouter(prefix="/analyze", tags=["analyze"])

# 略保守的配菜忽略門檻（g）
GARNISH_IGNORE_GRAMS = 5

def _should_force_include(item: dict) -> bool:
    """重量 >= 門檻就一定納入計算（即使被標記 is_garnish）"""
    try:
        w = float(item.get("weight_g", 0) or 0)
    except Exception:
        w = 0.0
    return w >= GARNISH_IGNORE_GRAMS

@router.post("/image")
async def analyze_image(file: UploadFile = File(...)):
    try:
        b = await file.read()
        img_b64 = base64.b64encode(b).decode("utf-8")
    except Exception:
        raise HTTPException(status_code=400, detail="上傳檔案無法讀取")

    # 1) 先用 Vision 取得辨識項目
    try:
        parsed = await vision_analyze_base64(img_b64)  # 預期 {"items":[...]}
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Vision 失敗: {e}")

    items = parsed.get("items") or []
    if not isinstance(items, list):
        items = []

    # 2) 預處理：重量足夠的配菜強制納入；其餘照原樣
    normalized = []
    for it in items:
        it = dict(it or {})
        if _should_force_include(it):
            it["is_garnish"] = False
        normalized.append(it)

    # 3) 計算營養（關鍵：直接把 include_garnish 設成 True）
    enriched, totals = nutrition.calc(normalized, include_garnish=True)

    return JSONResponse({"items": enriched, "summary": totals})
