"""Document lifecycle endpoints: upload, list, inspect, status, sources, delete."""

from __future__ import annotations

import logging
import threading
from pathlib import Path
from typing import List

from fastapi import APIRouter, Depends, File, Request, UploadFile, status

from ..core.errors import FileTooLargeError, NotFoundError, ValidationError
from ..schemas.models import (
    DocumentDetail,
    DocumentStatus,
    DocumentStatusResponse,
    DocumentSummary,
    SourceResponse,
    Stage,
    UploadResponse,
)
from ..services import pipeline as pipeline_module
from ..services.container import ServiceContainer
from ..services.qa import build_excerpt
from .deps import get_container

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/documents", tags=["documents"])

UPLOAD_CHUNK_BYTES = 1024 * 1024


# ---------------------------------------------------------------------------
# Serialisation helpers
# ---------------------------------------------------------------------------


def _stage_models(container: ServiceContainer, document_id: str) -> List[Stage]:
    rows = container.db.get_stages(document_id)
    stages: List[Stage] = []
    for row in rows:
        stages.append(
            Stage(
                name=row["name"],
                label=row["label"],
                state=row["state"],
                detail=row["detail"] or "",
                progress=float(row["progress"] or 0.0),
                started_at=row["started_at"],
                finished_at=row["finished_at"],
            )
        )
    return stages


def _to_detail(container: ServiceContainer, row) -> DocumentDetail:
    stages = _stage_models(container, row["id"])
    return DocumentDetail(
        id=row["id"],
        filename=row["filename"],
        extension=row["extension"],
        size_bytes=row["size_bytes"],
        status=row["status"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        page_count=row["page_count"],
        chunk_count=row["chunk_count"],
        char_count=row["char_count"],
        error=row["error"],
        stages=stages,
        embedding_provider=row["embedding_provider"],
        embedding_dim=row["embedding_dim"],
        answer_provider=row["answer_provider"],
        indexed=bool(row["indexed"]),
    )


def _to_summary(row) -> DocumentSummary:
    return DocumentSummary(
        id=row["id"],
        filename=row["filename"],
        extension=row["extension"],
        size_bytes=row["size_bytes"],
        status=row["status"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        page_count=row["page_count"],
        chunk_count=row["chunk_count"],
        char_count=row["char_count"],
        error=row["error"],
    )


def _require_document(container: ServiceContainer, document_id: str):
    row = container.db.get_document(document_id)
    if row is None:
        raise NotFoundError(f"No document with id '{document_id}'.")
    return row


# ---------------------------------------------------------------------------
# Upload
# ---------------------------------------------------------------------------


@router.post(
    "",
    response_model=UploadResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload a PDF, TXT or DOCX document",
)
async def upload_document(
    request: Request,
    file: UploadFile = File(...),
    container: ServiceContainer = Depends(get_container),
) -> UploadResponse:
    # Limits come from the container so tests can inject their own configuration.
    settings = container.settings
    if not file.filename:
        raise ValidationError("A filename is required.")

    safe_name = pipeline_module.sanitise_filename(file.filename)
    extension = pipeline_module.check_upload(safe_name, 1, settings)

    # Stream into memory with a hard ceiling so a huge upload cannot exhaust RAM.
    limit = settings.max_upload_mb * 1024 * 1024
    chunks_buffer = bytearray()
    while True:
        block = await file.read(UPLOAD_CHUNK_BYTES)
        if not block:
            break
        chunks_buffer.extend(block)
        if len(chunks_buffer) > limit:
            raise FileTooLargeError(
                f"The file exceeds the {settings.max_upload_mb} MB upload limit."
            )
    data = bytes(chunks_buffer)
    await file.close()

    pipeline_module.check_upload(safe_name, len(data), settings)

    # Content sniffing happens before anything is stored.
    from ..services.extraction import sniff_format

    sniff_format(data, extension)

    record = pipeline_module.persist_upload(container, safe_name, data, extension)
    container.db.create_document(record)
    container.db.reset_stages(record["id"], pipeline_module.stage_seed())
    container.db.log_event(
        "upload", {"document_id": record["id"], "filename": safe_name, "bytes": len(data)}
    )

    # Start indexing immediately so the observatory screen has progress to poll.
    thread = threading.Thread(
        target=pipeline_module.process_document,
        args=(record["id"], container),
        name=f"pipeline-{record['id']}",
        daemon=True,
    )
    thread.start()

    row = _require_document(container, record["id"])
    return UploadResponse(
        document=_to_detail(container, row),
        message="Upload accepted. Indexing has started.",
    )


# ---------------------------------------------------------------------------
# Reads
# ---------------------------------------------------------------------------


@router.get("", response_model=List[DocumentSummary], summary="List all documents")
def list_documents(container: ServiceContainer = Depends(get_container)) -> List[DocumentSummary]:
    return [_to_summary(row) for row in container.db.list_documents()]


@router.get("/{document_id}", response_model=DocumentDetail, summary="Get one document")
def get_document(
    document_id: str, container: ServiceContainer = Depends(get_container)
) -> DocumentDetail:
    return _to_detail(container, _require_document(container, document_id))


@router.get(
    "/{document_id}/status",
    response_model=DocumentStatusResponse,
    summary="Processing status used by the observatory screen",
)
def get_status(
    document_id: str, container: ServiceContainer = Depends(get_container)
) -> DocumentStatusResponse:
    row = _require_document(container, document_id)
    stages = _stage_models(container, document_id)
    payload = [
        {"state": stage.state.value, "progress": stage.progress} for stage in stages
    ]
    progress = pipeline_module.compute_progress(payload)
    return DocumentStatusResponse(
        id=document_id,
        status=row["status"],
        stages=stages,
        progress=progress,
        error=row["error"],
        retryable=row["status"] == "failed",
        indexed=bool(row["indexed"]),
    )


@router.get(
    "/{document_id}/sources",
    response_model=SourceResponse,
    summary="List the indexed chunks of a document",
)
def get_sources(
    document_id: str,
    container: ServiceContainer = Depends(get_container),
    limit: int = 50,
) -> SourceResponse:
    row = _require_document(container, document_id)
    chunks = container.db.get_chunks(document_id)[: max(1, min(limit, 500))]
    from ..schemas.models import Citation

    citations = [
        Citation(
            index=index,
            document_id=document_id,
            filename=row["filename"],
            chunk_id=chunk["id"],
            page=chunk["page"],
            score=0.0,
            excerpt=build_excerpt(chunk["text"], ""),
            char_start=chunk["char_start"],
            char_end=chunk["char_end"],
        )
        for index, chunk in enumerate(chunks, start=1)
    ]
    return SourceResponse(document_id=document_id, filename=row["filename"], sources=citations)


# ---------------------------------------------------------------------------
# Mutations
# ---------------------------------------------------------------------------


@router.delete("/{document_id}", status_code=status.HTTP_200_OK, summary="Delete a document")
def delete_document(document_id: str, container: ServiceContainer = Depends(get_container)) -> dict:
    row = _require_document(container, document_id)
    stored_path = Path(row["stored_path"])
    cleanup = container.remove_document(document_id, stored_path)
    container.db.log_event(
        "document_deleted", {"document_id": document_id, "filename": row["filename"]}
    )
    return {
        "deleted": document_id,
        "filename": row["filename"],
        "vectors_removed": cleanup["vectors_removed"],
        "files_removed": cleanup["files_removed"],
        "index_size_after": container.vector_index.size,
    }


@router.post(
    "/{document_id}/retry",
    response_model=UploadResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Re-run the processing pipeline for a failed document",
)
def retry_document(
    document_id: str, container: ServiceContainer = Depends(get_container)
) -> UploadResponse:
    row = _require_document(container, document_id)
    if row["status"] == "processing":
        raise ValidationError("This document is already being processed.")

    stored_path = Path(row["stored_path"])
    if not stored_path.exists():
        raise NotFoundError("The stored file is missing, so this document cannot be retried.")

    # Clear any partially written chunks before reprocessing.
    container.vector_index.remove_document(f"{document_id}::")
    container.db.delete_document(document_id)
    container.db.create_document(
        {
            "id": document_id,
            "filename": row["filename"],
            "stored_path": row["stored_path"],
            "extension": row["extension"],
            "size_bytes": row["size_bytes"],
            "sha256": row["sha256"],
            "status": "queued",
            "chunk_count": 0,
            "char_count": 0,
            "embedding_provider": container.embedder.name,
            "embedding_dim": container.embedder.dim,
            "answer_provider": container.answerer.name,
            "indexed": False,
        }
    )
    container.db.reset_stages(document_id, pipeline_module.stage_seed())
    container.refresh()

    thread = threading.Thread(
        target=pipeline_module.process_document,
        args=(document_id, container),
        name=f"pipeline-retry-{document_id}",
        daemon=True,
    )
    thread.start()

    return UploadResponse(
        document=_to_detail(container, _require_document(container, document_id)),
        message="Reprocessing started.",
    )
