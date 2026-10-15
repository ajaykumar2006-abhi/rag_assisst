"""Settings and privacy endpoints.

Never returns secrets: the configured LLM API key is represented only by the
boolean ``llm_configured``. ``/privacy`` reports exactly what is stored on disk
and where, so the Settings screen can state facts rather than reassurances.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends

from ..core.errors import ValidationError
from ..schemas.models import SettingsResponse, SettingsUpdate, SettingsUpdateResponse
from ..services.container import ServiceContainer
from .deps import get_container

router = APIRouter(tags=["settings"])


def _to_response(container: ServiceContainer) -> SettingsResponse:
    settings = container.settings
    available, reason = container.answerer.availability()

    runs_locally = [
        "Document upload, validation and storage",
        f"Text extraction (PDF, TXT, DOCX)",
        "Chunking and metadata generation",
        f"Embeddings ({container.embedder.name})",
        "Vector indexing and persistent storage",
        "Hybrid retrieval (dense cosine + BM25)",
        "Extractive answering and citation assembly",
        "All evaluation metrics",
    ]
    external = []
    if settings.answer_provider == "openai_compatible":
        external.append(f"Answer generation ({settings.llm_model or 'unconfigured model'})")
    if container.embedder.semantic:
        external.append("Embedding model download at first use (then runs locally)")
    if not external:
        external.append("Nothing -- every core feature runs on this machine.")

    return SettingsResponse(
        chunk_size=settings.chunk_size,
        chunk_overlap=settings.chunk_overlap,
        top_k=settings.top_k,
        dense_weight=settings.dense_weight,
        lexical_weight=settings.lexical_weight,
        min_relevance=settings.min_relevance,
        max_upload_mb=settings.max_upload_mb,
        max_pages=settings.max_pages,
        embedding_provider=settings.embedding_provider,
        embedding_model=container.embedder.name,
        embedding_dim=container.embedder.dim,
        answer_provider=settings.answer_provider,
        answer_max_sentences=settings.answer_max_sentences,
        # Literal answer to "is an API key stored?" -- never conflated with whether
        # the (possibly local and key-free) answerer is usable.
        llm_configured=bool(settings.llm_api_key.strip()),
        llm_base_url=settings.llm_base_url,
        llm_model=settings.llm_model,
        answerer_available=available,
        answerer_reason=reason,
        cors_origins=settings.cors_origins,
        allowed_extensions=settings.allowed_extensions,
        data_dir=str(settings.data_dir),
        runs_locally=runs_locally,
        requires_external_service=external,
    )


@router.get("/settings", response_model=SettingsResponse, summary="Current non-secret configuration")
def get_configuration(container: ServiceContainer = Depends(get_container)) -> SettingsResponse:
    return _to_response(container)


@router.patch(
    "/settings",
    response_model=SettingsUpdateResponse,
    summary="Adjust retrieval and chunking settings for this process",
)
def update_configuration(
    payload: SettingsUpdate, container: ServiceContainer = Depends(get_container)
) -> SettingsUpdateResponse:
    settings = container.settings
    notices = []

    if payload.chunk_size is not None or payload.chunk_overlap is not None:
        size = payload.chunk_size if payload.chunk_size is not None else settings.chunk_size
        overlap = payload.chunk_overlap if payload.chunk_overlap is not None else settings.chunk_overlap
        if overlap >= size:
            raise ValidationError("chunk_overlap must be smaller than chunk_size.")
        settings.chunk_size = size
        settings.chunk_overlap = overlap
        notices.append("Chunking changes apply to documents indexed from now on; re-upload to re-chunk.")

    if payload.top_k is not None:
        settings.top_k = payload.top_k
    if payload.dense_weight is not None:
        settings.dense_weight = payload.dense_weight
    if payload.lexical_weight is not None:
        settings.lexical_weight = payload.lexical_weight
    if payload.min_relevance is not None:
        settings.min_relevance = payload.min_relevance
    if payload.answer_max_sentences is not None:
        settings.answer_max_sentences = payload.answer_max_sentences

    if payload.embedding_provider is not None:
        if payload.embedding_provider != settings.embedding_provider:
            raise ValidationError(
                "Changing the embedding provider requires a restart: the vector index must be "
                "rebuilt for the new embedding space. Set EMBEDDING_PROVIDER in .env and restart."
            )
    if payload.answer_provider is not None:
        if payload.answer_provider != settings.answer_provider:
            raise ValidationError(
                "Changing the answer provider requires a restart so the provider can validate its "
                "configuration. Set ANSWER_PROVIDER in .env and restart."
            )

    return SettingsUpdateResponse(
        settings=_to_response(container),
        applied=True,
        notice=" ".join(notices) if notices else None,
    )


@router.get("/privacy", summary="Exactly what is stored locally, and where")
def privacy(container: ServiceContainer = Depends(get_container)) -> dict:
    settings = container.settings
    documents = [dict(row) for row in container.db.list_documents()]
    total_bytes = 0
    for document in documents:
        path = Path(document["stored_path"])
        if path.exists():
            total_bytes += path.stat().st_size

    storage = [
        {
            "what": "Uploaded documents",
            "where": str(settings.upload_dir),
            "count": len(documents),
            "bytes": total_bytes,
        },
        {
            "what": "Document metadata, chunks and chat history",
            "where": str(settings.db_path),
            "count": container.db.chunk_count(),
            "bytes": settings.db_path.stat().st_size if settings.db_path.exists() else 0,
        },
        {
            "what": "Vector index",
            "where": str(settings.index_dir / "collection"),
            "count": container.vector_index.size,
            "bytes": sum(
                path.stat().st_size
                for path in (settings.index_dir / "collection").glob("*")
                if path.is_file()
            )
            if (settings.index_dir / "collection").exists()
            else 0,
        },
    ]

    return {
        "data_dir": str(settings.data_dir),
        "storage": storage,
        "retention": (
            "Documents and their indexes persist until you delete them here or remove the data "
            "directory. Nothing is uploaded anywhere unless you configure an external answer provider."
        ),
        "external_services": (
            "None configured."
            if container.answerer.name == "extractive"
            else f"{container.answerer.name} is configured. Retrieved passages leave this machine."
        ),
        "delete_instructions": [
            "Delete an individual document from the Workspace or Settings screen.",
            f"Delete everything: stop the backend and remove '{settings.data_dir}'.",
        ],
    }


@router.delete("/privacy/documents", summary="Delete every document and all derived data")
def delete_all_documents(container: ServiceContainer = Depends(get_container)) -> dict:
    documents = [dict(row) for row in container.db.list_documents()]
    removed = 0
    for document in documents:
        container.remove_document(document["id"], Path(document["stored_path"]))
        removed += 1
    container.db.log_event("all_documents_deleted", {"count": removed})
    return {"documents_removed": removed, "index_size_after": container.vector_index.size}
