import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv

from app.routers import analyze, notion, nutrition, upload

load_dotenv()  # 確保 .env / Render env 已載入

app = FastAPI(title="Eatlyze Taiwan — MVP API (CORS debug)", version="0.2.2")

# ---- CORS: 以環境變數白名單為主 ----
ALLOWED_ORIGINS = os.getenv(
    "ALLOWED_ORIGINS",
    "http://localhost:5173,https://eatlyze-mvp-frontend.onrender.com"
)
origins = [o.strip().rstrip("/") for o in ALLOWED_ORIGINS.split(",") if o.strip()]

# 重要：印出實際 origins，方便在 Render Logs 看到
print("ENV ALLOWED_ORIGINS =", ALLOWED_ORIGINS)
print("CORS origins parsed =", origins)

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,      # 明確清單（不要含 "*"）
    allow_credentials=True,     # 清單模式下可開
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---- 靜態上傳目錄 ----
UPLOAD_DIR = os.path.join(os.path.dirname(__file__), "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")

# ---- 路由 ----
app.include_router(upload.router, prefix="/upload", tags=["Upload"])
app.include_router(analyze.router, prefix="/analyze", tags=["AI Analyze"])
app.include_router(nutrition.router, prefix="/nutrition", tags=["Nutrition"])
app.include_router(notion.router, prefix="/notion", tags=["Notion"])

@app.get("/health")
async def health():
    return {"status": "ok", "origins": origins}

# ✅ 新增：CORS 除錯端點
@app.get("/debug/cors")
async def debug_cors():
    return {
        "env.ALLOWED_ORIGINS": ALLOWED_ORIGINS,
        "parsed_origins": origins,
    }
