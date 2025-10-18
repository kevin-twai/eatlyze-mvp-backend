import os
import base64
import uuid
from fastapi import APIRouter, File, UploadFile
from fastapi.responses import JSONResponse
from app.services.openai_client import vision_analyze_base64
from app.services import nutrition_service as nutrition

router = APIRouter(prefix="/analyze", tags=["Analyze"])

UPLOAD_DIR = os.path.join(os.path.dirname(__file__), "..", "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

@router.post("/image")
async def analyze_image(file: UploadFile = File(...)):
    # 將上傳的圖片讀取成 bytes
    raw = await file.read()

    # 存檔
    filename = f"{uuid.uuid4().hex}_{file.filename}"
    filepath = os.path.join(UPLOAD_DIR, filename)
    with open(filepath, "wb") as f:
        f.write(raw)

    # Base64 給 OpenAI Vision 分析
    img_b64 = base64.b64encode(raw).decode("utf-8")

    try:
        parsed = await vision_analyze_base64(img_b64)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)

    enriched, totals = nutrition.calc(parsed.get("items", []))
    image_url = f"https://eatlyze-backend.onrender.com/image/{filename}"

    return {
    "image_url": f"{BASE_URL}/image/{filename}",
    "items": enriched,
    "summary": totals,
}
