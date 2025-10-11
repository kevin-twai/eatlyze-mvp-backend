
import os, uuid, shutil
from fastapi import APIRouter, UploadFile, File, HTTPException

router = APIRouter()

UPLOAD_ROOT = os.path.join(os.path.dirname(os.path.dirname(__file__)), "..", "uploads")
os.makedirs(UPLOAD_ROOT, exist_ok=True)

@router.post("")
async def upload_image(file: UploadFile = File(...)):
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in [".jpg", ".jpeg", ".png", ".webp"]:
        raise HTTPException(status_code=400, detail="Unsupported file type")
    fname = f"{uuid.uuid4().hex}{ext}"
    path = os.path.join(UPLOAD_ROOT, fname)
    with open(path, "wb") as f:
        shutil.copyfileobj(file.file, f)
    return {"filename": fname, "url": f"/uploads/{fname}", "path": path}
