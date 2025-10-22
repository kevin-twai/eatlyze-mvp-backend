# backend/app/main.py
from __future__ import annotations

import os
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

# ----------------- 建立 App -----------------
app = FastAPI(title="eatlyze-backend", version="1.0.0")

# ----------------- 簡單請求日誌 -----------------
@app.middleware("http")
async def log_requests(request: Request, call_next):
    print(f">>> {request.method} {request.url.path}")
    resp = await call_next(request)
    print(f"<<< {resp.status_code} {request.url.path}")
    return resp

# ----------------- CORS -----------------
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

# ----------------- 靜態檔案：上傳目錄 -----------------
UPLOAD_DIR = os.path.join(os.path.dirname(__file__), "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)
app.mount("/image", StaticFiles(directory=UPLOAD_DIR), name="image")

# ----------------- 直接提供 CSV 給前端讀 -----------------
CSV_PATH = os.path.normpath(os.path.join(os.path.dirname(__file__), "data", "foods_tw.csv"))

@app.get("/data/foods_tw.csv")
def get_foods_csv():
    if not os.path.exists(CSV_PATH):
        return {"error": "foods_tw.csv not found"}
    return FileResponse(CSV_PATH, media_type="text/csv")

# ----------------- 路由註冊 -----------------
# 注意：檔案放在 backend/app/routers/analyze.py
from app.routers import analyze as analyze_router  # noqa: E402
app.include_router(analyze_router.router)

# ----------------- 健康檢查 -----------------
@app.get("/")
def root():
    return {"status": "ok", "service": "eatlyze-backend"}
