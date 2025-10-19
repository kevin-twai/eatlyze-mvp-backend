# backend/main.py
from __future__ import annotations
import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

app = FastAPI(title="eatlyze-backend", version="1.0.0")

# CORS
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

# 靜態圖片 /image
UPLOAD_DIR = os.path.normpath(os.path.join(os.path.dirname(__file__), "app", "uploads"))
os.makedirs(UPLOAD_DIR, exist_ok=True)
app.mount("/image", StaticFiles(directory=UPLOAD_DIR), name="image")

# 路由
from app.routers import analyze as analyze_router
app.include_router(analyze_router.router)

@app.get("/")
def root():
    return {"status": "ok", "service": "eatlyze-backend"}
