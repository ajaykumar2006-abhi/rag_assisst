"""Embedding providers.

Two implementations sit behind one interface so the rest of the pipeline never
cares which is active:

``hashing`` (default)
    A deterministic, dependency-free **subword hashing** embedder: word
    unigrams, word bigrams and character 3-5 grams are hashed into a fixed
    dense vector with sublinear term weighting and a signed hash trick.
    It needs no download, is stable across processes and runs in milliseconds
    on a CPU-only laptop. It is a *lexical* embedding -- it captures surface
    form and morphology, not deep semantics. Callers must label it as such.

``sentence``
    Optional neural embeddings via ``sentence-transformers``. This is real
    semantic vector retrieval, but it requires an extra install and a one-time
    model download, so it is opt-in.

The active provider name is stored in the vector index manifest; switching
providers invalidates the index and triggers a rebuild rather than mixing
incompatible vector spaces.
"""

from __future__ import annotations

import hashlib
import logging
import math
import threading
from abc import ABC, abstractmethod
from typing import Dict, List, Sequence

import numpy as np

from .text_utils import tokenize

logger = logging.getLogger(__name__)

# Guard against pathological inputs when generating character n-grams.
_MAX_CHARS_FOR_NGRAMS = 200_000
_CHAR_NGRAMS = (3, 4, 5)

HASHING_PROVIDER_NAME = "hashing-subword-v1"


class Embedder(ABC):
    """Interface every embedding backend implements."""

    name: str
    dim: int
    #: Human-readable statement about what this embedder actually does.
    description: str
    #: True when the vectors encode learned semantics rather than surface form.
    semantic: bool

    @abstractmethod
    def embed_documents(self, texts: Sequence[str]) -> np.ndarray:
        """Embed a batch of documents -> (n, dim) float32 matrix."""

    def embed_query(self, text: str) -> np.ndarray:
        """Embed a single query -> (dim,) float32 vector."""
        return self.embed_documents([text])[0]

    @property
    def label(self) -> str:
        kind = "semantic" if self.semantic else "lexical"
        return f"{self.name} ({kind}, {self.dim}d)"


class HashingEmbedder(Embedder):
    """Deterministic subword hashing embedder (no downloads, pure numpy)."""

    semantic = False
    name = HASHING_PROVIDER_NAME

    def __init__(self, dim: int = 512) -> None:
        if dim < 32:
            raise ValueError("embedding_dim must be at least 32")
        self.dim = int(dim)
        self.description = (
            "Deterministic subword hashing embeddings (word unigrams/bigrams and "
            "character 3-5 grams, sublinear weighting, signed hash trick). "
            "Lexical, not neural: it matches surface form and morphology."
        )

    # -- feature extraction -------------------------------------------
    @staticmethod
    def _features(text: str) -> List[str]:
        lowered = (text or "").lower()
        tokens = tokenize(lowered)
        features: List[str] = [f"w:{token}" for token in tokens]
        features.extend(f"b:{tokens[i]}_{tokens[i + 1]}" for i in range(len(tokens) - 1))

        padded = f" {' '.join(tokens)} "
        padded = padded[:_MAX_CHARS_FOR_NGRAMS]
        for n in _CHAR_NGRAMS:
            if len(padded) <= n:
                continue
            features.extend(f"c{n}:{padded[i:i + n]}" for i in range(len(padded) - n + 1))
        return features

    def _bucket(self, feature: str) -> tuple[int, float]:
        digest = hashlib.blake2b(feature.encode("utf-8"), digest_size=8).digest()
        value = int.from_bytes(digest, "big")
        index = value % self.dim
        # Signed hashing keeps collisions from systematically inflating similarity.
        sign = 1.0 if (value >> 63) & 1 else -1.0
        return index, sign

    def _vector(self, text: str) -> np.ndarray:
        vector = np.zeros(self.dim, dtype=np.float32)
        counts: Dict[str, int] = {}
        for feature in self._features(text):
            counts[feature] = counts.get(feature, 0) + 1
        if not counts:
            return vector
        for feature, count in counts.items():
            index, sign = self._bucket(feature)
            # Sublinear term frequency: the 20th repeat matters far less than the 1st.
            vector[index] += sign * (1.0 + math.log(count))
        return vector

    def embed_documents(self, texts: Sequence[str]) -> np.ndarray:
        if not texts:
            return np.zeros((0, self.dim), dtype=np.float32)
        matrix = np.vstack([self._vector(text) for text in texts]).astype(np.float32)
        norms = np.linalg.norm(matrix, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        return (matrix / norms).astype(np.float32)


class SentenceTransformerEmbedder(Embedder):
    """Optional neural embedder backed by ``sentence-transformers``."""

    semantic = True
    name = "sentence-transformers"

    def __init__(self, model_name: str) -> None:
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:  # pragma: no cover - optional dependency
            raise ImportError(
                "sentence-transformers is not installed. Install it with "
                "'pip install sentence-transformers' (it downloads a model on first use), "
                "or keep EMBEDDING_PROVIDER=hashing."
            ) from exc

        self.model_name = model_name
        self._model = SentenceTransformer(model_name)
        self.dim = int(self._model.get_sentence_embedding_dimension())
        self.name = f"sentence-transformers:{model_name.split('/')[-1]}"
        self.description = (
            f"Neural sentence embeddings from '{model_name}'. Encodes meaning, so it "
            "retrieves paraphrases that lexical matching misses."
        )

    def embed_documents(self, texts: Sequence[str]) -> np.ndarray:
        if not texts:
            return np.zeros((0, self.dim), dtype=np.float32)
        vectors = self._model.encode(
            list(texts), batch_size=32, convert_to_numpy=True, normalize_embeddings=True
        )
        return np.asarray(vectors, dtype=np.float32)


# ---------------------------------------------------------------------------
# Factory with caching
# ---------------------------------------------------------------------------

_embedder_lock = threading.Lock()
_embedders: Dict[tuple[str, int, str], Embedder] = {}


def build_embedder(provider: str, dim: int, model_name: str) -> Embedder:
    """Construct (or fetch a cached) embedder for the given configuration."""
    key = (provider, dim, model_name)
    with _embedder_lock:
        cached = _embedders.get(key)
        if cached is not None:
            return cached
        if provider == "hashing":
            embedder: Embedder = HashingEmbedder(dim=dim)
        elif provider == "sentence":
            embedder = SentenceTransformerEmbedder(model_name)
        else:
            raise ValueError(f"Unknown embedding provider: {provider!r}")
        _embedders[key] = embedder
        return embedder


def get_embedder(settings) -> Embedder:
    """Return the configured embedder, falling back safely with a warning."""
    try:
        return build_embedder(
            settings.embedding_provider, settings.embedding_dim, settings.embedding_model
        )
    except (ImportError, OSError, ValueError) as exc:
        if settings.embedding_provider == "hashing":
            raise
        logger.warning(
            "Embedding provider '%s' unavailable (%s); falling back to the local hashing "
            "embedder. Retrieval will be lexical, not semantic.",
            settings.embedding_provider,
            exc,
        )
        return build_embedder("hashing", settings.embedding_dim, settings.embedding_model)


def reset_embedder_cache() -> None:
    """Drop cached models (tests / settings changes)."""
    with _embedder_lock:
        _embedders.clear()
