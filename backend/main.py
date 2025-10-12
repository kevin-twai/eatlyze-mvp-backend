from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import os, logging
from app.routers import analyze, nutrition, notion

app = FastAPI(title="Eatlyze Backend", version="0.1.0")

raw_origins = os.getenv("ALLOWED_ORIGINS", "").strip()
if raw_origins in ("", "*"):
    allow_origins = ["*"]
else:
    allow_origins = [o.strip() for o in raw_origins.split(",") if o.strip()]

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s :: %(message)s")
logging.info(f"[CORS] ALLOWED_ORIGINS raw='{raw_origins}' parsed={allow_origins}")

app.add_middleware(
    CORSMiddleware,
    allow_origins=allow_origins,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
)

app.include_router(analyze.router)
app.include_router(nutrition.router)
app.include_router(notion.router)

@app.get("/")
def root():
    return {"status": "ok"}
