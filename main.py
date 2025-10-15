
import os, logging
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from app.routers import analyze

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s :: %(message)s")
app = FastAPI(title="Eatlyze Backend", version="1.0.0")

ALLOWED_ORIGINS_RAW = os.getenv("ALLOWED_ORIGINS", "http://localhost:5173,https://eatlyze-mvp-frontend.onrender.com")
allowed = [o.strip() for o in ALLOWED_ORIGINS_RAW.split(",") if o.strip()]
print(f"[CORS] ALLOWED_ORIGINS raw='{ALLOWED_ORIGINS_RAW}' parsed={allowed}")

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed or ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    max_age=600,
)

@app.get("/")
async def root():
    return {"status":"ok","service":"eatlyze-backend"}

@app.middleware("http")
async def json_error_middleware(request: Request, call_next):
    try:
        return await call_next(request)
    except Exception as e:
        logging.exception("middleware_unhandled")
        return JSONResponse(status_code=500, content={"status":"error","reason":str(e)})

app.include_router(analyze.router)
