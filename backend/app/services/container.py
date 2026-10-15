"""Service container.

Owns the long-lived objects (database, embedder, vector index, lexical index,
retriever, answerer) so that models are initialised once per process instead of
per request, and keeps the in-memory indexes consistent with what is on disk.

Startup sequence:

1. Load the vector index from disk if its manifest matches the configured
   embedder.
2. Otherwise rebuild from the chunks stored in SQLite. This is what makes a
   restart safe: if the index files are missing or were produced by a different
   embedding space, the chunks are re-embedded rather than served as garbage.
3. Rebuild the BM25 statistics from the same chunk rows.
"""

from __future__ import annotations

import logging
import threading
import time
from pathlib import Path
from typing import Dict, List, Optional, Sequence

import numpy as np

from ..core.config import Settings, get_settings
from ..storage.db import Database
from ..storage.vector_store import VectorIndex
from .answering import Answerer, build_answerer
from .chunking import Chunk
from .embeddings import Embedder, get_embedder
from .retrieval import LexicalIndex, Retriever
from .text_utils import truncate

logger = logging.getLogger(__name__)

START_TIME = time.time()


class ServiceContainer:
    """Holds and synchronises every stateful service."""

    def __init__(self, settings: Optional[Settings] = None) -> None:
        self.settings = settings or get_settings()
        self.settings.ensure_dirs()

        self.db = Database(self.settings.db_path)
        self.embedder: Embedder = get_embedder(self.settings)
        self.vector_index = VectorIndex(
            directory=self.settings.index_dir / "collection",
            dim=self.embedder.dim,
            provider=self.embedder.name,
        )
        self.lexical = LexicalIndex()
        self.retriever = Retriever(self.embedder, self.vector_index, self.lexical)
        self.answerer: Answerer = build_answerer(self.settings)

        self._lock = threading.RLock()
        self._revision = 0
        self._metadata: Dict[str, Dict] = {}
        self.rebuild_reason: str = "cold start"

        self.initialise()

    # -- lifecycle -----------------------------------------------------
    def initialise(self) -> None:
        """Load or rebuild indexes so the process is ready to serve."""
        loaded = self.vector_index.load()
        self._reload_lexical_index()

        expected = self.db.chunk_count()
        if loaded and self.vector_index.size == expected:
            self.rebuild_reason = "loaded from disk"
        elif expected == 0:
            self.vector_index.reset()
            self.rebuild_reason = "empty collection"
        else:
            reason = (
                "embedding configuration changed"
                if loaded is False and self.vector_index.size == 0
                else "index out of sync with stored chunks"
            )
            logger.info("Rebuilding vector index (%s, %d chunks).", reason, expected)
            self.rebuild_index()
            self.rebuild_reason = reason

        logger.info(
            "Ready: embedder=%s dim=%d chunks=%d index=%d",
            self.embedder.name,
            self.embedder.dim,
            expected,
            self.vector_index.size,
        )

    def rebuild_index(self) -> int:
        """Re-embed every stored chunk. Returns the number of vectors written."""
        rows = [dict(row) for row in self._all_chunk_rows()]
        self.vector_index.reset()
        if not rows:
            self._revision += 1
            self._reload_lexical_index()
            self._persist_index()
            return 0

        texts = [row["text"] for row in rows]
        # Embed in batches so a large collection does not spike memory.
        vectors: List[np.ndarray] = []
        batch_size = 64
        for start in range(0, len(texts), batch_size):
            vectors.append(self.embedder.embed_documents(texts[start : start + batch_size]))
        matrix = np.vstack(vectors) if vectors else np.zeros((0, self.embedder.dim), dtype=np.float32)
        self.vector_index.add([row["chunk_id"] for row in rows], matrix)
        self._persist_index()
        self._revision += 1
        self._reload_lexical_index()
        return len(rows)

    def shutdown(self) -> None:
        try:
            self._persist_index()
        finally:
            self.db.close()

    # -- index maintenance --------------------------------------------
    def _persist_index(self) -> None:
        try:
            self.vector_index.save()
        except OSError as exc:  # pragma: no cover - disk issues
            logger.error("Could not persist the vector index: %s", exc)

    def _all_chunk_rows(self) -> Sequence:
        return list(
            self.db.conn.execute(
                """
                SELECT c.id AS chunk_id, c.document_id, c.ordinal, c.page, c.text,
                       c.char_start, c.char_end, d.filename
                  FROM chunks c JOIN documents d ON d.id = c.document_id
              ORDER BY c.document_id, c.ordinal
                """
            )
        )

    def _reload_lexical_index(self) -> None:
        rows = [dict(row) for row in self._all_chunk_rows()]
        self._metadata = {row["chunk_id"]: row for row in rows}
        self.lexical.rebuild(rows, revision=self._revision)
        self._revision += 1

    def refresh(self) -> None:
        """Re-sync the in-memory indexes with the database and persist them."""
        with self._lock:
            self._persist_index()
            self._reload_lexical_index()

    # -- chunk writes --------------------------------------------------
    def embed_chunks(self, chunks: Sequence[Chunk]) -> np.ndarray:
        """Embed chunk texts. Kept separate so the pipeline can report the
        embedding stage honestly before anything is persisted."""
        if not chunks:
            return np.zeros((0, self.embedder.dim), dtype=np.float32)
        # Batched so a large document does not spike memory on a modest laptop.
        vectors: List[np.ndarray] = []
        batch_size = 64
        for start in range(0, len(chunks), batch_size):
            batch = [chunk.text for chunk in chunks[start : start + batch_size]]
            vectors.append(self.embedder.embed_documents(batch))
        return np.vstack(vectors).astype(np.float32)

    def store_chunks(self, chunks: Sequence[Chunk], vectors: Optional[np.ndarray] = None) -> None:
        """Persist chunks to SQLite and add their vectors to the in-memory index."""
        if not chunks:
            return
        if vectors is None:
            vectors = self.embed_chunks(chunks)
        self.db.insert_chunks([chunk.to_record() for chunk in chunks])
        self.vector_index.add([chunk.id for chunk in chunks], vectors)
        self._persist_index()
        self._reload_lexical_index()

    # -- document removal ----------------------------------------------
    def remove_document(self, document_id: str, stored_path: Optional[Path]) -> Dict[str, int]:
        """Delete a document, its chunks, its vectors and its stored file."""
        removed_vectors = self.vector_index.remove_document(f"{document_id}::")
        self.db.delete_document(document_id)
        self._persist_index()
        self._reload_lexical_index()

        file_removed = 0
        if stored_path is not None:
            try:
                if stored_path.exists():
                    stored_path.unlink()
                    file_removed = 1
            except OSError as exc:
                logger.warning("Could not remove uploaded file %s: %s", stored_path, exc)

        # Clean up the isolated upload directory if we own it.
        if stored_path is not None:
            parent = stored_path.parent
            if parent.name == document_id and parent.exists():
                try:
                    for leftover in parent.iterdir():
                        leftover.unlink()
                    parent.rmdir()
                except OSError:
                    pass

        return {"vectors_removed": removed_vectors, "files_removed": file_removed}

    # -- retrieval helper ----------------------------------------------
    def search(
        self,
        query: str,
        top_k: Optional[int] = None,
        document_ids: Optional[Sequence[str]] = None,
    ):
        with self._lock:
            if not self.lexical.ready:
                self._reload_lexical_index()
        allowed = set(document_ids) if document_ids else None
        return self.retriever.search(
            query=query,
            top_k=top_k or self.settings.top_k,
            dense_weight=self.settings.dense_weight,
            lexical_weight=self.settings.lexical_weight,
            allowed_document_ids=allowed,
            metadata=self._metadata,
        )

    # -- status helpers ------------------------------------------------
    def health(self) -> Dict[str, object]:
        available, reason = self.answerer.availability()
        counts = self.db.count_by_status()
        # "Generative" only when an external provider is actually selected *and*
        # configured; the default extractive path must never be reported as such.
        is_generative = self.answerer.name != "extractive"
        return {
            "documents_indexed": counts.get("ready", 0),
            "chunks_indexed": self.db.chunk_count(),
            "vector_count": self.vector_index.size,
            "generative_available": bool(is_generative and available),
            "generative_reason": reason,
            "answer_provider": self.answerer.name,
            "rebuild_reason": self.rebuild_reason,
        }

    def document_metadata(self, document_id: str) -> Optional[Dict]:
        row = self.db.get_document(document_id)
        return dict(row) if row else None

    def source_excerpt(self, text: str, limit: int = 320) -> str:
        return truncate(text, limit)

    def uptime_seconds(self) -> float:
        return time.time() - START_TIME
