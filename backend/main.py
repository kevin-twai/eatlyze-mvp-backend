# backend/main.py
from __future__ import annotations

import os
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

# ---- 基本設定 ----
app = FastAPI(title="eatlyze-backend", version="1.0.0")

# ---- 請求紀錄中介層（Request Log Middleware）----
@app.middleware("http")
async def log_requests(request: Request, call_next):
    print(f">>> {request.method} {request.url.path}")
    response = await call_next(request)
    print(f"<<< {response.status_code} {request.url.path}")
    return response

# ---- CORS 設定 ----
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

# ---- CSV 公開存取（給前端載入對照表）----
@app.get("/data/foods_tw.csv")
def get_foods_csv():
    # 真實路徑：backend/app/data/foods_tw.csv
    csv_path = os.path.join(os.path.dirname(__file__), "app", "data", "foods_tw.csv")
    if not os.path.exists(csv_path):
        # 回傳 JSON 方便前端處理錯誤，而不是直接 404
        return {"error": "foods_tw.csv not found"}
    return FileResponse(csv_path, media_type="text/csv")

# ---- 路由註冊 ----
from app.routers import analyze as analyze_router  # noqa: E402
app.include_router(analyze_router.router)

# ---- 健康檢查 ----
@app.get("/")
def root():
    return {"status": "ok", "service": "eatlyze-backend"}
