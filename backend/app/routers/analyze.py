# backend/app/routers/analyze.py
from __future__ import annotations

import base64
from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse

# 視覺辨識與營養計算
from app.services.openai_client import vision_analyze_base64
try:
    from app.services import nutrition_service_v2 as nutrition
except Exception:
    from app.services import nutrition_service as nutrition  # 後備

router = APIRouter()


@router.get("/ping")
def ping():
    return {"pong": True}


def _run_pipeline(b64: str) -> Dict[str, Any]:
    """將 base64 圖片丟給視覺→比對→加總，回傳 {items, totals}"""
    try:
        result = vision_analyze_base64(b64)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"vision error: {e}")

    items: List[Dict[str, Any]] = result.get("items") or []
    try:
        enriched_items, totals = nutrition.calc(items, include_garnish=False)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"nutrition error: {e}")
    return {"items": enriched_items, "totals": totals}


@router.post("/image")
async def analyze_image(request: Request):
    """
    單一路徑同時支援：
      - application/json  : {"image_base64": "..."} 或 {"image_b64": "..."}
      - multipart/form-data: 欄位名 "file" (UploadFile)
    """
    ctype = (request.headers.get("content-type") or "").lower()

    # --- JSON 路徑 ---
    if "application/json" in ctype:
        try:
            body = await request.json()
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid JSON body")

        b64 = body.get("image_base64") or body.get("image_b64")
        if not b64 or not isinstance(b64, str):
            raise HTTPException(status_code=422, detail="image_base64 (or image_b64) is required")
        return _run_pipeline(b64)

    # --- Multipart 路徑 ---
    if "multipart/form-data" in ctype:
        form = await request.form()
        up = form.get("file")
        if up is None:
            raise HTTPException(status_code=422, detail="file is required in multipart form")
        try:
            data = await up.read()  # type: ignore[attr-defined]
        except Exception:
            raise HTTPException(status_code=400, detail="unable to read uploaded file")
        b64 = base64.b64encode(data).decode("ascii")
        return _run_pipeline(b64)

    # 其它格式
    return JSONResponse(
        {"error": "Unsupported Content-Type. Use application/json or multipart/form-data."},
        status_code=415,
    )
