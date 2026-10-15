"""Health and system-status endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from ..schemas.models import HealthResponse
from ..services.container import ServiceContainer
from .deps import get_container

router = APIRouter(tags=["health"])

VERSION = "1.0.0"


@router.get("/health", response_model=HealthResponse, summary="Backend health and capability check")
def health(container: ServiceContainer = Depends(get_container)) -> HealthResponse:
    status = container.health()
    return HealthResponse(
        status="ok",
        app_name=container.settings.app_name,
        version=VERSION,
        embedding_provider=container.embedder.name,
        embedding_dim=container.embedder.dim,
        answer_provider=container.answerer.name,
        generative_available=bool(status["generative_available"]),
        documents_indexed=int(status["documents_indexed"]),
        data_dir=str(container.settings.data_dir),
        uptime_seconds=round(container.uptime_seconds(), 3),
    )
