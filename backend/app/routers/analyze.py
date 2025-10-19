# backend/app/routers/analyze.py
from __future__ import annotations
import base64, uuid, os, logging
from fastapi import APIRouter, File, UploadFile
from fastapi.responses import JSONResponse
from app.services.openai_client import vision_analyze_base64
from app.services import nutrition_service as nutrition

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/analyze", tags=["Analyze"])

UPLOAD_DIR = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "uploads"))
os.makedirs(UPLOAD_DIR, exist_ok=True)
BASE_URL = os.getenv("BASE_URL", "https://eatlyze-backend.onrender.com")

@router.post("/image")
async def analyze_image(file: UploadFile = File(...)):
    raw = await file.read()

    # 儲存圖片（供前端顯示）
    fname = f"{uuid.uuid4().hex}.jpg"
    fpath = os.path.join(UPLOAD_DIR, fname)
    with open(fpath, "wb") as f:
        f.write(raw)
    image_url = f"{BASE_URL}/image/{fname}"

    # 丟給 Vision
    img_b64 = base64.b64encode(raw).decode("utf-8")
    logger.info(">>> POST /analyze/image")
    try:
        parsed = await vision_analyze_base64(img_b64)  # {"items":[...]}
    except Exception as e:
        logger.exception("vision_analyze_base64 failed")
        return JSONResponse({"error": "vision failed", "detail": str(e)}, status_code=502)

    items = parsed.get("items") or []
    logger.info("[analyze] vision parsed items (len=%d): %s", len(items), items[:3])

    # 計算營養（先排除 garnish，想含入可設 include_garnish=True）
    enriched, totals = nutrition.calc(items, include_garnish=False)
    logger.info("[analyze] nutrition totals: %s", totals)

    # 前端好讀：統一回傳一個物件（你前端已支援這種結構）
    return {
        "image_url": image_url,
        "items": enriched,
        "summary": totals,
    }
