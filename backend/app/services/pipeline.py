"""Document ingestion pipeline.

Runs the seven stages the Processing Observatory screen visualises. Stage state
and progress are written to SQLite as they happen, so what the UI shows is a
report of real backend work -- a stage is only ever marked ``completed`` after
its work has actually finished and been committed.

The pipeline runs on a worker thread started by the upload endpoint, so a large
PDF never blocks the HTTP response.
"""

from __future__ import annotations

import hashlib
import logging
import re
import sqlite3
import time
import uuid
from pathlib import Path
from typing import Callable, Dict, List, Optional

from ..core.errors import AppError, ExtractionError, FileTooLargeError, UnsupportedFileError
from ..storage.db import utcnow
from .chunking import chunk_sections
from .container import ServiceContainer
from .extraction import extract, sniff_format
from .text_utils import extract_keywords

logger = logging.getLogger(__name__)

# Stage definitions, in execution order. Declared once so the API, the frontend
# and the tests all agree on the pipeline shape.
STAGE_DEFINITIONS: List[Dict[str, str]] = [
    {"name": "validate", "label": "Upload validation"},
    {"name": "extract", "label": "Text extraction"},
    {"name": "structure", "label": "Page and section identification"},
    {"name": "chunk", "label": "Text chunking"},
    {"name": "embed", "label": "Embedding generation"},
    {"name": "index", "label": "Vector index creation"},
    {"name": "verify", "label": "Verification and completion"},
]

MAX_FILENAME_LENGTH = 180


def stage_seed() -> List[Dict[str, object]]:
    return [
        {"name": stage["name"], "label": stage["label"], "state": "pending", "detail": "", "progress": 0.0}
        for stage in STAGE_DEFINITIONS
    ]


def compute_progress(stages: List[Dict[str, object]]) -> float:
    """Fraction of weight completed, where a running stage counts half."""
    if not stages:
        return 0.0
    total = 0.0
    for stage in stages:
        state = stage.get("state", "pending")
        if state == "completed":
            total += 1.0
        elif state == "running":
            total += 0.5
    return round(total / len(stages), 4)


# ---------------------------------------------------------------------------
# Upload validation & storage
# ---------------------------------------------------------------------------

_UNSAFE = re.compile(r"[^A-Za-z0-9 ._\-()\[\]]+")


def sanitise_filename(raw: str) -> str:
    """Reduce a client-supplied filename to something safe to display/store."""
    name = Path(raw or "document").name  # strip any directory component
    name = _UNSAFE.sub("_", name).strip(" .")
    if not name:
        name = "document"
    if len(name) > MAX_FILENAME_LENGTH:
        stem = Path(name).stem[: MAX_FILENAME_LENGTH - len(Path(name).suffix) - 1]
        name = f"{stem}{Path(name).suffix}"
    return name


def check_upload(filename: str, size_bytes: int, settings) -> str:
    """Validate an incoming upload. Returns the lower-cased extension."""
    extension = Path(filename or "").suffix.lower()
    if not extension:
        raise UnsupportedFileError(
            "The file has no extension. Supported types: " + ", ".join(settings.allowed_extensions)
        )
    if extension not in settings.allowed_extensions:
        raise UnsupportedFileError(
            f"'{extension}' files are not supported. Allowed: " + ", ".join(settings.allowed_extensions)
        )
    if size_bytes <= 0:
        raise ExtractionError("The uploaded file is empty.")
    limit = settings.max_upload_mb * 1024 * 1024
    if size_bytes > limit:
        raise FileTooLargeError(
            f"The file is {size_bytes / (1024 * 1024):.1f} MB, which exceeds the "
            f"{settings.max_upload_mb} MB upload limit."
        )
    return extension


def persist_upload(container: ServiceContainer, safe_name: str, data: bytes, extension: str) -> Dict[str, object]:
    """Write the upload into its own directory under generated, safe names."""
    document_id = f"doc_{uuid.uuid4().hex[:16]}"
    directory = container.settings.upload_dir / document_id
    directory.mkdir(parents=True, exist_ok=True)
    # The stored name is generated -- never derived from client input.
    stored_path = directory / f"source{extension}"
    stored_path.write_bytes(data)

    return {
        "id": document_id,
        "filename": safe_name,
        "stored_path": str(stored_path),
        "extension": extension,
        "size_bytes": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
        "status": "queued",
        "chunk_count": 0,
        "char_count": 0,
        "embedding_provider": container.embedder.name,
        "embedding_dim": container.embedder.dim,
        "answer_provider": container.answerer.name,
        "indexed": False,
    }


# ---------------------------------------------------------------------------
# Pipeline execution
# ---------------------------------------------------------------------------


class PipelineRunner:
    """Executes the ingestion stages for one document."""

    def __init__(self, container: ServiceContainer) -> None:
        self.container = container
        self.settings = container.settings
        self.warnings: List[str] = []

    # -- stage helpers -------------------------------------------------
    def _start(self, document_id: str, name: str, detail: str = "") -> None:
        self.container.db.set_stage(
            document_id, name, state="running", detail=detail, progress=0.0, touch_started=True
        )

    def _complete(self, document_id: str, name: str, detail: str = "") -> None:
        self.container.db.set_stage(
            document_id, name, state="completed", detail=detail, progress=1.0
        )

    def _add_warning(self, message: str) -> None:
        if message not in self.warnings:
            self.warnings.append(message)

    # -- entry point ---------------------------------------------------
    def run(self, document_id: str) -> None:
        db = self.container.db
        document = db.get_document(document_id)
        if document is None:
            logger.warning("Pipeline invoked for unknown document %s", document_id)
            return

        started = time.perf_counter()
        db.update_document(document_id, status="processing", error=None)
        db.log_event("processing_started", {"document_id": document_id})

        try:
            result = self._execute(document_id, Path(document["stored_path"]))
            db.update_document(
                document_id,
                status="ready",
                indexed=True,
                chunk_count=result["chunk_count"],
                char_count=result["char_count"],
                page_count=result["page_count"],
                error=None,
            )
            latency = (time.perf_counter() - started) * 1000
            db.log_event(
                "processing_completed",
                {"document_id": document_id, "chunks": result["chunk_count"]},
                latency_ms=latency,
            )
            logger.info(
                "Document %s indexed: %d chunks, %d chars in %.0f ms",
                document_id,
                result["chunk_count"],
                result["char_count"],
                latency,
            )
        except AppError as exc:
            self._fail(document_id, exc.message, retryable=False)
        except sqlite3.Error as exc:  # pragma: no cover - storage failures
            self._fail(document_id, f"Storage error: {exc}", retryable=True)
        except Exception as exc:  # noqa: BLE001 - never let a worker die silently
            logger.exception("Unexpected pipeline failure for %s", document_id)
            self._fail(document_id, f"Unexpected error: {exc}", retryable=True)

    def _fail(self, document_id: str, message: str, retryable: bool) -> None:
        db = self.container.db
        stages = db.get_stages(document_id)
        running = next((row["name"] for row in stages if row["state"] == "running"), None)
        if running:
            db.set_stage(document_id, running, state="failed", detail=message, progress=0.0)
        db.update_document(document_id, status="failed", error=message, indexed=False)
        db.log_event("processing_failed", {"document_id": document_id, "retryable": retryable})
        logger.warning("Document %s failed: %s (retryable=%s)", document_id, message, retryable)

    # -- the stages ----------------------------------------------------
    def _execute(self, document_id: str, stored_path: Path) -> Dict[str, object]:
        db = self.container.db
        settings = self.settings

        # 1. Validate -------------------------------------------------
        self._start(document_id, "validate", "Re-checking the stored file")
        if not stored_path.exists():
            raise ExtractionError("The stored upload could not be found on disk.")
        data = stored_path.read_bytes()
        extension = Path(stored_path).suffix.lower()
        if extension not in settings.allowed_extensions:
            raise UnsupportedFileError(
                f"'{extension}' files are not supported. Allowed: "
                + ", ".join(settings.allowed_extensions)
            )
        # Content sniffing must agree with the extension, or the upload is refused.
        fmt = sniff_format(data, extension)
        expected = settings.max_upload_mb * 1024 * 1024
        if len(data) > expected:
            raise FileTooLargeError(f"The stored file exceeds the {settings.max_upload_mb} MB limit.")
        self._complete(document_id, "validate", f"{len(data):,} bytes, format={fmt.upper()}")

        # 2. Extract --------------------------------------------------
        self._start(document_id, "extract", "Extracting text")
        extraction = extract(
            stored_path,
            max_pages=settings.max_pages,
            max_chars=settings.max_extracted_chars,
            add_warning=self._add_warning,
        )
        extract_detail = (
            f"{extraction.char_count:,} characters from "
            f"{extraction.page_count if extraction.page_count else '1'} unit(s)"
        )
        # Non-fatal extraction notes (skipped pages, truncated page counts) are
        # surfaced in the stage detail rather than swallowed.
        if extraction.warnings:
            extract_detail += "; " + " | ".join(extraction.warnings)
        self._complete(document_id, "extract", extract_detail)

        # 3. Structure ------------------------------------------------
        self._start(document_id, "structure", "Identifying pages and sections")
        non_empty = [section for section in extraction.sections if section.text.strip()]
        pages = [section.page for section in non_empty if section.page is not None]
        keywords = extract_keywords(extraction.text, limit=8)
        self._complete(
            document_id,
            "structure",
            (
                f"{len(non_empty)} section(s); pages {min(pages)}-{max(pages)}"
                if pages
                else f"{len(non_empty)} section(s); no pagination available"
            )
            + (f"; key terms: {', '.join(keywords[:5])}" if keywords else ""),
        )

        # 4. Chunk ----------------------------------------------------
        self._start(document_id, "chunk", "Splitting into overlapping chunks")
        chunks = chunk_sections(
            sections=non_empty,
            document_id=document_id,
            chunk_size=settings.chunk_size,
            chunk_overlap=settings.chunk_overlap,
            max_chunks=settings.max_chunks_per_document,
        )
        if not chunks:
            raise ExtractionError("No readable text remained after chunking.")
        if len(chunks) >= settings.max_chunks_per_document:
            self._add_warning(
                f"Chunk count hit the configured limit of {settings.max_chunks_per_document}; "
                "later parts of the document were not indexed."
            )
        self._complete(
            document_id,
            "chunk",
            f"{len(chunks)} chunks (~{settings.chunk_size} chars, {settings.chunk_overlap} overlap)",
        )

        # 5. Embed ----------------------------------------------------
        self._start(document_id, "embed", f"Embedding with {self.container.embedder.name}")
        vectors = self.container.embed_chunks(chunks)
        self._complete(
            document_id,
            "embed",
            f"{len(chunks)} x {self.container.embedder.dim}d vectors ({self.container.embedder.name})",
        )

        # 6. Index ----------------------------------------------------
        self._start(document_id, "index", "Persisting vectors and metadata")
        self.container.store_chunks(chunks, vectors)
        self._complete(
            document_id,
            "index",
            f"index now holds {self.container.vector_index.size} vectors on disk",
        )

        # 7. Verify ---------------------------------------------------
        self._start(document_id, "verify", "Verifying the index")
        missing = [chunk.id for chunk in chunks if not self.container.vector_index.has(chunk.id)]
        if missing:
            raise ExtractionError(
                f"Verification failed: {len(missing)} chunk(s) are missing from the vector index."
            )
        stored = len(db.get_chunks(document_id))
        if stored != len(chunks):
            raise ExtractionError(
                f"Verification failed: {stored} chunk rows stored but {len(chunks)} were created."
            )
        self._complete(
            document_id,
            "verify",
            f"{stored} chunks retrievable"
            + (f"; warnings: {' | '.join(self.warnings)}" if self.warnings else ""),
        )

        return {
            "chunk_count": len(chunks),
            "char_count": extraction.char_count,
            "page_count": extraction.page_count,
        }


def process_document(document_id: str, container: ServiceContainer) -> None:
    """Thread entry point.

    Deliberately runs against the *same* container the API serves from: SQLite
    connections are thread-local and index mutation is lock-protected, and
    sharing means retrieval sees a freshly indexed document immediately instead
    of waiting for a process restart.
    """
    try:
        PipelineRunner(container).run(document_id)
    except Exception as exc:  # noqa: BLE001 - a dead worker must not hang the UI
        logger.exception("Worker crashed for document %s", document_id)
        try:
            container.db.update_document(
                document_id,
                status="failed",
                error="The processing worker crashed unexpectedly.",
                indexed=False,
            )
            container.db.log_event("pipeline_crash", {"document_id": document_id, "error": str(exc)})
        except Exception:  # noqa: BLE001 - last resort
            pass
