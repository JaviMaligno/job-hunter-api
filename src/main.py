"""FastAPI application entry point."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.config import settings

# Try to import langfuse tracing, but make it optional
try:
    from src.integrations.langfuse.tracing import flush_langfuse, init_langfuse, shutdown_langfuse

    LANGFUSE_AVAILABLE = True
except Exception:
    LANGFUSE_AVAILABLE = False

    def init_langfuse():
        pass

    def flush_langfuse():
        pass

    def shutdown_langfuse():
        pass


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan manager."""
    # Startup
    if LANGFUSE_AVAILABLE:
        init_langfuse()
    yield
    # Shutdown
    if LANGFUSE_AVAILABLE:
        flush_langfuse()
        shutdown_langfuse()


app = FastAPI(
    title="Job Hunter API",
    description="AI-powered job hunting automation",
    version="0.1.0",
    lifespan=lifespan,
)

# Global exception handler to log unhandled errors
import logging
import traceback

from fastapi import Request
from fastapi.responses import JSONResponse

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Log and handle all unhandled exceptions."""
    logger.error(f"Unhandled error: {type(exc).__name__}: {exc}")
    logger.error(traceback.format_exc())
    return JSONResponse(
        status_code=500,
        content={"detail": f"Internal server error: {type(exc).__name__}: {str(exc)}"},
    )


# CORS middleware
# Note: For WebSocket connections, explicit origins are needed when allow_credentials=True
_dev_origins = [
    "http://localhost:3000",
    "http://localhost:3001",
    "http://localhost:8000",
    "http://127.0.0.1:3000",
    "http://127.0.0.1:3001",
    "http://127.0.0.1:8000",
]
# Production uses FRONTEND_URL env var (set in Render dashboard)
_prod_origins = [settings.frontend_url] if settings.frontend_url else []
app.add_middleware(
    CORSMiddleware,
    allow_origins=_dev_origins if settings.is_development else _prod_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "name": "Job Hunter API",
        "version": "0.1.0",
        "status": "running",
    }


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {
        "status": "ok",
        "environment": settings.app_env.value,
    }


# Test WebSocket endpoint (for debugging 403 issue)
from fastapi import WebSocket


@app.websocket("/ws/test")
async def websocket_test(websocket: WebSocket):
    """Simple test WebSocket endpoint."""
    await websocket.accept()
    logger.info("Test WebSocket connected!")
    try:
        while True:
            data = await websocket.receive_text()
            await websocket.send_text(f"Echo: {data}")
    except Exception as e:
        logger.info(f"Test WebSocket closed: {e}")


# Import and include routers
from src.api.routes import applications, auth, gmail, jobs, linkedin, users

app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
app.include_router(jobs.router, prefix="/api/jobs", tags=["jobs"])
app.include_router(users.router, prefix="/api/users", tags=["users"])
app.include_router(applications.router, prefix="/api/applications", tags=["applications"])
app.include_router(gmail.router, prefix="/api/gmail", tags=["gmail"])
app.include_router(linkedin.router, prefix="/api/linkedin", tags=["linkedin"])
