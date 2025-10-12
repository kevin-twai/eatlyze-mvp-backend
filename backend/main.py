import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv

from app.routers import analyze, notion, nutrition, upload

load_dotenv()

app = FastAPI(title="Eatlyze Taiwan — MVP API (stable)", version="0.3.0")

ALLOWED_ORIGINS = os.getenv(
    "ALLOWED_ORIGINS",
    "http://localhost:5173,https://eatlyze-mvp-frontend.onrender.com"
)
origins = [o.strip().rstrip("/") for o in ALLOWED_ORIGINS.split(",") if o.strip()]

print("ENV ALLOWED_ORIGINS =", ALLOWED_ORIGINS)
print("CORS origins parsed =", origins)

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

UPLOAD_DIR = os.path.join(os.path.dirname(__file__), "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")

app.include_router(upload.router, prefix="/upload", tags=["Upload"])
app.include_router(analyze.router, prefix="/analyze", tags=["AI Analyze"])
app.include_router(nutrition.router, prefix="/nutrition", tags=["Nutrition"])
app.include_router(notion.router, prefix="/notion", tags=["Notion"])

@app.get("/health")
async def health():
    return {"status": "ok", "origins": origins}

@app.get("/debug/cors")
async def debug_cors():
    return {"env.ALLOWED_ORIGINS": ALLOWED_ORIGINS, "parsed_origins": origins}
