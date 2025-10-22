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


def _strip_data_url_prefix(b64: str) -> str:
    """移除 data:image/...;base64, 前綴"""
    if not b64:
        return b64
    s = b64.strip()
    if "base64," in s:
        return s.split("base64,", 1)[-1].strip()
    if s.startswith("data:") and "," in s:
        return s.split(",", 1)[-1].strip()
    return s


async def _parse_image_b64(request: Request) -> Tuple[str, bool]:
    """容錯解析圖片 base64"""
    ct = (request.headers.get("content-type") or "").lower()
    include_garnish = False

    # JSON
    if "application/json" in ct:
        try:
            data = await request.json()
            if isinstance(data, dict):
                include_garnish = bool(
                    data.get("include_garnish")
                    or data.get("includeGarnish")
                    or False
                )
                b64 = (
                    data.get("image_base64")
                    or data.get("imageBase64")
                    or data.get("image_b64")
                    or data.get("imageB64")
                    or ""
                )
                if isinstance(b64, bytes):
                    b64 = b64.decode("utf-8", errors="ignore")
                return _strip_data_url_prefix(b64 or ""), include_garnish
        except Exception:
            pass

    # multipart/form-data
    if "multipart/form-data" in ct:
        try:
            form = await request.form()

            ig_val = form.get("include_garnish") or form.get("includeGarnish")
            if isinstance(ig_val, str):
                include_garnish = ig_val.lower() in ("1", "true", "yes", "y", "on")
            elif ig_val is not None:
                include_garnish = bool(ig_val)

            upload = form.get("file") or form.get("image")
            if upload is not None and hasattr(upload, "read"):
                content: bytes = await upload.read()
                return base64.b64encode(content).decode("ascii"), include_garnish

            b64 = (
                form.get("image_base64")
                or form.get("imageBase64")
                or form.get("image_b64")
                or form.get("imageB64")
                or ""
            )
            if isinstance(b64, bytes):
                b64 = b64.decode("utf-8", errors="ignore")
            return _strip_data_url_prefix(b64 or ""), include_garnish
        except Exception:
            pass

    # raw bytes
    try:
        raw = await request.body()
        if not raw:
            return "", include_garnish
        try:
            text = raw.decode("utf-8", errors="ignore").strip()
            if (text.startswith("data:") and "," in text) or len(text) > 32:
                return _strip_data_url_prefix(text), include_garnish
        except Exception:
            pass
        return base64.b64encode(raw).decode("ascii"), include_garnish
    except Exception:
        return "", include_garnish


@router.get("/ping")
async def ping():
    return {"ok": True, "route": "/analyze/image"}


@router.post("/image")
async def analyze_image(request: Request) -> JSONResponse:
    payload = _empty_payload()

    try:
        image_b64, include_garnish = await _parse_image_b64(request)
        if not image_b64:
            payload["error"] = "no_image"
            return JSONResponse(payload, status_code=200)

        # === Step 1. 視覺辨識 ===
        try:
            detected_result = vision_analyze_base64(image_b64)
            print("[DEBUG] Vision output:", detected_result)  # ← 加上 debug log

            detected_items = (
                detected_result.get("items", [])
                if isinstance(detected_result, dict)
                else []
            )
            if not detected_items:
                payload["error"] = "no_items_detected"
        except Exception as e:
            detected_items = []
            payload["error"] = f"vision_error:{type(e).__name__}"

        # === Step 2. 營養計算 ===
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
