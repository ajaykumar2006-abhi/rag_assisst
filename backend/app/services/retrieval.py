"""Hybrid retrieval.

Two complementary scorers run over the same candidate chunks and are fused:

* **Dense** -- cosine similarity between the embedded query and embedded chunks
  (exact search in :class:`~app.storage.vector_store.VectorIndex`).
* **Lexical** -- Okapi BM25 over the chunk tokens. BM25 is robust when a
  question shares rare terms with a passage (names, numbers, codes) that a
  low-dimensional embedding can smear away.

Fusion is a configurable weighted sum. Each score is mapped into a comparable
0..1 range first -- BM25 through a saturating curve so that "sort of matches"
cannot masquerade as "strongly matches", which keeps the
``min_relevance`` gate meaningful for the insufficient-evidence behaviour.

Retrieval reports both component scores alongside the fused score so the
Evaluation Studio can show *why* a chunk was chosen.
"""

from __future__ import annotations

import math
import threading
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Sequence, Set

import numpy as np

from ..storage.vector_store import VectorIndex
from .embeddings import Embedder
from .text_utils import content_tokens, tokenize

BM25_K1 = 1.5
BM25_B = 0.75
# Saturating constant for turning BM25 into 0..1. Higher = slower saturation.
BM25_SATURATION = 6.0


@dataclass
class RetrievedChunk:
    chunk_id: str
    document_id: str
    document_filename: str
    page: Optional[int]
    text: str
    dense_score: float
    lexical_score: float
    fused_score: float
    char_start: int = 0
    char_end: int = 0


class LexicalIndex:
    """In-memory BM25 statistics over chunks, rebuilt when content changes."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self.revision = -1
        self._rows: List[Dict] = []
        self._df: Dict[str, int] = {}
        self._avgdl: float = 1.0
        self._doc_tokens: Dict[str, List[str]] = {}

    def rebuild(self, rows: Sequence[Dict], revision: int) -> None:
        """Recompute document frequencies from chunk rows."""
        with self._lock:
            self._rows = [dict(row) for row in rows]
            self._doc_tokens = {}
            df: Dict[str, int] = {}
            total = 0
            for row in self._rows:
                tokens = tokenize(row.get("text", ""))
                self._doc_tokens[row["chunk_id"]] = tokens
                total += len(tokens)
                for token in set(tokens):
                    df[token] = df.get(token, 0) + 1
            self._df = df
            self._avgdl = (total / len(self._rows)) if self._rows else 1.0
            self.revision = revision

    @property
    def ready(self) -> bool:
        return self.revision >= 0

    def score(
        self,
        query_tokens: Sequence[str],
        allowed_document_ids: Optional[Set[str]] = None,
    ) -> Dict[str, float]:
        """Return BM25 scores for chunks matching the document filter."""
        with self._lock:
            if not self._rows:
                return {}
            total_docs = len(self._rows)
            scores: Dict[str, float] = {}
            for row in self._rows:
                if allowed_document_ids is not None and row["document_id"] not in allowed_document_ids:
                    continue
                tokens = self._doc_tokens.get(row["chunk_id"], [])
                if not tokens:
                    continue
                length = len(tokens)
                counts: Dict[str, int] = {}
                for token in tokens:
                    counts[token] = counts.get(token, 0) + 1

                score = 0.0
                for token in query_tokens:
                    frequency = counts.get(token, 0)
                    if not frequency:
                        continue
                    df = self._df.get(token, 0)
                    if df == 0:
                        continue
                    idf = math.log(1.0 + (total_docs - df + 0.5) / (df + 0.5))
                    denominator = frequency + BM25_K1 * (
                        1 - BM25_B + BM25_B * (length / (self._avgdl or 1.0))
                    )
                    score += idf * (frequency * (BM25_K1 + 1)) / denominator
                if score > 0:
                    scores[row["chunk_id"]] = score
            return scores

    def row(self, chunk_id: str) -> Optional[Dict]:
        with self._lock:
            for row in self._rows:
                if row["chunk_id"] == chunk_id:
                    return row
        return None


class Retriever:
    """Combines the vector index and the BM25 index into one ranked list."""

    def __init__(self, embedder: Embedder, vector_index: VectorIndex, lexical: LexicalIndex) -> None:
        self.embedder = embedder
        self.vector_index = vector_index
        self.lexical = lexical

    @staticmethod
    def _normalise_lexical(score: float) -> float:
        if score <= 0:
            return 0.0
        return score / (score + BM25_SATURATION)

    def search(
        self,
        query: str,
        top_k: int,
        dense_weight: float,
        lexical_weight: float,
        allowed_document_ids: Optional[Set[str]] = None,
        metadata: Optional[Dict[str, Dict]] = None,
    ) -> List[RetrievedChunk]:
        """Retrieve the best chunks for ``query``.

        ``metadata`` maps chunk_id -> {document_id, filename, page, text,
        char_start, char_end}. When omitted the lexical index rows are used.
        """
        query = (query or "").strip()
        if not query or top_k <= 0:
            return []

        meta = metadata if metadata is not None else {
            row["chunk_id"]: row for row in self.lexical._rows  # noqa: SLF001 - internal cache reuse
        }

        # ---- dense ----------------------------------------------------
        allowed_chunk_ids = None
        if allowed_document_ids is not None:
            allowed_chunk_ids = {
                chunk_id
                for chunk_id, row in meta.items()
                if row.get("document_id") in allowed_document_ids
            }
            if not allowed_chunk_ids:
                return []

        dense_scores: Dict[str, float] = {}
        if self.vector_index.size:
            query_vector = self.embedder.embed_query(query)
            # Pull a generous candidate pool; fusion re-ranks it anyway.
            pool = max(top_k * 8, 40)
            for hit in self.vector_index.search(query_vector, top_k=pool, allowed_chunk_ids=allowed_chunk_ids):
                dense_scores[hit.chunk_id] = max(0.0, float(hit.score))

        # ---- lexical --------------------------------------------------
        lexical_raw = self.lexical.score(content_tokens(query), allowed_document_ids)

        # ---- fuse -----------------------------------------------------
        weight_total = dense_weight + lexical_weight
        if weight_total <= 0:
            dense_weight, lexical_weight, weight_total = 1.0, 0.0, 1.0

        candidates = set(dense_scores) | set(lexical_raw)
        results: List[RetrievedChunk] = []
        for chunk_id in candidates:
            row = meta.get(chunk_id)
            if row is None:
                continue
            dense = dense_scores.get(chunk_id, 0.0)
            lexical = self._normalise_lexical(lexical_raw.get(chunk_id, 0.0))
            fused = (dense * dense_weight + lexical * lexical_weight) / weight_total
            results.append(
                RetrievedChunk(
                    chunk_id=chunk_id,
                    document_id=row.get("document_id", ""),
                    document_filename=row.get("filename", ""),
                    page=row.get("page"),
                    text=row.get("text", ""),
                    dense_score=dense,
                    lexical_score=lexical,
                    fused_score=fused,
                    char_start=int(row.get("char_start", 0) or 0),
                    char_end=int(row.get("char_end", 0) or 0),
                )
            )

        results.sort(key=lambda item: (-item.fused_score, item.chunk_id))
        return results[:top_k]
