# backend/app/routers/analyze.py
from __future__ import annotations

import base64
from typing import Any, Dict

from fastapi import APIRouter, HTTPException, Request, UploadFile, File
from app.services.openai_client import vision_analyze_base64
from app.services import nutrition_service_v2 as nutrition

router = APIRouter(prefix="/analyze", tags=["analyze"])


def _ensure_b64(s: Any) -> str:
    """
    將輸入統一轉成 base64 (str)：
    - 若是 str：回傳去除 dataURL 前綴的字串
    - 若是 bytes/bytearray：直接 b64encode
    """
    if s is None:
        raise HTTPException(status_code=422, detail="image_b64 is required")

    # bytes / bytearray 直接轉 base64
    if isinstance(s, (bytes, bytearray)):
        return base64.b64encode(s).decode("ascii")

    if not isinstance(s, str):
        raise HTTPException(status_code=422, detail="image_b64 must be base64 string or bytes")

    # 去 dataURL prefix
    if s.startswith("data:image"):
        # 例如 data:image/jpeg;base64,xxxxx
        try:
            return s.split(",", 1)[1]
        except Exception:
            # split 失敗就當一般 base64 用
            return s
    return s


@router.post("/image")
async def analyze_image(
    request: Request,
    file: UploadFile | None = File(default=None),
):
    """
    同時支援兩種輸入：
    1) JSON: {"image_b64": "<base64字串或原始bytes>"}
    2) multipart/form-data: file=<影像檔>
    """
    # 1) multipart 檔案
    b64: str | None = None
    if file is not None:
        raw = await file.read()
        b64 = _ensure_b64(raw)
    else:
        # 2) JSON
        try:
            payload: Dict[str, Any] = await request.json()
        except Exception:
            raise HTTPException(status_code=400, detail="Expect JSON body or multipart file upload.")
        b64 = _ensure_b64(payload.get("image_b64"))

    try:
        # 視覺模型 → 取得 ingredients（name/canonical/weight_g/is_garnish）
        parsed = await vision_analyze_base64(b64)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"vision analyze failed: {e}")

    # 送去營養結算（會做 alias/exact/fuzzy/ontology 展開）
    items = parsed.get("items") or []
    try:
        enriched, totals = nutrition.calc(items, include_garnish=False)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"nutrition calc failed: {e}")

    return {
        "items": enriched,
        "totals": totals,
    }
