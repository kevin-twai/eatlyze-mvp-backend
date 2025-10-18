# backend/main.py
from __future__ import annotations

import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

# ---- 基本設定 ----
app = FastAPI(title="eatlyze-backend", version="1.0.0")

# 允許的前端來源（可用環境變數 ALLOWED_ORIGINS 以逗點分隔覆蓋）
_allowed = os.getenv(
    "ALLOWED_ORIGINS",
    "http://localhost:5173,https://eatlyze-mvp-frontend.onrender.com",
)
ALLOWED_ORIGINS = [o.strip() for o in _allowed.split(",") if o.strip()]

print(f"[CORS] ALLOWED_ORIGINS raw='{_allowed}' parsed={ALLOWED_ORIGINS}")

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---- 靜態圖片服務 (/image/...) ----
# 注意：這支檔案位於 backend/，而圖片實際在 backend/app/uploads/
UPLOAD_DIR = os.path.join(os.path.dirname(__file__), "app", "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

# 例如：/image/xxxxx.jpg -> 讀取 backend/app/uploads/xxxxx.jpg
app.mount("/image", StaticFiles(directory=UPLOAD_DIR), name="image")

# ---- 路由註冊 ----
from app.routers import analyze as analyze_router
app.include_router(analyze_router.router)

# ---- 健康檢查 ----
@app.get("/")
def root():
    return {"status": "ok", "service": "eatlyze-backend"}
