"""FastAPI application entry point."""

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.config import settings

# Try to import langfuse tracing, but make it optional
try:
    from src.integrations.langfuse.tracing import flush_langfuse, init_langfuse, shutdown_langfuse
    LANGFUSE_AVAILABLE = True
except Exception:
    LANGFUSE_AVAILABLE = False
    def init_langfuse(): pass
    def flush_langfuse(): pass
    def shutdown_langfuse(): pass


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
from fastapi import Request
from fastapi.responses import JSONResponse
import logging
import traceback

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
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if settings.is_development else ["https://job-hunter.vercel.app"],
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


# Import and include routers
from src.api.routes import applications, auth, gmail, jobs, users

app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
app.include_router(jobs.router, prefix="/api/jobs", tags=["jobs"])
app.include_router(users.router, prefix="/api/users", tags=["users"])
app.include_router(applications.router, prefix="/api/applications", tags=["applications"])
app.include_router(gmail.router, prefix="/api/gmail", tags=["gmail"])

