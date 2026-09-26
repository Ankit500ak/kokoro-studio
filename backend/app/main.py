import asyncio
import logging
import sys
import time
from contextlib import asynccontextmanager
from logging.handlers import RotatingFileHandler
from pathlib import Path
from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.status import HTTP_422_UNPROCESSABLE_ENTITY
from .api.tts import router as tts_router
from .api.library import router as library_router
from .api.projects import router as projects_router
from .api.media import router as media_router
from .api.renders import router as renders_router
from .api.templates import router as templates_router
from .api.story_forge import router as story_forge_router
from .api.youtube import router as youtube_router
from .core.config import settings
from .core.database import init_db
from .services.youtube_uploader import uploader


LOG_FORMAT = "%(asctime)s | %(levelname)-7s | %(name)-30s | %(message)s"
LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

# Persist logs so failures are diagnosable after the console window is gone.
LOG_DIR = Path(__file__).resolve().parent.parent / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)
_file_handler = RotatingFileHandler(
    LOG_DIR / "kokoro.log",
    maxBytes=5 * 1024 * 1024,
    backupCount=5,
    encoding="utf-8",
)
_file_handler.setFormatter(logging.Formatter(LOG_FORMAT, datefmt=LOG_DATE_FORMAT))

logging.basicConfig(
    level=logging.INFO,
    format=LOG_FORMAT,
    datefmt=LOG_DATE_FORMAT,
    handlers=[logging.StreamHandler(sys.stdout), _file_handler],
    force=True,
)

logging.getLogger("watchfiles").setLevel(logging.WARNING)

log = logging.getLogger("kokoro")


# Global startup flag
_startup_complete = False


@asynccontextmanager
async def lifespan(app):
    global _startup_complete
    init_db()
    uploader.startup_maintenance()
    task = asyncio.create_task(uploader.start_processing())
    log.info("Kokoro Studio API started")
    _startup_complete = True
    yield
    uploader.stop_processing()
    task.cancel()


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    lifespan=lifespan,
    docs_url="/api/docs",
    redoc_url="/api/redoc",
)

# Production-ready CORS configuration
# In production, restrict allow_origins to specific domains
# Development uses "*" for flexibility.
# The spec forbids Allow-Credentials with a wildcard origin, and this API does
# not authenticate via cookies (OAuth tokens live server-side), so credentials
# are only enabled when explicit origins are configured.
_allow_credentials = "*" not in settings.CORS_ORIGINS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=_allow_credentials,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=[
        "Authorization",
        "Content-Type",
        "X-Requested-With",
        "X-Request-ID",
        "Accept",
        "Origin",
    ],
    expose_headers=["X-Request-ID"],
)


@app.middleware("http")
async def request_id_middleware(request: Request, call_next):
    """Add unique request ID to all requests for tracing."""
    request_id = f"req-{int(time.time_ns()) % 10**8:08d}"
    request.state.request_id = request_id
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    return response


@app.middleware("http")
async def log_requests(request: Request, call_next):
    start = time.perf_counter()
    response = await call_next(request)
    elapsed = (time.perf_counter() - start) * 1000
    log.info(
        f"{request.method} {request.url.path} -> {response.status_code} ({elapsed:.0f}ms)"
    )
    return response


# Global exception handlers


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "success": False,
            "error": exc.detail,
            "request_id": getattr(request.state, "request_id", "unknown"),
        },
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "success": False,
            "error": "Validation failed",
            "details": exc.errors(),
            "request_id": getattr(request.state, "request_id", "unknown"),
        },
    )


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    log.error(f"Unhandled exception: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={
            "success": False,
            "error": "Internal server error",
            "request_id": getattr(request.state, "request_id", "unknown"),
        },
    )


app.include_router(tts_router, prefix="/api")
app.include_router(library_router, prefix="/api")
app.include_router(projects_router, prefix="/api")
app.include_router(media_router, prefix="/api")
app.include_router(renders_router, prefix="/api")
app.include_router(templates_router, prefix="/api")
app.include_router(story_forge_router, prefix="/api")
app.include_router(youtube_router, prefix="/api")


@app.get("/")
async def root():
    return {"message": "Kokoro Studio API", "version": settings.APP_VERSION}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host=settings.HOST, port=settings.PORT)
