"""FastAPI application entry point.

Run it with::

    python -m uvicorn app.main:app --reload --port 8000      # from backend/

Interactive API documentation is served at ``/docs`` and the raw OpenAPI
document at ``/openapi.json``.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .api import routes_documents, routes_evaluation, routes_health, routes_qa, routes_settings
from .core.config import get_settings
from .core.errors import register_exception_handlers
from .core.logging import configure_logging
from .services.container import ServiceContainer

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Build the service container on startup and release it on shutdown."""
    settings = get_settings()
    configure_logging(settings.debug)
    logger.info("Starting %s with data directory %s", settings.app_name, settings.data_dir)
    app.state.container = ServiceContainer(settings)
    try:
        yield
    finally:
        container = getattr(app.state, "container", None)
        if container is not None:
            container.shutdown()
            logger.info("Service container shut down cleanly.")


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="RAG Document Intelligence API",
        description=(
            "Grounded question answering over your own PDF, TXT and DOCX documents. "
            "Real extraction, chunking, embedding, hybrid retrieval and citation-backed answers."
        ),
        version=routes_health.VERSION,
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["*"],
    )

    register_exception_handlers(app)

    prefix = settings.api_prefix
    app.include_router(routes_health.router, prefix=prefix)
    app.include_router(routes_documents.router, prefix=prefix)
    app.include_router(routes_qa.router, prefix=prefix)
    app.include_router(routes_evaluation.router, prefix=prefix)
    app.include_router(routes_settings.router, prefix=prefix)

    @app.get("/", include_in_schema=False)
    def index() -> JSONResponse:
        return JSONResponse(
            {
                "name": settings.app_name,
                "docs": "/docs",
                "api": prefix,
                "health": f"{prefix}/health",
            }
        )

    return app


app = create_app()
