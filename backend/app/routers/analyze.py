# backend/app/routers/analyze.py
from __future__ import annotations

import base64
from typing import Any, Dict, Tuple

from fastapi import APIRouter, Request
from starlette.responses import JSONResponse

from app.services.openai_client import vision_analyze_base64
from app.services import nutrition_service_v2 as nutrition

router = APIRouter(prefix="/analyze", tags=["analyze"])


def _empty_payload() -> Dict[str, Any]:
    return {
        "items": [],
        "totals": {"kcal": 0.0, "protein_g": 0.0, "fat_g": 0.0, "carb_g": 0.0},
        "error": None,
    }


async def _parse_image_b64(request: Request) -> Tuple[str, bool]:
    """
    盡量容錯地把請求體轉成 base64 字串，並回傳 include_garnish。
    支援 JSON、multipart/form-data、octet-stream/raw。
    """
    ct = (request.headers.get("content-type") or "").lower()
    include_garnish = False

    # 1) JSON
    if "application/json" in ct:
        try:
            data = await request.json()
            if isinstance(data, dict):
                include_garnish = bool(
                    data.get("include_garnish")
                    or data.get("includeGarnish")
                    or False
                )
                b64 = data.get("image_base64") or data.get("imageBase64") or ""
                if isinstance(b64, bytes):
                    # 若是 bytes 就直接當作已是 base64 的 bytes
                    b64 = b64.decode("utf-8", errors="ignore")
                return (b64 or "").strip(), include_garnish
        except Exception:
            pass  # fallthrough to raw parsing

    # 2) multipart/form-data
    if "multipart/form-data" in ct:
        try:
            form = await request.form()
            # 常見欄位名：file / image
            upload = form.get("file") or form.get("image")
            if upload is not None and hasattr(upload, "read"):
                content: bytes = await upload.read()
                return base64.b64encode(content).decode("ascii"), include_garnish

            # 也支援直接傳 image_base64 欄位
            b64 = form.get("image_base64") or form.get("imageBase64") or ""
            if isinstance(b64, bytes):
                b64 = b64.decode("utf-8", errors="ignore")
            return (b64 or "").strip(), include_garnish
        except Exception:
            pass  # fallthrough to raw parsing

    # 3) 其他（octet-stream 或 raw）
    try:
        raw = await request.body()  # bytes
        if not raw:
            return "", include_garnish
        # 嘗試把 bytes 解成文字（若本來就是 base64 字串）
        try:
            text = raw.decode("utf-8")
            # 粗略判斷是否像 base64
            if any(k in text for k in ("data:image", "/", "+")) and len(text) > 16:
                return text.strip(), include_garnish
        except Exception:
            pass
        # 直接把二進位轉 base64
        return base64.b64encode(raw).decode("ascii"), include_garnish
    except Exception:
        return "", include_garnish


@router.post("/image")
async def analyze_image(request: Request) -> JSONResponse:
    payload = _empty_payload()

    try:
        image_b64, include_garnish = await _parse_image_b64(request)
        if not image_b64:
            payload["error"] = "no_image"
            return JSONResponse(payload, status_code=200)

        # 1) 視覺辨識（容錯）
        try:
            detected_items = await vision_analyze_base64(image_b64)
        except Exception as e:
            detected_items = []
            payload["error"] = f"vision_error:{type(e).__name__}"

        # 2) 營養計算
        try:
            enriched, totals = nutrition.calc(
                detected_items, include_garnish=include_garnish
            )
            payload["items"] = enriched
            payload["totals"] = totals
            return JSONResponse(payload, status_code=200)
        except Exception as e:
            payload["error"] = f"nutrition_error:{type(e).__name__}"
            return JSONResponse(payload, status_code=200)

    except Exception as e:
        payload["error"] = f"fatal:{type(e).__name__}"
        return JSONResponse(payload, status_code=200)
