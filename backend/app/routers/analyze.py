# backend/app/routers/analyze.py
from __future__ import annotations
import base64
from fastapi import APIRouter, File, UploadFile, Query
from fastapi.responses import JSONResponse

from app.services.openai_client import vision_analyze_base64
from app.services import nutrition_service as nutrition
from app.services.storage import store_image_and_get_url

router = APIRouter(prefix="/analyze", tags=["Analyze"])

@router.post("/image")
async def analyze_image(
    file: UploadFile = File(...),
    debug: int = Query(0, description="1=附加除錯資訊")
):
    raw = await file.read()
    image_url = store_image_and_get_url(raw, file.filename)

    img_b64 = base64.b64encode(raw).decode("utf-8")

    try:
        parsed = await vision_analyze_base64(img_b64)  # {"items":[...]}
    except Exception as e:
        print("[analyze] OpenAI error:", e)
        return JSONResponse({"error": str(e)}, status_code=500)

    # 後端直接記錄 AI 解析的 items
    print(f"[analyze] vision parsed items (len={len(parsed.get('items', []))}): {parsed.get('items')}")

    enriched, totals = nutrition.calc(parsed.get("items", []), include_garnish=False)

    # 後端也記錄計算後總和，確認是不是 0
    print(f"[analyze] nutrition totals: {totals}")

    payload = {
        "image_url": image_url,
        "items": enriched,
        "summary": totals,
    }

    if debug == 1:
        payload["_debug_raw_items"] = parsed.get("items", [])

    return payload
