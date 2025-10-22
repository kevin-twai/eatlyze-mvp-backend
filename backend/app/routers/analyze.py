# backend/app/routers/analyze.py
from __future__ import annotations

import base64
from typing import Any, Dict, Tuple

from fastapi import APIRouter, Request
from starlette.responses import JSONResponse

# 注意：vision_analyze_base64 是「同步」函式，不要 await
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
    """
    剝掉 data URL 前綴，例如：
    data:image/jpeg;base64,/9j/4AAQSk... -> /9j/4AAQSk...
    """
    if not b64:
        return b64
    s = b64.strip()
    if "base64," in s:
        return s.split("base64,", 1)[-1].strip()
    if s.startswith("data:") and "," in s:
        return s.split(",", 1)[-1].strip()
    return s


async def _parse_image_b64(request: Request) -> Tuple[str, bool]:
    """
    盡量容錯地把請求體轉成 base64 字串，並回傳 include_garnish。
    支援 JSON、multipart/form-data、octet-stream/raw。
    """
    ct = (request.headers.get("content-type") or "").lower()
    include_garnish = False
    print(f"[DEBUG] Content-Type: {ct}")

    # 1) JSON
    if "application/json" in ct:
        try:
            data = await request.json()
            print(f"[DEBUG] JSON keys: {list(data.keys()) if isinstance(data, dict) else type(data)}")
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
                b64 = _strip_data_url_prefix(b64 or "")
                return b64, include_garnish
        except Exception as e:
            print(f"[WARN] JSON parse failed: {type(e).__name__}: {e}")

    # 2) multipart/form-data
    if "multipart/form-data" in ct:
        try:
            form = await request.form()
            print(f"[DEBUG] multipart fields: {list(form.keys())}")

            ig_val = form.get("include_garnish") or form.get("includeGarnish")
            if isinstance(ig_val, str):
                include_garnish = ig_val.lower() in ("1", "true", "yes", "y", "on")
            elif ig_val is not None:
                include_garnish = bool(ig_val)

            # 常見檔案欄位：file / image
            upload = form.get("file") or form.get("image")
            if upload is not None and hasattr(upload, "read"):
                content: bytes = await upload.read()
                print(f"[DEBUG] multipart binary size: {len(content)}")
                return base64.b64encode(content).decode("ascii"), include_garnish

            # 也支援直接 base64 欄位
            b64 = (
                form.get("image_base64")
                or form.get("imageBase64")
                or form.get("image_b64")
                or form.get("imageB64")
                or ""
            )
            if isinstance(b64, bytes):
                b64 = b64.decode("utf-8", errors="ignore")
            b64 = _strip_data_url_prefix(b64 or "")
            print(f"[DEBUG] multipart base64 length: {len(b64)}")
            return b64, include_garnish
        except Exception as e:
            print(f"[WARN] multipart parse failed: {type(e).__name__}: {e}")

    # 3) 其他（octet-stream 或 raw）
    try:
        raw = await request.body()  # bytes
        if not raw:
            print("[DEBUG] raw body empty")
            return "", include_garnish

        # 嘗試把 bytes 解成文字（若本來就是 base64 字串或 data-url）
        text = b""
        try:
            text = raw.decode("utf-8", errors="ignore").strip()
        except Exception:
            text = b""

        if isinstance(text, str) and text:
            looks_like_b64 = (text.startswith("data:") and "," in text) or len(text) > 32
            print(f"[DEBUG] raw->text len={len(text)}, looks_like_b64={looks_like_b64}")
            if looks_like_b64:
                return _strip_data_url_prefix(text), include_garnish

        # 直接把二進位轉 base64
        print(f"[DEBUG] raw binary size: {len(raw)}")
        return base64.b64encode(raw).decode("ascii"), include_garnish

    except Exception as e:
        print(f"[WARN] body read failed: {type(e).__name__}: {e}")
        return "", include_garnish


@router.get("/ping")
async def ping():
    return {"ok": True, "route": "/analyze/image"}


@router.post("/image")
async def analyze_image(request: Request) -> JSONResponse:
    print("=== /analyze/image called ===")
    payload = _empty_payload()

    try:
        image_b64, include_garnish = await _parse_image_b64(request)
        print(f"[DEBUG] base64 length after parse: {len(image_b64)} ; include_garnish={include_garnish}")
        if not image_b64:
            payload["error"] = "no_image"
            return JSONResponse(payload, status_code=200)

        # 1) 視覺辨識（同步呼叫）
        try:
            result = vision_analyze_base64(image_b64)  # returns dict: {items, model, error}
            print(f"[DEBUG] Vision model: {result.get('model')}, error: {result.get('error')}")
            print(f"[DEBUG] Vision items: {result.get('items')}")
            detected_items = result.get("items") or []
            if result.get("error"):
                payload["error"] = f"vision_error:{result.get('error')}"
        except Exception as e:
            detected_items = []
            payload["error"] = f"vision_error:{type(e).__name__}"
            print(f"[ERROR] vision failed: {type(e).__name__}: {e}")

        # 2) 營養計算
        try:
            enriched, totals = nutrition.calc(
                detected_items, include_garnish=include_garnish
            )
            payload["items"] = enriched
            payload["totals"] = totals
            print(f"[DEBUG] Nutrition totals: {totals}")
            return JSONResponse(payload, status_code=200)

        except Exception as e:
            payload["error"] = f"nutrition_error:{type(e).__name__}"
            print(f"[ERROR] nutrition failed: {type(e).__name__}: {e}")
            return JSONResponse(payload, status_code=200)

    except Exception as e:
        payload["error"] = f"fatal:{type(e).__name__}"
        print(f"[FATAL] analyze_image: {type(e).__name__}: {e}")
        return JSONResponse(payload, status_code=200)
