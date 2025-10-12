from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import os, logging
from app.routers import analyze, nutrition, notion

app = FastAPI(title="Eatlyze Backend", version="0.1.0")

raw_origins = os.getenv("ALLOWED_ORIGINS", "").strip()
if raw_origins == "" or raw_origins == "*":
    allow_origins = ["*"]
else:
    allow_origins = [o.strip() for o in raw_origins.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allow_origins,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
)
