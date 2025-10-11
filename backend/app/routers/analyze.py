
import os
from fastapi import APIRouter, UploadFile, File, HTTPException
from app.services.openai_client import analyze_food_image
from app.services.nutrition_calc import summarize_items

router = APIRouter()

@router.post("/image")
async def analyze_image(file: UploadFile = File(...)):
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in [".jpg", ".jpeg", ".png", ".webp"]:
        raise HTTPException(status_code=400, detail="Unsupported file type")
    image_bytes = await file.read()
    det = analyze_food_image(image_bytes)
    items = det.get("items", [])
    summary = summarize_items(items)
    return {"detection": det, "summary": summary}
