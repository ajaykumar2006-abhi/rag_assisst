"""Persistent vector index.

A single flat, L2-normalised matrix of chunk embeddings kept in memory and
mirrored to disk (``.npy`` + a small JSON manifest). Flat cosine search is
exact and, at the scale of a personal document collection (thousands of
chunks), comfortably faster than any approximate structure while being far
simpler to reason about.

The index is decoupled from the embedder: it only ever sees float32 vectors and
their chunk ids, so the embedding implementation can be swapped freely. The
manifest records which provider produced the vectors so a mismatch after a
restart triggers a rebuild rather than silently returning garbage scores.
"""

from __future__ import annotations

import json
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple

import numpy as np


@dataclass
class SearchHit:
    chunk_id: str
    score: float


class VectorIndex:
    """Flat cosine index over chunk embeddings."""

    def __init__(self, directory: Path, dim: int, provider: str) -> None:
        self.directory = Path(directory)
        self.dim = int(dim)
        self.provider = provider
        self._lock = threading.RLock()
        self._ids: List[str] = []
        self._pos: Dict[str, int] = {}
        self._matrix: np.ndarray = np.zeros((0, self.dim), dtype=np.float32)
        self.dirty = True

    # -- paths ---------------------------------------------------------
    @property
    def vectors_path(self) -> Path:
        return self.directory / "vectors.npy"

    @property
    def manifest_path(self) -> Path:
        return self.directory / "manifest.json"

    # -- lifecycle -----------------------------------------------------
    def load(self) -> bool:
        """Load vectors from disk. Returns False when a rebuild is required."""
        with self._lock:
            if not self.vectors_path.exists() or not self.manifest_path.exists():
                return False
            try:
                manifest = json.loads(self.manifest_path.read_text(encoding="utf-8"))
                matrix = np.load(self.vectors_path)
            except (OSError, ValueError, json.JSONDecodeError):
                return False

            if manifest.get("provider") != self.provider or int(manifest.get("dim", -1)) != self.dim:
                # Embedding space changed -- existing vectors are meaningless.
                return False
            if matrix.ndim != 2 or (matrix.size and matrix.shape[1] != self.dim):
                return False
            if len(manifest.get("ids", [])) != matrix.shape[0]:
                return False

            self._ids = list(manifest["ids"])
            self._pos = {chunk_id: i for i, chunk_id in enumerate(self._ids)}
            self._matrix = matrix.astype(np.float32, copy=False)
            self.dirty = False
            return True

    def save(self) -> None:
        with self._lock:
            self.directory.mkdir(parents=True, exist_ok=True)
            vectors_tmp = self.vectors_path.with_suffix(".npy.tmp")
            manifest_tmp = self.manifest_path.with_suffix(".json.tmp")
            # ``np.save`` appends .npy; write via an open handle to keep the name exact.
            with open(vectors_tmp, "wb") as handle:
                np.save(handle, self._matrix)
            manifest_tmp.write_text(
                json.dumps(
                    {"provider": self.provider, "dim": self.dim, "count": len(self._ids), "ids": self._ids}
                ),
                encoding="utf-8",
            )
            vectors_tmp.replace(self.vectors_path)
            manifest_tmp.replace(self.manifest_path)
            self.dirty = False

    def reset(self) -> None:
        """Drop every vector (used when rebuilding from scratch)."""
        with self._lock:
            self._ids = []
            self._pos = {}
            self._matrix = np.zeros((0, self.dim), dtype=np.float32)
            self.dirty = True

    # -- introspection -------------------------------------------------
    @property
    def size(self) -> int:
        with self._lock:
            return len(self._ids)

    def ids(self) -> List[str]:
        with self._lock:
            return list(self._ids)

    def has(self, chunk_id: str) -> bool:
        with self._lock:
            return chunk_id in self._pos

    # -- mutation ------------------------------------------------------
    @staticmethod
    def _normalise(vectors: np.ndarray) -> np.ndarray:
        vectors = np.asarray(vectors, dtype=np.float32)
        if vectors.ndim == 1:
            vectors = vectors.reshape(1, -1)
        norms = np.linalg.norm(vectors, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        return vectors / norms

    def add(self, chunk_ids: Sequence[str], vectors: np.ndarray) -> None:
        """Add or replace vectors for the given chunk ids."""
        if not chunk_ids:
            return
        vectors = self._normalise(vectors)
        if vectors.shape[1] != self.dim:
            raise ValueError(f"Expected {self.dim}-dimensional vectors, got {vectors.shape[1]}")
        with self._lock:
            keep = [i for i, chunk_id in enumerate(self._ids) if chunk_id not in set(chunk_ids)]
            kept_matrix = self._matrix[keep] if keep else np.zeros((0, self.dim), dtype=np.float32)
            kept_ids = [self._ids[i] for i in keep]
            # If the index was previously empty with a stale manifest, extend the width safely.
            self._matrix = np.vstack([kept_matrix, vectors]) if len(kept_matrix) else vectors
            self._ids = kept_ids + list(chunk_ids)
            self._pos = {chunk_id: i for i, chunk_id in enumerate(self._ids)}
            self.dirty = True

    def remove(self, chunk_ids: Iterable[str]) -> int:
        targets: Set[str] = set(chunk_ids)
        if not targets:
            return 0
        with self._lock:
            keep = [i for i, chunk_id in enumerate(self._ids) if chunk_id not in targets]
            removed = len(self._ids) - len(keep)
            if not removed:
                return 0
            self._matrix = self._matrix[keep] if keep else np.zeros((0, self.dim), dtype=np.float32)
            self._ids = [self._ids[i] for i in keep]
            self._pos = {chunk_id: i for i, chunk_id in enumerate(self._ids)}
            self.dirty = True
            return removed

    def remove_document(self, document_prefix: str) -> int:
        """Remove every vector whose chunk id belongs to ``document_prefix``.

        Chunk ids are ``<document_id>::<ordinal>`` so the prefix is unambiguous.
        """
        return self.remove([chunk_id for chunk_id in self.ids() if chunk_id.startswith(document_prefix)])

    # -- search --------------------------------------------------------
    def search(
        self,
        query_vector: np.ndarray,
        top_k: int = 10,
        allowed_chunk_ids: Optional[Set[str]] = None,
    ) -> List[SearchHit]:
        """Exact cosine search returning the best ``top_k`` hits."""
        with self._lock:
            if not self._ids or self._matrix.shape[0] == 0:
                return []
            query = self._normalise(np.asarray(query_vector, dtype=np.float32).reshape(-1))
            if query.shape[1] != self._matrix.shape[1]:
                raise ValueError("Query vector dimension does not match the index")

            scores = (self._matrix @ query.T).reshape(-1)  # cosine, vectors already unit norm

            if allowed_chunk_ids is not None:
                if not allowed_chunk_ids:
                    return []
                mask = np.fromiter(
                    (chunk_id in allowed_chunk_ids for chunk_id in self._ids),
                    dtype=bool,
                    count=len(self._ids),
                )
                if not mask.any():
                    return []
                candidate_scores = np.where(mask, scores, -np.inf)
            else:
                candidate_scores = scores

            k = min(top_k, int(candidate_scores.shape[0]))
            top_idx = np.argpartition(-candidate_scores, k - 1)[:k]
            top_idx = top_idx[np.argsort(-candidate_scores[top_idx])]
            return [
                SearchHit(chunk_id=self._ids[int(i)], score=float(candidate_scores[int(i)]))
                for i in top_idx
                if np.isfinite(candidate_scores[int(i)])
            ]

    def matrix_snapshot(self) -> Tuple[List[str], np.ndarray]:
        """Return a copy of (ids, matrix) -- used by tests and evaluation."""
        with self._lock:
            return list(self._ids), self._matrix.copy()
