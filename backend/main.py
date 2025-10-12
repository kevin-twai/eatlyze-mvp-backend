from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
import os, logging
from app.routers import analyze, nutrition, notion

app = FastAPI(title="Eatlyze Backend", version="0.1.0")

raw_origins = os.getenv("ALLOWED_ORIGINS", "").strip()
if raw_origins in ("", "*"):
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

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s :: %(message)s")
logging.info(f"[CORS] ALLOWED_ORIGINS raw='{raw_origins}' parsed={allow_origins}")

@app.get("/")
def root():
    return {"status": "ok"}

# ---- Global exception handlers ----
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    logging.exception("validation_error")
    return JSONResponse(
        status_code=422,
        content={"status": "fail", "reason": "validation_error", "debug": {"detail": exc.errors()}},
    )

@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    logging.exception("unhandled_exception")
    return JSONResponse(
        status_code=500,
        content={"status": "fail", "reason": "unhandled_exception", "debug": {"error": str(exc)}},
    )

# ---- Catch-all HTTP middleware ----
@app.middleware("http")
async def json_error_middleware(request: Request, call_next):
    try:
        resp = await call_next(request)
        return resp
    except Exception as e:
        logging.exception("middleware_unhandled")
        return JSONResponse(
            status_code=500,
            content={"status": "fail", "reason": "middleware_unhandled", "debug": {"error": str(e)}},
        )

app.include_router(analyze.router)
app.include_router(nutrition.router)
app.include_router(notion.router)
