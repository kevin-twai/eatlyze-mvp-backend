# backend/main.py
from __future__ import annotations
import os
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

app = FastAPI(title="eatlyze-backend", version="1.0.0")

# --- 日誌中介層 ---
@app.middleware("http")
async def log_requests(request: Request, call_next):
    print(f">>> {request.method} {request.url.path}")
    try:
        resp = await call_next(request)
        print(f"<<< {resp.status_code} {request.url.path}")
        return resp
    except Exception as e:
        print(f"[ERROR] {request.url.path}: {e}")
        # 保證回應（避免 Starlette 進一步處理 bytes）
        from starlette.responses import JSONResponse
        return JSONResponse(
            {"items": [], "totals": {"kcal": 0, "protein_g": 0, "fat_g": 0, "carb_g": 0}, "error": "server_error"},
            status_code=200,
        )

# --- CORS ---
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

# --- 靜態 CSV 與上傳圖檔 ---
BASE_DIR = os.path.dirname(__file__)
UPLOAD_DIR = os.path.join(BASE_DIR, "app", "uploads")
DATA_DIR = os.path.join(BASE_DIR, "app", "data")
os.makedirs(UPLOAD_DIR, exist_ok=True)

# /image/xxx.jpg -> backend/app/uploads/xxx.jpg
app.mount("/image", StaticFiles(directory=UPLOAD_DIR), name="image")

# /data/foods_tw.csv -> backend/app/data/foods_tw.csv
app.mount("/data", StaticFiles(directory=DATA_DIR), name="data")

# --- 路由 ---
from app.routers import analyze as analyze_router  # noqa: E402
app.include_router(analyze_router.router)

# --- 健檢 ---
@app.get("/")
def root():
    return {"status": "ok", "service": "eatlyze-backend"}
