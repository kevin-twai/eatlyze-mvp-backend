from __future__ import annotations
import base64, traceback
from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse

from app.services.openai_client import vision_analyze_base64
try:
    from app.services import nutrition_service_v2 as nutrition
except Exception:
    from app.services import nutrition_service as nutrition  # 後備

router = APIRouter(prefix="/analyze", tags=["Analyze"])


@router.get("/ping")
def ping():
    return {"pong": True}


def ok(payload: Dict[str, Any]) -> JSONResponse:
    return JSONResponse({"status": "ok", **payload}, status_code=200)


def err(where: str, exc: Exception) -> JSONResponse:
    tb = "".join(traceback.format_exc())
    print(f"[analyze][ERROR] {where}: {exc}\n{tb}")
    return JSONResponse(
        {"status": "error", "where": where, "error": str(exc)},
        status_code=200,  # 以 200 回避前端因 500 中斷流程
    )


def run_pipeline(img_b64: str) -> JSONResponse:
    # 1) Vision
    try:
        result = vision_analyze_base64(img_b64)  # 預期 {"items":[...]}
    except Exception as e:
        return err("vision", e)

    items: List[Dict[str, Any]] = result.get("items") or []
    print(f"[analyze] vision items = {len(items)} -> {items[:3]}...")

    # 2) Nutrition
    try:
        enriched, totals = nutrition.calc(items, include_garnish=False)
    except Exception as e:
        return err("nutrition", e)

    print(f"[analyze] totals = {totals}")
    return ok({"data": {"items": enriched, "summary": totals}})


@router.post("/image")
async def analyze_image(request: Request):
    """
    支援：
      - application/json  : {"image_base64": "..."} 或 {"image_b64": "..."}
      - multipart/form-data: 欄位 "file"
    回傳：
      { "status":"ok", "data": { "items":[...], "summary": {...} } }
      或 { "status":"error", "where":"...", "error":"..." }
    """
    ctype = (request.headers.get("content-type") or "").lower()

    # JSON
    if "application/json" in ctype:
        try:
            body = await request.json()
        except Exception as e:
            return err("read_json", e)
        b64 = body.get("image_base64") or body.get("image_b64")
        if not isinstance(b64, str) or not b64.strip():
            return JSONResponse(
                {"status": "error", "where": "validate_json", "error": "image_base64 (or image_b64) is required"},
                status_code=200,
            )
        return run_pipeline(b64.strip())

    # Multipart
    if "multipart/form-data" in ctype:
        try:
            form = await request.form()
            up = form.get("file")
            if up is None:
                return JSONResponse(
                    {"status": "error", "where": "validate_form", "error": "file is required"},
                    status_code=200,
                )
            data = await up.read()  # type: ignore[attr-defined]
            b64 = base64.b64encode(data).decode("ascii")
        except Exception as e:
            return err("read_form", e)
        return run_pipeline(b64)

    # 其它
    return JSONResponse(
        {"status": "error", "where": "content_type",
         "error": "Unsupported Content-Type. Use application/json or multipart/form-data."},
        status_code=200,
    )
