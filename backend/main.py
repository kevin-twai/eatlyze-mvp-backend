# backend/main.py
from __future__ import annotations

import os
from typing import Callable

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse

# --------------------------
# 建立 FastAPI App
# --------------------------
app = FastAPI(title="eatlyze-backend", version="1.0.0")

# --------------------------
# 簡單請求日誌
# --------------------------
@app.middleware("http")
async def log_requests(request: Request, call_next: Callable):
    print(f">>> {request.method} {request.url.path}")
    try:
        response = await call_next(request)
    except Exception as e:
        # 統一攔住避免 bytes 造成 JSON encode 失敗
        print(f"[ERROR] {request.url.path}: {e}")
        return JSONResponse({"error": "internal error"}, status_code=500)
    print(f"<<< {response.status_code} {request.url.path}")
    return response

# --------------------------
# CORS
# --------------------------
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

# --------------------------
# 靜態檔／圖片
# --------------------------
UPLOAD_DIR = os.path.join(os.path.dirname(__file__), "app", "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)
app.mount("/image", StaticFiles(directory=UPLOAD_DIR), name="image")

# --------------------------
# 提供 CSV 給前端直接讀
# GET /data/foods_tw.csv
# --------------------------
@app.get("/data/foods_tw.csv")
def get_foods_csv():
    csv_path = os.path.join(os.path.dirname(__file__), "app", "data", "foods_tw.csv")
    if not os.path.exists(csv_path):
        return JSONResponse({"error": "foods_tw.csv not found"}, status_code=404)
    # 直接回傳檔案
    return FileResponse(csv_path, media_type="text/csv")

# --------------------------
# 健康檢查
# --------------------------
@app.get("/")
def root():
    return {"status": "ok", "service": "eatlyze-backend"}

# --------------------------
# 掛上 /analyze 路由
# --------------------------
from app.routers import analyze as analyze_router  # noqa: E402

app.include_router(analyze_router.router, prefix="/analyze", tags=["analyze"])
