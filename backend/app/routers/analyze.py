import os
import base64
import uuid
from fastapi import APIRouter, File, UploadFile, Request
from fastapi.responses import JSONResponse
from app.services.openai_client import vision_analyze_base64
from app.services import nutrition_service as nutrition

router = APIRouter(prefix="/analyze", tags=["Analyze"])

# Render 環境可覆蓋 BASE_URL
BASE_URL = os.getenv("BASE_URL", "https://eatlyze-backend.onrender.com")

# uploads 與 main.py 一致
UPLOAD_DIR = os.path.join(os.path.dirname(__file__), "..", "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

@router.post("/image")
async def analyze_image(request: Request, file: UploadFile = File(...)):
    """接收上傳圖片並進行分析"""
    raw = await file.read()

    # 儲存圖片
    filename = f"{uuid.uuid4().hex}_{file.filename}"
    filepath = os.path.join(UPLOAD_DIR, filename)
    with open(filepath, "wb") as f:
        f.write(raw)

    # Base64 給 OpenAI Vision
    img_b64 = base64.b64encode(raw).decode("utf-8")

    try:
        parsed = await vision_analyze_base64(img_b64)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)

    # 營養計算
    enriched, totals = nutrition.calc(parsed.get("items", []), include_garnish=True)

    # 正確組合靜態圖片 URL
    image_url = f"{BASE_URL}/image/{filename}"

    return {
        "status": "ok",
        "data": {
            "image_url": image_url,
            "items": enriched,
            "summary": {"totals": totals},
        },
    }
